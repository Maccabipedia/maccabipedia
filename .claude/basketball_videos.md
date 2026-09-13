# Basketball game videos

How highlight and full-game links get onto `כדורסל:` game pages, and what to know
before changing any of it.

## The two channels

**Maccabi Tel Aviv Basketball** (`UCqxNoI856R_vgs7aQolQhlg`) — about 6,000 videos in a
`Season YYYY/YY` playlist per season from 1979/80, plus `Games Highlights` and
`Full Games` playlists from 2013/14. A title carries the two teams and the final score
but never a date, so the match key is **season + score + opponent**.

**EuroLeague** (`@EuroLeague`) — per-round highlights, `Maccabi - Panathinaikos | R24
BASKETBALL HIGHLIGHTS 2025-26`, and `EUROLEAGUE CLASSIC GAMES` replays. No score in the
title, so the key is **season + round + opponent**, the round matching the `Leg` column
(`מחזור 24`). One channel-search request returns every video mentioning Maccabi.

## Title traps, all of them found the hard way

- **Hebrew titles read right to left.** In `מכבי ת"א - הפועל ת"א 80:74` Maccabi scored
  74, not 80. English titles read in order. Verified against Cargo across the whole
  channel: before the fix, 234 of 236 parseable Hebrew titles matched only the reversed
  score while 482 of 495 English ones matched as written; after it, 780 of 785 Hebrew
  titles match as written. The channel published both `74:80` and `80:74` in English for
  one and the same game, so when both orders match a game against the same opponent the
  matcher refuses rather than guessing.
- **The home team is written first**, so the score order follows the teams, not Maccabi.
  Which side is the club is decided by name — and several opponents are themselves
  named Maccabi, so a bare "Maccabi" only counts when nothing else is left in the name.
- **Pre-2010 uploads carry no keyword at all**: `National League 1985, Round 15, Hapoel
  Holon - Maccabi Tel Aviv 82:83`. Only the last comma-separated segment before the
  score names the teams, and the kind has to come from the video's length.
- **`תרכיז` / "Condensed Game"** is the whole game with dead time cut out, 14-17
  minutes, against about 3 for a `תקציר`. It counts as an extended highlight and shares
  the `תקציר` slots, ranked below a real highlight.
- **Player compilations carry the real game score** (`(18 points)`, `המהלכים של`,
  a leading `היילייטס`) and must be rejected, as must friendlies and training games.
- **Opponent names vary by era** on both sides. Cargo holds `ראשון לציון`,
  `מכבי ראשון לציון` and `ראשל"צ` for one club, so names are compared by significant
  word containment, and the alias table maps to the distinctive part of the name.
  `translations.canonical_team_name()` is deliberately NOT used here: it rewrites
  towards the spelling used for NEW uploads, away from what the old pages hold. For the
  same reason an alias must never rewrite a Hebrew name to a spelling the pages do not
  use — `מלאגה`→`מאלגה` and `אולימפיה לובליאנה`→`אולימפיה` each broke real matches.
- **The DESCRIPTION carries the date the archive titles lack.** The club writes it two
  ways: `נערך ביד אליהו ב-14/1/88` gives a day, `נערך בקלן באוקטובר 1981` only a month.
  `played_date.py` reads both, resolving a two-digit year against the video's season
  (`00` is 2000 and `95` is 1995, so no fixed pivot works). A day that agrees scores the
  match 10; a month scores 9; **a date that disagrees drops it to 2**, and when that
  fires it is usually the game page that is wrong. Descriptions come from the watch page
  alongside the upload date, in one request per video (`watch_page.py`).
- **A name gap is expensive, not cosmetic.** An unrecognised opponent costs two points,
  which drops the match below the write floor and sends it to a human. Fifty-three rows
  sat on the review page purely because of 1980s sponsor prefixes (`Tracer Milano`,
  `Nashua Den Bosch`), an appended city (`Aris Thessaloniki`), a hyphen (`ליון-וילרבאן`)
  or one letter (`מאלגה`/`מלאגה`). Hyphen and slash are word breaks, spelling variants
  fold both sides of the comparison, and each sponsor era needs its own alias.

## The 1-10 confidence score

Every proposed match carries one, and the review page is ordered by it rather than by
season, so the weak end is where a reviewer starts. It is built from evidence that can
be checked, weighted towards the one piece that does not come from the title: when the
video was uploaded.

| score | what it means |
|---|---|
| 10 | unique score that season, opponent recognised outright, uploaded within days |
| 9 | the same, but the upload came weeks or months later |
| 7 | the same, but an archive upload whose date says nothing either way |
| 1 | uploaded before the game, so the pairing cannot be right |

Points come off for two things only: a score shared by more than one game that season
(unless the upload date confirms the pick anyway), and an opponent name that does not
agree with the page chosen. A year in the title that contradicts the game's year sinks
the score outright. `--min-confidence N` refuses to write anything below N; the scheduled
job uses 9.

Two things deliberately do NOT affect it, each pinned by a test. Whether the title stated
the kind of video decides which parameter the link goes in, not whether the link is right.
Whether the opponent matched exactly or by containment is the designed-for case, since the
alias table maps each club to the distinctive part of its name. Counting either cost 655
sound archive matches a rung of confidence they had earned.

Upload dates come from the watch page's embedded `uploadDate`, one plain concurrent GET
per video, which is minutes for the whole channel where yt-dlp would be hours. That is
also why the date can be used to CHOOSE between candidate games, not merely to confirm
one: a video posted within ten days of exactly one candidate settles it.

## Where things live

| Path | What |
|---|---|
| `basketball/videosbot_basketball.py` | the CLI, used for both the backfill and the scheduled run |
| `basketball/videos/title_parser.py` | club-channel titles |
| `basketball/videos/euroleague_title.py` | EuroLeague titles |
| `basketball/videos/aliases.py` | opponent name comparison |
| `basketball/videos/matcher.py` | buckets and slot assignment |
| `basketball/videos/inventory.py`, `rss.py` | the two ways of listing videos |
| `basketball/videos/upload_dates.py` | bulk upload-date fetch from the watch page |
| `basketball/videos/dates.py` | game date against upload date |
| `basketball/videos/confidence.py` | the 1-10 score |
| `basketball/videos/sampling.py` | the upload-date verification sample |
| `basketball/videos/report.py` | the review page |
| `basketball/videos/writing.py` | the writes and the season purge |
| `maintenance/videos/sport_templates.py` | which template and parameters each sport uses |

## Running it

Backfill, from a workstation, in two steps. Build the inventory first — yt-dlp on PATH may
be too old, and an out-of-date build stops after the first 100 videos of a playlist and
says so nowhere, which is why the inventory refuses a short listing:

```
YT_DLP_COMMAND="uvx yt-dlp@latest" uv run python -m maccabipediabot.basketball.videosbot_basketball \
  --build-inventory --inventory inventory.json --euroleague-inventory euroleague_inventory.json
```

That also fetches every video's upload date, which takes a few minutes and is what makes a
confidence of 10 reachable at all. Then match and report:

```
uv run python -m maccabipediabot.basketball.videosbot_basketball \
  --source file --inventory inventory.json --euroleague-inventory euroleague_inventory.json \
  --seasons all --sample 20 --report ~/served_reports/basketball_videos.html
```

Add `--write` to edit pages, `--dry-run` to see what it would do, `--pages FILE` to
restrict the run to named pages, `--purge` to refresh the season pages afterwards.
Progress is recorded per video, so a killed run resumes without re-editing.

The scheduled run in `basketball_games_uploader.yaml` uses `--source rss --seasons
current,previous --write --purge`. It needs no API key: YouTube's feed endpoint answers
datacenter IPs, unlike yt-dlp. **Annual maintenance:** add the new season's playlist ids
to `SEASON_PLAYLIST_IDS`; the run warns when the current season is missing.

## Slots

Cargo stores two of each kind: `תקציר וידאו`, `תקציר וידאו2`, `משחק מלא`, `משחק מלא2`.
The template renders a third and fourth of each, but does not pass them to Cargo, so a
link written there would show on the page and be invisible to every Cargo-driven tool.
A parameter that already holds a link is never overwritten.
