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
import time
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image

from maccabipediabot.common.maccabipedia_http import build_maccabipedia_session
from maccabipediabot.maintenance.papers.newspaper_crop import (
    CropSpecError, before_after, check_edges, compose, kept_fraction, load_scan, load_spec,
)
from maccabipediabot.maintenance.papers.newspaper_names import (
    GAME_CAPS, TEMPLATES, NewspaperClip, NewspaperClipError, check_cap, game_cap, game_page_title,
)
from maccabipediabot.maintenance.tickets.ticket_names import Sport

API_URL = "https://www.maccabipedia.co.il/api.php"
MAX_MEGAPIXELS = 4.0  # a finished --image above this is treated as a whole page
MAX_KEPT_SHARE = 0.5  # a crop keeping more than half the scan is a whole page
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
    p.add_argument("--tier", choices=list(GAME_CAPS), default="regular",
                   help="how big the game is, which sets the newspaper cap (the maintainer decides): "
                        + ", ".join(f"{t} {c}" for t, c in GAME_CAPS.items()))
    src = p.add_mutually_exclusive_group()  # neither: info only (game, name, cap)
    src.add_argument("--orig", type=Path, help="the full scan; with --spec")
    src.add_argument("--image", type=Path, help="a finished crop")
    p.add_argument("--spec", type=Path, help="crop spec JSON (with --orig)")
    p.add_argument("--accept-edge", action="append", default=[], type=_edge_note, metavar="LABEL=REASON",
                   help="explain a cuts_ink edge that is really a rule or a seam")
    p.add_argument("--blanks-read", action="append", default=[], metavar="LABEL",
                   help="this off-rule blank edge was zoomed into and covers none of the article (repeat per edge)")
    p.add_argument("--no-edge-check-because", default="", help="required with --image")
    p.add_argument("--whole-page-because", default="",
                   help=f"required above {MAX_MEGAPIXELS:.0f} MP: why the whole page is the Maccabi story")
    p.add_argument("--replace", type=lambda s: re.sub(r"^(?:File|קובץ):", "", s.strip()),
                   help="existing newspaper file of this game to upload a new version of")
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


def build_image(args: argparse.Namespace) -> tuple[Image.Image, list[str], list[str], Image.Image | None]:
    """The crop, the problems that block the upload, the waived checks, and a before/after preview."""
    overrides = []
    if args.image:
        overrides.append(f"no edge check: {args.no_edge_check_because}")
        if args.whole_page_because:
            overrides.append(f"whole page: {args.whole_page_because}")
        return load_scan(args.image), [], overrides, None
    orig = load_scan(args.orig)
    spec = load_spec(args.spec)
    accepted = dict(args.accept_edge)
    problems = []
    share = kept_fraction(orig.size, spec)
    print(f"kept:      {share:.0%} of a page")
    if share > MAX_KEPT_SHARE:
        if args.whole_page_because:
            overrides.append(f"whole page: {args.whole_page_because}")
        else:
            problems.append(f"the crop keeps {share:.0%} of a page, a whole page; crop to the Maccabi article, "
                            f"or --whole-page-because '<why the page is all one Maccabi story>'")
    flagged = []
    for edge in check_edges(orig, spec):
        print("   ", edge)
        if edge.verdict == "cuts_ink":
            flagged.append(edge)
            if edge.label in accepted:
                overrides.append(f"{edge.label}: {accepted[edge.label]}")
            else:
                problems.append(f"{edge.label} cuts ink: move it onto the rule or gutter, or "
                                f"--accept-edge '{edge.label}=<why it is not a cut>'")
        if edge.verdict == "off_rule":
            flagged.append(edge)
            if edge.label in args.blanks_read:
                overrides.append(f"{edge.label}: blank read")
            else:
                problems.append(f"{edge.label} is a blank edge off any rule: zoom into what it covers, "
                                f"then --blanks-read '{edge.label}'")
    crop = compose(orig, spec)
    return crop, problems, overrides, before_after(orig, spec, crop, flagged)


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


def resolved_title(title: str) -> str:
    """Follow a redirect (e.g. Oren's old spaced 'כדורסל: 13-04-1956 ...' titles)."""
    data = api(action="query", titles=title, redirects=1)["query"]
    return data["pages"][0]["title"]


def current_sha1(file_name: str) -> str | None:
    page = api(action="query", titles=f"File:{file_name}", prop="imageinfo", iiprop="sha1")["query"]["pages"][0]
    info = page.get("imageinfo")
    return info[0]["sha1"] if info else None


def check_replace_target(file_name: str, game_page: str, data: bytes, clip: NewspaperClip) -> list[str]:
    text = file_text(file_name)
    if text is None:
        return [f"--replace: {file_name} does not exist"]
    if not file_name.lower().endswith((".jpg", ".jpeg")):
        return [f"--replace: {file_name} is not a JPEG; the crop is uploaded as JPEG bytes"]
    if not any(f"{{{{{t}" in text for t in TEMPLATES.values()):
        return [f"--replace: {file_name} is not a newspaper file"]
    link = re.search(r"שיוך משחק\s*=\s*([^\n|}]*)", text)
    linked = link.group(1).strip() if link else ""
    if not linked or resolved_title(linked) != game_page:
        return [f"--replace: {file_name} is linked to {linked or 'no game'!r}, not to {game_page!r}"]
    for param, wanted in (("שם עיתון", clip.paper), ("תאריך פרסום", f"{clip.publish_date:%d-%m-%Y}"),
                          ("סיווג", clip.classification)):
        found = re.search(rf"{param}\s*=\s*([^\n|}}]*)", text)
        if not found or found.group(1).strip() != wanted:
            return [f"--replace: {file_name} has {param}={found.group(1).strip() if found else '(none)'!r}, "
                    f"but this clip is {wanted!r}: a new version must be the same piece"]
    if current_sha1(file_name) == hashlib.sha1(data).hexdigest():
        return [f"--replace: the wiki already has exactly this image as {file_name}"]
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
        existing = linked_newspaper_files(game_page)
        print(f"game page: {game_page}\nfile:      {file_name}")
        if args.replace and rename_target(args.replace, clip):
            print(f"rename to: {rename_target(args.replace, clip)}  (after the new version)")
        print(file_text(file_name) if args.replace else clip.page_text)
        print(f"linked:    {len(existing)} newspaper file(s) on this game (cap "
              f"{game_cap(args.tier)}){''.join(chr(10) + '           ' + f for f in existing)}")
        if not args.replace and len(existing) >= game_cap(args.tier):
            print(f"AT CAP:    no room for a new file; a swap needs the maintainer's choice"
                  f" ({args.tier}; ask whether the game is a higher --tier)")
        if not args.replace and file_text(file_name) is not None:
            print(f"EXISTS:    {file_name} is already on the wiki; another piece needs its own --description")
        if not (args.orig or args.image):
            print("info only: no image given (add --orig/--spec or --image to check a crop)")
            return 0
        print("edges:")
        image, problems, overrides, comparison = build_image(args)
    except (NewspaperClipError, GameLookupError, CropSpecError, WikiCheckError) as error:
        print(f"REFUSED: {error}")
        return 2

    print(f"image:     {image.width}x{image.height} ({image.width * image.height / 1e6:.1f} MP)")
    data = image_bytes(args, image)
    already_uploaded = (not args.replace and current_sha1(file_name) == hashlib.sha1(data).hexdigest())
    if already_uploaded:
        print(f"finish:    the wiki already has exactly this image as {file_name} (an earlier --apply "
              f"stopped after the upload); --apply now only purges and checks the game link")
    else:
        problems += upload_problems(args, clip, file_name, game_page, existing, image, data)

    preview = (args.spec or args.image).with_suffix(".preview.jpg")
    image.save(preview, quality=90)
    print(f"preview:   {preview}")
    if comparison is not None:
        comparison_path = preview.with_suffix("").with_suffix(".before_after.jpg")
        comparison.save(comparison_path, quality=85)
        print(f"compare:   {comparison_path}  (show this to the maintainer)")
    if problems:
        print("REFUSED:\n  " + "\n  ".join(problems))
        return 2
    if not args.apply:
        print("dry run: everything passes; add --apply to upload")
        return 0
    comment = args.comment or ("חיתוך לכתבה על מכבי בלבד" if args.replace else f"העלאת עיתון: {clip.classification}")
    if overrides:
        comment += " | " + "; ".join(overrides)  # the maintainer sees why a check was waived
    if not already_uploaded:
        from maccabipediabot.common.wiki_login import get_site
        from maccabipediabot.maintenance.tickets.wiki_tickets import upload_file
        upload_file(get_site(), file_name, data, file_text(file_name) if args.replace else clip.page_text, comment)
    finish(file_name, game_page, sport)
    target = rename_target(args.replace, clip) if args.replace else None
    if target:
        rename(file_name, target, game_page)
    return 0


def rename_target(file_name: str, clip: NewspaperClip) -> str | None:
    """A replaced file still named for a whole page ('... עמוד 68.jpg') takes the clip's name."""
    if not re.search(r"עמוד \d+", file_name) or clip.file_name == file_name:
        return None
    return clip.file_name


def rename(old: str, new: str, game_page: str) -> None:
    import pywikibot as pw

    from maccabipediabot.common.wiki_login import get_site
    from maccabipediabot.common.wiki_purge import purge_pages

    site = get_site()
    pw.FilePage(site, f"File:{old}").move(f"File:{new}", reason="שם לפי המוסכמה, אחרי חיתוך לכתבה",
                                          noredirect=True)
    purge_pages(site, [game_page])
    print(f"renamed:  {old}\n       -> https://www.maccabipedia.co.il/File:{new.replace(' ', '_')}")


def image_bytes(args: argparse.Namespace, image: Image.Image) -> bytes:
    """A finished JPEG --image goes up byte for byte; anything built here is encoded once."""
    if args.image and args.image.suffix.lower() in (".jpg", ".jpeg"):
        original = Image.open(args.image)
        if original.getexif().get(0x0112, 1) == 1:  # no EXIF rotation to bake in
            return args.image.read_bytes()
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def upload_problems(args: argparse.Namespace, clip: NewspaperClip, file_name: str, game_page: str,
                    existing: list[str], image: Image.Image, data: bytes) -> list[str]:
    """Every wiki-side rule for one upload, in one place. Wiki reads all go through api()."""
    problems = []
    megapixels = image.width * image.height / 1e6
    if args.image and megapixels > MAX_MEGAPIXELS and not args.whole_page_because:
        problems.append(f"{megapixels:.1f} MP is a whole page; crop to the Maccabi article, or "
                        f"--whole-page-because '<why the page is all one Maccabi story>'")
    if args.replace:
        problems += check_replace_target(args.replace, game_page, data, clip)
        target = rename_target(args.replace, clip)
        if target and file_text(target) is not None:
            problems.append(f"after the new version, {args.replace} would be renamed to {target}, which is "
                            f"taken; give this piece its own --description")
    else:
        if file_text(file_name) is not None:
            problems.append(f"{file_name} already exists with a different image; if this is another piece "
                            f"from the same paper and day, give it its own --description")
        if was_deleted(file_name):
            problems.append(f"{file_name} was deleted by an admin before; ask before uploading it again")
        try:
            check_cap(existing, 1, args.tier)
        except NewspaperClipError as error:
            problems.append(str(error))
    duplicates = [t for t in same_bytes_on_wiki(data) if t.removeprefix("File:").removeprefix("קובץ:") != file_name]
    if duplicates:
        problems.append(f"the same image is already on the wiki: {', '.join(duplicates)}")
    return problems


def finish(file_name: str, game_page: str, sport: Sport) -> None:
    """After the upload: purge, then confirm the game link took. Safe to re-run."""
    import pywikibot as pw

    from maccabipediabot.common.wiki_login import get_site
    from maccabipediabot.common.wiki_purge import purge_pages

    site = get_site()
    purge_pages(site, [game_page, f"File:{file_name}"])
    # The templates file a wrong or empty game link under a tracking category. Categories
    # land after the links update, so look a few times before concluding.
    for _ in range(4):
        time.sleep(5)
        categories = [c.title() for c in pw.FilePage(site, f"File:{file_name}").categories()]
        if categories:
            break
    bad = [c for c in categories if "שיוך לא תקין" in c or "ללא שיוך" in c]
    if not categories:
        raise RuntimeError(f"uploaded, but {file_name} has no categories yet: open it and check the game link")
    if bad:
        raise RuntimeError(f"uploaded, but the game link is broken: {', '.join(bad)}")
    # Football files also land in a per-game category ("עיתונות למשחק מה-..."); its absence
    # means the template did not recognise the game.
    if sport is Sport.FOOTBALL and not any("עיתונות למשחק" in c for c in categories):
        raise RuntimeError(f"uploaded, but {file_name} is not in its per-game category: check the game link")
    print(f"uploaded: https://www.maccabipedia.co.il/File:{file_name.replace(' ', '_')}")


if __name__ == "__main__":
    sys.exit(main())
