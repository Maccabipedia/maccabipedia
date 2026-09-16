"""Old strip vs converted tabber, compared in every interaction state.

    uv run --with playwright python infra/tabs/compare_tab_states.py

The at-rest pixel comparison missed the panel fade, the hover colours and
TabberNeue's hover underline, because a screenshot is taken with the
pointer away and after motion settles. This compares COMPUTED STYLES for the
active and an inactive tab at rest, hovered, pressed and focused, the
container, and the panel right after a switch. Host pages come from
infra/tabs/make_host_pages.py. Exits 1 on any difference.
"""
from urllib.parse import quote

from playwright.sync_api import sync_playwright

BASE = 'http://localhost:8080/'
SIDES = {
    'old': ('ארגז חול/טאבים/לפני', '.slim-tabs ul li label', '.slim-tabs', '#tab{n}-content', '.slim-tabs .content'),
    'new': ('ארגז חול/טאבים/אחרי', '.tabber__tab', '.tabber-converted', '.tabber__panel:nth-child({n})', '.tabber-converted .tabber__section'),
}
PROPS = ['color', 'backgroundColor', 'cursor', 'userSelect', 'webkitTouchCallout', 'whiteSpace',
         'borderRadius', 'fontWeight', 'transitionDuration', 'opacity',
         'outlineStyle', 'boxShadow', 'textDecorationLine']
CONTAINER = ['position', 'minWidth']
PANEL = ['animationName', 'animationDuration', 'animationTimingFunction']
SECTION = ['scrollBehavior']

READ = """([selector, index, props]) => {
  const node = document.querySelectorAll(selector)[index];
  const s = getComputedStyle(node);
  return Object.fromEntries(props.map(p => [p, s[p]]));
}"""


def measure(page, tab_selector, container, panel_pattern, section):
    out = {}
    first = page.locator(tab_selector).nth(0)
    second = page.locator(tab_selector).nth(1)
    out['container'] = page.evaluate(READ, [container, 0, CONTAINER])
    # How a switch moves: the old strip swapped in place, the tabber must not slide.
    # TabberNeue only enables its slide when $wgTabberNeueEnableAnimation is on
    # (it is off here and on prod), so the class it would add is forced on -
    # otherwise this reads 'auto' with or without the skin's override.
    page.evaluate("() => document.documentElement.classList.add('tabber-animations-ready')")
    out['section'] = page.evaluate(READ, [section, 0, SECTION])
    page.mouse.move(1, 1)
    page.wait_for_timeout(400)
    out['active/rest'] = page.evaluate(READ, [tab_selector, 0, PROPS])
    out['inactive/rest'] = page.evaluate(READ, [tab_selector, 1, PROPS])
    first.hover(); page.wait_for_timeout(400)
    out['active/hover'] = page.evaluate(READ, [tab_selector, 0, PROPS])
    second.hover(); page.wait_for_timeout(400)
    out['inactive/hover'] = page.evaluate(READ, [tab_selector, 1, PROPS])
    page.mouse.down(); page.wait_for_timeout(400)
    out['inactive/pressed'] = page.evaluate(READ, [tab_selector, 1, PROPS])
    page.mouse.up(); page.mouse.move(1, 1); page.wait_for_timeout(700)
    # keyboard focus on the (now) inactive first tab
    first.focus(); page.wait_for_timeout(400)
    out['first/focus'] = page.evaluate(READ, [tab_selector, 0, PROPS])
    # switch to tab 3 and read the panel right away
    page.locator(tab_selector).nth(2).click(); page.wait_for_timeout(50)
    out['panel3/just-switched'] = page.evaluate(READ, [panel_pattern.format(n=3), 0, PANEL])
    return out


with sync_playwright() as runner:
    browser = runner.chromium.launch()
    results = {}
    for side, (title, tab, container, panel, section) in SIDES.items():
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        page.goto(BASE + quote(title.replace(' ', '_')), wait_until='networkidle')
        page.wait_for_timeout(2500)
        results[side] = measure(page, tab, container, panel, section)
        page.close()
    browser.close()

differences = 0
for state in results['old']:
    for prop, old_value in results['old'][state].items():
        new_value = results['new'][state].get(prop)
        if old_value != new_value:
            differences += 1
            print(f'{state:22} {prop:22} old={old_value!r:38} new={new_value!r}')
print(f'\n{differences} differing (state, property) pairs')
raise SystemExit(1 if differences else 0)
