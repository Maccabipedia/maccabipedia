"""Production gate for the basketball leaderboards: whole pages, live template vs the
candidate (its #cargo_query replaced by {{#invoke:BasketballStatsBlock|leaderboardTab|…}}),
byte for byte - with two things normalised, both documented in .claude/lua_modules.md:

  * the "עוד..." link's href: Cargo built it from the template's raw SQL text (newlines and
    all), the module builds the same ranking from its own query. The link text and its place
    are compared; the query string is not.
  * tied players: the old template shows a tie in whatever order MySQL returns it (it differs
    between two renders of the same page), the module by name. A run of tied rows is sorted
    by name on both sides before comparing; a missing or extra player, or another number,
    still differs. This is the departure football's conversion also made.
  * a mismatch is rendered a second time both ways: the old template orders tied players
    however MySQL returns them, so two renders of the SAME page can differ.

The candidate is rendered through TemplateSandbox (nothing saved); the modules it needs must
be published. NEW must list Module:BasketballStatsBlock among its templates, so an ignored
override cannot pass. Prints old -> new walltime per page.

    uv run python infra/lua_modules/compare_basketball_tabs.py .claude/tmp/bb_sample_pages.txt
    uv run python infra/lua_modules/compare_basketball_tabs.py --candidate-only   (prints the candidate)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, 'infra/lua_modules')
sys.path.insert(0, 'infra/season_pages')
from compare_module_swap import render  # noqa: E402
from compare_stadium_leaderboards import page_text  # noqa: E402

TEMPLATE = 'תבנית:כדורסל/סטטיסטיקה/שיאנים לפי אירוע'
MODULE = 'Module:BasketballStatsBlock'
INVOKE = ('{{#invoke:BasketballStatsBlock|leaderboardTab|בלוק=leaderboards|תיבה={{{אירוע|}}}'
          '|קטגוריית מפעל={{#תנאי: {{{קטגוריית מפעל|}}} |{{{קטגוריית מפעל}}} |ברירת מחדל}}'
          '|כמות={{{כמות|10}}}|עונה={{{עונה|}}}|שחקנים={{{שחקנים|}}}|מפעלים={{{מפעלים|}}}'
          '|יריבות={{{יריבות|}}}|מגרשים={{{מגרשים|}}}|תוצאה={{{תוצאה|}}}|שופט ראשי={{{שופט ראשי|}}}'
          '|עוזר שופט={{{עוזר שופט|}}}|האם עבור יריבה={{{האם עבור יריבה|}}}}}')
VIEWDATA_HREF = re.compile(r'href="[^"]*ViewData[^"]*"')
# One leaderboard row as the row template prints it: the player (a link, or plain text for
# a player with no page) and the record.
# The row's tail is `</div>\n</div>` and a newline follows every row but the last of an
# uncut tab (the parser trims it), so the newline is NOT part of the match: a pattern that
# required it ran past that last row into the next tab and displaced it.
PLAYER_ROW = re.compile(r'<div class="atom-records-list-player-row"><span class="player-name">\n(.*?)</span>'
                        r'<div class="atom-recors-list-player-info"><span class="record">([^<]*)</span>'
                        r'.*?</div>\n</div>', re.S)


def tie_sorted(html: str) -> str:
    """The page with every run of tied rows (same record, adjacent) sorted by name.

    MySQL returns tied players in whatever order it likes - it differs between two renders
    of the same page - and the module orders a tie by name. A tie sorted both ways reads
    the same, so the comparison is on that; a player missing, extra, or with another
    number still differs.
    """
    out, position, run = [], 0, []

    def flush(boundary=False, cut=False):
        # A tie that runs into the END of a tab is cut by the limit: MySQL fills the last
        # places with arbitrary members of it, the module with the first by name. Same
        # record, same count, different names - so the names are masked there and only
        # there. A cut tab (an "עוד" link follows) may show ONE member of such a tie, so
        # its last row counts as a tie too.
        # Every chunk but possibly the last carries the newline that followed it; the
        # rows are sorted without their newlines and the layout re-applied, so which
        # row came last in the original does not leak into the comparison.
        trailing = sum(1 for _, chunk in run if chunk.endswith('\n'))
        sorted_rows = []
        for _, chunk in sorted(run, key=lambda entry: entry[0]):
            chunk = chunk.rstrip('\n')
            if boundary and (len(run) > 1 or cut):
                chunk = re.sub(r'<span class="player-name">\n.*?</span>', '<span class="player-name">TIE</span>',
                               chunk, count=1, flags=re.S)
            sorted_rows.append(chunk)
        if sorted_rows:
            out.append('\n'.join(sorted_rows) + ('\n' if trailing == len(run) else ''))
        run.clear()

    last_record = None
    for match in PLAYER_ROW.finditer(html):
        between = html[position:match.start()]
        if between == '\n' and run:
            # The newline between two rows of one tab: part of the run, so the rows
            # can still be sorted as one tie. Sorting keeps every chunk's own newline.
            run[-1] = (run[-1][0], run[-1][1] + between)
        elif between:
            flush(boundary=True, cut=between.lstrip().startswith(('<p><a', '<a ')))
            out.append(between)
            last_record = None
        name, record = match.group(1), match.group(2)
        if run and record != last_record:
            flush()
        run.append((name, match.group(0)))
        last_record = record
        position = match.end()
    flush(boundary=True, cut=html[position:].lstrip().startswith(('<p><a', '<a ')))
    out.append(html[position:])
    return ''.join(out)


def candidate_of(body: str) -> str:
    """The template with its #cargo_query (and only that) replaced by the invoke."""
    start = body.index('{{#cargo_query:')
    depth, index = 0, start
    while index < len(body):
        if body.startswith('{{', index):
            depth += 1
            index += 2
        elif body.startswith('}}', index):
            depth -= 1
            index += 2
            if depth == 0:
                break
        else:
            index += 1
    assert depth == 0, 'unbalanced braces in the template'
    return body[:start] + INVOKE + body[index:]


def normalised(html: str) -> str:
    return tie_sorted(VIEWDATA_HREF.sub('href="VIEWDATA"', html))


def option(name: str) -> str | None:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


def main() -> int:
    # Another template through the same gate: --template "תבנית:…" --candidate FILE
    # (the candidate's body ready-made). The basketball numbers template
    # (סך אירועים) goes this way; its pages hold the same leaderboards, so the same
    # normalisations apply.
    template = option('--template') or TEMPLATE
    arguments = [argument for argument in sys.argv[1:]
                 if not argument.startswith('--') and not argument.endswith('.wiki')
                 and not argument.startswith('תבנית:')]
    if '--against' in sys.argv:
        # After the switch: the LIVE template is the module's, and the saved previous
        # text (switch_template_prod.py's record) is rendered as the sandbox side. Same
        # comparison, mirrored - OLD below is then the module, NEW the old template.
        candidate = Path(option('--against')).read_text(encoding='utf-8')
    elif '--candidate' in sys.argv:
        candidate = Path(option('--candidate')).read_text(encoding='utf-8')
    elif '--template' in sys.argv:
        # Another template's candidate is never derived: candidate_of() knows only the
        # leaderboard template's body, so the leaderboard candidate would be rendered
        # under the other template's title and the gate would compare the wrong thing.
        print('--template needs --candidate FILE (or --against FILE)')
        return 2
    else:
        candidate = candidate_of(page_text(TEMPLATE))
        if '--candidate-only' in sys.argv:
            print(candidate)
            return 0
        Path('.claude/tmp/bb_inner_candidate.wiki').write_text(candidate, encoding='utf-8')
    override = {'templatesandboxtitle': template, 'templatesandboxtext': candidate,
                'templatesandboxcontentmodel': 'wikitext'}
    failed, used, unstable = 0, 0, 0
    for title in Path(arguments[0]).read_text(encoding='utf-8').split('\n'):
        title = title.strip()
        if not title or title.startswith('#'):
            continue
        try:
            text = page_text(title)
        except (KeyError, IndexError):
            print(f'  skip {title}: no such page')
            continue
        old, old_wall, live_templates = render(title, text, None)
        new, new_wall, templates = render(title, text, override)
        invokes = any(MODULE in group or MODULE.replace('Module:', 'יחידה:') in group
                      for group in (templates, live_templates))
        used += invokes
        verdict = 'identical' if normalised(old) == normalised(new) else 'DIFFERS'
        if verdict == 'DIFFERS':
            old2, _, _ = render(title, text, None)
            new2, _, _ = render(title, text, override)
            if normalised(old2) == normalised(new2):
                verdict = 'identical on rerun (tie order)'
            elif normalised(old2) != normalised(old):
                verdict = 'differs, and so do two unchanged renders'
                unstable += 1
        if verdict == 'DIFFERS':
            failed += 1
            a, b = normalised(old), normalised(new)
            index = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            print(f'    at {index}: OLD {a[index - 80:index + 120]!r}\n              NEW {b[index - 80:index + 120]!r}')
        print(f'  {title}: {verdict}{"" if invokes else " (NEW did NOT invoke the module)"}  '
              f'({old_wall:.2f}s -> {new_wall:.2f}s)', flush=True)
    # An unstable page is NOT evidence either way - it is named here so the summary
    # line cannot read as a clean pass over pages that were never really compared.
    print(f'{failed} page(s) differ, {unstable} page(s) could not be compared (unstable between '
          f'two unchanged renders), {used} page(s) invoked the module')
    return 1 if failed or not used else 0


if __name__ == '__main__':
    sys.exit(main())
