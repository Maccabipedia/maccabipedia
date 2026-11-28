# The wiki's tracking system (קטגוריות תפעוליות)

MaccabiPedia keeps its maintenance work in one category tree. Its root is
`קטגוריה:קטגוריות תפעוליות`, and it is about four levels deep. Read this before you call anything in it unused,
empty or safe to delete.

## The two branches

| Branch | What it holds | How it fills |
|---|---|---|
| `קטגוריה:עמודי מעקב` (tracking pages), split by area: `עמודי מעקב לכדורגל`, `…לכדורסל`, `…לכדורעף`, `…לתבניות`, `…לאוסף שירים`, `…לכרטיסים ומנויים`, `…לעמודי יום`, … | **Tracking pages.** Each holds a `#cargo_query` (or DPL) that lists the items needing a look, e.g. `תבנית:משחקים עם כמות קהל נמוכה` lists football games with 0 < Crowd < 500. It also holds **tracking categories** that templates fill, e.g. `משחקים המכילים אירוע לא תקין`. | A person writes the tracking page and files it under its area's category, e.g. `קטגוריה:עמודי מעקב למשחקים` under `עמודי מעקב לכדורגל`. A template adds a page to a tracking category when its data is missing or wrong. |
| `קטגוריה:עמודי מעקב לשגיאות` | Categories for **wrong template input**: an image that doesn't exist, a design box with no title, a league table naming a missing team, a page-navigation strip with no links, … | The template adds the category in its error branch (`#if`/`#switch` default). |

## Rules that follow from it

- **A tracking page is not an orphan.** Editors open it to read its list, and nothing transcludes it. Pages in
  the `תבנית:` namespace therefore show up on `Special:UnusedTemplates` by mistake. Keep them.
- **An empty tracking or error category is good news, not a dead page.** It is empty because nothing is broken
  today. Don't delete it. If it is deleted and later refills, AutoCreateCategoryPages recreates it as a bare
  stub, without `__HIDDENCAT__` and without its parent link. It then shows on articles and drops out of the tree.
- **Most of these categories are hidden.** Their page holds `__HIDDENCAT__` plus the parent link, e.g.
  `__HIDDENCAT__ [[קטגוריה: עמודי מעקב לתבניות]]`. MediaWiki then lists them in `קטגוריה:קטגוריות מוסתרות` by
  itself. A new tracking category needs both lines on its page: without the parent link nobody finds it, and
  without `__HIDDENCAT__` it shows at the bottom of articles.
- **Judge a page in any category together with that category.** A person filed it there for a reason. Even
  outside this tree (for example `קטגוריה:שימושי לטבלאות קארגו`, `קטגוריה:מדריכי עריכה`), the page is not
  unused on its own. Decide about the category first.
- The automatic `קטגוריה:Pages using DynamicPageList3 parser function` is the exception. The extension adds it,
  so it says nothing about intent.

## Listing the tree

Walk `list=categorymembers` from the root with `cmlimit=max`, queueing every member in namespace 14, and read
each category's `prop=pageprops` (`hiddencat`) and `categoryinfo`. For `prop=categories` over many titles, use
batches of about 15 titles: Hebrew titles URL-encode to six bytes per letter, and 50 of them get a 414 from nginx.
