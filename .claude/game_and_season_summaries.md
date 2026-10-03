# Writing game and season summaries

The conventions for the free-text summaries on game and season pages. **The owner's rules in the
last section override everything above them.**

## Where they live

| Page | Field | Ends at |
|---|---|---|
| Game page (`משחק:...`) | `\|סיכום משחק=` | the next `\|param=` of the game template |
| Season page (`עונת YYYY/YY`) | `\|סיכום העונה=` of `{{עונת כדורגל}}` | the template's closing `}}`; text boxes (`מולטימדיה`, `כתבות`) follow it |

Learned from football pages; the same voice, link and score rules apply to basketball and volleyball.
Model pages to read before writing: `משחק:30-09-1958 הפועל חיפה נגד מכבי תל אביב - גביע המדינה`
(match report), `משחק:17-03-2014 הפועל תל אביב נגד מכבי תל אביב - ליגת העל` (iconic game),
`עונת 1957/58` (chronicle), `עונת 1978/79` (feature). Don't learn from a page just because its
summary is long or recent; season pages 2005/06–2017/18 are a bot import.

**Editing an existing summary:** fix facts, links, spelling and score order; don't rewrite another
writer's prose into this style. A stub may be expanded.

## Game summary

**Only when it adds something** the score and the events don't already show: how it happened,
context, why it mattered, something unusual. A summary that restates the score or the goal list
is left out, and the field stays empty.

1. **What was at stake:** stage, form, the previous meeting (linked), a back story.
   > לאחר שלושה נצחונות ופתיחת עונה טובה, מתארחת מכבי בחיפה אצל קבוצתו של לא אחר מ[[אלי פוקס]]...
2. **The game in order, by minute:** `בדקה ה-32 ...`, `דקה חולפת ו...`. Each goal: who, from where,
   how it went in, then the score. Misses, saves, disallowed goals and red cards belong too.
3. **The end:** the result and what it means (trophy, double, table). It may close on the question
   the next game answers: `האם תשלים הקבוצה דאבל נטול הפסדים?`

**Short notes** for unusual games: an awarded game gives the score on the pitch, then the official
awarded score, why and by whose decision (the score fields hold only the official one); a game never
played says so in bold; an estimated date says so and gives the reasoning.
> '''תאריך המשחק הוא הערכה בלבד''', המבוססת על דפוס המשחקים: כל משחקי אפריל 1950 נערכו בימי שבת...

**Iconic games** (a handful) are told as a story: why the game has a name (`"דרבי זהבי"`), the
ending held back, the build-up to the decisive moment, what it changed, a light closing line.

## Season summary

**Chronicle** (old seasons): flowing prose with no `=` sections. It opens where the previous
season ended, then covers what changed in the break. One bold label per competition
(`'''ליגה לאומית''':{{ש}}`), and it ends on the trophy. Games are linked through a short phrase:
`[[משחק:04-01-1958 ...|רביעייה נגד הפועל כפר סבא]]`.

**Feature** (landmark seasons):
- It opens with a hook: `את סיפורה של עונת 1978/79 צריך להתחיל דווקא מהסוף`.
- `=='''...'''==` headings tell the story in order (`השתלטות מהירה על הפסגה`, `משחק העונה וגמר
  הגביע`), never dry labels or placeholders. It explains *why*, with the newspaper that said so.
- Scores live on the game pages: a run of results becomes one clause (`לא הצליחה לנצח והוסיפה
  למאזנה רק שתי נקודות`); only key results stay, linked.
- It closes with `== המספרים הבולטים ==` and, where it matters, `== מה קרה אחרי זה? ==`.

## Conventions

### Scores
- Colon, never dash.
- **Typed away:home**, so a score reads home–away right to left, like the game title. Home is the team
  first in the title, wherever the game was played. Maccabi beats Hapoel 1–0 at Bloomfield → `0:1`;
  Maccabi wins 3–2 away at Hapoel → `3:2`. Old pages are mixed: check the real result before flipping one.
- Say who when it is not obvious: `0:1 למכבי`.
- Extra time, shootouts and two-leg totals go in words, in the same order and with who:
  `והמשחק הלך להארכה`, `עבר לשלב הפנדלים`, `בסיכום שני המשחקים 3:2 למכבי`. No bracket formats.
- A game page does not link its own score; a link to *another* game goes on its score or a phrase.

### Links
- Full page name, short display: `[[אבי נמני|נמני]]`, `[[אצטדיון בלומפילד|בלומפילד]]`,
  `[[פ.צ. באזל]]`, historic clubs by their current page (`[[בית"ר תל אביב רמלה|בית"ר ת"א]]`).
- The Hebrew prefix stays outside: `ו[[שייע גלזר|גלזר]]`, `ש[[מכבי רחובות|רחובות]]`.
- **First mention on the page only.**
  > [[שייע גלזר|גלזר]] בעט פצצה אל הרשת... דקה חולפת וגלזר בישל ל[[רפי לוי]]... ושוב רפי לוי מרעיד את הרשת
- Link what has a page: clubs (`[[הפועל תל אביב|הפועל]]`), stadiums, seasons (`[[עונת 1963/64|64]]`),
  referees (`[[כדורגל:זיו אדלר (שופט)]]`), stat pages (`[[שלושער]]`).
- No link for what has no page (most opposing players), generic words (`ניצחון טכני`, `VAR`), anything
  red. An opponent who has a page (a former Maccabi player) is linked.
- A game link matches the real title: no `- מוקדמות`, the right date, home team first. Seasons are
  `עונת YYYY/YY`, except `עונת 1955`.

### Spelling, punctuation, numbers
- `ניצחון`, never `נצחון`. Names are spelled as on the player's page.
- `(!)` only, attached to the word (`בליגה(!)`), never `(!!!)`.
- A hyphen after a prefix letter before a number or link: `ה-19`, `ב-2:2`, `ב-[[משחק:...`.
  Minutes are `בדקה ה-11`.
- Small numbers in words in running text (`שתי דקות`, `שמונה נקודות`); scores, minutes and big
  numbers stay digits.
- A comma after an opening clause, but none after a short opener (`לאחר מכן`). A bold closing line
  ends with a period after the `'''`.

### Layout
- `{{ש}}<!--` ends each paragraph and `-->` starts the next line; no runs of blank lines.
- Standings go in `{{מיני טבלת ליגה}}`, not in prose.
- Bold only for: the running score in a goal-by-goal account, a real first or record, the
  "never played" / "estimated date" notice, and an optional closing line.

### Voice
- Neutral, never "we" (`העלה אותנו`, `בכדורגל שלנו` go). Warmth comes from verbs (`הביסה`,
  `חמישייה משכנעת`) and nicknames (`הצהובים`).
- **Nicknames** for another team only once it is named in the same paragraph and only one team fits
  (`הפועל חיפה` → `האדומים מהכרמל`); never in headings. With two other teams in play, write the names:
  `בין מכבי חיפה להפועל תל אביב`, not `בין הירוקים לאדומים`. Maccabi's own (`הצהובים`) are free.
- Past tense, except a match report of a pre-1990s game may use the historic present throughout.
  Recalling an older game does not change the tense. One tense per summary.
- `ז"ל` after a deceased person.

### Facts
- Every detail comes from a source; for pre-1990s games name the newspaper and date (or an NLI link
  or `<ref>`). Never invent a minute, a pass or a name to make the story flow.
- Unknown is written as unknown (`...אינן ידועות`); never work out a result or a number by guessing.
- Every "last time"/"for the Xth time" claim gets checked against Cargo before saving.
- When the prose names a goal or an assist the events lack, add it to the events too.

### Leave out
- Off-topic incidents, gushing, tangents hung on a stat, repetition.
- Media inside the summary: videos go in the `מולטימדיה` box and articles in `כתבות`, after the template.
- Categories inside the prose; they go after the template's `}}`.

## The owner's additions

<!-- Owner rules go here. -->
