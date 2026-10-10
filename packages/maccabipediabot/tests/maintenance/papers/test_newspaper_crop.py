from PIL import Image, ImageDraw

import pytest

from maccabipediabot.maintenance.papers.newspaper_crop import CropSpecError, check_edges, compose

# A synthetic page: two text blocks of 6 px "letters" separated by a 2 px rule at y=200.
W, H = 600, 400


def page() -> Image.Image:
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    for top in (40, 240):
        for row in range(5):
            y = top + row * 24
            for x in range(40, 560, 14):
                d.rectangle([x, y, x + 8, y + 14], fill=0)  # a "letter"
    d.rectangle([20, 199, 580, 200], fill=0)               # the rule between the stories
    return img


def verdicts(spec):
    return {e.label: e.verdict for e in check_edges(page(), spec)}


def test_edge_on_the_rule_is_clean():
    spec = {"width": 600, "height": 200, "pieces": [{"box": [0, 0, 600, 200], "at": [0, 0]}]}
    assert verdicts(spec)["P0 bottom"] == "on_rule"


def test_edge_through_a_text_line_cuts_ink():
    spec = {"width": 600, "height": 147, "pieces": [{"box": [0, 0, 600, 147], "at": [0, 0]}]}
    assert verdicts(spec)["P0 bottom"] == "cuts_ink"


def test_cut_just_above_a_rule_still_cuts_ink():
    """The 16b case: an edge within snapping distance of a rule that slices the last line."""
    spec = {"width": 600, "height": 190, "pieces": [{"box": [0, 0, 600, 190], "at": [0, 0]}]}
    page_img = page()
    ImageDraw.Draw(page_img).rectangle([40, 184, 560, 196], fill=0)  # a last line right above the rule
    edges = {e.label: e.verdict for e in check_edges(page_img, spec)}
    assert edges["P0 bottom"] == "cuts_ink"


def test_blank_edge_in_plain_gutter_must_be_read():
    spec = {"width": 600, "height": 400,
            "pieces": [{"box": [0, 0, 600, 400], "at": [0, 0], "blank": [[0, 110, 600, 400]]}]}
    assert verdicts(spec)["P0 blank0 top"] == "off_rule"


def test_one_cut_letter_on_a_long_edge_is_still_a_cut():
    img = Image.new("L", (1400, 400), 255)
    ImageDraw.Draw(img).rectangle([700, 90, 708, 110], fill=0)  # one letter, crossed by y=100
    spec = {"width": 1400, "height": 100, "pieces": [{"box": [0, 0, 1400, 100], "at": [0, 0]}]}
    assert {e.label: e.verdict for e in check_edges(img, spec)}["P0 bottom"] == "cuts_ink"


@pytest.mark.parametrize("spec", [
    {"width": 600, "height": 150, "pieces": [{"box": [0, 0, 600, 200], "at": [0, 0]}]},        # off canvas
    {"width": 600, "height": 400, "pieces": [{"box": [0, 0, 600, 200], "at": [0, 0]},
                                              {"box": [0, 200, 600, 400], "at": [0, 100]}]},  # overlap
    {"width": 600, "height": 500, "pieces": [{"box": [0, 0, 600, 500], "at": [0, 0]}]},        # outside scan
])
def test_spec_that_would_lose_text_is_refused(spec):
    with pytest.raises(CropSpecError):
        compose(page(), spec)


def test_compose_stacks_pieces_and_blanks():
    spec = {"width": 300, "height": 200,
            "pieces": [{"box": [0, 0, 300, 100], "at": [0, 0]},
                       {"box": [300, 0, 600, 100], "at": [0, 100], "blank": [[0, 0, 300, 100]]}]}
    out = compose(page(), spec)
    assert out.size == (300, 200)
    assert out.convert("L").crop((0, 100, 300, 200)).getextrema() == (255, 255)
