"""Collapse the "general numbers" block from 32 queries to 2.

Opponent pages and season pages show the same block: four competition tabs,
nine rows each (games, wins, draws, losses, goals, conceded, clean sheets,
yellows, reds). Both built it the same way -- six calls to
סטטיסטיקה/שליפות/מתקדמות/כמות נתוני משחק and two to כמות אירועי שחקן, per tab.

Module:סטטיסטיקה משחקים|numbersBlock renders all four tabs from one games query
and one cards query.

This also fixes a copy-paste bug present in both templates: the fourth tab's
content div carried id="tab3-content", the same id as the third, so the CSS
rule for #tab4-content matched nothing and the international tab rendered
blank. The module emits tab4-content.

The signed <shtml> tab header is copied through byte-for-byte -- its hash
covers its exact content.
"""
import os
import re
from pathlib import Path

import requests

BASE = os.environ.get("MW_LOCAL_URL", "http://localhost:8080")
USER, PASSWORD = "maccabi", "maccabi2026"
WIKI = Path(__file__).parent

# Each parent template, and the filter it hands the module.
PARENTS = {
    "תבנית:יריבת כדורגל/הצגת מספרים כלליים":
        "|יריבות={{{יריבות לשליפה|}}}",
    "תבנית:עונת כדורגל/הצגת מספרים עונתיים":
        "|עונה={{{עונה|}}}",
}

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


def build(header: str, filter_arg: str) -> str:
    return (
        "<includeonly><!--\n\n"
        "ארבע הלשוניות מגיעות מ[[יחידה:סטטיסטיקה משחקים]] בשתי שליפות - אחת\n"
        "למשחקים ואחת לכרטיסים. קודם לכן כל לשונית הריצה שמונה שליפות נפרדות\n"
        "(ניצחונות, תיקו, הפסדים, שערים, ספיגות, שער נקי, צהובים, אדומים),\n"
        "כלומר 32 לגוש.\n\n"
        f"-->{header}<!--\n\n"
        '--><div class="content" id="res-tabs-content">\n'
        "{{#invoke:סטטיסטיקה משחקים|numbersBlock" + filter_arg + "}}\n"
        "</div></div><!--\n\n"
        "--></includeonly>"
    )


def main() -> None:
    token = api(action="query", meta="tokens",
                type="login")["query"]["tokens"]["logintoken"]
    api(action="login", lgname=USER, lgpassword=PASSWORD, lgtoken=token)
    csrf = api(action="query", meta="tokens",
               type="csrf")["query"]["tokens"]["csrftoken"]

    api(action="edit", title="יחידה:סטטיסטיקה משחקים", contentmodel="Scribunto",
        text=(WIKI / "Module_סטטיסטיקה_משחקים.lua").read_text(encoding="utf-8"),
        summary="local perf experiment: whole numbers block per query",
        token=csrf)
    print("יחידה:סטטיסטיקה משחקים saved")

    for title, filter_arg in PARENTS.items():
        current = get_text(title)
        if current is None:
            print(f"  SKIP (missing) {title}")
            continue

        backup = WIKI / "backups" / (
            title.replace("/", "__").replace(":", "_") + ".wiki")
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_text(current, encoding="utf-8")

        header = HEADER.search(backup.read_text(encoding="utf-8"))
        if not header:
            raise SystemExit(f"no signed <shtml> tab header found in {title}")

        wanted = build(header.group(0), filter_arg)
        if current == wanted:
            print(f"  up to date  {title}")
            continue
        api(action="edit", title=title, text=wanted,
            summary="local perf experiment: one numbers block per query",
            token=csrf)
        print(f"  applied  {title}")


if __name__ == "__main__":
    main()
