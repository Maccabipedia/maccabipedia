--[[
Module:FootballSeasonTable - the rows of a "season by season" table, football's.

Wiki page: Module:FootballSeasonTable

The logic lives in Module:SeasonTable, shared by every sport; this page binds it
to football's query module and says what is football's own. The opponent table
and the two referee tables invoke it:

    {{#invoke:FootballSeasonTable|rows|יריבות={{{יריבות לשליפה|}}}}}
    {{#invoke:FootballSeasonTable|rows|שופט={{{שופט|}}}|קישור מפעל=מרכז}}

The name given here prefixes every error message.
Documentation: .claude/lua_modules.md in the repository.
]]

local Queries = require('Module:FootballQueries')

return require('Module:SeasonTable').new(Queries, {
	season = 'Football_Games.Season',
	competition = 'Football_Games.Competition',
	-- Football's three result columns, in the table header's order.
	results = {
		{ key = 'wins', word = 'ניצחון' },
		{ key = 'draws', word = 'תיקו' },
		{ key = 'losses', word = 'הפסד' },
	},
	catalogue = { table = 'Competitions', name = 'OriginalName',
	              league = 'League', trophy = 'Trophy' },
	-- A football season page is `עונת 1959/60`, in the main namespace, and a
	-- competition is its own name.
	seasonLink = 'עונת %s',
	competitionLink = '%s',
	entities = { 'יריבות', 'שופט', 'עוזר שופט' },
	-- The referee tables link a competition through its grouping name.
	concentrated = { table = 'Football_Competitions_Map',
	                 name = 'ConcentratedName', names = 'Names' },
}, 'FootballSeasonTable')
