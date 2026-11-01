"""The before/after comparison and the PR-description page block.

Shots are tiny synthetic PNGs: what is under test is the verdict (same,
changed, unstable), not the browser.
"""
import json

import pytest
from PIL import Image

import compare
import run

TITLE = 'משחק:04-04-2023 מכבי תל אביב נגד מכבי חיפה - ליגת העל'


def write_shot(directory, image):
    directory.mkdir(exist_ok=True)
    image.save(directory / 'game-desktop.png')
    shots = [{'file': 'game-desktop.png', 'title': TITLE, 'viewport': 'desktop',
              'status': 200, 'height': image.height}]
    (directory / 'shots.json').write_text(json.dumps(shots), encoding='utf-8')


def page(height=200, box=None, colour=(0, 80, 160)):
    image = Image.new('RGB', (100, height), 'white')
    if box:
        image.paste(colour, box)
    return image


def verdict_of(tmp_path, before, after, again=None):
    write_shot(tmp_path / 'before', before)
    write_shot(tmp_path / 'after', after)
    write_shot(tmp_path / 'again', again or before)
    [result] = compare.compare(tmp_path / 'before', tmp_path / 'after',
                               tmp_path / 'again', tmp_path / 'out')
    return result


def test_identical_shots_are_the_same_and_write_no_images(tmp_path):
    result = verdict_of(tmp_path, page(box=(10, 10, 30, 30)), page(box=(10, 10, 30, 30)))
    assert result['verdict'] == 'same'
    assert not list((tmp_path / 'out').glob('*.jpg'))


def test_a_moved_box_is_a_change_with_three_images(tmp_path):
    result = verdict_of(tmp_path, page(box=(10, 10, 30, 30)), page(box=(14, 10, 34, 30)))
    assert result['verdict'] == 'changed'
    names = sorted(p.name for p in (tmp_path / 'out').glob('*.jpg'))
    assert names == ['game-desktop-after.jpg', 'game-desktop-before.jpg',
                     'game-desktop-changes.jpg']


def test_changes_image_marks_the_changed_pixels_red(tmp_path):
    verdict_of(tmp_path, page(box=(10, 10, 30, 30)), page(box=(60, 60, 80, 80)))
    changes = Image.open(tmp_path / 'out' / 'game-desktop-changes.jpg').convert('RGB')
    red, green, _ = changes.getpixel((70, 70))
    assert red > 180 and green < 60
    assert changes.getpixel((5, 150))[1] > 200  # untouched area stays light


def test_a_taller_page_counts_as_changed(tmp_path):
    result = verdict_of(tmp_path, page(height=200),
                        page(height=260, box=(10, 220, 90, 250)))
    assert result['verdict'] == 'changed'


def test_noise_between_two_base_shots_is_unstable_not_changed(tmp_path):
    result = verdict_of(tmp_path, page(box=(10, 10, 30, 30)), page(box=(50, 50, 70, 70)),
                        again=page(box=(12, 10, 32, 30)))
    assert result['verdict'] == 'unstable'


def test_anti_aliasing_below_the_threshold_is_the_same(tmp_path):
    result = verdict_of(tmp_path, page(height=400), page(height=400, box=(0, 0, 1, 1)))
    assert result['verdict'] == 'same'


def test_comment_lists_changed_pages_with_quoted_image_urls(tmp_path):
    result = verdict_of(tmp_path, page(box=(10, 10, 30, 30)), page(box=(14, 10, 34, 30)))
    text = compare.comment([result], 'https://example.org/run', 'base → head')
    assert text.startswith(compare.MARKER)
    assert '1 of 1 shots changed' in text
    assert TITLE in text
    assert 'https://example.org/run/game-desktop-changes.jpg' in text


@pytest.mark.parametrize('body, expected', [
    ('no block here', []),
    ('intro\r\n<!-- visual-pages\r\nתארים (כדורגל)\r\n\r\n# a note\r\nעונות\r\n-->\r\n',
     ['תארים (כדורגל)', 'עונות']),
])
def test_pages_come_from_the_pr_description_block(monkeypatch, body, expected):
    monkeypatch.setenv('PR_BODY', body)
    defaults = run.titles_from((run.HERE / 'pages.txt').read_text(encoding='utf-8'))
    assert run.wanted_titles([]) == defaults + [t for t in expected if t not in defaults]


def test_page_list_is_capped(monkeypatch):
    monkeypatch.setenv('PR_BODY', '')
    many = [f'עמוד {n}' for n in range(50)]
    assert len(run.wanted_titles(many)) == run.MAX_PAGES
