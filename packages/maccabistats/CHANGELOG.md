## Version 2.69 ##

    Validate the CargoExport response shape before iterating it, and log the raw body
    when it is wrong. The `Accept: application/json` header added in 2.68 did stop the
    HTTP 415s, but some crawls still receive a 200 whose body parses as a bare JSON
    string rather than a row array - an edge/WAF block page. That previously surfaced
    far from its cause as "'str' object has no attribute 'items'"; it now raises a
    ValueError naming the real problem and logs the response body, server and
    content-type so the block can be reported to the host.

## Version 2.68 ##

    Send an explicit `Accept: application/json` header on every maccabipedia Cargo
    request. The host's Imunify360 WAF returns HTTP 415 to the default wildcard `*/*`
    Accept header for datacenter IPs, which was failing scheduled crawls. MediaWiki
    ignores Accept (format is set by `&format=json`), so responses are unchanged.

## Version 2.67 ##

    Skip unfinished maccabi-tlv.co.il matches in the season crawler so the football
    games-uploader workflow can no longer publish a wiki page mid-match. A match
    is considered finished iff the per-match top banner does NOT carry the `live`
    CSS class — set throughout the match (including half-time and stoppage) and
    stripped the moment the final whistle is logged. Missing banner is treated as
    unfinished so a future site rename fails loudly.

## Version 2.66 ##

    Retry MaccabiPedia Cargo Export requests on transient 5xx/4xx (415, 429, 500-504) via
    a requests.Session with urllib3.Retry, so daily jobs survive the brief openresty blips
    that take the site off-nginx (CI runs 24473693887 and 24685264058).

## Version 2.65 ##

    Retry maccabi-tlv.co.il game page fetches on transient 5xx errors via a
    requests.Session mounted with urllib3.Retry, so a single server hiccup no
    longer aborts the whole season crawl (CI run 24640051609).

## Version 2.64 ##

    Remove stale debug logging block in parse.general_fixes (TODO: delete me).

## Version 2.63 ##

    Add HEADER_ASSIST to AssistTypes and map MaccabiPedia subtype 47 (בישול-נגיחה) to it.
    Add best_assisters_by_header stat to PlayersStats.

## Version 2.62 ##

    Add best_scorers_in_one_game(score_at_least) and best_assisters_in_one_game(assist_at_least)
    to rank players by how many games they scored/assisted at least N goals (e.g. hattrick kings)

## Version 2.61 ##

    Replace hardcoded Windows paths with configurable MACCABISTATS_DATA_DIR env var (defaults to ~/maccabistats/)

## Version 2.60 ##

    Include players data in MaccabiGamesStats pickle for offline loading
    MaccabiPediaPlayers singleton is now cached in the pickle, so loading works without internet access

## Version 2.53 ##

    Add 3 new ErrorsFinder checks: sub-out without playing, same player on both teams, duplicate events

## Version 2.52 ##

    Ignore EventType=13 (display-only events) from MaccabiPedia parser

## Version 2.51 ##

    Support crawling season 2025/26, use higher timeout

## Version 2.50 ##

    Minimum python version changed from 3.7 to 3.11 

## Version 2.42 ##

    Support export maccabistats data to csv 

## Version 2.41 ##

    Add more name aliases for Ligat Haal 

## Version 2.39 ##

    Adapt to MaccabiPedia with MediaWIki 1.35 (new cargo version)

## Version 2.38.1 ##

    Use new MaccabiPedia page format (no spaces)
    Fix player names

## Version 2.38.0 ##

    Better support teams with multiple names in timeline

## Version 2.37.0 ##

    Support second yellow change from MaccabiPedia

## Version 2.36.0 ##

    Fix player goals involved calculations
    Adapt to new Maccabipedia Cargo tables format

## Version 2.35.0 ##
    Coaches stats fixes
    New Ligat Haal sponser support

## Version 2.34.0 ##
    Add new Goal sub-type (Corner)
    Add new errors types for ErrorsFinder

## Version 2.33.0 ##
    New Github Action that upload the latest MaccabiPedia games data to our FTP server (to be used by the Telegram bot)

## Version 2.32.0 ##
    Created a Github Actions that find the errors from MaccabiPedia and sends them to our Telegram group

## Version 2.31.0 ##
    Find the players that used to be captains (youngest + oldest)

## Version 2.30.0 ##
    Add streaks that count on player+specific team, for example what is the longest streak of unbeaten player against a specific team (any team)?

## Version 2.29.0 ##
    Add Transfermarkt partial source, used to valudate which players played in a game (useful from 1990~+)

## Version 2.28.0 ##
    Add error monitoring for players who scored without playing
    Support uncategorized goal and assist (new in maccabipedia)
    Support comparing assist types when comparing MaccabiGamesStats
    Fix technical games parsing issue

## Version 2.27.0 ##
    Support exporting of game data (in addition of players events data)
    Add AssistType and AssistGameEvent
    
    2.27.2:
    Use minutes instead of HH:MM:SS in the exported file

## Version 2.26.0 ##
    Allow to export MaccabiGamesStats in flatten format (each player event is a record, multiple events for a game) - csv\json.
    - Change the minimum required python version to be 3.7 (we use dataclass)
    - Remove the need for the settings.ini, use pure python config

## Version 2.24.0 ##
    Make sure that maccabistats can be installed on fresh virtualenv.
    - Change the minimum required python version to be 3.7 (we use dataclass)
    - Remove the need for the settings.ini, use pure python config

## Version 2.23.0 ##
    Added goals timing (which games are with the fatest 2-3-4 goals for maccabi?)
    Changed the .games mega link

## Version 2.22.0 ##
    Created a summary object to show all the streaks, players stats and players_streaks in the current MaccabiGamesStats

## Version 2.20.0 ##
    Type annotations for most of the code

## Version 2.17.0 ##
    Add coach statistics

## Version 2.16.0 ##
    Added statistics about home-players part in: goals/assists/goals involved.
    Allow to sort the seasons by this stats

## Version 2.15.0 ##
    Added ability to checks player stats for "goals after sub-in"

## Version 2.14.0 ##
    Added Bicycle-Kick support

## Version 2.13.1 ##
    Added maccabiGamesStats.official_games(), return all the competitions without "friendly games"

## Version 2.13.0 ##
    Support technical games + penalty-stop event

## Version 2.12.0 ##
    Adds the ability to check which players satisfy a condition on their first/last game, like: "Which players scored on their first game?"

## Version 2.11.0 ##
    Adds the ability to query: "Top players by most games in a row"

## Version 2.10.0 ##
    Adds the ability to get the most young\old players with some game activity (goal/assist/played)

## Version 2.9.2 ##
    Allow to send conditions to the MaccabiPediaCrawler

## Version 2.9.1 ##
    Add hebrew "repr" to MaccabiGamesStats

## Version 2.9.0 ##
    Add "to_json" to the result class

## Version 2.8.0 ##
    Add scripts folder, used to save&run some more complicated manipulations.

## Version 2.7.0 ##
    Add Teams statistics.

## Version 2.6.0 ##
    Add Teams streak.
    Add "current" streak (running streaks) for general, players and teams streaks.
    Add players events summary (for maccabipedia tracking).

## Version 2.4.0 ##
    Add players_streaks, check the best players by any streak that possible on MaccabiGamesStats.

## Version 2.2.2 ##
    Stadiums names fixes.

## Version 2.2.0 ##
    Internal changes (move half parsed goals parsing from general fixes to maccabi tlv site parsing).

## Version 2.1.5 ##
    Add option to json maccabi games stats objects.

## Version 2.1.4 ##
    Changed game.is_maccabi_home_team to be property (found by: games with opponent named "Maccabi tel aviv").

## Version 2.1.3 ##
    Moved manual_fixes to maccabistats.parse (and named general_fixes).
    Add many teams name changes (with and without years range).

## Version 2.1.2 ##
    Fix some games dates.

## Version 2.1.0 ##
    Fix some games dates.

## Version 2.0.0 ##
    Supports table maccabi games source, combines all sources outputs to one maccabiGamesStats object (maccabitlv-site & table).

## Version 1.10.1 ##
    Replaced mega.nz link

## Version 1.10.0 ##
    "Solved" many goals without owner, carry them from the parsing time and trying to relate them after all the game is parsed.
    Allow more date formats as inputs.
    Fix competitions names for maccabipedia.
    Add 'ErrorsFinder' class to find errors (run manually).
    Add Important goals statistics! (maccabi_games_stats.important_goals).
    Add Graphs! (maccabi_games_stats.graphs).

## Version 1.9.1 ##
    Read readme.md file as utf-8

## Version 1.9.0 ##
    Change lot of players names with manual-fixes for maccabipedia.
    Adapt season to be with "/" instead of "-" for maccabipedia.
    Add get similar streaks for showing streaks with at least of len X by given condition.

## Version 1.8.0 ##
	Add to manual_fixes player names fix to adapt players names to maccabipedia.
	Add MaccabiGamesStats.get_players_by_name to search for similar player names.
	Add lxml to requirement for faster parsing.
	Creating the folders from settings that responsible for saving the html files, only if not exists.

	Add comeback statistics! (MaccabiGamesStats.comebacks).
	Add to manual_fixes - fix specific games - most of them games which should count one opponent goal as own goal,
	    The parsing from maccabi fail to parse this.

	Add support for seasons statistics! (MaccabiGamesStats.seasons).

## Version 1.7.1 ##
	Added all ref (to manual_fixes) saw with NamingErrorFinder.

## Version 1.7.0 ##
	Support multi-process crawling - faster, but logging is not process-safe, so dont use them with this mode.

## Version 1.6.5 ##
	Add season identifier for each game.
	Change "ליגת לאומית" to "ליגה לאומית" in manual fixes.

## Version 1.6.4 ##
	Allow using lxml parser for beautiful soup (in settings).

## Version 1.6.3 ##
	Normalize coaches and opponents names.

## Version 1.6.2 ##
	Print msg to user when get_maccabi_stats() cant find any file.

## Version 1.6.1 ##
	Fix lot of referees naming using manual fixes

## Version 1.6.0 ##

	Add manual fixes (each one will be added using the data improvement classes (atm namingErrorFinder).
	using the NamingErrorFinder - fix almost every player naming error,
	by adding name normalization to the squad page parser.

## Version 1.5.1 ##

	Bug-fix: removed maccabi.games from manifest.in

## Version 1.5.0 ##

	Add logging handlers.
	Add faster logging.
	Add name normalization for all (players, referees, coaches ...).
	Fixed bug when crawling new games (saved events page as squad on disk).
	Removed maccabi.games from repo.

## Version 1.4.0 ##

	Allow to crawl maccabi-tlv site from disk if available. updated game to 14/03/18

## Version 1.3.0 ##

	Add useful imports to maccabistats.__init__.
	average -> averages.
	Fix bug of empty maccabi_game_stats object when getting players stats.
	Add referees stats (similar to coaches).
	Add tie streak to streaks.py.
	Add change-log.
	Add most:
		winner, loser, unbeaten, clean-sheet (not maccabi team scored 0 goals).
		to players stats, all is calculated by games scores.
	Add game.events to get all events (both teams) ordered by time_occur.

## Version 1.2.0 ##

	This version created just to reupload to pypi

## Version 1.1.0 ##

	## Summary ##
	
		Support getting all available opponents (from filtered games)
		TeamInGame & GameData is jsonable !
		Enable logging on linux
		require py3+

## Version 1.0.0 ##

	## Summary ##
	
		Support getting all available competitions (from filtered games)
	
	## Filtering ##
	
		Support filtering maccabi games by:
			* Home games
			* Away games
			* Game played date
			* Competition
			* Wins
			* First league games
	
		Support finding maccabi games (also filtered) *longest* streaks by:
			* Wins
			* Unbeaten
			* Score at least X goals
			* Score Exactly X goals
			* Game score diff at least X
			* Game score diff exactly X
			* Clean Sheet
			* Lambda condition
			
		Support finding maccabi games (also filtered) top players that match condition, like:
			* Best scorers
			* Scorers by free-kick
			* Scorers by head
			* Scorers by own goals
			* Best assisters
			* Got yellow card
			* Got red card
			* Substitute in
			* Substitute out
			* Played as captain
			* Most played
			
		Support finding maccabi games (also filtered) top coaches that match condition, like:
			* Most Trained
			* Most winner
			* Most winner by percentage
			* Most loser
			* Most loser by percentage
			
			
	
	## Configuration ##
	
		Support crawling maccabi-tlv.co.il site for football games (since 1949 atm).
		Support crawling games from pre-saved html files from disk.
