"""Parse cost of a page on production, from its own limit report.

Fetching a page measures the parser cache, not the parser: production serves a
cached parse in a tenth of a second no matter what it cost to build. Editing a
template invalidates that cache, so a naive before/after of page load times
reports a large regression that is purely the cold parse.

This purges the page first and reads CPU time out of the structured limit
report, which is the number the work is actually trying to move.

Usage:  measure_parse_cost.py <pages file> <out.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "infra/perf")
from wiki_api import WikiApi  # noqa: E402

PROD = "https://www.maccabipedia.co.il"
WANTED = {
    "limitreport-cputime": "cpu",
    "limitreport-walltime": "wall",
    "limitreport-ppvisitednodes": "nodes",
    "limitreport-expensivefunctioncount": "expensive",
}


def measure(api: WikiApi, title: str) -> dict | None:
    api.post(action="purge", titles=title)
    try:
        payload = api.get(action="parse", page=title,
                          prop="limitreportdata", formatversion=2)["parse"]
    except Exception as error:
        print(f"  skip {title}: {error}")
        return None
    out = {}
    for entry in payload["limitreportdata"]:
        name = WANTED.get(entry["name"])
        if name:
            out[name] = float(entry["0"])
    return out


def main() -> None:
    pages = [line.strip() for line in
             Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
             if line.strip()]
    out = Path(sys.argv[2])
    result = {}
    for title in pages:
        found = measure(WikiApi(PROD, pace_seconds=1.0), title)
        if found:
            result[title] = found
            print(f"  {title[:34]:36s} cpu {found.get('cpu', 0):6.2f}s  "
                  f"nodes {int(found.get('nodes', 0)):7,d}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    if result:
        mean = sum(r.get("cpu", 0) for r in result.values()) / len(result)
        print(f"\nmean CPU {mean:.2f}s over {len(result)} pages -> {out}")


if __name__ == "__main__":
    main()
