# Tables on season pages (all sports)

Every sport's season page shows its tables the same way: **one template per season
holds only the rows**, the season template shows it **only if that page exists**, and
a **shared renderer** draws it. Nothing is computed at render time and no Cargo query
is involved — a table is wikitext someone wrote.

## The pattern

```
תבנית:<per-season table> <season>      the rows:  {{<renderer> |טבלה=team^...^pts, ...}}
תבנית:עונת <sport>                     {{#קיים: תבנית: <per-season table> {{#var: עונה להצגה}} | show it }}
```

To add a table to a season: create the per-season template. To remove it: delete that
page. The season template never changes. After either, purge the season page.

## What exists per sport (September 2026)

| Sport | Template per season | Count | Section title |
|---|---|---|---|
| Football | `טבלת ליגת כדורגל <season>` | 100 | טבלת הליגה |
| Football | `טבלת בית בינלאומי כדורגל <season>` | 17 | from the template (see below) |
| Basketball | `טבלת ליגת כדורסל <season>` | 72 | טבלת הליגה |
| Basketball | `טבלת יורוליג <season>` (2016/17→) | 10 | טבלת יורוליג |
| Basketball | `טבלת יורוליג בתים <season>` (2001/02–2015/16) | 15 | טבלת יורוליג (בתים) |
| Basketball | `טבלת יורוליג טופ16 <season>` (2001/02–2014/15) | 14 | טבלת יורוליג (טופ 16) |
| Volleyball | `טבלת ליגת כדורעף <season>` | 43 | טבלת ליגה |
| Basketball | ~40 more European tables, named per competition (see below) | | טבלת דירוג |

Counts are `list=allpages&apnamespace=10&apprefix=`, minus the renderer itself where it
shares the prefix. **Don't count by category**: `קטגוריה:טבלאות ליגת כדורגל` holds 89 of
the 100 football tables (1928, 1929, 1930, 1933, 1936, 1941, 1942, 1943, 1945/46,
2004/05 and 2008/09 are outside it). Note also `טבלת יורוליג` as a prefix returns 39 —
10 of its own, plus בתים and טופ16.

**Three renderers, three different row formats** (rows separated by commas, fields by `^`):

| Renderer | Fields |
|---|---|
| `תבנית:טבלת ליגת כדורגל` | `שם^מש'^נצ'^תיקו^הפ'^שע' זכות^שע' חובה^נק'` (8) |
| `תבנית:טבלת כדורסל` | `שם^מש'^נצ'^הפ'^נק' זכות^נק' חובה^נק'` (7, **no draw column**) |
| `תבנית:טבלת ליגת כדורעף` | `שם^מש'^נצ'^הפ'^נ"ז^נ"ח^מערכות זכות^מערכות חובה^נק'` (9) |

Volleyball's renderer *is* `תבנית:טבלת ליגת כדורעף`, the same page as its per-season
prefix — there is no `תבנית:טבלת כדורעף`. Each renderer documents its own format in
its `<noinclude>`; read that before writing rows.

**Basketball has a generic route that football lacks.** `טבלה משתנה1..3` on the season
page, each with `כותרת טבלה משתנה1..3`, takes **the name of a table template** (not
wikitext): `תבנית:עונת כדורסל/הצגת טבלה` expands `{{תבנית: {{{טבלה}}} }}`. So
`כדורסל:עונת 1987/88` carries `|טבלה משתנה1=טבלת גביע אירופה לאלופות (כדורסל) 1987/88`
with its own title, and about 40 such tables exist: `טבלת גביע אירופה לאלופות (כדורסל)`
(21), `טבלת פיב״א יורוליג מוקדמות …`, `טבלת הליגה האירופית (כדורסל)` (4),
`טבלת גביע קוראץ׳ (כדורסל)`, `טבלת סופרוליג בית מוקדם (כדורסל)`. They all share one
table-of-contents entry, "טבלת דירוג".

That is the alternative football did **not** take: football hard-codes one name per
season (below). If a third kind of football table is ever needed, copy basketball's
`טבלה משתנה` route rather than adding another hard-coded name.

## Football's international group table (cards #540 / #161, 2026-09-22)

`תבנית:טבלת בית בינלאומי כדורגל <season>` — one per season in which Maccabi played a
group stage: 1968/69, 1970/71 (Asian Champion Club Tournament), 1977/78, 1978/79,
1980/81, 1993/94 (Intertoto), 2004/05, 2015/16 (Champions League), 2011/12, 2013/14,
2016/17, 2017/18, 2020/21, 2024/25, 2025/26 (Europa League), 2021/22, 2023/24
(Conference League). 2026/27 has none — out in the Conference League play-off.

Unlike the league table, the **title is per season**, because the competition varies.
The template answers `{{... |כותרת}}` with its title and otherwise renders the table:

```
{{#switch: {{{1|}}}
|כותרת=הליגה האירופית - בית ד'
|#default={{טבלת ליגת כדורגל |מספר יורדות=0 |הערות=... |טבלה=...}}
}}<noinclude>מקור: ...</noinclude>
```

`תבנית:עונת כדורגל` resolves that title once into a variable, uses it for the
table-of-contents entry and for the `{{פרק}}` section after the league table.

**A 36-club league phase (2024/25, 2025/26) shows only the 7 rows around Maccabi.**
That works through `מספר יורדות`'s neighbour on the renderer, **`מיקום ראשון`**: the
position of the first row (rows are numbered from it, and only a real 1st place gets
the `champion` highlight). Without it the renderer numbers from 1, exactly as before —
verified byte for byte across the 89 league tables in `קטגוריה:טבלאות ליגת כדורגל` —
which, as above, is not all 100. The 11 outside it were checked separately: they
render with no error and no row of theirs carries a 9th field.
It is a template-level parameter
and **not a 9th row field**, because three live league tables (1946/47 Hapoel Petah
Tikva, 1970/71 Hapoel Kfar Saba, 1974/75 Hakoah Maccabi Ramat Gan) already carry a
stray 9th field in one row.

`מספר יורדות=0` is passed explicitly: left empty, the renderer's `{{#ifexpr: > 0}}`
raises "שגיאה בביטוי" on every row.

Tool: `infra/season_pages/european_group_tables.py` (data in the JSON beside it) —
`check`, `renderer`, `candidate`, `preview`, `publish`. See `.claude/season_pages.md`
for the rollout order of season-page changes in general.

## Game pages already hold the press tables — use them

**`תבנית:קטלוג משחקים` takes `|טבלת ליגה=<file>`, and 72 European group games carry a
scanned newspaper/UEFA table "after matchday N".** (Match the parameter allowing
spaces — `|טבלת ליגה =` appears too, and MediaWiki trims it; a strict `=` match finds
only 71.) That is a primary source for the
standings of that round, and for the last matchday it is the final table. It beats
en.wikipedia, RSSSF and wildstat, which copy each other.

Found this way, 2026-09-22:
- **1980/81**: the press table gives Maccabi 9:15 and Netanya 12:7. en.wikipedia and
  wildstat have 8:14 / 11:6 because they hold the 1.7.1980 game as 1-0; it was 2-1
  (Yedioth 2.7.1980 p38, the club's site, our game page). Wikipedia is wrong.
- **1970/71**: the press table counts the 3-0 walkover against Al-Shorta in the goals
  (11:2), as our game page does; RSSSF leaves it out.
- **1977/78 and 2020/21**: the scan on the last game predates the group's end (other
  clubs still had games, or a game was postponed), so it is not the final table.
- Scans are absent for 2024/25 and 2025/26 (league phase).

The scans also name clubs as the Israeli press did: "משטרת בגדאד" for Al-Shorta,
"מועדון טהרן" for the 1969 Iranian club, "פאראק מאליזיה" for Perak.

**1968/69, the Iranian club:** our pages call it `משטרת טהרן`, following Maariv of
26.1.1969 ("אלופת איראן, משטרת טהראן"). Yedioth that same week calls it "פרספוליס",
as do RSSSF and en.wikipedia (Persepolis won the 1968-69 Tehran tournament; PAS
Tehran, the actual police club, finished 4th and did not travel). The contemporary
Israeli press contradicts itself — don't "fix" one to the other without new evidence.
