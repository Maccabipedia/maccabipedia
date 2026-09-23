"""Production gate for swapping ONE module page: do the pages that use it render byte-identically?

TemplateSandbox renders a page with one unsaved page substituted, so a module can be gated
before it is published: the live module vs the repo file, on sample pages of every family
that invokes it. Any other module the candidate requires must already be published.

    uv run python infra/lua_modules/compare_module_swap.py "Module:FootballQueries" \
        infra/lua_modules/Module_FootballQueries.lua .claude/tmp/sample_pages.txt

Some pages differ between two identical renders (leaderboard tie order on opponent pages,
the homepage's rotating boxes): a mismatch is rendered a second time, both ways, and only a
difference that survives counts. The gate refuses to pass when nothing on the list actually
invoked the module (prop=templates), so an empty or wrong list cannot pass vacuously.
"""
import sys
from pathlib import Path

sys.path.insert(0, 'infra/lua_modules')
sys.path.insert(0, 'infra/season_pages')
from season_api import call  # noqa: E402
from compare_stadium_leaderboards import page_text  # noqa: E402


def render(title: str, text: str, override: dict | None) -> tuple[str, float, set[str]]:
    params = dict({'action': 'parse', 'title': title, 'text': text, 'contentmodel': 'wikitext',
                   'prop': 'text|limitreportdata|templates', 'disablelimitreport': '1'}, **(override or {}))
    data = call('prod', params, post=True)['parse']
    report = {row['name']: row.get('0') for row in data['limitreportdata']}
    return data['text'], float(report['limitreport-walltime']), {entry['title'] for entry in data['templates']}


def main() -> int:
    module, candidate_path, pages_path = sys.argv[1:4]
    candidate = Path(candidate_path).read_text(encoding='utf-8')
    override = {'templatesandboxtitle': module, 'templatesandboxtext': candidate,
                'templatesandboxcontentmodel': 'Scribunto'}
    localised = module.replace('Module:', 'יחידה:')
    failed, used = 0, 0
    for title in Path(pages_path).read_text(encoding='utf-8').split('\n'):
        title = title.strip()
        if not title or title.startswith('#'):
            continue
        text = page_text(title)
        old, old_wall, templates = render(title, text, None)
        new, new_wall, _ = render(title, text, override)
        invokes = module in templates or localised in templates
        used += invokes
        verdict = 'identical'
        if old != new:
            old2, _, _ = render(title, text, None)
            new2, _, _ = render(title, text, override)
            if old2 != new2 or old2 != old:
                verdict = 'differs (also between two unchanged renders)' if old2 != old else 'DIFFERS'
        if verdict == 'DIFFERS':
            failed += 1
            index = next((i for i, (a, b) in enumerate(zip(old, new)) if a != b), min(len(old), len(new)))
            print(f'    at {index}: OLD {old[index - 60:index + 80]!r}\n              NEW {new[index - 60:index + 80]!r}')
        print(f'  {title}: {verdict}{"" if invokes else " (does NOT invoke the module)"}  '
              f'({old_wall:.2f}s -> {new_wall:.2f}s)', flush=True)
    print(f'{module}: {failed} page(s) differ, {used} page(s) invoked the module')
    return 1 if failed or not used else 0


if __name__ == '__main__':
    sys.exit(main())
