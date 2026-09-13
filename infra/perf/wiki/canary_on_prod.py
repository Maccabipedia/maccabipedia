"""Switch ONE display template on production, with a before/after value check.

This is the first change a reader sees. Scope is deliberately one template --
שיאני מוצהבים, the lowest-stakes of the four -- so that if anything is wrong it
is wrong in one section of the page and revert is a single command.

The signed <shtml> header is taken from PRODUCTION's own copy of the template,
never from backups/. Those backups came off the local wiki, which signs with a
different secret: the same markup carries hash b303… on production and 59a5…
locally. Writing the local header to production would make the tab strip render
a SecureHTML error on every page that transcludes it.

  before   snapshot the affected pages' values and render times
  apply    back up production's template, then switch it
  after    re-snapshot and diff against `before`
  revert   restore production's template from the backup taken by `apply`
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, "infra/perf")
sys.path.insert(0, "infra/perf/wiki")
from apply_record_sections import DISPLAYS, HEADER, build  # noqa: E402
from shadow_verify_on_prod import LEADERBOARDS, live_section  # noqa: E402
from wiki_api import WikiApi  # noqa: E402

PROD = "https://www.maccabipedia.co.il"
TEMPLATE = "תבנית:סטטיסטיקה/תצוגה/שחקנים/שיאני מוצהבים/עיצוב חדש"
SPEC_KEY = "שיאני מוצהבים/עיצוב חדש"
BACKUP = Path("infra/perf/wiki/backups/prod")
SNAPSHOT = Path(".claude/tmp/canary")

# The section this template renders, under either title the wiki gives it.
SECTION = next(names for names, _, _ in LEADERBOARDS if "מוצהבים" in names[0])
RECORD = re.compile(r'<span class="record">([^<]*)</span>')
TAB_HEADER = re.compile(r'<div class="tab-header">\s*(.*?)\s*</div>', re.S)


def prod_template_text(api: WikiApi) -> str:
    page = api.get(action="query", prop="revisions", rvslots="main",
                   rvprop="content", titles=TEMPLATE,
                   formatversion=2)["query"]["pages"][0]
    return page["revisions"][0]["slots"]["main"]["content"]


def snapshot(api: WikiApi, pages: list[str], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    result = {}
    for title in pages:
        started = time.monotonic()
        try:
            html = api.get(action="parse", page=title, prop="text",
                           formatversion=2)["parse"]["text"]
        except Exception as error:
            print(f"  skip {title}: {error}")
            continue
        section = live_section(html, SECTION)
        result[title] = {
            "values": RECORD.findall(section),
            "headers": TAB_HEADER.findall(section),
            "seconds": round(time.monotonic() - started, 3),
        }
        print(f"  {title[:34]:36s} {len(result[title]['values']):3d} values  "
              f"{result[title]['seconds']:5.2f}s")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\nwrote {out} ({len(result)} pages)")


def compare(before: Path, after: Path) -> int:
    old = json.loads(before.read_text(encoding="utf-8"))
    new = json.loads(after.read_text(encoding="utf-8"))
    failures = 0
    faster = []
    for title, was in old.items():
        now = new.get(title)
        if now is None:
            failures += 1
            print(f"  {title}: missing after")
            continue
        for field in ("values", "headers"):
            if was[field] != now[field]:
                failures += 1
                print(f"  {title} — {field} CHANGED")
                print(f"      before: {was[field][:6]}")
                print(f"      after:  {now[field][:6]}")
        faster.append((was["seconds"], now["seconds"]))
    if faster:
        was_total = sum(a for a, _ in faster) / len(faster)
        now_total = sum(b for _, b in faster) / len(faster)
        print(f"\nmean page render {was_total:.2f}s -> {now_total:.2f}s "
              f"({(now_total - was_total) / was_total:+.0%}) over {len(faster)} pages")
    return failures


def apply_to_prod() -> None:
    from maccabipediabot.common.wiki_login import get_site
    import pywikibot as pw

    api = WikiApi(PROD, pace_seconds=0.4)
    current = prod_template_text(api)
    if "#invoke:שיאנים|section" in current:
        raise SystemExit("already applied on production")

    header = HEADER.search(current)
    if not header:
        raise SystemExit("no <shtml> header in production's template")

    BACKUP.mkdir(parents=True, exist_ok=True)
    target = BACKUP / (TEMPLATE.replace("/", "__").replace(":", "_") + ".wiki")
    if not target.exists():
        target.write_text(current, encoding="utf-8")
        print(f"backed up production's template to {target}")

    wanted = build(header.group(0), DISPLAYS[SPEC_KEY])
    site = get_site()
    page = pw.Page(site, TEMPLATE)
    page.text = wanted
    page.save(summary="perf: render the whole records block from one query "
                      "(see infra/perf/wiki/README.md)", minor=False)
    print(f"applied to {TEMPLATE}")


def revert_prod() -> None:
    from maccabipediabot.common.wiki_login import get_site
    import pywikibot as pw

    target = BACKUP / (TEMPLATE.replace("/", "__").replace(":", "_") + ".wiki")
    if not target.exists():
        raise SystemExit(f"no backup at {target} -- nothing to revert to")
    site = get_site()
    page = pw.Page(site, TEMPLATE)
    page.text = target.read_text(encoding="utf-8")
    page.save(summary="perf: revert canary", minor=False)
    print(f"reverted {TEMPLATE}")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "before"
    if command == "apply":
        apply_to_prod()
        return
    if command == "revert":
        revert_prod()
        return

    source = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    pages = [line.strip() for line in
             source.read_text(encoding="utf-8").splitlines() if line.strip()] \
        if source else []
    api = WikiApi(PROD, pace_seconds=0.4)

    if command == "before":
        snapshot(api, pages, SNAPSHOT / "before.json")
    elif command == "after":
        snapshot(api, pages, SNAPSHOT / "after.json")
        failures = compare(SNAPSHOT / "before.json", SNAPSHOT / "after.json")
        print(f"\n{failures} pages changed" if failures
              else "\nevery value identical")
        sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
