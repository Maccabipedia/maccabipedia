"""Put the LOCAL wiki into the optimised state. Idempotent and re-runnable.

Seeding re-imports pages from prod and silently reverts template edits, so this
must be safe to apply repeatedly.

  --revert   restore every touched page from ./backups/
  --status   report which optimisations are currently in place
"""
import os
import re
import sys
from pathlib import Path

import requests

BASE = os.environ.get("MW_LOCAL_URL", "http://localhost:8080")
USER, PASSWORD = "maccabi", "maccabi2026"
BACKUP = Path(__file__).parent / "backups"
MODULE_TITLE = "יחידה:סטטיסטיקה שחקן"
MODULE_SOURCE = Path(__file__).parent / "Module_סטטיסטיקה_שחקן.lua"
CACHE_PERIOD = 86400

session = requests.Session()
session.headers["User-Agent"] = "MaccabipediaPerfBenchmark/1.0"

PASS_THROUGH = ["שחקן", "מספר אירוע", "תת אירוע", "ללא תת אירוע",
                "קטגוריית מפעל", "תוצאה", "עונה", "מכבי"]
ARGS = "".join(f"|{name}={{{{{{{name}|}}}}}}" for name in PASS_THROUGH)

# Filters the module cannot answer, per template. These MUST route to the
# original query, which is preserved under .../שליפה מלאה.
#
# The module refuses a parameter it does not implement rather than ignoring it,
# but that guard only fires for parameters it is actually handed -- and a shim
# that forwards a fixed list silently drops the rest before the guard can see
# them. That is not a missing feature, it is a wrong answer wearing the right
# shape: an opponent page asking "yellow cards against מכבי חיפה" was handed the
# wiki-wide total of 425, the same number it gets with no filter at all.
FALLBACK_ARGS = {
    "תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות אירועי שחקן": [
        "אצטדיון", "אצטדיונים", "יריבה", "יריבות", "מאמן", "מפעל מקורי",
        "מפעל נוכחי", "מפעלים", "עוזר שופט", "שופט", "תוצאה יריבה",
        "תוצאה מכבי"],
    "תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות משחקים המכילים אירוע שחקן": [
        "אצטדיון", "מאמן", "תוצאה יריבה", "תוצאה מכבי"],
}


def dispatcher(title: str, function: str) -> str:
    """Module for what it can answer, preserved original for everything else."""
    full = title + "/שליפה מלאה"
    fallback = FALLBACK_ARGS[title]
    guard = "".join("{{{" + name + "|}}}" for name in fallback)
    forwarded = "".join(f"|{name}={{{{{{{name}|}}}}}}"
                        for name in [*PASS_THROUGH, *fallback])
    return (
        "<includeonly><!--\n\n"
        f"מנתב: [[יחידה:סטטיסטיקה שחקן]] עונה על הסינונים הנפוצים בשליפה אחת\n"
        "משותפת לכל הקריאות בדף. סינון לפי יריבה, אצטדיונים, שופט, מאמן או\n"
        f"תוצאת יריבה עדיין דורש את השליפה המלאה, שנשמרה ב[[{full}]].\n\n"
        "-->{{#if: " + guard + "\n"
        "  |{{" + full.removeprefix("תבנית:") + forwarded + "}}\n"
        f"  |{{{{#invoke:סטטיסטיקה שחקן|{function}{ARGS}}}}}\n"
        "}}</includeonly>"
    )


# Leaf templates that become thin module wrappers.
SHIMS = {
    "תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות אירועי שחקן":
        dispatcher("תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות אירועי שחקן", "count"),
    "תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות משחקים המכילים אירוע שחקן":
        dispatcher("תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות משחקים המכילים אירוע שחקן",
                   "countGames"),
    # Alias lookups go through יחידה:המרות, which shares one Cargo query across
    # every call on the page via mw.loadData -- the only Scribunto mechanism
    # that survives between #invoke calls. Measured over 32 lookups:
    # template 0.110s CPU, module 0.037s.
    "תבנית:המרות/המרות אצטדיון/אצטדיון לרשימת אצטדיונים מקושרים":
        "<includeonly>{{#invoke:המרות|stadiumAliases"
        "|אצטדיון={{{אצטדיון|}}}}}</includeonly>",
    "תבנית:המרות/המרות יריבה/יריבה לרשימת יריבות מקושרות":
        "<includeonly>{{#invoke:המרות|opponentAliases"
        "|יריבה={{{יריבה|}}}}}</includeonly>",
}

CONVERSION_MODULES = {
    "יחידה:המרות/נתונים": Path(__file__).parent / "Module_המרות_נתונים.lua",
    "יחידה:המרות": Path(__file__).parent / "Module_המרות.lua",
}

# The stats column, rendered by a single module call.
#
# Scribunto does not keep module state between #invoke calls -- measured: 1 call
# 0.035s CPU, 65 calls 0.968s, perfectly linear -- so a per-statistic #invoke
# re-runs the Cargo query every time and saves nothing. One call for the whole
# column means one query for the whole column: 0.235s -> 0.032s per column.
DISPLAY = "תבנית:פרופיל כדורגל/הצגת עמודת סטטיסטיקה/שחקן/הצגה"
DISPLAY_WIKITEXT = (
    "<includeonly>{{#invoke:סטטיסטיקה שחקן|column"
    "|שם להצגה={{{שם להצגה|}}}"
    "|קטגוריית מפעל={{{קטגוריית מפעל|}}}"
    "|האם שוער={{{האם שוער|}}}}}</includeonly>"
    "<noinclude>\n"
    "עמודת הסטטיסטיקה של שחקן. הנתונים והעיצוב מוגדרים ב־[[יחידה:סטטיסטיקה שחקן]],\n"
    "בפונקציה column - טבלה אחת של שורות במקום חזרה על אותו מבנה לכל נתון.\n\n"
    "פרמטרים:\n"
    "* שם להצגה: שם השחקן\n"
    "* קטגוריית מפעל: ליגה / גביע / בינלאומי / רשמי / יתר-רשמיים, או ריק להכל\n"
    "* האם שוער: ערך כלשהו כדי להוסיף את נתוני השוער\n"
    "</noinclude>")


class ApiError(RuntimeError):
    def __init__(self, code: str, info: str) -> None:
        super().__init__(f"{code}: {info}")
        self.code = code


def api(**data):
    data.update(format="json", formatversion="2")
    response = session.post(f"{BASE}/api.php", data=data, timeout=600)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        error = payload["error"]
        raise ApiError(error.get("code", "?"), error.get("info", ""))
    return payload


def login() -> str:
    token = api(action="query", meta="tokens", type="login")["query"]["tokens"]["logintoken"]
    api(action="login", lgname=USER, lgpassword=PASSWORD, lgtoken=token)
    return api(action="query", meta="tokens", type="csrf")["query"]["tokens"]["csrftoken"]


def get_text(title: str) -> str | None:
    page = api(action="query", prop="revisions", rvslots="main",
               rvprop="content", titles=title)["query"]["pages"][0]
    return page["revisions"][0]["slots"]["main"]["content"] if "revisions" in page else None


def backup_path(title: str) -> Path:
    return BACKUP / (title.replace("/", "__").replace(":", "_") + ".wiki")


_token = {"csrf": None}


def edit(title: str, text: str, summary: str) -> None:
    """Edit, refreshing the CSRF token once if the session has rolled over.

    The scan over every template takes long enough that a token grabbed at
    startup can go stale mid-run.
    """
    for attempt in (1, 2):
        try:
            api(action="edit", title=title, text=text,
                summary=summary, token=_token["csrf"])
            return
        except ApiError as exc:
            if attempt == 2 or "badtoken" not in exc.code.lower():
                raise
            _token["csrf"] = login()


def save(title: str, text: str, token: str | None = None,
         keep_backup: bool = True) -> None:
    if keep_backup:
        path = backup_path(title)
        if not path.exists():
            current = get_text(title)
            if current is not None:
                BACKUP.mkdir(parents=True, exist_ok=True)
                path.write_text(current, encoding="utf-8")
    edit(title, text, "local perf experiment")


def all_pages(namespace: int) -> list[str]:
    titles, cont = [], {}
    while True:
        payload = api(action="query", list="allpages", apnamespace=namespace,
                      aplimit=500, **cont)
        titles += [p["title"] for p in payload["query"]["allpages"]]
        if "continue" not in payload:
            return titles
        cont = payload["continue"]


def strip_bad_cacheperiod(text: str) -> str:
    """Undo an earlier insertion that put cacheperiod FIRST inside {{#dpl:}}.

    The first parameter of a parser function carries no leading '|', so putting
    '|cacheperiod=' ahead of it made that original first parameter part of the
    cacheperiod value -- silently unsetting `category` and making the gallery
    list everything.
    """
    return re.sub(r"(\{\{#dpl:)\n\s*\|cacheperiod=\d+", r"\1", text)


def add_cacheperiod(text: str) -> tuple[str, int]:
    """Append |cacheperiod=N as the LAST parameter of each {{#dpl:}} call."""
    text = strip_bad_cacheperiod(text)
    out, added, index = [], 0, 0
    for match in re.finditer(r"\{\{#dpl:", text):
        depth, cursor = 0, match.start()
        while cursor < len(text):
            if text[cursor] == "{":
                depth += 1
            elif text[cursor] == "}":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        call = text[match.start():cursor + 1]
        if "cacheperiod" in call:
            continue
        # cursor points at the first '}' of the closing '}}'.
        out.append(text[index:cursor - 1])
        out.append(f"\n        |cacheperiod={CACHE_PERIOD}\n")
        index = cursor - 1
        added += 1
    out.append(text[index:])
    return "".join(out), added


CHECK_TEMPLATE = "תבנית:קטגוריה מכילה קבצים"
CHECK_SOURCE = """<includeonly><!--

בדיקה זולה: האם קטגוריה מכילה לפחות דף אחד.
מחזירה "1" אם כן, וריק אם לא.

PAGESINCATEGORY קורא את המונה שמדיה-ויקי כבר מתחזקת בטבלת category -
שורה אחת באינדקס. לשם השוואה, בדיקה דרך DPL מפעילה מנגנון שליפה שלם:
נמדד על 171 בדיקות, DPL עלה 0.654 שניות מעבד ו-433 שאילתות, ואילו
PAGESINCATEGORY עלה 0.024 שניות ו-116 שאילתות.

-->{{#if: {{{שם קטגוריה|}}}
	|{{#ifexpr: {{PAGESINCATEGORY:{{{שם קטגוריה}}}|R}} > 0 |1}}
}}<!--

--></includeonly><noinclude>
מחזירה "1" אם הקטגוריה מכילה לפחות דף אחד, אחרת ריק.

פרמטרים:
* שם קטגוריה: שם הקטגוריה לבדיקה (ללא הקידומת "קטגוריה:")

שימושי כתנאי, למשל להצגת סמל כאשר קיימות תמונות למשחק.
ראו גם: [[תבנית:הצגת גלריה לפי קטגוריה]] - להצגת הגלריה עצמה.
</noinclude>"""

GAME_ROW = "תבנית:כדורגל/רשימת משחקים/הצגת משחק"
IMAGE_FORMATS = "תבנית:תיקון פורמט תמונה"
EXTENSIONS = "jpg,JPG,jpeg,JPEG,png,PNG,gif,GIF"


def apply_cheap_category_check() -> None:
    """Stop building whole galleries just to test whether a category is empty."""
    if get_text(CHECK_TEMPLATE) != CHECK_SOURCE:
        save(CHECK_TEMPLATE, CHECK_SOURCE, keep_backup=False)
        print(f"  check  {CHECK_TEMPLATE}")

    text = get_text(GAME_ROW)
    if not text:
        return
    # Only calls carrying |אין תוצאות= (empty) are boolean tests, not displays.
    # The category value can contain pipes, so match lazily to that marker.
    new, count = re.subn(
        r"\{\{הצגת גלריה לפי קטגוריה \|שם קטגוריה=(.*?)\s*\|אין תוצאות=\}\}",
        r"{{קטגוריה מכילה קבצים |שם קטגוריה=\1}}", text)
    if count:
        save(GAME_ROW, new)
        print(f"  icons  {GAME_ROW} ({count} emptiness checks)")


# Changes big enough to own their own script. Each is idempotent on its own, so
# this stays a plain delegation -- but they must run from here too, or a local
# wiki rebuilt with apply_wiki_optimisations.py silently comes back without them.
DELEGATES = {
    "apply_leaderboards.py": "leader",
    "apply_record_sections.py": "records",
    "apply_numbers_blocks.py": "numbers",
}


def delegate(script: str, label: str) -> None:
    import subprocess
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / script)],
        capture_output=True, text=True, env={**os.environ, "MW_LOCAL_URL": BASE})
    if result.returncode != 0:
        raise SystemExit(f"{script} failed:\n{result.stdout}\n{result.stderr}")
    for line in result.stdout.strip().splitlines():
        print(f"  {label} {line}")


GAME_STATS_MODULE = "יחידה:סטטיסטיקה משחקים"
GAME_STATS_SOURCE = Path(__file__).parent / "Module_סטטיסטיקה_משחקים.lua"
SEASON_NUMBERS = "תבנית:עונת כדורגל/הצגת מספרים עונתיים/הצגה לפי מפעל"


def apply_game_stats() -> None:
    """Route the season summary's 24 game aggregates through one grouped query.

    The template כמות נתוני משחק is left alone: it accepts parameters the module
    does not implement (referee, coach, stadium, date...), and the module reports
    an error rather than silently ignoring them. Only this caller -- whose six
    calls per competition category use supported filters -- is redirected.
    """
    if get_text(GAME_STATS_MODULE) != GAME_STATS_SOURCE.read_text(encoding="utf-8"):
        api(action="edit", title=GAME_STATS_MODULE,
            text=GAME_STATS_SOURCE.read_text(encoding="utf-8"),
            contentmodel="Scribunto", summary="local perf experiment",
            token=_token["csrf"])
        print(f"  games  {GAME_STATS_MODULE}")

    text = get_text(SEASON_NUMBERS)
    if not text:
        return
    new, count = re.subn(
        r"\{\{\s*סטטיסטיקה/שליפות/מתקדמות/כמות נתוני משחק\s*(?=\|)",
        "{{#invoke:סטטיסטיקה משחקים|gameStat ", text)
    if count:
        save(SEASON_NUMBERS, new)
        print(f"  games  {SEASON_NUMBERS} ({count} calls)")


AGE_MODULE = "יחידה:גיל"
AGE_SOURCE = Path(__file__).parent / "Module_גיל.lua"
AGE_TEMPLATE = "תבנית:גיל"
AGE_WIKITEXT = (
    "<includeonly>{{#invoke:גיל|age"
    "|{{{1|}}}|{{{2|}}}|{{{3|}}}|{{{4|}}}|{{{5|}}}|{{{6|}}}}}</includeonly>"
    "<noinclude>\n"
    "גיל בשנים שלמות.\n\n"
    "פרמטרים 1-3: שנה, חודש, יום של הלידה.\n"
    "פרמטרים 4-6 (רשות): תאריך ייחוס; ללא הם - היום.\n\n"
    "החישוב ב־[[יחידה:גיל]] ולא ב־{{שנה נוכחית}} כדי שהדף לא יסומן כתלוי-זמן,\n"
    "מה שמקצר את מטמון המפענח משעה ליממה שלמה.\n"
    "</noinclude>")


def apply_age_module() -> None:
    """Move the age calculation off CURRENTYEAR/MONTH/DAY.

    Those magic words mark the page time-dependent, which caps its parser cache
    at 3600s -- for a number that changes once a year. Computed in Lua the page
    keeps the full 86400s.
    """
    if get_text(AGE_MODULE) != AGE_SOURCE.read_text(encoding="utf-8"):
        api(action="edit", title=AGE_MODULE,
            text=AGE_SOURCE.read_text(encoding="utf-8"),
            contentmodel="Scribunto", summary="local perf experiment",
            token=_token["csrf"])
        print(f"  age    {AGE_MODULE}")
    if get_text(AGE_TEMPLATE) != AGE_WIKITEXT:
        save(AGE_TEMPLATE, AGE_WIKITEXT)
        print(f"  age    {AGE_TEMPLATE}")


def apply_extension_list() -> None:
    """43 extension permutations -> 8. The miss path runs one #ifexist each."""
    text = get_text(IMAGE_FORMATS)
    if not text:
        return
    match = re.search(r"\{\{#arraydefine:פורמטים נתמכים\|([^}]*)\}\}", text)
    if not match or match.group(1) == EXTENSIONS:
        return
    new = text.replace(
        match.group(0),
        "{{#arraydefine:פורמטים נתמכים|" + EXTENSIONS + "}}<!--\n"
        "  רשימת הסיומות שנבדקות כאשר הקובץ לא נמצא בשם שנשלח.\n"
        "  רק אותיות קטנות או רק גדולות - צירופים מעורבים (jPg) לא קיימים בפועל,\n"
        "  וכל סיומת נוספת כאן עולה קריאת #קיים נוספת לכל תמונה חסרה.\n"
        "-->")
    save(IMAGE_FORMATS, new)
    print(f"  exts   {IMAGE_FORMATS} ({len(match.group(1).split(','))} -> "
          f"{len(EXTENSIONS.split(','))})")


def apply_all(token: str) -> None:
    save(MODULE_TITLE, MODULE_SOURCE.read_text(encoding="utf-8"), token, keep_backup=False)
    print(f"module: {MODULE_TITLE}")

    for title, path in CONVERSION_MODULES.items():
        if get_text(title) != path.read_text(encoding="utf-8"):
            api(action="edit", title=title, text=path.read_text(encoding="utf-8"),
                contentmodel="Scribunto", summary="local perf experiment",
                token=_token["csrf"])
            print(f"  alias  {title}")

    for title, text in SHIMS.items():
        # The dispatcher's fallback branch must exist before the dispatcher does,
        # or the pages that need it render a red link instead of a number.
        if title in FALLBACK_ARGS:
            original = backup_path(title)
            full = title + "/שליפה מלאה"
            if original.exists() and get_text(full) is None:
                api(action="edit", title=full,
                    text=original.read_text(encoding="utf-8"),
                    summary="local perf experiment: preserve full query",
                    token=_token["csrf"])
                print(f"  preserved  {full}")
        if get_text(title) != text:
            save(title, text, token)
            print(f"  shim  {title}")

    if get_text(DISPLAY) != DISPLAY_WIKITEXT:
        save(DISPLAY, DISPLAY_WIKITEXT)
        print(f"  column {DISPLAY}")

    for script, label in DELEGATES.items():
        delegate(script, label)
    apply_cheap_category_check()
    apply_age_module()
    apply_game_stats()
    apply_extension_list()

    changed = 0
    # Namespace 14 (Category) matters too: portals transclude category pages,
    # and a #dpl there caps the transcluding page just the same.
    for title in all_pages(10) + all_pages(0) + all_pages(14):
        text = get_text(title)
        if not text or "#dpl:" not in text:
            continue
        new, added = add_cacheperiod(text)
        if added:
            save(title, new)
            changed += added
            print(f"  dpl +{added}  {title}")
    print(f"cacheperiod added to {changed} #dpl call sites")


def revert(token: str) -> None:
    for path in sorted(BACKUP.glob("*.wiki")):
        if path.name == "display_column.wiki":
            title = DISPLAY
        else:
            title = path.stem.replace("__", "/").replace("_", ":", 1)
        edit(title, path.read_text(encoding="utf-8"), "revert local perf experiment")
        print(f"  reverted {title}")


def status() -> None:
    for title in [MODULE_TITLE, *SHIMS, DISPLAY]:
        text = get_text(title)
        mark = "MISSING" if text is None else (
            "optimised" if "#invoke:סטטיסטיקה שחקן" in (text or "") or title == MODULE_TITLE
            else "original")
        print(f"  {mark:10s} {title}")


def main() -> None:
    if "--status" in sys.argv:
        status()
        return
    _token["csrf"] = login()
    if "--revert" in sys.argv:
        revert(_token["csrf"])
    else:
        apply_all(_token["csrf"])


if __name__ == "__main__":
    main()
