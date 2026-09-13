"""Collapse each שיאנים display template from eight queries to one.

Every one of the four display templates (הופעות, כיבושים, בישולים, מוצהבים)
ran two queries per competition tab: one for the table, and one that re-ran the
same query with |הגבלה=2000 purely to count how many distinct players it
returned. Four tabs, so eight queries -- and a records page transcludes all
four display templates, so 32.

[[יחידה:שיאנים]]'s `section` renders a whole display template -- four tabs and
their four counts -- from a single query, taking the page's filter directly.
That is 32 -> 4 on a stadium, opponent, season or referee page, and 32 -> 1 on
an unfiltered one (those share a single query through mw.loadData).

The signed <shtml> tab header is copied through byte-for-byte: its hash covers
its exact content, so it must not be regenerated.
"""
import os
import re
from pathlib import Path

import requests

BASE = os.environ.get("MW_LOCAL_URL", "http://localhost:8080")
USER, PASSWORD = "maccabi", "maccabi2026"
WIKI = Path(__file__).parent
PREFIX = "תבנית:סטטיסטיקה/תצוגה/שחקנים/"

# The noun each template counts, and the event filter that defines it. Taken
# from the templates themselves -- see the |מספר אירוע= they pass today.
DISPLAYS = {
    "שיאני הופעות/עיצוב חדש": {
        "noun": "מופיעים שונים", "מספר אירוע": "1, 5"},
    "שיאני כיבושים/עיצוב חדש": {
        "noun": "כובשים שונים", "מספר אירוע": "3", "ללא תת אירוע": "33"},
    "שיאני בישולים/עיצוב חדש": {
        "noun": "שחקנים שונים", "מספר אירוע": "4"},
    "שיאני מוצהבים/עיצוב חדש": {
        "noun": "שחקנים שונים", "מספר אירוע": "7", "תת אירוע": "71"},
}

# The signed tab header: everything from the wrapper div through </shtml>.
HEADER = re.compile(r'<div class="slim-tabs">.*?</shtml>', re.S)

session = requests.Session()
session.headers["User-Agent"] = "MaccabipediaPerfBenchmark/1.0"


def api(**data):
    data.update(format="json", formatversion="2")
    response = session.post(f"{BASE}/api.php", data=data, timeout=900)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise SystemExit(f"API error: {payload['error'].get('info')}")
    return payload


def get_text(title):
    page = api(action="query", prop="revisions", rvslots="main",
               rvprop="content", titles=title)["query"]["pages"][0]
    if "revisions" not in page:
        return None
    return page["revisions"][0]["slots"]["main"]["content"]


def build(header: str, spec: dict) -> str:
    events = "".join(f" |{name}={value}" for name, value in spec.items()
                     if name != "noun")
    return (
        "<includeonly><!--\n\n"
        "ארבע הלשוניות והספירות שלהן מגיעות מ[[יחידה:שיאנים]] בשליפה אחת.\n"
        "קודם לכן כל לשונית הריצה שתי שליפות - אחת לטבלה ואחת שרצה שוב על\n"
        "אותם נתונים רק כדי לספור כמה שחקנים שונים יש בה - כלומר שמונה לתבנית.\n"
        "הסינון של הדף (שחקנים, אצטדיונים, יריבות, שופטים, עונה או מפעלים)\n"
        "עובר ליחידה כמו שהוא.\n\n"
        f"-->{header}<!--\n\n"
        '--><div class="content" id="res-tabs-content">'
        "{{#invoke:שיאנים|section\n"
        f" |כינוי={spec['noun']}{events}\n"
        " |הגבלה={{{כמות שחקנים|10}}}\n"
        " |עוד תוצאות={{{עוד תוצאות|עוד}}}\n"
        " |שחקנים={{{שחקנים|}}}\n"
        " |אצטדיונים={{{אצטדיונים|}}}\n"
        " |יריבות={{{יריבות לשליפה|{{{יריבות|}}}}}}\n"
        " |שופטים={{{שופטים|}}}\n"
        " |עונה={{{עונה|}}}\n"
        " |מפעלים={{{מפעלים|}}}\n"
        "}}</div>\n"
        "</div><!--\n\n"
        "--></includeonly>"
    )


def main() -> None:
    token = api(action="query", meta="tokens",
                type="login")["query"]["tokens"]["logintoken"]
    api(action="login", lgname=USER, lgpassword=PASSWORD, lgtoken=token)
    csrf = api(action="query", meta="tokens",
               type="csrf")["query"]["tokens"]["csrftoken"]

    api(action="edit", title="יחידה:שיאנים", contentmodel="Scribunto",
        text=(WIKI / "Module_שיאנים.lua").read_text(encoding="utf-8"),
        summary="local perf experiment: render a whole records block per query",
        token=csrf)
    print("יחידה:שיאנים saved")

    for name, spec in DISPLAYS.items():
        title = PREFIX + name
        current = get_text(title)
        if current is None:
            print(f"  SKIP (missing) {title}")
            continue
        backup = WIKI / "backups" / (
            title.replace("/", "__").replace(":", "_") + ".wiki")
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_text(current, encoding="utf-8")

        # The signed <shtml> header comes from the original, which after a
        # first run lives in the backup rather than on the wiki.
        source = backup.read_text(encoding="utf-8")
        header = HEADER.search(source)
        if not header:
            raise SystemExit(f"no signed <shtml> tab header found in {title}")

        wanted = build(header.group(0), spec)
        if current == wanted:
            print(f"  up to date  {title}")
            continue

        api(action="edit", title=title, text=wanted,
            summary="local perf experiment: one query per records block",
            token=csrf)
        print(f"  applied  {title}")


if __name__ == "__main__":
    main()
