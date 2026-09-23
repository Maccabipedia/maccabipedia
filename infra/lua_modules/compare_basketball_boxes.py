"""Production gate for the basketball leaderboard boxes: the <shtml> strip becomes a
<tabber>, so the MARKUP changes by design and a byte comparison would say nothing.

What must not change is what the box SHOWS: the four tabs in order, each with the same
players, the same records and the same "more" link. This renders a page twice - once as
it is live, once with one box template replaced by its one-invoke candidate - reads the
rows out of both, and compares those.

Reading the rows: both markups put every row in `atom-records-list-player-row`, and both
head each panel with `<div class="tab-header">`, so the panels split on the headings and
the rows are read inside them. A tie is sorted by name on both sides, as the tab gate
does: MySQL returns tied players in arbitrary order and the module orders them by name.

    uv run python infra/lua_modules/compare_basketball_boxes.py .claude/tmp/bb_box_pages.txt
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, 'infra/lua_modules')
sys.path.insert(0, 'infra/season_pages')
from compare_module_swap import render  # noqa: E402
from compare_stadium_leaderboards import page_text  # noqa: E402

MODULE = 'Module:BasketballStatsBlock'
CANDIDATES = Path('.claude/tmp/bb_box_candidates')
PANEL = re.compile(r'<div class="tab-header">(.*?)</div>')
ROW = re.compile(r'<div class="atom-records-list-player-row">.*?<span class="player-name">\s*'
                 r'(.*?)</span>.*?<span class="record">([^<]*)</span>', re.S)
# The "more" link: its query string is Cargo's own text on neither side here (both sides
# are the module once the template is switched), but the OLD side builds it from the live
# template's SQL, so only its presence and text are compared.
MORE = re.compile(r'>עוד\.\.\.<|\sעוד\.\.\.\]')
NAME = re.compile(r'<[^>]+>')


def panels(html: str) -> list[tuple[str, list[tuple[str, str]], int]]:
    """Each panel of every box on the page: its heading, its rows, its link count."""
    out = []
    marks = list(PANEL.finditer(html))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(html)
        body = html[mark.end():end]
        rows = [(NAME.sub('', name).strip(), record.strip()) for name, record in ROW.findall(body)]
        # A tie reads the same once both sides are sorted by name; a missing or extra
        # player, or another number, still differs.
        ordered, run = [], []
        for row in rows + [None]:
            if run and (row is None or row[1] != run[0][1]):
                ordered.extend(sorted(run))
                run = []
            if row is not None:
                run.append(row)
        out.append((mark.group(1), ordered, len(MORE.findall(body))))
    return out


def main() -> int:
    pages = [line.strip() for line in Path(sys.argv[1]).read_text(encoding='utf-8').split('\n')
             if line.strip() and not line.startswith('#')]
    words = [path.stem for path in sorted(CANDIDATES.glob('*.wiki'))]
    # A gate that cannot fail proves nothing: --selftest points every candidate at the
    # APPEARANCES box, whatever box template it replaces, so every box but that one must
    # be reported as differing. A clean "identical" here means the gate is blind.
    selftest = '--selftest' in sys.argv
    failed, used = 0, 0
    for title in pages:
        text = page_text(title)
        old, old_wall, _ = render(title, text, None)
        before = panels(old)
        for word in words:
            # A page shows 4, 6 or 8 of the boxes (the portal and the player
            # categories show four, a season page all eight). Replacing a template
            # the page never transcludes changes nothing, which would read as a
            # pass; such a box is skipped and said so instead.
            if f'<div class="title">שיאני {word}</div>' not in old:
                print(f'  {title} / {word}: not on this page')
                continue
            template = f'תבנית:כדורסל/סטטיסטיקה/שיאני {word}'
            body = (CANDIDATES / f'{word}.wiki').read_text(encoding='utf-8')
            if selftest:
                body = body.replace(f'|תיבה={word}|', '|תיבה=הופעות|')
            override = {'templatesandboxtitle': template,
                        'templatesandboxtext': body,
                        'templatesandboxcontentmodel': 'wikitext'}
            new, new_wall, templates = render(title, text, override)
            # NOT "does the page invoke the module": the LIVE templates already do,
            # through leaderboardTab, so that check passes whether or not the override
            # was applied. The converted box is the only thing on these pages that
            # emits `tabber-converted`, so one more of those is the candidate running.
            invoked = new.count('tabber-converted') == old.count('tabber-converted') + 1
            used += invoked
            after = panels(new)
            verdict = 'identical' if before == after else 'DIFFERS'
            if verdict == 'DIFFERS':
                for index, (was, now) in enumerate(zip(before, after)):
                    if was != now:
                        print(f'      panel {index} {was[0]!r}: OLD {was[1][:3]} more={was[2]}')
                        print(f'                    {now[0]!r}: NEW {now[1][:3]} more={now[2]}')
                        break
                if len(before) != len(after):
                    print(f'      {len(before)} panels -> {len(after)}')
                failed += 1
            if not invoked:
                failed += 1
            print(f'  {title} / {word}: {verdict}'
                  f'{"" if invoked else " (the candidate did NOT render)"} '
                  f'({old_wall:.2f}s -> {new_wall:.2f}s)', flush=True)
    print(f'{failed} box(es) differ or did not render, {used} candidate(s) rendered')
    return 1 if failed or not used else 0


if __name__ == '__main__':
    sys.exit(main())
