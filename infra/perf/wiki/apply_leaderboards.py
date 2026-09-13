"""Route simple leaderboard calls to the module, keep the full query for the rest.

The leaderboard template is used by opponent, stadium and season pages with
filters the module does not implement (opponent, stadium, referee, coach,
season, result). Replacing it outright would silently ignore them, so the
template becomes a dispatcher: the module for the common case, the original
query -- preserved under a new name -- for anything else.
"""
import os
import re
from pathlib import Path

import requests

BASE = os.environ.get("MW_LOCAL_URL", "http://localhost:8080")
USER, PASSWORD = "maccabi", "maccabi2026"
WIKI = Path(__file__).parent

LEADERS = "תבנית:סטטיסטיקה/שליפות/מתקדמות/שיאני כמות אירועי שחקן/עיצוב חדש"
FULL = "תבנית:סטטיסטיקה/שליפות/מתקדמות/שיאני כמות אירועי שחקן/שליפה מלאה"

# Any of these being set means the module cannot answer the question.
FALLBACK_PARAMS = [
    "מפעל מקורי", "מפעל נוכחי", "יריבה", "יריבות", "אצטדיון", "אצטדיונים",
    "מפעלים", "שופטים", "עוזר שופט", "מאמן", "שחקן", "שחקנים", "עונה",
    "תוצאה", "תוצאה מכבי", "תוצאה יריבה", "שיאנים", "תצוגת יחיד", "הצגה",
]

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
    return page["revisions"][0]["slots"]["main"]["content"] if "revisions" in page else None


def main() -> None:
    token = api(action="query", meta="tokens", type="login")["query"]["tokens"]["logintoken"]
    api(action="login", lgname=USER, lgpassword=PASSWORD, lgtoken=token)
    csrf = api(action="query", meta="tokens", type="csrf")["query"]["tokens"]["csrftoken"]

    for title, path in {
        "יחידה:שיאנים/נתונים": WIKI / "Module_שיאנים_נתונים.lua",
        "יחידה:שיאנים": WIKI / "Module_שיאנים.lua",
    }.items():
        api(action="edit", title=title, text=path.read_text(encoding="utf-8"),
            contentmodel="Scribunto", summary="local perf experiment", token=csrf)
    print("modules saved")

    current = get_text(LEADERS)
    if current is None:
        raise SystemExit(f"missing {LEADERS}")

    if "#invoke:שיאנים" not in current:
        backup = WIKI / "backups" / (LEADERS.replace("/", "__").replace(":", "_") + ".wiki")
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_text(current, encoding="utf-8")
        api(action="edit", title=FULL, text=current,
            summary="local perf experiment: preserve full query", token=csrf)
        print(f"preserved original as {FULL}")

    guard = "".join("{{{" + name + "|}}}" for name in FALLBACK_PARAMS)
    passthrough = "".join("|" + name + "={{{" + name + "|}}}"
                          for name in FALLBACK_PARAMS)
    dispatcher = (
        "<includeonly><!--\n\n"
        "מנתב: רוב טבלאות השיאנים מסננות רק לפי סוג אירוע וקטגוריית מפעל, וזה\n"
        "מה ש[[יחידה:שיאנים]] יודעת לענות - בשליפה אחת המשותפת לכל הטבלאות בדף.\n"
        "סינון לפי יריבה, אצטדיון, שופט, מאמן, עונה או תוצאה עדיין דורש את\n"
        "השליפה המלאה, ולכן היא נשמרה ב[[" + FULL + "]].\n\n"
        "-->{{#if: " + guard + "\n"
        "  |{{" + FULL.removeprefix("תבנית:") + passthrough +
        "|מספר אירוע={{{מספר אירוע|}}}|תת אירוע={{{תת אירוע|}}}"
        "|ללא תת אירוע={{{ללא תת אירוע|}}}|קטגוריית מפעל={{{קטגוריית מפעל|}}}"
        "|הגבלה={{{הגבלה|}}}|עוד תוצאות={{{עוד תוצאות|}}}}}\n"
        "  |{{#invoke:שיאנים|top|מספר אירוע={{{מספר אירוע|}}}"
        "|תת אירוע={{{תת אירוע|}}}|ללא תת אירוע={{{ללא תת אירוע|}}}"
        "|קטגוריית מפעל={{{קטגוריית מפעל|}}}|הגבלה={{{הגבלה|10}}}}}\n"
        "}}</includeonly>")

    api(action="edit", title=LEADERS, text=dispatcher,
        summary="local perf experiment: route simple leaderboards to the module",
        token=csrf)
    print(f"dispatcher installed at {LEADERS}")


if __name__ == "__main__":
    main()
