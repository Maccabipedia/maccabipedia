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
    uv run python infra/lua_modules/compare_basketball_boxes.py PAGES --against   (after the switch)
    uv run python infra/lua_modules/compare_basketball_boxes.py PAGES --selftest  (prove it bites)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, 'infra/lua_modules')
sys.path.insert(0, 'infra/season_pages')
from compare_module_swap import render  # noqa: E402
from compare_stadium_leaderboards import page_text  # noqa: E402

MODULE = 'Module:BasketballStatsBlock'
CANDIDATES = Path('infra/lua_modules/wiki_templates/basketball_boxes')
PANEL = re.compile(r'<div class="tab-header">(.*?)</div>')
ROW = re.compile(r'<div class="atom-records-list-player-row">.*?<span class="player-name">\s*'
                 r'(.*?)</span>.*?<span class="record">([^<]*)</span>', re.S)
# The "more" link: its query string is Cargo's own text on neither side here (both sides
# are the module once the template is switched), but the OLD side builds it from the live
# template's SQL, so only its presence and text are compared.
MORE = re.compile(r'>עוד\.\.\.<|\sעוד\.\.\.\]')
NAME = re.compile(r'<[^>]+>')
BOX = re.compile(r'<div class="records-list-tabs-container"[^>]*>'
                 r'(.*?)(?=<div class="records-list-tabs-container"|\Z)', re.S)
TITLE = re.compile(r'<div class="title">(.*?)</div>', re.S)
# The tab's name in either markup: the old strip's icon tooltip, or the tabber's link.
TAB_NAME = re.compile(r'<li title="([^"]*)"|class="tabber__tab"[^>]*>([^<]*)<')


def panels(body: str) -> list[tuple[str, list[tuple[str, str]], int, str]]:
    """Each panel of one box: its heading, its rows, its link count, and - when it has
    no rows - the sentence printed instead, which the module now supplies (`emptyText`)
    and the old template supplied through Cargo's `default`."""
    out = []
    marks = list(PANEL.finditer(body))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(body)
        panel = body[mark.end():end]
        rows = [(NAME.sub('', name).strip(), record.strip()) for name, record in ROW.findall(panel)]
        # A tie reads the same once both sides are sorted by name; a missing or extra
        # player, or another number, still differs.
        ordered, run = [], []
        for row in rows + [None]:
            if run and (row is None or row[1] != run[0][1]):
                ordered.extend(sorted(run))
                run = []
            if row is not None:
                run.append(row)
        empty = '' if ordered else ' '.join(NAME.sub(' ', panel).split())
        out.append((mark.group(1), ordered, len(MORE.findall(panel)), empty))
    return out


def boxes(html: str) -> list[tuple[str, list[str], list]]:
    """Every leaderboard box on the page: its TITLE, its TAB NAMES and its panels.

    The title and the tab names are compared because the conversion took them over:
    they used to be literal text in each template, and the module now builds them from
    `box.title` and `tabStrip[].label`. A gate that compared only the rows would call a
    box with the wrong title identical - and that is the kind of mistake a data page of
    eight near-identical entries invites.

    The two markups name their tabs differently: the old strip put the name in the
    `<li title="…">` of the icon, the tabber puts it in the tab link's text. Both are
    read here, so the sequences can be compared across the conversion.
    """
    out = []
    for match in BOX.finditer(html):
        body = match.group(1)
        title = TITLE.search(body)
        names = [old or new for old, new in TAB_NAME.findall(body)]
        out.append((title.group(1).strip() if title else '', names, panels(body)))
    return out


def previous_texts() -> dict[str, str]:
    """The text each box template had before the switch, from the records
    `switch_template_prod.py` writes. Keyed by the box word in the title."""
    out = {}
    for record in sorted(Path('.claude/tmp/template_switches').glob('*.json')):
        saved = json.loads(record.read_text(encoding='utf-8'))
        match = re.fullmatch(r'תבנית:כדורסל/סטטיסטיקה/שיאני (.*)', saved['title'])
        if match:
            out[match.group(1)] = saved['previous_text']
    return out


def main() -> int:
    listed = [argument for argument in sys.argv[1:] if not argument.startswith('--')]
    pages = [line.strip() for line in Path(listed[0]).read_text(encoding='utf-8').split('\n')
             if line.strip() and not line.startswith('#')]
    words = [path.stem for path in sorted(CANDIDATES.glob('*.wiki'))]
    # A gate that cannot fail proves nothing: --selftest points every candidate at the
    # APPEARANCES box, whatever box template it replaces, so every box but that one must
    # be reported as differing. A clean "identical" here means the gate is blind.
    selftest = '--selftest' in sys.argv
    # After the switch the LIVE template IS the candidate, so rendering the candidate
    # in the sandbox compares a thing with itself. --against renders the template each
    # box replaced (switch_template_prod.py saved its text) as the sandbox side: the
    # same comparison, mirrored, and the only one that still means anything once the
    # conversion has shipped.
    against = '--against' in sys.argv
    previous = previous_texts() if against else {}
    failed, used = 0, 0
    for title in pages:
        text = page_text(title)
        old, old_wall, _ = render(title, text, None)
        before = boxes(old)
        for word in words:
            # A page shows 4, 6 or 8 of the boxes (the portal and the player
            # categories show four, a season page all eight). Replacing a template
            # the page never transcludes changes nothing, which would read as a
            # pass; such a box is skipped and said so instead.
            if f'<div class="title">שיאני {word}</div>' not in old:
                print(f'  {title} / {word}: not on this page')
                continue
            template = f'תבנית:כדורסל/סטטיסטיקה/שיאני {word}'
            if against:
                if word not in previous:
                    print(f'  {title} / {word}: no saved previous text')
                    failed += 1
                    continue
                body = previous[word]
            else:
                body = (CANDIDATES / f'{word}.wiki').read_text(encoding='utf-8')
            if selftest:
                # The two sides name the box differently: the candidate through the
                # invoke's תיבה, the old template through the query template's אירוע.
                # Replacing only one of them would make --selftest a no-op there, and
                # a self-test that changes nothing is worse than none.
                patched = (body.replace(f'|תיבה={word}|', '|תיבה=הופעות|')
                           .replace(f'|אירוע={word} ', '|אירוע=הופעות '))
                if patched == body:
                    print(f'  {title} / {word}: --selftest changed nothing - it cannot bite here')
                    failed += 1
                    continue
                body = patched
            override = {'templatesandboxtitle': template,
                        'templatesandboxtext': body,
                        'templatesandboxcontentmodel': 'wikitext'}
            new, new_wall, templates = render(title, text, override)
            # NOT "does the page invoke the module": the templates invoke it either
            # way, so that check passes whether or not the override was applied. The
            # converted box is the only thing on these pages that emits
            # `tabber-converted`, so the count moves by exactly one - up when the
            # candidate replaces an old strip, down when --against puts an old strip
            # back in place of a live converted box.
            step = -1 if against else 1
            invoked = new.count('tabber-converted') == old.count('tabber-converted') + step
            used += invoked
            after = boxes(new)
            verdict = 'identical' if before == after else 'DIFFERS'
            if verdict == 'DIFFERS':
                for index, (was, now) in enumerate(zip(before, after)):
                    if was != now:
                        print(f'      box {index}: OLD title={was[0]!r} tabs={was[1]}')
                        print(f'                 NEW title={now[0]!r} tabs={now[1]}')
                        for was_panel, now_panel in zip(was[2], now[2]):
                            if was_panel != now_panel:
                                print(f'        OLD {was_panel[0]!r} {was_panel[1][:3]} '
                                      f'more={was_panel[2]} empty={was_panel[3][:60]!r}')
                                print(f'        NEW {now_panel[0]!r} {now_panel[1][:3]} '
                                      f'more={now_panel[2]} empty={now_panel[3][:60]!r}')
                                break
                        break
                if len(before) != len(after):
                    print(f'      {len(before)} boxes -> {len(after)}')
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
