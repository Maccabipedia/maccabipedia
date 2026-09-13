"""What does the FOURTH identical query on a page actually cost?

A filtered page runs Module:שיאנים four times -- once per leaderboard -- and all
four issue the same Cargo query, because the query groups by event type and the
filtering happens in Lua. Merging them into one invoke is possible but awkward:
each leaderboard sits behind its own signed <shtml> tab strip, which Lua cannot
produce.

So the question is whether the duplication is worth that complexity. This renders
1, 2 and 4 invokes of the same section against a real page and reads wall and CPU
time out of the limit report, so the marginal cost of an extra identical query
falls out of the slope. If MySQL's query cache makes repeats nearly free, the
merge buys little; if they cost full price, it buys three quarters of them.

Read-only. Usage:  measure_invoke_scaling.py [page] [filter-arg]
"""
import statistics
import sys

sys.path.insert(0, "infra/perf")
sys.path.insert(0, "infra/perf/wiki")
from wiki_api import WikiApi  # noqa: E402

PROD = "https://www.maccabipedia.co.il"
COUNTS = [0, 1, 2, 4]
REPEATS = 3

SECTION = ("{{#invoke:שיאנים|section|כינוי=כובשים שונים"
           "|מספר אירוע=3 |ללא תת אירוע=33 |הגבלה=10")


def cost(api: WikiApi, title: str, wikitext: str) -> dict:
    payload = api.post(action="parse", text=wikitext, title=title,
                       contentmodel="wikitext", prop="limitreportdata",
                       formatversion=2)["parse"]
    out = {}
    for entry in payload["limitreportdata"]:
        if entry["name"] == "limitreport-cputime":
            out["cpu"] = float(entry["0"])
        elif entry["name"] == "limitreport-walltime":
            out["wall"] = float(entry["0"])
    return out


def main() -> None:
    title = sys.argv[1] if len(sys.argv) > 1 else "אצטדיון בלומפילד"
    filter_arg = sys.argv[2] if len(sys.argv) > 2 else "|אצטדיונים=אצטדיון בלומפילד"
    api = WikiApi(PROD, pace_seconds=1.0)

    print(f"{title}   {filter_arg}\n")
    print(f"{'invokes':>8s} {'wall':>8s} {'cpu':>8s} {'wall/invoke':>13s}")
    print("-" * 44)

    base = None
    for count in COUNTS:
        body = "\n".join([SECTION + filter_arg + "}}"] * count) if count else "x"
        runs = [cost(api, title, body) for _ in range(REPEATS)]
        wall = statistics.median(r.get("wall", 0) for r in runs)
        cpu = statistics.median(r.get("cpu", 0) for r in runs)
        if base is None:
            base = wall
        each = f"{(wall - base) / count:.3f}s" if count else "-"
        print(f"{count:>8d} {wall:>7.2f}s {cpu:>7.2f}s {each:>13s}")

    print("\nIf wall/invoke stays flat, every repeat costs full price and merging\n"
          "the four saves three of them. If it falls away, the repeats are\n"
          "already nearly free and the merge is not worth the shtml problem.")


if __name__ == "__main__":
    main()
