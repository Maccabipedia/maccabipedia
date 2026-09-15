# Tabs without `<shtml>` — design (v2)

Status: **spec.** v1 proposed building a tab component in the skin. An
independent review falsified its two load-bearing claims; v2 is a different
design and a much smaller one. What changed and why is in §9.

## 1. What this is actually worth

A tab strip today is a CSS radio hack — hidden `<input type="radio">` plus
`<label>`, switched by `:checked` sibling combinators in
`skins/Maccabipedia/customize/styles/atoms/slim-tabs.less`. `<input>` is not
sanitizer-allowed, so each strip is wrapped in `<shtml>`, whose hash is an
HMAC under `$wgSecureHTMLSecrets`.

The honest benefit of removing that, stated narrowly:

- **An ordinary editor can add, reorder or retitle a tab.** Today they cannot:
  the strip is inside a signed block, so it takes a secret holder.
- **The 5-tab ceiling disappears.** `slim-tabs.less` hardcodes
  `:nth-of-type(1..5)`; a sixth tab silently never shows.

What it is **not** worth, and v1 oversold:

- **Not performance.** The day family is already live at 28 Cargo queries → 1,
  p50 559 → 162 ms across 366 pages, with `<shtml>` untouched. That benefit is
  banked and this work adds none.
- **Not "one `#invoke` instead of nine".** That is tidiness in one template
  source, not a user-visible or correctness gain.
- **Not a smaller raw-HTML surface.** `<shtml>` stays installed for the
  4 non-tab blocks, so nothing about the attack surface changes.

If that first bullet is not worth a migration, the correct decision is to stop
here. The reviewer's alternative is recorded in §10.

## 2. What is on the wiki (measured, production, 2026-09-15)

Namespace 10 read directly, 1,521 pages. The pattern matters: radio names are
**prefixed** (`fb-tab-control-games`) and the CSS matches
`[name*="tab-control"]`, so a naive `name="tab-control` search undercounts.

| | count |
|---|---|
| pages carrying `<shtml>` | 102 |
| …that are real tab strips | **98** |
| …that are not tab strips (out of scope) | **4** |
| radio inputs in total | 397 |
| **templates already using `<tabber>`** | **15** |

Strips by size: 79 with 4 tabs, 14 with 5, 4 with 2, 1 with 3.

The 4 non-tab blocks are all main-page furniture:
`עמוד ראשי/יומן משחקים/כדורגל`, `עמוד ראשי/יומן משחקים/כדורעף`,
`עמוד ראשי/לוח שנה`, `עמוד ראשי/מכביפדיה ברשתות`.

**The main page itself has no radio strip.** Its tabs are already `<tabber>`
(`עמוד ראשי/יומן משחקים`, `ימי הולדת`, `משחקי היום`, `משחקים אחרונים`,
`עונות אחרונות`). v1 claimed the main page was in scope and put it last; that
was wrong in both directions.

## 3. The design: use the incumbent

**Extension:TabberNeue is already installed, pinned, configured and live.**

- `infra/local-wiki/extensions.json` — commit `4432a1a9`, `REL1_39`
- `LocalSettings.shared.php:379-382` — `wfLoadExtension('TabberNeue')` plus
  `$wgTabberNeueUpdateLocationOnTabChange`, `$wgTabberNeueEnableAnimation=false`,
  `$wgTabberNeueParseTabName=true`
- the skin already styles it: `customize/styles/mixins/tabs.less`, 131 lines
  written against `.tabber__header`, `nav.tabber__tabs`, `a.tabber__tab`,
  `.tabber__indicator`, `.tabber__section`, applied from six call sites
- 15 templates already use it, the main page among them

So the design is: **write no new tab code.** Convert a strip from

```wikitext
<shtml keyname="…" hash="…"><input type="radio" id="fb-tab1" …><ul><li…
```

to

```wikitext
<tabber>
|-|ליגה=
{{…panel one…}}
|-|גביע=
{{…panel two…}}
</tabber>
```

`$wgTabberNeueParseTabName=true` means a tab title can be computed — the main
page already passes `{{#var:}}` titles — so icon markup and template-derived
titles both work. Lua can emit the same thing with
`frame:extensionTag('tabber', body)` when we get to §7.

Everything v1 would have hand-built — ARIA roles, keyboard handling, focus
management, no-JS behaviour, storage of the chosen tab — is the extension's
job and already shipped. `slim-tabs.less` stays untouched for unconverted
strips; the two mechanisms do not interact, because the radio engine is pure
CSS keyed on inputs the converted pages no longer have. The end state has
**one** mechanism, not a new third one.

## 4. Scope

**Convert one template. Verify. Stop.**

First subject: `סטטיסטיקות מדי כדורגל` — the single namespace-0 page with a
strip, self-contained, not transcluded by anything, low traffic.

Then stop, and convert the next one only when an editor actually wants to
change a strip. There is no schedule for the remaining 97. Planning 97
conversions in advance is inventory work against a benefit nobody has yet
asked for, and §5 explains why each conversion is harder to undo than to do.

## 5. Rollback, and why it argues for stopping early

- **A converted template** reverts by restoring the previous revision —
  one edit, and the text is recoverable from history.
- **But re-signing is not available to us.** Reverting to `<shtml>` needs a
  valid `hash` for the payload, which needs the secret. So rollback-by-editing
  is only possible because the old revision *already carries* a valid hash;
  any subsequent change to that strip's content while reverted needs the
  secret holder again.
- **The point of no return** is deleting the `:checked` rules from
  `slim-tabs.less`. That happens only when a positive check says zero strips
  remain — `radios == 0` across namespaces 0 and 10 — never on elapsed time.
  Given §4, that point is not expected to arrive soon, and that is fine.

## 6. Verification

Byte-identical comparison is not available: the markup changes by design. What
replaces it, in the order that finds problems earliest:

1. **Sanitizer round-trip, first and cheapest.** Post the proposed wikitext to
   `action=parse` and assert the tab elements are **present** in the output —
   not merely that `<input>` is absent. This one HTTP call is what falsified
   v1's markup contract (`<label>` came back escaped as visible text, and
   `aria-selected` was silently stripped from a `<span>`). It belongs in CI.
2. **Panel-text equality.** Compare the old and new rendering panel by panel,
   filtering to element children and **failing on a count mismatch** rather
   than zipping the shorter list — otherwise a panel lost to a stray `<p>`
   passes unnoticed. Numbers and labels must match exactly.
3. **Interaction, in a real browser** (Playwright already runs against the
   local wiki): clicking tab N shows panel N and hides the rest; two strips on
   one page switch independently; **arrow-key direction under RTL** — this is a
   Hebrew wiki and left/right are reversed relative to tab order.
4. **Screenshot comparison** of the converted page before and after, with a
   stated tolerance. Not "0 pixels": the DOM changes, so anti-aliasing and
   sub-pixel layout will differ. The check is that no *region* changes beyond
   the strip itself.
5. **No-JS load**: assert every panel's text is in the DOM with JavaScript
   disabled. TabberNeue's behaviour here is the extension's, not ours — this
   records what it actually does rather than assuming.

Items 1 and 2 gate the edit. Items 3–5 run once per converted family.

## 7. The Lua side — deferred

`Module:FootballStatsBlock` could collapse from nine `#invoke` calls to one by
emitting `frame:extensionTag('tabber', …)`. **Not in this change.** It is
tidiness (§1), it moves tab titles and icons out of wikitext into a Lua data
page, and it would land on top of a migration whose own verification is new.
Revisit after a converted strip has been live and boring for a while.

## 8. Risks

- Converting a strip is easier than reverting it (§5).
- Two mechanisms coexist until the last strip is converted. Benign, but it
  means "how do tabs work here" has two answers for a while.
- TabberNeue's look is close but not identical to `slim-tabs`; §6 item 4 is
  where that surfaces. The existing mixins may need applying to the new call
  site.
- `<shtml>` remains installed and required for 4 blocks. "We removed `<shtml>`"
  must not be claimed.

## 9. What the review changed

29 findings; the material ones:

- **v1's markup contract did not work.** `<label>` is not sanitizer-allowed —
  verified against production, it renders as escaped text. The entire
  "tab strip as ordinary wikitext" design was built on that false premise.
  v2 uses `<tabber>` and has no hand-written markup contract.
- **TabberNeue was already installed, pinned, configured, styled and live**,
  and v1 rejected it for "adding a pinned dependency that needs maintaining".
  That was the single strongest argument in v1 §4 and it was false.
- **The inventory was wrong**: 98 strips and 4 non-tab blocks, not 91 and 10,
  because the radio-name pattern missed prefixed names. v1's Phase 4 would
  have stranded 6 real strips on panel 1 forever.
- **The main page has no radio strip** and already uses `<tabber>`; v1's
  Phase 3 and its matching risk were both fictional.
- **v1 Phase 0 was not a no-op**: its script would have enhanced all 97 legacy
  strips, putting `:checked` and `.is-active` in competition.
- **Guaranteed FOUC** in v1, since the non-enhanced default was "all panels
  stacked" while the script loaded async.
- **The benefit was oversold.** The query collapse is already banked with
  `<shtml>` untouched, so §1 now states the one real benefit and the three
  non-benefits.
- **Gold-plating removed**: `sessionStorage` tab persistence, and the
  cross-skin check whose stated bar could not be met.
- **Rollback was absent**, and writing it out showed it is asymmetric in a way
  that argues for converting fewer templates, not more (§5).

## 10. The alternative the reviewer preferred

Spend the effort on query collapsing instead: `סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים`
is **32 queries** per call and `.../סיכום אירועים לפי מפעל` is 8, both still
unconverted. That reuses a pattern already validated on production, needs no
new UI mechanism, and keeps byte-identical verification — the safety property
§6 has to work to replace.

Recorded rather than acted on: the tab work was chosen deliberately. But if
only one of the two gets done, the reviewer's case for the other is strong.
