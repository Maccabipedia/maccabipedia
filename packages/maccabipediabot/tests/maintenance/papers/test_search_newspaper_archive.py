from datetime import date
from pathlib import Path

from maccabipediabot.maintenance.papers.search_newspaper_archive import (
    EXTRACTION_FAILED,
    NO_TEXT_LAYER,
    candidate_files,
    find_hits,
    has_text_layer,
    search,
    strip_bidi,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def _build_archive(root: Path) -> None:
    yedioth = root / "ארכיון ידיעות אחרונות" / "עמודים בודדים" / "1963"
    _touch(yedioth / "1963-11-19_p8.pdf")
    _touch(yedioth / "1963-11-19_p10.pdf")
    _touch(yedioth / "1963-11-19_p9.pdf")
    _touch(yedioth / "1963-11-20_p9.pdf")
    _touch(yedioth / "1963-11-25_p9.pdf")
    yedioth_full = root / "ארכיון ידיעות אחרונות" / "עיתונים מלאים" / "1963"
    _touch(yedioth_full / "1963-11-20.pdf")
    hadashot = root / "ארכיון חדשות הספורט" / "1963"
    _touch(hadashot / "11-20-1963.pdf")
    _touch(hadashot / "11-24-1963.pdf")


def test_candidate_files_follow_each_sources_naming_in_page_order(tmp_path: Path) -> None:
    _build_archive(tmp_path)
    window = (date(1963, 11, 19), date(1963, 11, 21))

    yedioth = candidate_files(tmp_path, "yedioth", *window)
    yedioth_full = candidate_files(tmp_path, "yedioth-full", *window)
    hadashot = candidate_files(tmp_path, "hadashot", *window)

    assert [Path(f).name for f in yedioth] == [
        "1963-11-19_p8.pdf", "1963-11-19_p9.pdf", "1963-11-19_p10.pdf", "1963-11-20_p9.pdf"
    ]
    assert [Path(f).name for f in yedioth_full] == ["1963-11-20.pdf"]
    assert [Path(f).name for f in hadashot] == ["11-20-1963.pdf"]


def test_candidate_files_survive_glob_metacharacters_in_root(tmp_path: Path) -> None:
    root = tmp_path / "drive [mirror]"
    _build_archive(root)

    found = candidate_files(root, "hadashot", date(1963, 11, 20), date(1963, 11, 20))

    assert [Path(f).name for f in found] == ["11-20-1963.pdf"]


def test_candidate_files_empty_when_year_folder_missing(tmp_path: Path) -> None:
    assert candidate_files(tmp_path, "yedioth", date(1970, 1, 1), date(1970, 1, 3)) == []


def test_strip_bidi_and_find_hits_match_through_bidi_marks() -> None:
    text = "כותרת\n‫מכבי ת\"א ניצח את הפועל גבעת ברנר 79:64‬\nשורה אחרונה"

    hits = find_hits(strip_bidi(text), ["גבעת ברנר"], context=1)

    assert len(hits) == 1
    term, line_no, snippet = hits[0]
    assert (term, line_no) == ("גבעת ברנר", 1)
    assert "79:64" in snippet and "‫" not in snippet


def test_has_text_layer_requires_real_hebrew_content() -> None:
    assert has_text_layer("מכבי תל אביב " * 20)
    assert not has_text_layer("^^ 11 ## 3 ק")


def test_search_reports_missing_text_layer_instead_of_no_hit(tmp_path: Path, capsys) -> None:
    _build_archive(tmp_path)

    def stub_extractor(pdf: str) -> str:
        if "חדשות הספורט" in pdf:
            return NO_TEXT_LAYER
        if "עיתונים מלאים" in pdf:
            return f"{EXTRACTION_FAILED}: pdftotext exit 1: Syntax Error: Couldn't read xref table"
        return "מכבי תל אביב ניצחה אמש את הפועל גבעת ברנר 79:64 ביד אליהו"

    found = search(
        tmp_path,
        ["yedioth", "yedioth-full", "hadashot"],
        date(1963, 11, 20),
        date(1963, 11, 20),
        ["79:64"],
        1,
        stub_extractor,
    )

    out = capsys.readouterr().out
    assert found
    assert "HIT in" in out and "1963-11-20_p9.pdf" in out
    assert "NO TEXT LAYER" in out and "11-20-1963.pdf" in out
    assert "EXTRACTION FAILED" in out and "Couldn't read xref table" in out
