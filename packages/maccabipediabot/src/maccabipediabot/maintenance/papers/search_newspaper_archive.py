"""Search the local newspaper archive (Google Drive scans) by date window and terms.

Uses only the PDF text layer (pdftotext) - no OCR. Files with no usable text
layer are reported as such rather than silently counted as "no hit": render them
with `pdftoppm -r 200 -png` and read the page image instead.

See .claude/newspaper_archives.md for the archive layout and reading conventions.
"""

import argparse
import glob
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable

ARCHIVE_ROOT_ENV = "MACCABIPEDIA_NEWSPAPER_ARCHIVE"

# source -> (subfolder under the archive root, filename glob per day)
# yedioth: single pre-selected pages per day, has a text layer.
# yedioth-full: complete issues, has a text layer.
# hadashot: full daily issues, image-only scans (no text layer).
SOURCES = {
    "yedioth": (Path("ארכיון ידיעות אחרונות") / "עמודים בודדים", "{iso}_p*.pdf"),
    "yedioth-full": (Path("ארכיון ידיעות אחרונות") / "עיתונים מלאים", "{iso}*.pdf"),
    "hadashot": (Path("ארכיון חדשות הספורט"), "{mdy}*.pdf"),
}

_BIDI_CHARS = "".join(
    chr(codepoint)
    for codepoint in [*range(0x200E, 0x2010), *range(0x202A, 0x202F), *range(0x2066, 0x206A)]
)
_BIDI_RE = re.compile(f"[{re.escape(_BIDI_CHARS)}]")
_HEBREW_RE = re.compile(r"[֐-׿]")
_PAGE_NUMBER_RE = re.compile(r"_p(\d+)\.pdf$")
NO_TEXT_LAYER = "__NO_TEXT_LAYER__"
EXTRACTION_FAILED = "__EXTRACTION_FAILED__"


def strip_bidi(text: str) -> str:
    return _BIDI_RE.sub("", text)


def has_text_layer(text: str, min_hebrew_chars: int = 80) -> bool:
    return len(_HEBREW_RE.findall(text)) >= min_hebrew_chars


def _page_sort_key(pdf_path: str) -> tuple[int, str]:
    match = _PAGE_NUMBER_RE.search(pdf_path)
    return (int(match.group(1)) if match else 0, pdf_path)


def candidate_files(archive_root: Path, source: str, start: date, end: date) -> list[str]:
    subfolder, pattern = SOURCES[source]
    files: list[str] = []
    day = start
    while day <= end:
        year_dir = archive_root / subfolder / str(day.year)
        if year_dir.is_dir():
            name = pattern.format(iso=day.isoformat(), mdy=day.strftime("%m-%d-%Y"))
            matches = glob.glob(os.path.join(glob.escape(str(year_dir)), name))
            files.extend(sorted(matches, key=_page_sort_key))
        day += timedelta(days=1)
    return files


def extract_text(pdf_path: str) -> str:
    try:
        result = subprocess.run(["pdftotext", pdf_path, "-"], capture_output=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return f"{EXTRACTION_FAILED}: {error}"
    if result.returncode != 0:
        return f"{EXTRACTION_FAILED}: pdftotext exit {result.returncode}: {result.stderr.decode(errors='replace').strip()}"
    text = strip_bidi(result.stdout.decode("utf-8", errors="replace"))
    return text if has_text_layer(text) else NO_TEXT_LAYER


def find_hits(text: str, terms: Iterable[str], context: int = 3) -> list[tuple[str, int, str]]:
    lines = text.splitlines()
    hits = []
    for term in terms:
        needle = strip_bidi(term)
        for index, line in enumerate(lines):
            if needle in line:
                window = lines[max(0, index - context): index + context + 1]
                hits.append((term, index, "\n".join(window)))
    return hits


def search(
    archive_root: Path,
    sources: Iterable[str],
    start: date,
    end: date,
    terms: list[str],
    context: int,
    extractor: Callable[[str], str] = extract_text,
) -> bool:
    any_hit = False
    print(f"# window {start} .. {end}  terms={terms}")
    for source in sources:
        files = candidate_files(archive_root, source, start, end)
        print(f"## {source}: {len(files)} file(s)")
        for pdf in files:
            text = extractor(pdf)
            if text == NO_TEXT_LAYER:
                print(f"  NO TEXT LAYER (render and read visually): {pdf}")
                continue
            if text.startswith(EXTRACTION_FAILED):
                print(f"  EXTRACTION FAILED: {pdf} - {text.split(': ', 1)[1]}")
                continue
            hits = find_hits(text, terms, context)
            if not hits:
                print(f"  no hit: {pdf}")
                continue
            any_hit = True
            print(f"  HIT in {pdf}")
            for term, line_no, snippet in hits:
                print(f"    --- term={term!r} line={line_no} ---")
                print("    " + snippet.replace("\n", "\n    "))
    if not any_hit:
        print("# NO HITS - a text-layer miss is not proof of absence, see newspaper_archives.md")
    return any_hit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", required=True, help="center date, YYYY-MM-DD")
    parser.add_argument("--before", type=int, default=0, help="days before --date to include")
    parser.add_argument("--after", type=int, default=4, help="days after --date to include")
    parser.add_argument("--terms", nargs="+", required=True, help="substrings to look for")
    parser.add_argument("--sources", nargs="+", default=["yedioth"], choices=sorted(SOURCES))
    parser.add_argument("--context", type=int, default=3, help="lines of context around a hit")
    parser.add_argument(
        "--archive-root",
        default=os.environ.get(ARCHIVE_ROOT_ENV),
        help=f"path to 'ארכיון עיתונים' (default: ${ARCHIVE_ROOT_ENV})",
    )
    args = parser.parse_args(argv)
    if not args.archive_root:
        parser.error(f"pass --archive-root or set {ARCHIVE_ROOT_ENV}")

    center = date.fromisoformat(args.date)
    found = search(
        Path(args.archive_root),
        args.sources,
        center - timedelta(days=args.before),
        center + timedelta(days=args.after),
        args.terms,
        args.context,
    )
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
