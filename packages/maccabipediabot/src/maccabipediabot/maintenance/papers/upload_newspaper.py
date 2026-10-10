"""Upload one newspaper clip to MaccabiPedia, with every convention enforced.

You choose what to keep on the page (by eye, in a crop spec); this tool builds the file
name and page text from strict params, checks the crop's edges, the per-game cap and the
dates, and only then uploads. Dry run by default; ``--apply`` uploads. Rules and their
reasons: `.claude/skills/upload-newspaper/rules.md`.

    uv run python -m maccabipediabot.maintenance.papers.upload_newspaper \\
        --sport כדורסל --paper "ידיעות אחרונות" --publish-date 30-10-1998 \\
        --classification "סיקור משחק" --opponent "הכוכב האדום בלגרד" --game-date 29-10-1998 \\
        --orig scan.jpg --spec crop.json [--description "תגובות קטש"] [--apply]

A crop spec is described in ``newspaper_crop``. ``--image`` uploads a crop made elsewhere
(no edge check is possible then, so it needs ``--no-edge-check-because``).
``--replace`` uploads a new version of an existing newspaper file of the same game.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from maccabipediabot.common.maccabipedia_http import build_maccabipedia_session
from maccabipediabot.maintenance.papers.newspaper_crop import CropSpecError, check_edges, compose, load_spec
from maccabipediabot.maintenance.papers.newspaper_names import (
    TEMPLATES, NewspaperClip, NewspaperClipError, check_cap, game_page_title,
)
from maccabipediabot.maintenance.tickets.ticket_names import Sport

API_URL = "https://www.maccabipedia.co.il/api.php"
MAX_MEGAPIXELS = 6.0
_SPORTS = {s.value: s for s in Sport}
_session = build_maccabipedia_session()


class WikiCheckError(RuntimeError):
    """The wiki answered with something other than the JSON we asked for."""


def _date(text: str) -> date:
    try:
        return datetime.strptime(text, "%d-%m-%Y").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a DD-MM-YYYY date") from None


def _edge_note(text: str) -> tuple[str, str]:
    label, sep, reason = text.partition("=")
    if not sep or not label.strip() or not reason.strip():
        raise argparse.ArgumentTypeError(f"{text!r}: use 'LABEL=why it is not a cut', e.g. 'P0 left=frame line'")
    return label.strip(), reason.strip()


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sport", required=True, choices=list(_SPORTS))
    p.add_argument("--paper", required=True)
    p.add_argument("--publish-date", required=True, type=_date, help="DD-MM-YYYY")
    p.add_argument("--classification", required=True, help="סיווג, e.g. 'סיקור משחק'")
    p.add_argument("--opponent", required=True, help="as in the game page title, without quote marks")
    p.add_argument("--game-date", required=True, type=_date, help="DD-MM-YYYY")
    p.add_argument("--description", default="", help="a second piece from the same paper and day")
    p.add_argument("--game-page", help="needed only when the date has more than one game")
    p.add_argument("--special", action="store_true", help="title, cup final or milestone game: cap 5")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--orig", type=Path, help="the full scan; with --spec")
    src.add_argument("--image", type=Path, help="a finished crop")
    p.add_argument("--spec", type=Path, help="crop spec JSON (with --orig)")
    p.add_argument("--accept-edge", action="append", default=[], type=_edge_note, metavar="LABEL=REASON",
                   help="explain a cuts_ink edge that is really a rule or a seam")
    p.add_argument("--blanks-read", action="store_true",
                   help="you read what every off-rule blank covers and none of it is the article")
    p.add_argument("--no-edge-check-because", default="", help="required with --image")
    p.add_argument("--whole-page-because", default="",
                   help=f"required above {MAX_MEGAPIXELS:.0f} MP: why the whole page is the Maccabi story")
    p.add_argument("--replace", help="existing newspaper file of this game to upload a new version of")
    p.add_argument("--comment", default="", help="upload summary (a default is used)")
    p.add_argument("--apply", action="store_true", help="upload; without it, a dry run")
    args = p.parse_args(argv)
    if args.orig and not args.spec:
        p.error("--orig needs --spec")
    if args.image and not args.no_edge_check_because:
        p.error("--image skips the edge check; say why with --no-edge-check-because")
    return args


def api(**params) -> dict:
    """GET the API and return its JSON, refusing an HTML error page (CLAUDE.md: validate first)."""
    response = _session.get(API_URL, params={**params, "format": "json", "formatversion": "2"})
    if response.status_code != 200 or "application/json" not in response.headers.get("Content-Type", ""):
        raise WikiCheckError(f"API {params.get('action')} returned {response.status_code}: {response.text[:300]}")
    data = response.json()
    if "error" in data:
        raise WikiCheckError(f"API error: {data['error']}")
    return data


def find_game(sport: Sport, game_date: date, override: str | None) -> str:
    from maccabipediabot.maintenance.tickets.wiki_tickets import find_game_page
    title = game_page_title(override or find_game_page(sport, game_date))
    page = api(action="query", titles=title, redirects=0)["query"]["pages"][0]
    if page.get("missing") or page.get("invalid"):
        raise NewspaperClipError(f"game page {title!r} does not exist")
    if "redirect" in page:
        raise NewspaperClipError(f"game page {title!r} is a redirect; link the page it points to")
    return title


def build_image(args: argparse.Namespace) -> tuple[Image.Image, list[str]]:
    """The crop, and the problems that block the upload."""
    if args.image:
        return ImageOps.exif_transpose(Image.open(args.image)).convert("RGB"), []
    orig = ImageOps.exif_transpose(Image.open(args.orig))
    spec = load_spec(args.spec)
    accepted = dict(args.accept_edge)
    problems = []
    for edge in check_edges(orig, spec):
        print("   ", edge)
        if edge.verdict == "cuts_ink" and edge.label not in accepted:
            problems.append(f"{edge.label} cuts ink: move it onto the rule or gutter, or "
                            f"--accept-edge '{edge.label}=<why it is not a cut>'")
        if edge.verdict == "off_rule" and not args.blanks_read:
            problems.append(f"{edge.label} is a blank edge off any rule: read what it covers, then --blanks-read")
    return compose(orig, spec), problems


def linked_newspaper_files(game_page: str) -> list[str]:
    """Newspaper files linked to the game, also through a redirect to it (old spaced titles)."""
    templates = {f"תבנית:{name}" for name in TEMPLATES.values()}
    data = api(action="query", generator="backlinks", gbltitle=game_page, gblnamespace=6,
               gblredirect=1, gbllimit="max", prop="templates", tllimit="max",
               tltemplates="|".join(sorted(templates)))
    return sorted(p["title"] for p in data.get("query", {}).get("pages", [])
                  if any(t["title"] in templates for t in p.get("templates", [])))


def same_bytes_on_wiki(data: bytes) -> list[str]:
    sha1 = hashlib.sha1(data).hexdigest()
    found = api(action="query", list="allimages", aisha1=sha1, ailimit=10)["query"]["allimages"]
    return [f["title"] for f in found]


def was_deleted(file_name: str) -> bool:
    events = api(action="query", list="logevents", letype="delete", letitle=f"File:{file_name}", lelimit=1)
    return bool(events["query"]["logevents"])


def file_text(file_name: str) -> str | None:
    page = api(action="query", titles=f"File:{file_name}", prop="revisions", rvprop="content",
               rvslots="main")["query"]["pages"][0]
    if page.get("missing"):
        return None
    return page["revisions"][0]["slots"]["main"]["content"]


def check_replace_target(file_name: str, game_page: str) -> list[str]:
    text = file_text(file_name)
    if text is None:
        return [f"--replace: {file_name} does not exist"]
    if not any(f"{{{{{t}" in text for t in TEMPLATES.values()):
        return [f"--replace: {file_name} is not a newspaper file"]
    link = re.search(r"שיוך משחק\s*=\s*([^\n|}]*)", text)
    if not link or link.group(1).strip() != game_page:
        return [f"--replace: {file_name} is linked to {link.group(1).strip() if link else 'no game'!r}, "
                f"not to {game_page!r}"]
    return []


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    sport = _SPORTS[args.sport]

    from maccabipediabot.maintenance.tickets.wiki_tickets import GameLookupError
    try:
        game_page = find_game(sport, args.game_date, args.game_page)
        clip = NewspaperClip(paper=args.paper, publish_date=args.publish_date,
                             classification=args.classification, sport=sport, opponent=args.opponent,
                             game_date=args.game_date, game_page=game_page, description=args.description)
        file_name = args.replace or clip.file_name
        print(f"game page: {game_page}\nfile:      {file_name}\n{clip.page_text}\nedges:")
        image, problems = build_image(args)
    except (NewspaperClipError, GameLookupError, CropSpecError, WikiCheckError) as error:
        print(f"REFUSED: {error}")
        return 2

    megapixels = image.width * image.height / 1e6
    print(f"image:     {image.width}x{image.height} ({megapixels:.1f} MP)")
    if megapixels > MAX_MEGAPIXELS and not args.whole_page_because:
        problems.append(f"{megapixels:.1f} MP is a whole page; crop to the Maccabi article, or "
                        f"--whole-page-because '<why the page is all one Maccabi story>'")

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    data = buffer.getvalue()
    existing = linked_newspaper_files(game_page)
    print(f"linked:    {len(existing)} newspaper file(s) on this game")
    if args.replace:
        problems += check_replace_target(args.replace, game_page)
    else:
        if file_text(file_name) is not None:
            problems.append(f"{file_name} already exists; a second piece needs its own --description")
        if was_deleted(file_name):
            problems.append(f"{file_name} was deleted by an admin before; ask before uploading it again")
        try:
            check_cap(existing, 1, args.special)
        except NewspaperClipError as error:
            problems.append(str(error))
    duplicates = [t for t in same_bytes_on_wiki(data) if t.removeprefix("File:").removeprefix("קובץ:") != file_name]
    if duplicates:
        problems.append(f"the same image is already on the wiki: {', '.join(duplicates)}")

    preview = (args.spec or args.image).with_suffix(".preview.jpg")
    image.save(preview, quality=90)
    print(f"preview:   {preview}")
    if problems:
        print("REFUSED:\n  " + "\n  ".join(problems))
        return 2
    if not args.apply:
        print("dry run: everything passes; add --apply to upload")
        return 0
    comment = args.comment or ("חיתוך לכתבה על מכבי בלבד" if args.replace else f"העלאת עיתון: {clip.classification}")
    upload(file_name, data, file_text(file_name) if args.replace else clip.page_text, comment, game_page)
    return 0


def upload(file_name: str, data: bytes, text: str, comment: str, game_page: str) -> None:
    import pywikibot as pw

    from maccabipediabot.common.wiki_login import get_site
    from maccabipediabot.common.wiki_purge import purge_pages
    from maccabipediabot.maintenance.tickets.wiki_tickets import upload_file

    site = get_site()
    upload_file(site, file_name, data, text, comment)
    purge_pages(site, [game_page, f"File:{file_name}"])
    # The templates file a wrong or empty game link under a tracking category.
    bad = [c.title() for c in pw.FilePage(site, f"File:{file_name}").categories()
           if "שיוך לא תקין" in c.title() or "ללא שיוך" in c.title()]
    if bad:
        raise RuntimeError(f"uploaded, but the game link is broken: {', '.join(bad)}")
    print(f"uploaded: https://www.maccabipedia.co.il/File:{file_name.replace(' ', '_')}")


if __name__ == "__main__":
    sys.exit(main())
