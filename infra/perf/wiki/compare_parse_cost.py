"""Compare two measure_parse_cost.py snapshots.

Reports wall time as well as CPU. CPU time excludes the wait on Cargo's
queries, and cutting query COUNT is the whole point of this work -- so CPU
alone can show almost no change while the page genuinely got faster, or the
reverse.

Usage:  compare_parse_cost.py <before.json> <after.json>
"""
import json
import statistics
import sys
from pathlib import Path


def main() -> None:
    before = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    after = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

    fields = ["cpu", "wall", "nodes", "expensive"]
    print(f"{'page':32s} " + " ".join(f"{name:>16s}" for name in fields))
    print("-" * 100)
    deltas: dict[str, list[float]] = {name: [] for name in fields}
    for title, was in before.items():
        now = after.get(title)
        if not now:
            continue
        cells = []
        for name in fields:
            a, b = was.get(name, 0), now.get(name, 0)
            if a:
                deltas[name].append((b - a) / a)
            fmt = "{:,.0f}" if name in ("nodes", "expensive") else "{:.2f}"
            cells.append(f"{fmt.format(a)}->{fmt.format(b)}".rjust(16))
        print(f"{title[:30]:32s} " + " ".join(cells))

    print()
    for name in fields:
        if deltas[name]:
            median = statistics.median(deltas[name]) * 100
            print(f"  {name:10s} median {median:+.0f}%  "
                  f"({len(deltas[name])} pages)")


if __name__ == "__main__":
    main()
