# The wiki's tracking system (קטגוריות תפעוליות)

MaccabiPedia keeps its maintenance work in a category tree rooted at `קטגוריה:קטגוריות תפעוליות`, about four
levels deep. **The tree is a floor, not the whole system** (see "Outside the tree" below). Read this before you
call a page or category unused, empty or safe to delete.

## The two branches

| Branch | What it holds |
|---|---|
| `קטגוריה:עמודי מעקב`, split by area: `עמודי מעקב לכדורגל`, `…לכדורסל`, `…לכדורעף`, `…לתבניות`, `…לאוסף שירים`, `…לכרטיסים ומנויים`, `…לעמודי יום`, … | **Tracking pages**, filed by hand under their area, e.g. `קטגוריה:עמודי מעקב למשחקים` under `עמודי מעקב לכדורגל`. Also **tracking categories** that templates fill, e.g. `משחקים המכילים אירוע לא תקין`, `טבלת ליגת כדורסל עם הפניה ליריבה ללא עמוד` (under `עמודי מעקב לתבניות`). |
| `קטגוריה:עמודי מעקב לשגיאות` | More categories for **wrong template input**: an image that doesn't exist, a design box with no title, a league table naming a missing team, a page-navigation strip with no links, … Input errors are split between this branch and `עמודי מעקב לתבניות`, so search both. |

## Tracking pages

A tracking page holds a `#cargo_query` or DPL query (rarely, a template that renders a category's members) and lists
the items needing a look, e.g. `תבנית:משחקים עם כמות קהל נמוכה` lists football games with 0 < Crowd < 500.
Editors open it to read the list; nothing transcludes or links to it. Most live in the **main namespace**, a few
in `תבנית:` and `כדורעף:`. So they show up on `Special:Lonelypages` (main namespace) and `Special:UnusedTemplates`
(`תבנית:`) by mistake. They are not orphans. Keep them.

## How tracking categories fill

Only template parser functions add them: `#תנאי` / `#if`, `#קיים` on a missing page, the `#ברירת מחדל` branch of a
`#בחר`, `#שווה`. No Lua module, bot or the daily sync adds one. Kinds:

- **Missing or wrong input:** `משחקים ללא הזנת שופט ראשי`, `עמודים עם תמונה לא קיימת`, …
- **Manual override present** (`…ידני`): the editor typed a value that replaces the one Cargo computes, e.g.
  `אנשי כדורגל עם משחק בכורה ידני` (from `פרופיל כדורגל`), and the same in `מפעל כדורגל`. Not an error.
- **A state, not an error:** e.g. `משחקים עם עיתון המשחק` / `משחקים ללא עיתון המשחק`. Some of these are visible
  and show at the bottom of articles.
- **Typed by hand on the page:** e.g. `עונות שעברו דיוק נתונים` on season pages.
- **Names built from parameters**, e.g. `שירי {{…}} ללא ביצוע`. Some names also differ by an extra space or a
  trailing invisible right-to-left mark. MediaWiki ignores both, but grep doesn't, so normalise before you match.

## Outside the tree

- **Detached roots.** Several `עמודי מעקב ל…` pages are bare AutoCreateCategoryPages stubs with no parent link,
  so their whole subtree is missing from a walk from the root. Examples: `עמודי מעקב למשחקי כדורסל`, which the
  basketball game template's categories name as their parent, and `עמודי מעקב לאתר` → `עמודי מעקב לעמוד ראשי`.
- **Categories with no page at all.** Some categories a template adds were never created (e.g. several
  `פרופילים ללא …`, `שחקנים ללא מספר חולצה במכבי`). See also `maccabipedia_structure_knowledge.md` on red-link
  categories.

So the complete set is **every category a template adds**: grep template source for `[[קטגוריה:` (the
`ללא` / `שגיאה` / `לא תקין` / `ידני` families) and union it with the tree walk.

## Rules that follow

- **An empty tracking category is good news only if a template still adds it.** Then it is empty because
  nothing is broken today: keep it. If AutoCreateCategoryPages recreates a deleted one, the new page is a bare
  stub without `__HIDDENCAT__` or its parent link, so it shows on articles and drops out of the tree. But when a
  template renamed its category, the old name sits empty forever, with nothing adding it, e.g. `משחקים ללא שופט
  ידוע`, now `משחקים ללא הזנת שופט ראשי`. That one is a leftover, and pages pointing at it (such as project pages
  linking to it) show nothing. Check the template source before you call one either way.
- **A new tracking category needs two lines on its page:** `__HIDDENCAT__` and its parent link, e.g.
  `__HIDDENCAT__ [[קטגוריה: עמודי מעקב לתבניות]]`. MediaWiki then lists it in `קטגוריה:קטגוריות מוסתרות` by
  itself. Without the parent link nobody finds it; without `__HIDDENCAT__` it shows at the bottom of articles.
- **Judge a page in any category together with that category.** A person filed it there for a reason. Even
  outside the tracking tree (for example `קטגוריה:שימושי לטבלאות קארגו`, `קטגוריה:מדריכי עריכה`), the page is
  not unused on its own. Decide about the category first. The exception is the automatic
  `קטגוריה:Pages using DynamicPageList3 parser function`, which the extension adds by itself.

## Listing the tree

Walk `list=categorymembers` from the root with `cmlimit=max`, queueing every member in namespace 14, and read
each category's `prop=pageprops` (`hiddencat`) and `categoryinfo`. Send batched `titles=` queries by POST
(see `maccabipedia_structure_knowledge.md`), because a GET of 50 Hebrew titles is too long and returns a 414.
Then add the categories found only in template source (above).
