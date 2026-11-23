"""Reclassify standalone game photos that went up as סיקור משחק to רגע ממשחק.

A candidate is a file in the category whose name says סיקור משחק and whose description
(after the game-date brackets) starts with תמונה/תמונות. For each one: set |סיווג= to
רגע ממשחק on the file page, then move the file to the same name with סיקור משחק replaced,
leaving no redirect.

    uv run python -m maccabipediabot.maintenance.papers.fix_game_moment_classification \
        --category "קטגוריה:עיתונות כדורסל עונת 1976/77" [--file "<name>"] [--limit 1] [--apply]

Without --apply it only prints old -> new names.
"""
import argparse
import re

import pywikibot as pw

from maccabipediabot.common.wiki_login import get_site
from maccabipediabot.maintenance.papers.upload_newspaper import rename

OLD, NEW = "סיקור משחק", "רגע ממשחק"
PHOTO_DESCRIPTION = re.compile(r"\(\d{2}\.\d{2}\.\d{4}\) תמונ")
GAME_LINK = re.compile(r"\|\s*שיוך משחק\s*=\s*([^\n|}]+)")
CLASSIFICATION = re.compile(r"(\|\s*סיווג\s*=\s*)" + OLD + r"(\s*[\n|}])")


def candidates(site: pw.Site, category: str) -> list[pw.FilePage]:
    pages = pw.Category(site, category).members(namespaces=[6])
    return sorted((pw.FilePage(p) for p in pages
                   if f" {OLD} " in p.title() and PHOTO_DESCRIPTION.search(p.title())),
                  key=lambda p: p.title())


def fix(page: pw.FilePage, apply: bool) -> None:
    old_name = page.title(with_ns=False)
    new_name = old_name.replace(f" {OLD} ", f" {NEW} ", 1)
    text = page.text
    new_text, count = CLASSIFICATION.subn(rf"\g<1>{NEW}\g<2>", text)
    already = count == 0 and re.search(r"\|\s*סיווג\s*=\s*" + NEW + r"\s*[\n|}]", text)
    game = GAME_LINK.search(text)
    if not (count == 1 or already) or not game:
        print(f"SKIP (סיווג={OLD} found {count}x, שיוך משחק {'found' if game else 'missing'}): {old_name}")
        return
    print(f"{old_name}\n  -> {new_name}{'  (סיווג already ' + NEW + ', rename only)' if already else ''}")
    if not apply:
        return
    if pw.FilePage(page.site, f"File:{new_name}").exists():
        print(f"SKIP (target exists): {new_name}")
        return
    if not already:
        page.text = new_text
        page.save(summary=f"סיווג: {OLD} -> {NEW} (תמונה מהמשחק, לא כתבה)")
    rename(old_name, new_name, game.group(1).strip())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--category", required=True)
    p.add_argument("--file", help="only this file name (no 'קובץ:' prefix)")
    p.add_argument("--limit", type=int)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    site = get_site()
    pages = candidates(site, args.category)
    if args.file:
        pages = [pg for pg in pages if pg.title(with_ns=False) == args.file]
    if args.limit:
        pages = pages[:args.limit]
    print(f"{len(pages)} file(s){'' if args.apply else ' (dry run)'}")
    for page in pages:
        fix(page, args.apply)


if __name__ == "__main__":
    main()
