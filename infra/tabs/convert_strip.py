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
# The box's own heading, when it has one: `<div class="title">שיאני נקודות</div>`
BOX_TITLE = re.compile(r'<div class="title">(?P<title>[^<]{1,60})</div>')
CONTENT = re.compile(
    r'<div class="content"(?P<attributes>[^>]*)>(?P<panels>.*)$', re.DOTALL)
PANEL_OPEN = re.compile(r'<div id="tab(?P<index>\d+)-content">')


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

    panels = panels_in(content.group('panels'))
    if len(panels) != len(items):
        raise Refused(
            f'{len(items)} tab(s) but {len(panels)} panel(s) - a strip whose '
            'panels do not match its labels must be converted by hand')

    seen = [panel['index'] for panel in panels]
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
            'body': panel['body'],
        })
    return tabs, content.group('attributes')


def fallback_context(title: str) -> str:
    """A box name derived from the page title, for a strip with no heading.

    `תבנית:…/שיאני הופעות/עוזר שופט/עיצוב חדש` -> `שיאני הופעות עוזר שופט`:
    the last two meaningful segments, which is what distinguishes one box from
    its siblings.
    """
    parts = [part for part in title.removeprefix('תבנית:').split('/')
             if part not in ('עיצוב חדש',)]
    return ' '.join(parts[-2:])


def context_of(text: str, fallback: str | None) -> str | None:
    """A name for this box, to qualify its tab labels with."""
    heading = BOX_TITLE.search(text)
    if heading:
        return heading.group('title').strip()
    return fallback


def tabber_of(tabs: list[dict], context: str | None = None) -> str:
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
    icons = icon_class(tabs)
    if not icons:
        # Said out loud, because the alternative is a strip that quietly
        # stops being an icon bar and becomes a row of Hebrew words. The
        # docstring used to claim this happened; it did not.
        print(f'WARNING: icon set not recognised {icons_of(tabs)} - '
              'converting to TEXT tabs', file=sys.stderr)

    lines = ['<tabber>']
    for tab in tabs:
        label = tab['tooltip']
        # Qualified only when the CSS hides the label text - see the module
        # docstring. On a visible tab, `ליגה - שיאני כיבושים` reads worse than
        # a positional anchor.
        if icons and context:
            label = f'{label} - {context}'
        lines.append(f'|-|{label}=')
        lines.append(tab['body'].strip())
    lines.append('</tabber>')
    block = '\n'.join(lines)

    # `tabber-converted` always: it is what the rhythm and heading styles are
    # scoped to, and a text-tab strip needs those just as much as an icon one.
    # The icon class is added only when the sequence was recognised.
    classes = ' '.join(filter(None, ['tabber-converted', icons]))
    return f'<div class="{classes}">\n{block}\n</div>'


# Icon sets the skin can reproduce in CSS, by the sequence of FontAwesome
# classes the old labels used. The tab NAME has to stay plain text (see
# tabber_of), so the icons come back as ::before content keyed on tab position
# - which is only safe when the sequence is one the CSS knows. An unknown
# sequence converts to text tabs and says so, rather than showing four icons
# in the wrong order.
ICON = re.compile(r'<i\b[^>]*class="(?P<classes>[^"]+)"')
# Measured across all 51 strips on the local wiki: three sequences, and the
# CSS carries one class for each. A sequence not listed here converts to TEXT
# tabs with a warning - four icons in the wrong order would be worse than
# words, and silently so.
ICON_SETS = {
    ('far fa-circle', 'fas fa-home', 'fas fa-trophy', 'fas fa-euro-sign'):
        'tabber-icons-competitions',
    ('far fa-circle', 'fas fa-home', 'fas fa-trophy', 'fas fa-euro-sign',
     'fas fa-asterisk'):
        'tabber-icons-competitions-plus',
    ('far fa-circle', 'fas fa-home', 'fas fa-trophy', 'fas fa-globe'):
        'tabber-icons-competitions-globe',
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


DIV_TAG = re.compile(r'<div\b[^>]*>|</div>', re.IGNORECASE)


def panels_in(region: str) -> list[dict]:
    """Each `<div id="tabN-content">` panel, to its OWN closing tag.

    Counted, not matched with a regex ending at `</div><!--`. That ending cut
    a panel short the moment its body held a nested div followed by a comment,
    and dropped whatever came after inside the same panel - silently, because
    the panel-text comparison only ever saw the truncated version on one side.
    """
    found = []
    for opening in PANEL_OPEN.finditer(region):
        end = matching_close(region, opening.start())
        found.append({
            'index': int(opening.group('index')),
            'body': region[opening.end():end - len('</div>')],
        })
    return found


def matching_close(text: str, start: int) -> int:
    """End index of the `</div>` that closes the `<div>` opening at `start`.

    Counting rather than searching. The first version took everything after
    the LAST `</div>` in the panel region as the tail, which threw away the
    closing tags of the wrappers AROUND the strip: a converted template came
    out with 8 opening divs and 6 closing ones, so MediaWiki auto-closed them
    at the end of the page and wrapped everything after the template inside
    `.records-list-tabs-container`. 16 of 25 conversions were affected, and
    every one of them passed the panel-text comparison, which is why this now
    refuses instead of guessing.
    """
    depth = 0
    for tag in DIV_TAG.finditer(text, start):
        depth += 1 if tag.group().startswith('</') is False else -1
        if depth == 0:
            return tag.end()
    raise Refused('the strip\'s <div> is never closed')


def convert(text: str, context: str | None = None) -> str:
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

    # The widget is exactly `<div class="slim-tabs"> … </div>`, and only that
    # is replaced. Everything outside it - including the wrappers it sits in
    # and anything after the template - is preserved byte for byte.
    after = text[matching_close(text, strip.start()):]

    converted = (before + middle
                 + tabber_of(tabs, context_of(text, context)) + after)

    opened = len(re.findall(r'<div\b', converted))
    closed = len(re.findall(r'</div>', converted))
    if opened != closed:
        raise Refused(
            f'the conversion would leave {opened} opening and {closed} '
            'closing <div> tags - refusing rather than emitting markup that '
            'swallows the rest of the page')
    return converted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file', help='wikitext file to convert')
    group.add_argument('--local', help='page title on the local wiki')
    options = parser.parse_args()

    text = (open(options.file, encoding='utf-8').read() if options.file
            else local_text(options.local))

    # The page title is the fallback name for the box when it has no
    # heading of its own: `…/שיאני הופעות/עוזר שופט/עיצוב חדש` -> the two
    # meaningful segments.
    fallback = fallback_context(options.local) if options.local else None

    try:
        print(convert(text, fallback))
    except Refused as refusal:
        print(f'REFUSED: {refusal}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
