"""Upload one newspaper clip to MaccabiPedia, with every convention enforced.

You choose what to keep on the page (by eye, in a crop spec); this tool builds the file
name and page text from strict params, checks the crop's edges, the per-game cap and the
dates, and only then uploads. Dry run by default; ``--apply`` uploads. Rules and their
reasons: ``.claude/uploading_newspapers.md``.

    uv run python -m maccabipediabot.maintenance.papers.upload_newspaper \\
        --sport כדורסל --paper "ידיעות אחרונות" --publish-date 30-10-1998 \\
        --classification "סיקור משחק" --opponent "הכוכב האדום בלגרד" --game-date 29-10-1998 \\
        --orig scan.jpg --spec crop.json [--description "תגובות קטש"] [--apply]

A crop spec is described in ``newspaper_crop``. ``--image`` uploads a crop made elsewhere
(no edge check is possible then, so it needs ``--no-edge-check-because``).
``--replace`` uploads a new version of an existing file under its existing name.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image

from maccabipediabot.maintenance.papers.newspaper_crop import check_edges, compose, load_spec
from maccabipediabot.maintenance.papers.newspaper_names import (
    NewspaperClip, NewspaperClipError, check_cap, TEMPLATES,
)
from maccabipediabot.maintenance.tickets.ticket_names import Sport

API_URL = "https://www.maccabipedia.co.il/api.php"
MAX_MEGAPIXELS = 6.0
_SPORTS = {s.value: s for s in Sport}

logger = logging.getLogger(__name__)


def _date(text: str) -> date:
    return datetime.strptime(text, "%d-%m-%Y").date()


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sport", required=True, choices=list(_SPORTS))
    p.add_argument("--paper", required=True)
    p.add_argument("--publish-date", required=True, type=_date, help="DD-MM-YYYY")
    p.add_argument("--classification", required=True, help="סיווג, e.g. 'סיקור משחק'")
    p.add_argument("--opponent", required=True, help="spelled exactly as in the game page title")
    p.add_argument("--game-date", required=True, type=_date, help="DD-MM-YYYY")
    p.add_argument("--description", default="", help="a second piece from the same paper and day")
    p.add_argument("--game-page", help="needed only when the date has more than one game")
    p.add_argument("--special", action="store_true", help="title, cup final or milestone game: cap 5")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--orig", type=Path, help="the full scan; with --spec")
    src.add_argument("--image", type=Path, help="a finished crop")
    p.add_argument("--spec", type=Path, help="crop spec JSON (with --orig)")
    p.add_argument("--accept-edge", action="append", default=[], metavar="LABEL=REASON",
                   help="explain a cuts_ink edge that is really a rule or a seam, e.g. 'P0 left=frame line'")
    p.add_argument("--blanks-read", action="store_true",
                   help="you read what every off-rule blank covers and none of it is the article")
    p.add_argument("--no-edge-check-because", default="", help="required with --image")
    p.add_argument("--whole-page-because", default="",
                   help=f"required above {MAX_MEGAPIXELS:.0f} MP: why the whole page is the Maccabi story")
    p.add_argument("--replace", help="existing file name to upload a new version of")
    p.add_argument("--apply", action="store_true", help="upload; without it, a dry run")
    args = p.parse_args(argv)
    if args.orig and not args.spec:
        p.error("--orig needs --spec")
    if args.image and not args.no_edge_check_because:
        p.error("--image skips the edge check; say why with --no-edge-check-because")
    return args


def build_image(args: argparse.Namespace) -> tuple[Image.Image, list[str]]:
    """The crop, and the problems that block the upload."""
    if args.image:
        return Image.open(args.image).convert("RGB"), []
    orig = Image.open(args.orig)
    spec = load_spec(args.spec)
    accepted = dict(item.split("=", 1) for item in args.accept_edge)
    problems = []
    for edge in check_edges(orig, spec):
        print("   ", edge)
        if edge.verdict == "cuts_ink" and edge.label not in accepted:
            problems.append(f"{edge.label} cuts ink: move it onto the rule or gutter, or "
                            f"--accept-edge '{edge.label}=<why it is not a cut>'")
        if edge.verdict == "off_rule" and not args.blanks_read:
            problems.append(f"{edge.label} is a blank edge off any rule: read what it covers, then --blanks-read")
    return compose(orig, spec), problems


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(sys.argv[1:] if argv is None else argv)
    sport = _SPORTS[args.sport]

    from maccabipediabot.maintenance.tickets.wiki_tickets import GameLookupError, file_exists, find_game_page
    try:
        game_page = args.game_page or find_game_page(sport, args.game_date)
        clip = NewspaperClip(paper=args.paper, publish_date=args.publish_date,
                             classification=args.classification, sport=sport, opponent=args.opponent,
                             game_date=args.game_date, game_page=game_page, description=args.description)
    except (NewspaperClipError, GameLookupError) as error:
        print(f"REFUSED: {error}")
        return 2

    file_name = args.replace or clip.file_name
    print(f"game page: {game_page}\nfile:      {file_name}\n{clip.page_text}\nedges:")
    image, problems = build_image(args)
    megapixels = image.width * image.height / 1e6
    print(f"image:     {image.width}x{image.height} ({megapixels:.1f} MP)")
    if megapixels > MAX_MEGAPIXELS and not args.whole_page_because:
        problems.append(f"{megapixels:.1f} MP is a whole page; crop to the Maccabi article, or "
                        f"--whole-page-because '<why the page is all one Maccabi story>'")

    existing = linked_newspaper_files(game_page)
    if args.replace:
        if not file_exists(args.replace):
            problems.append(f"--replace: {args.replace} does not exist")
    else:
        if file_exists(file_name):
            problems.append(f"{file_name} already exists; a second piece needs --description")
        try:
            check_cap(existing, 1, args.special)
        except NewspaperClipError as error:
            problems.append(str(error))
    print(f"linked:    {len(existing)} newspaper file(s) on this game")

    preview = (args.spec or args.image).with_suffix(".preview.jpg")
    image.save(preview, quality=90)
    print(f"preview:   {preview}")
    if problems:
        print("REFUSED:\n  " + "\n  ".join(problems))
        return 2
    if not args.apply:
        print("dry run: everything passes; add --apply to upload")
        return 0
    upload(file_name, image, clip, game_page, replace=bool(args.replace))
    return 0


def linked_newspaper_files(game_page: str) -> list[str]:
    from maccabipediabot.maintenance.tickets.wiki_tickets import _session
    templates = {f"תבנית:{name}" for name in TEMPLATES.values()}
    files: list[str] = []
    params = {"action": "query", "list": "backlinks", "bltitle": game_page, "blnamespace": 6,
              "bllimit": "max", "format": "json", "formatversion": "2"}
    response = _session.get(API_URL, params=params)
    response.raise_for_status()
    for link in response.json()["query"]["backlinks"]:
        info = _session.get(API_URL, params={"action": "query", "titles": link["title"], "prop": "templates",
                                             "tllimit": "max", "format": "json", "formatversion": "2"})
        info.raise_for_status()
        used = {t["title"] for t in info.json()["query"]["pages"][0].get("templates", [])}
        if used & templates:
            files.append(link["title"])
    return files


def upload(file_name: str, image: Image.Image, clip: NewspaperClip, game_page: str, *, replace: bool) -> None:
    import pywikibot as pw

    from maccabipediabot.common.wiki_login import get_site
    from maccabipediabot.common.wiki_purge import purge_pages
    from maccabipediabot.maintenance.tickets.wiki_tickets import upload_file

    site = get_site()
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    text = pw.FilePage(site, f"File:{file_name}").text if replace else clip.page_text
    comment = "חיתוך לכתבה על מכבי בלבד" if replace else f"העלאת עיתון: {clip.classification}"
    upload_file(site, file_name, buffer.getvalue(), text, comment)
    purge_pages(site, [game_page, f"File:{file_name}"])
    # The templates file a wrong or empty game link under a tracking category.
    bad = [c.title() for c in pw.FilePage(site, f"File:{file_name}").categories()
           if "שיוך לא תקין" in c.title() or "ללא שיוך" in c.title()]
    if bad:
        raise RuntimeError(f"uploaded, but the game link is broken: {', '.join(bad)}")
    print(f"uploaded: https://www.maccabipedia.co.il/File:{file_name.replace(' ', '_')}")


if __name__ == "__main__":
    sys.exit(main())
