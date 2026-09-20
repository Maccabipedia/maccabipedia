# maccabistats Python Package — Knowledge Reference

The `maccabistats` package (v2.51, installed in the bot's venv) provides data loading, filtering, and statistical analysis for all Maccabi Tel-Aviv **football** game history. Source repo: `/mnt/c/code/maccabi_statistics/`.

---

## 1. Loading Data

```python
from maccabistats import (
    get_maccabi_stats,                    # Load from pickle file
    get_maccabi_stats_as_newest_wrapper,  # Load + wrap in latest MaccabiGamesStats
    load_from_maccabipedia_source,        # Load from cached MaccabiPedia crawl
    run_maccabipedia_source,              # Fresh crawl from wiki Cargo API (slow, minutes)
    load_from_maccabisite_source,         # Load from cached Maccabi TLV site crawl
    run_maccabitlv_site_source,           # Fresh crawl from maccabi-tlv.co.il
    serialize_maccabi_games,              # Pickle games to disk
)
```

- **Fastest**: `get_maccabi_stats("path.games")` — loads pre-serialized pickle from `~/maccabistats/`
- **Normal**: `load_from_maccabipedia_source()` — loads from already-crawled Cargo data
- **Fresh crawl**: `run_maccabipedia_source()` — hits wiki Cargo API, parses, applies fixes, serializes
- The bot typically uses `get_maccabi_stats_as_newest_wrapper()` or `load_from_maccabipedia_source()`

---

## 2. Fluent Filter API

All filters return a new `MaccabiGamesStats` object, enabling chaining:

```python
games.home_games.league_games.get_games_against_team("הפועל תל אביב").maccabi_wins
```

### Filter Properties (return `MaccabiGamesStats`)
| Property | Description |
|---|---|
| `home_games` / `away_games` | Home/away split |
| `league_games` | League competitions only |
| `europe_games` | European competitions only |
| `trophy_games` | Cup/trophy competitions only |
| `official_games` / `non_official_games` | Official vs friendlies |
| `maccabi_wins` / `maccabi_losses` / `maccabi_ties` | By result |
| `technical_result_games` | Technical result games |

### Filter Methods (return `MaccabiGamesStats`)
| Method | Description |
|---|---|
| `get_games_against_team(name)` | vs specific opponent |
| `get_games_by_coach(name)` | under specific coach |
| `get_games_by_referee(name)` | with specific referee |
| `get_games_by_player_name(name)` | player in squad |
| `get_games_by_played_player_name(name)` | player actually played |
| `get_games_by_season(season)` | e.g. `"2022/23"` |
| `get_games_by_competition(comp)` | by competition name(s) |
| `get_games_by_stadium(name)` | by stadium |
| `played_before(date)` / `played_after(date)` / `played_at(date)` | by date |
| `get_games_by_day_at_month(day, month)` | specific calendar day |

### Available Data Properties
- `available_players` / `available_players_names` — all players in the dataset
- `available_opponents` / `available_competitions` / `available_stadiums`
- `available_coaches` / `available_referees` / `available_seasons`
- `first_game_date` / `last_game_date` — date strings
- `points` / `success_rate` — league point calculations

### Utility
- `len(games)` — number of games
- `games[i]` — access single GameData
- `for game in games` — iterate
- `games.description` — text description of the filter applied
- `played_games_by_player_name()` → `DefaultDict[str, MaccabiGamesStats]`

---

## 3. Stats Modules

Access via properties on `MaccabiGamesStats`:

### `.players` — Player Statistics
- `best_scorers` — top scorers (excludes own goals), returns `List[Tuple[str, int]]`
- `best_scorers_by_freekick` / `_by_penalty` / `_by_head` / `_by_foot`
- `most_played` — most appearances
- `most_unbeaten` — games without loss while playing
- `most_goals_involved` — goals + assists combined
- `most_assists`
- `get_top_scorers_on_last_minutes(from_minute=75)`
- `get_top_players_for_goals_per_game(minimum_games_played=10)`

### `.results` — Results Summary
- `total_games_count`, `wins_count`, `losses_count`, `ties_count`
- `wins_percentage`, `losses_percentage`, `ties_percentage`
- `total_goals_for_maccabi`, `total_goals_against_maccabi`, `total_goals_diff_for_maccabi`
- `goals_ratio` — for/against ratio
- `clean_sheets_count`, `clean_sheets_percentage`

### `.averages` — Per-Game Averages
- `goals_for_maccabi`, `goals_against_maccabi`, `maccabi_diff`

### `.coaches` — Coach Statistics
- `most_trained_coach`, `most_winner_coach`, `most_loser_coach`, `most_tied_coach`
- `most_goals_for_maccabi_coach`, `most_goals_against_maccabi_coach`
- `most_clean_sheet_games_coach`
- `most_games_with_goals_from_bench_coach`

### `.referees` — Referee Statistics
- `most_judged_referee`, `best_referee`, `worst_referee`
- `best_referee_by_percentage`, `worst_referee_by_percentage`

### `.teams` — Opponent Team Statistics
- `teams_ordered_by_maccabi_wins()`, `_by_wins_percentage()`, `_by_losses()`, `_by_ties()`
- `_by_clean_sheets_count()` etc.
- Optional params: `top_teams_count`, `minimum_games_against_team`

### `.streaks` — Team Streak Analysis
- `get_longest_wins_streak_games()` → `MaccabiGamesStats` (the actual streak games)
- `get_current_wins_streak()` → current ongoing streak
- `get_similar_wins_streak_by_length(minimum_streak_length)` → `List[MaccabiGamesStats]`
- Same pattern for: ties, losses, unbeaten, clean sheets, scoring games

### `.players_streaks` — Individual Player Streaks
- `get_players_with_best_scoring_goal_streak()`
- `get_players_with_best_unbeaten_streak()` / `_win_streak()`
- `get_players_with_current_unbeaten_streak()`
- Returns `List[Tuple[str, MaccabiGamesStats]]`

### `.teams_streaks` — Opponent Streak Analysis
- `get_teams_with_best_win_streak()` — opponent wins against Maccabi
- `get_teams_with_current_win_streak()`
- Same for unbeaten, ties, losses, scoring

### `.seasons` — Season-by-Season Analysis
- `get_seasons_stats()` → `List[Tuple[str, MaccabiGamesStats]]`
- Sort methods: `sort_by_wins_count()`, `sort_by_wins_percentage()`, `sort_by_goals_for()`, `sort_by_goals_against()`, `sort_by_games_count()`
- Dict-like access: `seasons["2022/23"]` or `seasons[0]`

### `.comebacks` — Comeback Victories
- `won_from_exactly_one_goal_diff()` / `_two_goal_diff()` / `_x_goal_diff(x)`
- `won_from_any_goal_diff()`

### `.goals_timing` — Fastest Goals
- `fastest_two_goals(top_games_number=5)`, `fastest_three_goals()`, `fastest_four_goals()`
- Returns `List[Tuple[GameData, int]]` (game, minutes to score N goals)

### `.important_goals` — Clutch/Advantage Goals
- `get_top_scorers_for_advantage()` — goals that gave lead
- `get_top_scorers_in_last_minutes(minimum_diff, maximum_diff, from_minute=85)`
- `get_top_scorers_by_percentage_from_all_their_goals(minimum_important_goals=10)`

### `.players_special_games` — Age Milestones
- `youngest_players_by_first_time_to_score()` / `_to_assist()` / `_to_play()`
- `oldest_players_by_first_time_to_score()` / `_to_assist()` / `_to_play()`
- Returns `List[PlayerAgeAtSpecialGame]` with `.player_name`, `.birth_date`, `.time_in_years`

### `.players_first_and_last_games` — Debut/Farewell Performance
- `players_that_scored_at_their_first_game(score_at_least=1)`
- `players_that_scored_at_their_last_game(score_at_least=1)`
- Same for assists

### `.players_categories` — Home Player (Academy) Analysis
- `home_players_goals_count()` / `home_players_goals_ratio()`
- `non_home_players_goals_count()` / `non_home_players_goals_ratio()`

### `.export` — Data Export
- `export_everything_json()` — zip with JSONs

### `.summary` — Display Summary
- `show_summary()`, `show_top_players()`

---

## 4. Data Models

### `GameData` — Single Game
| Property | Type | Description |
|---|---|---|
| `date` | `datetime` | Game date (no time) |
| `competition` | `str` | Hebrew competition name |
| `season_string` | `str` | e.g. `"2022/23"` |
| `stadium` | `str` | Stadium name |
| `crowd` | `str` | Attendance |
| `referee` | `str` | Referee name |
| `home_team` / `away_team` | `TeamInGame` | Both teams |
| `maccabi_team` | `TeamInGame` | Maccabi's side |
| `not_maccabi_team` | `TeamInGame` | Opponent |
| `maccabi_score` | `int` | Maccabi goals |
| `maccabi_score_diff` | `int` | Score differential |
| `is_maccabi_win` | `bool` | Win flag |
| `is_maccabi_home_team` | `bool` | Home flag |
| `league_fixture` | `Optional[int]` | Matchday number |
| `technical_result` | `bool` | Technical result flag |
| `fixture` | `str` | Raw fixture string |
| `goals()` | method | All goals with running scores |
| `json_dict()` | method | Serialization |

### `TeamInGame` — Team in a Specific Game
| Property | Type | Description |
|---|---|---|
| `name` | `str` | Team name as appeared |
| `current_name` | `Optional[str]` | Canonical current name |
| `coach` | `str` | Coach name |
| `score` | `int` | Goals scored |
| `players` | `List[PlayerInGame]` | All squad members |
| `lineup_players` | `List[PlayerInGame]` | Starting XI |
| `players_from_bench` | `List[PlayerInGame]` | Subs who entered |
| `not_played_players` | `List[PlayerInGame]` | Unused subs |
| `played_players` | `List[PlayerInGame]` | Everyone who played |
| `scored_players` | `List[PlayerInGame]` | Scorers |
| `assist_players` | `List[PlayerInGame]` | Assisters |
| `yellow_carded_players` | `List[PlayerInGame]` | Yellow cards |
| `red_carded_players` | `List[PlayerInGame]` | Red/2nd yellow |
| `captain` | `PlayerInGame` | Captain |
| `has_goal_from_bench` | `bool` | Bench goal flag |
| `scored_players_with_amount` | `Counter[str]` | Scorer → goal count |
| `assist_players_with_amount` | `Counter[str]` | Assister → assist count |

### `PlayerInGame` — Player in a Specific Game
| Property | Type | Description |
|---|---|---|
| `name` | `str` | Player name |
| `number` | `int` | Jersey number |
| `events` | `List[GameEvent]` | Events in this game |
| `played_in_game` | `bool` | Started or subbed in |
| `scored` | `bool` | Scored any goal |
| `scored_after_sub_in` | `bool` | Scored after coming on |
| `has_event_type(type)` | method | Check for event |
| `event_count_by_type(type)` | method | Count by event type |
| `goals_count_by_goal_type(type)` | method | Count by goal type |
| `get_events_by_type(type)` | method | Get events of type |

---

## 5. Event Enums

### `GameEventTypes`
```
LINE_UP, BENCHED, GOAL_SCORE, GOAL_ASSIST,
SUBSTITUTION_IN, SUBSTITUTION_OUT,
YELLOW_CARD, FIRST_YELLOW_CARD, SECOND_YELLOW_CARD, RED_CARD,
CAPTAIN, PENALTY_MISSED, PENALTY_STOPPED, UNKNOWN
```

### `GoalTypes`
```
FREE_KICK, PENALTY, HEADER, OWN_GOAL, BICYCLE_KICK,
NORMAL_KICK, CORNER, CHEST, UNCATEGORIZED, UNKNOWN
```

### `AssistTypes`
```
NORMAL_ASSIST, FREE_KICK_ASSIST, CORNER_ASSIST,
THROW_IN_ASSIST, PENALTY_WINNING_ASSIST, UNCATEGORIZED, UNKNOWN
```

### Event Classes
- `GameEvent` — has `event_type: GameEventTypes` and `time_occur: timedelta`
- `GoalGameEvent(GameEvent)` — adds `goal_type: GoalTypes`
- `AssistGameEvent(GameEvent)` — adds `assist_type: AssistTypes`

### MaccabiPedia Cargo Event ID Mapping
```
EventType: 1=LINE_UP, 2=BENCHED, 3=GOAL, 4=ASSIST, 5=SUB_IN, 6=SUB_OUT,
           7.71=YELLOW, 7.72=2ND_YELLOW, 7.73=RED, 8.82=PEN_MISS, 8.83=PEN_STOP, 9=CAPTAIN
GoalTypes (SubType 30-39): 30=NORMAL, 31=HEADER, 32=OG, 33=FREE_KICK, 34=PENALTY, etc.
AssistTypes (SubType 40-46): 40=NORMAL, 41=FREE_KICK, 42=CORNER, 43=THROW_IN, etc.
```

---

## 6. Competition Constants (Hebrew)

```python
LEAGUE_COMPETITIONS = ["ליגת העל", "ליגה לאומית", "ליגת Winner",
                       "ליגת הבורסה לניירות ערך", "ליגה א'", "ליגה א", "הליגה הארצית"]

EUROPE_COMPETITIONS = ["ליגת האלופות", "גביע אירופה לאלופות", "הליגה האירופית",
                       "גביע אופא", ...]  # 13 total

TROPHY_COMPETITIONS = ["גביע המלחמה", "הגביע הארץ ישראלי", "גביע המדינה"]

NON_OFFICIAL_COMPETITIONS = ["ידידות", "מחנה האימונים בארצות הברית",
                              "מחנה האימונים באוסטרליה", "גביע לייבו"]
```

---

## 7. Cargo Integration

The package queries MaccabiPedia's MediaWiki Cargo extension:

- **Endpoint**: `http://www.maccabipedia.co.il/index.php?title=Special:CargoExport&format=json`
- **Pagination**: 5000 items per request via offset
- **Tables queried**:
  - `Football_Games` (joined with `Competitions`, `Stadiums`, `Opponents`) — game metadata
  - `Games_Events` — player events (goals, cards, subs, lineup) with fields: `_pageName, Date, PlayerName, PlayerNumber, Minute, EventType, SubType, Team, Part`
  - `Profiles` — player metadata (DoB, HomePlayer flag)
- **Crawler class**: `MaccabiPediaCargoChunksCrawler(tables_name, tables_fields, join_tables_on, where_condition)`

---

## 8. Bot Integration Patterns

### Event Translation Layer
`packages/maccabipediabot/src/maccabipediabot/common/maccabistats_player_event.py` — `PlayerEvent` class translates maccabistats enums to Hebrew wiki labels:
```python
PlayerEvent.from_maccabistats_event_type(name, number, time_occur,
    GameEventTypes.GOAL_SCORE, GoalTypes.PENALTY, maccabi_player=True)
```

### Data fixes live in maccabistats, not the bot
If a game page comes out wrong (names, stadiums, competitions, events), fix it in maccabistats' own fix layers, not in `gamesbot.py` before upload. They run while the data is parsed and saved, so every consumer gets the fix:
- `parse/name_normalization.py` → `normalize_name()`: every name from the club site passes through it (spaces, RTL marks, geresh → apostrophe).
- `parse/general_fixes.py` → `run_general_fixes()`: source-independent maps (`_stadiums_name_fixes`, `_players_name_fixes`, `_referees_name_fixes`, `_competitions_name_fixes`), team renames (`teams_names_changer.py`), season/fixture formats.
- `parse/maccabi_tlv_site/fix_specific_games.py`: fixes for the club-site source and for single games.
- `parse/maccabi_tlv_site/team_parser.py` / `game_events_parser.py`: how club-site squads and events become `GameEventTypes`.
- `error_finder/`: `ErrorsFinder` for manually finding inconsistent data.

The CI flow is fetch (`fetch_games_from_maccabi_tlv_site`: crawl → general fixes → specific fixes → serialize), then upload (loads the saved data). So anything the bot needs has to be in the saved data.

### Players data (`maccabipedia/players.py` → `MaccabiGamesStats.players_data`)
`MaccabiPediaPlayers` is crawled from MaccabiPedia's Cargo whenever a source is parsed, and pickled with the games, so it's available offline wherever the games are:
- `players_dates` and `home_players`: from `Profiles` (DoB, HomePlayer).
- `goalkeepers`: `Profiles.MainPosition == 1`, so a Maccabi keeper is known from his debut.

This class holds **Maccabi players only**, since `Profiles` has no opponent pages. The uploader looks opponent goalkeepers up itself (`football/opponent_goalkeepers.py`): names with `Games_Events` 111/211 rows in at least 2 games (a single mark may be a mistake), skipping one-word names, so an opponent keeper met for the first time stays unmarked. It marks `הרכב-שוער`/`ספסל-שוער` from both sets.
Anything the uploader needs from the wiki itself belongs here rather than in a new query at upload time.

### Game Upload Flow
1. Load games via `get_maccabi_stats_as_newest_wrapper()` or `load_from_maccabipedia_source()`
2. Iterate `GameData` objects, extract metadata and player events
3. Translate events via `PlayerEvent` wrapper
4. Format into MediaWiki template arguments
5. Create/update wiki pages via pywikibot + mwparserfromhell

### Bot files using maccabistats
- `football/gamesbot.py` — main game page creation
- `football/upload_last_game_to_maccabipedia.py` — latest game upload
- `football/fetch_games_from_maccabi_tlv_site.py` — MaccabiTLV crawling
- `football/sort_players_events.py` — sort events in existing pages
- `football/bots/playersbot.py`, `coachesbot.py`, `teamsbot.py`, `refereesbot.py`, `stadiumsbot.py` — entity page creation
- `maintenance/football/refresh_games.py` — find games with missing events

---

## 9. Concrete Use Cases

### Questions maccabistats can answer
- Who are the all-time top scorers / assisters / most-capped players?
- What's the longest winning/unbeaten streak?
- Which season had the best win percentage?
- Who scored the most clutch goals (last 5 minutes, tying/winning)?
- What's our record against a specific opponent, home vs away?
- Who is the youngest/oldest player to score?
- Which coach has the best win record?
- Which players scored in their debut?
- What are the fastest 3 consecutive goals in a game?
- What's the biggest comeback victory?
- Which referee do we win most under?
- How many goals came from academy (home) players vs imports?

### Automation opportunities
- **Auto-generate stat pages**: season summaries, player career stats, head-to-head records
- **Data validation**: cross-reference wiki game pages against maccabistats data
- **Content enrichment**: add statistical context to player/team pages
- **Maintenance**: find games with missing events or inconsistent data
- **Reports**: periodic stat reports (e.g., after each season)
