"""Convert a `<shtml>` radio tab strip into `<tabber>` wikitext.

    uv run python infra/tabs/convert_strip.py --file <wikitext file>
    uv run python infra/tabs/convert_strip.py --local '<page title>'

Prints the converted wikitext. Writes nothing.

See `.claude/shtml_free_tabs_design.md`. TabberNeue is already installed,
configured and used by 15 templates, so this converts a strip to the mechanism
already in use rather than inventing one.

The conversion is refused unless the strip has the exact shape this
understands. A partial conversion would render a page that looks nearly right,
which is the failure mode worth the most care here:

    <div class="slim-tabs"><shtml hash="…">
      <input type="radio" id="…" name="…tab-control…" [checked]> × N
      <ul><li title="TOOLTIP"><label for="…" …>LABEL</label></li> × N</ul>
    </shtml>
    <div class="content" [id="res-tabs-content"]>
      <div id="tabN-content">BODY</div> × N
    </div>

Two details that are easy to lose and that this keeps:

  * the tooltip on `<li title>` and the heading inside the panel are NOT always
    the same string - `גביע` versus `גביע המדינה` in the basketball records
    strips - so the tooltip becomes the tab name and the panel keeps its own
    heading untouched;
  * labels are icon-only (`<i class="fas fa-trophy">`), so the tab name has to
    carry both the icon and an accessible name.
"""
import argparse
import re
import subprocess
import sys

COMPOSE = 'infra/local-wiki/docker-compose.yml'

STRIP = re.compile(
    r'<div class="slim-tabs"[^>]*>\s*<shtml\b[^>]*>(?P<strip>.*?)</shtml>',
    re.DOTALL)
RADIO = re.compile(r'<input\s+type="radio"[^>]*>')
ITEM = re.compile(
    r'<li\b(?P<attributes>[^>]*)>\s*<label\b[^>]*>(?P<label>.*?)</label>\s*</li>',
    re.DOTALL)
TITLE = re.compile(r'title="(?P<title>[^"]*)"')
CONTENT = re.compile(
    r'<div class="content"(?P<attributes>[^>]*)>(?P<panels>.*)$', re.DOTALL)
PANEL = re.compile(
    r'<div id="tab(?P<index>\d+)-content">(?P<body>.*?)</div><!--', re.DOTALL)


class Refused(Exception):
    """The strip is not the shape this understands."""


def local_text(title: str) -> str:
    result = subprocess.run(
        ['docker', 'compose', '-f', COMPOSE, 'exec', '-T', 'mediawiki',
         'php', 'maintenance/getText.php', title],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'{title} is not on the local wiki')
    return result.stdout


def parse_strip(text: str) -> tuple[list[dict], str]:
    """The tabs, and the `content` div's attributes."""
    strip = STRIP.search(text)
    if not strip:
        raise Refused('no <div class="slim-tabs"><shtml …> strip found')

    radios = RADIO.findall(strip.group('strip'))
    items = list(ITEM.finditer(strip.group('strip')))
    if not items:
        raise Refused('the strip has no <li><label> items')
    if len(radios) != len(items):
        raise Refused(
            f'{len(radios)} radio input(s) but {len(items)} label(s) - '
            'refusing to guess which drives which')

    content = CONTENT.search(text[strip.end():])
    if not content:
        raise Refused('no <div class="content"> after the strip')

    panels = list(PANEL.finditer(content.group('panels')))
    if len(panels) != len(items):
        raise Refused(
            f'{len(items)} tab(s) but {len(panels)} panel(s) - a strip whose '
            'panels do not match its labels must be converted by hand')

    seen = [int(panel.group('index')) for panel in panels]
    if seen != sorted(seen) or seen != list(range(1, len(seen) + 1)):
        raise Refused(f'panel ids are not 1..N in order: {seen}')

    tabs = []
    for item, panel in zip(items, panels):
        tooltip = TITLE.search(item.group('attributes'))
        if not tooltip:
            raise Refused('an <li> has no title attribute, so the tab would '
                          'have no accessible name')
        tabs.append({
            'tooltip': tooltip.group('title').strip(),
            'label': item.group('label').strip(),
            'body': panel.group('body'),
        })
    return tabs, content.group('attributes')


def tabber_of(tabs: list[dict], key: str) -> str:
    """The `<tabber>` block. Tab names are PLAIN TEXT, deliberately.

    Two measurements on the local wiki decided this, both of them from trying
    to keep the icon markup in the tab name:

    1. Written inline, TabberNeue splits `|-|name=` at the FIRST `=`, which
       lands inside `class="fas fa-home"`. The name became `<i class` and the
       rest of the attributes spilled into the panel as visible text - every
       panel came back carrying `"fas fa-home" aria-hidden="true">`.
    2. Moved into a page variable (the idiom the main page uses), the split
       problem went away and the panels matched - but TabberNeue derives each
       panel's anchor id from the tab NAME, so the ids became
       `#tabber-tabpanel-&lt;i_class=&quot;far_fa-circle&quot;...`. This wiki
       sets `$wgTabberNeueUpdateLocationOnTabChange = true`, so every click
       wrote that into the address bar.

    So the name is the tooltip text - which is also the accessible name an
    icon-only tab never had. The icons come back as CSS on the wrapper the
    strip already sits in (`.records-list-tabs-container` and friends), where
    the four competition categories always use the same four glyphs.
    """
    lines = ['<tabber>']
    for tab in tabs:
        lines.append(f'|-|{tab["tooltip"]}=')
        lines.append(tab['body'].strip())
    lines.append('</tabber>')
    block = '\n'.join(lines)

    wrapper = icon_class(tabs)
    if wrapper:
        block = f'<div class="{wrapper}">\n{block}\n</div>'
    return block


# Icon sets the skin can reproduce in CSS, by the sequence of FontAwesome
# classes the old labels used. The tab NAME has to stay plain text (see
# tabber_of), so the icons come back as ::before content keyed on tab position
# - which is only safe when the sequence is one the CSS knows. An unknown
# sequence converts to text tabs and says so, rather than showing four icons
# in the wrong order.
ICON = re.compile(r'<i\b[^>]*class="(?P<classes>[^"]+)"')
ICON_SETS = {
    ('far fa-circle', 'fas fa-home', 'fas fa-trophy', 'fas fa-euro-sign'):
        'tabber-icons-competitions',
}


def icons_of(tabs: list[dict]) -> tuple[str, ...]:
    sequence = []
    for tab in tabs:
        found = ICON.search(tab['label'])
        sequence.append(found.group('classes').strip() if found else '')
    return tuple(sequence)


def icon_class(tabs: list[dict]) -> str | None:
    """The wrapper class whose CSS restores this strip's icons, if known."""
    return ICON_SETS.get(icons_of(tabs))


def variable_key(text: str) -> str:
    """A prefix for this strip's page variables.

    Taken from the radio group name the strip already carries
    (`name="tab-control-bb-points"` -> `bb-points`), because it is unique per
    strip on the page - which is exactly the property the variables need, and
    #var is one flat namespace shared with every template on the page.
    """
    group = re.search(r'name="(?:tab-control-?)?(?P<key>[^"]*)"', text)
    key = (group.group('key') if group else '').strip('-') or 'tabs'
    return re.sub(r'[^A-Za-z0-9_-]', '-', key.replace('tab-control', ''))\
        .strip('-') or 'tabs'


def convert(text: str) -> str:
    tabs, _ = parse_strip(text)
    strip = STRIP.search(text)
    remainder = text[strip.end():]
    content = CONTENT.search(remainder)

    before = text[:strip.start()]

    # Everything between </shtml> and <div class="content"> is KEPT. Dropping
    # it was a real defect: the "עיצוב חדש" leaderboards define the counts
    # their panels print in exactly that gap, so converting them silently
    # replaced "(62 שחקנים)" with "(" - four templates, every panel. The
    # basketball strips have only a comment there, which is why it passed
    # unnoticed on the first subject.
    middle = remainder[:content.start()]

    after = ''
    tail = content.group('panels')
    closing = tail.rfind('</div>')
    if closing != -1:
        after = tail[closing + len('</div>'):]

    return (before + middle
            + tabber_of(tabs, variable_key(text)) + after)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file', help='wikitext file to convert')
    group.add_argument('--local', help='page title on the local wiki')
    options = parser.parse_args()

    text = (open(options.file, encoding='utf-8').read() if options.file
            else local_text(options.local))

    try:
        print(convert(text))
    except Refused as refusal:
        print(f'REFUSED: {refusal}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
