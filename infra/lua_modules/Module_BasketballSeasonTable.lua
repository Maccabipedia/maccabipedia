--[[
Module:BasketballSeasonTable - the rows of a "season by season" table, basketball's.

Wiki page: Module:BasketballSeasonTable

The logic lives in Module:SeasonTable, shared by every sport; this page binds it
to basketball's query module and says what is basketball's own. The opponent
pages' table invokes it:

    {{#invoke:BasketballSeasonTable|rows|יריבות={{{יריבות לשליפה|}}}}}

Two things differ from football beyond the table names: basketball has no draw,
so the table is wins and losses; and its season and competition pages live in
the `כדורסל:` namespace, which the row template wrote out per row.

The name given here prefixes every error message.
Documentation: .claude/lua_modules.md in the repository.
]]

local Queries = require('Module:BasketballQueries')

return require('Module:SeasonTable').new(Queries, {
	season = 'Basketball_Games.Season',
	competition = 'Basketball_Games.Competition',
	results = {
		{ key = 'wins', word = 'ניצחון' },
		{ key = 'losses', word = 'הפסד' },
	},
	catalogue = { table = 'Basketball_Competitions', name = 'OriginalName',
	              league = 'League', trophy = 'Trophy' },
	-- The row template wrote `כדורסל: עונת X` and `כדורסל: C`, with the space
	-- after the colon that MediaWiki normalises away. Kept as it wrote them.
	seasonLink = 'כדורסל: עונת %s',
	competitionLink = 'כדורסל: %s',
	entities = { 'יריבות' },
	-- basketball's schema declares no defaultLimit, so the limit is named here;
	-- the query layer raises rather than truncate when a result reaches it.
	limit = 5000,
}, 'BasketballSeasonTable')
