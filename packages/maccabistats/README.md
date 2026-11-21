# MaccabiStats

MaccabiStats package used to analyze Maccabi Tel-Aviv games data, based on several sites but mostly on [MaccabiPedia](https://maccbaipedia.co.il).
```
pip install maccabistats
``` 

# TL;DR
* In order to work with MaccabiStats package you need to have the serialized Maccabi Tel-Aviv games data, you can get it from [Mega](https://mega.nz/folder/vbgEED7R#0bpotoxTX-ZXGpI8hqbHOA)
Download the latest serialized data, which can be used as:
```
from maccabistats import get_maccabi_stats
maccabi_games = get_maccabi_stats(your_maccabi.games_file_path)  # Use the local path you've downloaded the file from mega.

# maccabi_games object will contains everything you need
```
* In order to use and analyze MaccabiPedia data without the Python package, checkout this [Mega](https://mega.nz/folder/jGww3bbR#5h2-xmjM-e8Dk0jROfnGdQ) link.  
You find inside a zip with the games data and players events in json format.

now, enjoy :)

# Intro

### Loading games
After you've downloaded the last serialized games from [Mega](https://mega.nz/folder/vbgEED7R#0bpotoxTX-ZXGpI8hqbHOA), load it as:
```
from maccabistats import get_maccabi_stats
maccabi_games = get_maccabi_stats(your_maccabi.games_file_path)  # Use the local path you've downloaded the file from mega.
```

### Filtering games
You can filter games by several sub categories, such as: home or away, game result, competition, opponent, etc.
```
>>> maccabi_games = ... (look above)
>>>
>>> home_games = maccabi_games.home_games
>>> away_games = maccabi_games.away_games
>>>
>>> official_games = maccabi_games.official_games
>>>
>>> league_games = maccabi_games.league_games
>>> europe_games = maccabi_games.europe_games
>>>
>>> derby = maccabi_games.get_games_against_team("הפועל תל אביב")
>>> sheran = maccabi_games.get_games_by_played_player_name("שרן ייני")
>>> great_season = maccabi_games.get_games_by_season("1976/77")
>>> # Search for the others 'maccabi_games.get_games*" functions
>>>
>>> old_games = maccabi_games.played_before("2000")
>>> great_team = maccabi_games.played_before("1997").played_after("1993")
>>>
>>> # You can even chain these sub-categories:
>>> home_derby = maccabi_games.home_games.get_games_against_team("הפועל תל אביב")
>>> sheran_europe_away_wins = maccabi_games.europe_games.away_games.get_games_by_played_player_name("שרן ייני").maccabi_wins
>>>
>>> # If you have filtered too much, checkout the description - it's aggregated
>>> maccabi_games.home_games.league_games.get_games_against_team("הפועל חיפה")
>>> 'Source: MaccabiPedia + Home games + League games + Against team: Hapoel Haifa | 64 games | (from 05-12-1931 to 13-12-2020)'
```

MaccabiStats object is based on fluent mechanism, that allows you to get the same object after filtering games for each 'sub-category', like:
```
>>> type(maccabi_games)
>>> 'MaccabiGamesStats'
>>>
>>> home_games = maccabi_games.home_games
>>> type(home_games)
>>> 'MaccabiGamesStats'
>>>
>>> # Same for every other sub-category or any chain of them
```

# Basic Analysis

### Players
When you have your MaccabiGamesStats object, you can check some players statistics for these games:
```
>>> maccabi_games.players.best_scorers[:10]  # This will show you the top 10 scorers
>>> maccabi_games.players.most_unbeaten[:10]  # This will show you the top 10 players with most unbeaten games (from what you've filter) 
```

MaccabiGamesStats has several analysis options - same as ".players" we just saw, all of them are accessible under your object.
Some others general analysis options are:
```
>>> maccabi_games.coaches # Analyze information from coaches perspective
>>> maccabi_games.referees # Analyze information from referees perspective
```

### Streaks
Another option of analysis is to examine streaks, players streaks and teams streaks, this can be used as:
```
>>> # Get the players with best scoring streak - count the game ONLY if the player has played
>>> maccabi_games.players_streaks.get_players_with_best_goal_scoring_streak()
>>> # Same for unbeaten players
>>> maccabi_games.players_streaks.get_players_with_current_unbeaten_streak()
>>>
>>>
>>> # You can analyze teams streaks as well, for example the teams has longest active winning streak against them
>>> maccabi_games.teams_streaks.get_teams_with_current_win_streak()
>>>
>>>
>>> # You can analyze streak from Maccabi perspective as well, like:
>>> maccabi_games.streaks.get_longest_clean_sheet_games()  #  Games in a row without goal against Maccabi
>>>
>>> # If you found interesting streak and you want to see if Maccabi had something similar before, use:
>>> maccabi_games.streaks.get_similar_unbeaten_streak_by_length(minimum_streak_length=20)
>>> maccabi_games.streak.get_similar_* = use to get similar with len of at least X and by condition.
```

### Other analysis options
```
>>> # You can get the craziest maccabi comebacks by:
>>> maccabi_games.comebacks.won_from_exactly_two_goal_diff()
>>> maccabi_games.comebacks.won_from_exactly_x_goal_diff(goals=3)  # Wow!
>>>
>>> # Or getting the fatests 2/3/4 goals Maccabi scored in a game:
>>> maccabi_games.goals_timing.fastest_three_goals()
>>>
>>> # If you want to get a short numeric summary of the results in your filtered games, use:
>>> maccabi_games.results.*
>>>
>>> # In order to analysis Maccabi performance against other teams (non-streak), for example the team Maccabi has the most clean sheets games against:
>>> maccabi_games.teams.teams_ordered_by_maccabi_clean_sheets_count()
```

# Advanced Analysis

### Seasons
You can group the filtered games by season and sort the seasons by any condition, like:
```
>>> seasons = maccabi_games.seasons.get_seasons_stats()  # At default the season will be sorted by year.
>>> seasons.sort_by_wins_percentage()  # Sort the season by winning percentage, you should print the season object).
>>> seasons  # Print it
```

### Players advanced analysis
In order to find the oldest\youngest players by the first time they scored\assist\played, use:
```
>>> maccabi_games.players_special_games.oldest_players_by_first_time_to_assist()
```

In order to find the the players that scored\assist in their first\last games, use:
```
>>> # Find the players that scored twice in their first game
>>> maccabi_games.players_first_and_last_games.players_that_scored_at_their_first_game(score_at_least=2)
>>> # Reminder, you can search for the players that scored twice in their first away game using:
>>> maccabi_games.away_games.players_first_and_last_games.players_that_scored_at_their_first_game(score_at_least=2)
```  

If you are interested in the home players part in the statistics, check out this:
```
>>> maccabi_games.players_categories.home_players_goals_count()
>>> # Or finding their % from the total goals on europe
>>> maccabi_games.europe_games.players_categories.home_players_goals_ratio()
```

Sometimes it's very useful to measure which player contribute the most in the "money time", to do so, use:
```
>>> # Who are the top scorers - when we count only goals that made Maccabi to lead
>>> maccabi_games.important_goals.get_top_scorers_for_advantage()
>>> # Who did that on derby?
>>> maccabi_games.get_games_against_team("הפועל תל אביב").important_goals.get_top_scorers_for_advantage()
>>>
>>> # Who scored the most in the last 5 minutes? including removal of "non-important" goals - you can change the range
>>> maccabi_games.important_goals.get_top_scorers_in_last_minutes(minimum_diff_for_maccabi=-1, maximum_diff_for_maccabi=1, from_minute=85)
```

# Basketball

Basketball sits next to football in `maccabistats.basketball`; football's API above is unchanged.

```python
from maccabistats import load_basketball_from_maccabipedia, serialize_basketball_games, get_basketball_stats

basketball_games = load_basketball_from_maccabipedia()  # Crawls MaccabiPedia, with the players' box scores
serialize_basketball_games(basketball_games)  # To the home folder, under maccabistats/basketball
basketball_games = get_basketball_stats()  # The newest pickle this maccabistats version wrote
```

### Filtering and results

Filters return a new object, so they chain like the football ones.

```python
basketball_games.league_games.home_games.maccabi_wins
basketball_games.international_games.get_games_against_team("ריאל מדריד").results.wins_percentage  # 0 to 1
basketball_games.get_games_by_season("2003/04").get_games_by_played_player_name("טל בורשטיין")
basketball_games.overtime_games.played_after("2000-01-01")

basketball_games.results.biggest_wins(5)
basketball_games.streaks.get_longest_wins_streak_games()
basketball_games.opponents  # Maccabi's record against each opponent; also .coaches and .seasons
```

The names follow football's where the idea is the same (`played_before` and `played_after` include the day itself, `wins_percentage` is a fraction). What differs: competition filters read the wiki's competition flags, so football's `europe_games` is `international_games` here, and there is `neutral_games` and `overtime_games`.

A streak is a run of consecutive games of the filtered collection, so `league_games.streaks` ignores the cup games in between. A game with no result neither breaks a streak nor adds to it.

Points totals leave out awarded (technical) games: their score fields hold the official 20:0, not points from the court.

### Players

```python
basketball_games.players.most_played
basketball_games.players.best_scorers  # Also best_rebounders, best_assisters
basketball_games.players.get_players_total("steals")
basketball_games.players.get_best_single_games("points", limit=10)
```

Every total is `(name, value, games_with_data)`: `games_with_data` is the number of the player's games in which that stat is known for him. Old box scores have the points and little else, so read a total next to it.

### A game

```python
game = basketball_games.played_at("2004-05-01")[0]  # Games are sorted by date; one with no date is last
game.maccabi.score, game.opponent_team.score, game.maccabi.quarters, game.overtimes_played
game.is_maccabi_win, game.is_home
game.competition_flags  # The competition's flags (is_league, ...), or None when it has no catalog row
game.maccabi.players, game.maccabi.has_recorded("assists")
```

A value the wiki does not have is `None` (never 0), and a game stored as 0:0 has no result. In an awarded (technical) game the technical flag decides the result, as on the wiki.

### Errors finder

Like the football one: every `get_*` method is one check.

```python
from maccabistats import BasketballErrorsFinder

finder = BasketballErrorsFinder(basketball_games)
finder.get_games_missing_overtime()  # Periods tie, the final score does not, no overtime points
finder.find_all()  # Every check, keyed by its name
```

`python -m maccabistats.github_actions_scripts.find_basketball_errors --out errors.tsv` runs them all on MaccabiPedia.

# Export data
If you want to export the current object MaccabiGamesStats you work on, use:
```
>>> maccabi_games.export.export_everything_json()
>>> # You will get a zip with some jsons and a readme - check it out  
```

# Internal & Dev

### Crawling maccabi games

When crawling maccabi games each page will be saved on your disk to allow optimization for the next time.
To serialize maccabi games (it might take some time), use:
```
>>> from maccabistats import serialize_maccabi_games
# The object will be serialized to home folder (%userprofile%) with its version and the current date.
>>> serialize_maccabi_games(maccabi_games_stats_object)
```

Manual-fixes will be run after crawling is finished and before serializing to disk.

You can 'use_multi-process-crawl' from settings to allow multi-processing,  
BUT atm logging does not support multi-processing, so don't use that if you need to debug.


### Manual fixes

There are some information that need to be fix manually.  
When serializing maccabi games that done automatically.
If you Add anything to run_general_fixes, you can re-run it by:
```
>>> from maccabistats import get_maccabi_stats, run_general_fixes, serialize_maccabi_games
>>> 
>>> games = get_maccabi_stats()
>>> new_games = run_general_fixes(games)
>>> serialize_maccabi_games(new_games)
```

### Logging

All of the log files will be saved at 'maccabistats\logs' folder under the user home folder (%userprofile%)
There are several log files, each one has this pattern - maccabistats-{suffix}.log (at the mentioned folder): 

* all - save all log levels
* info - save just the info log level
* warning - save just the warn log level
* exception - save just exceptions (log.exception)
* stdout - not a file but log handler that print to stdout (info level +) 

### Optimization 
* You can use 'use-disk-to-crawl-when-available' to crawl from disk when available, each page that will be crawled from internet wil be save on disk. 
* You can reduce logging when crawling by use :
```
>>> from maccabistats import faster_logging
>>> faster_logging() will disable the stdout & debug handlers.
```

### Errors Finder

Manual check for errors might be helpful, this is can be done by:
```
>>> from maccabistats import get_maccabi_stats
>>> from maccabistats.error_finder.error_finder import ErrorsFinder
>>> games = get_maccabi_stats()
>>> e = ErrorsFinder(games)
>>> e.get_all_errors_numbers()  # run all the manual errors exists
```

### Known issues

* Ignoring events after 120 min (in game_events_parser -> fully_game_time_without_penalties)
* Logging with multi-process crawling mode isn't working.

### MaccabiPedia Source

You can manipulate [MaccabiPedia](http:\\www.maccabipedia.co.il) data by downloading it and then loading it 
(You may have to install some 'advanced' packages such as pywikibot), as the following:

```
>>> from maccabistats import run_maccabipedia_source
>>>
>>> # You should run this once a while, this is a heavy action to do:
>>> maccabipedia = run_maccabipedia_source()
>>> # Now you can manipulate maccabipedia data as explain above (its MaccabiGamesStats object, referred as "games" above") 
```
