--[[
Module:BasketballStatsBlock - a basketball statistics block from one query.

Wiki page: Module:BasketballStatsBlock

The renderer lives in Module:StatsBlock, shared by every sport; this page
binds it to basketball's query module and block data. The leaderboard tabs
of every basketball page invoke it:

    {{#invoke:BasketballStatsBlock|leaderboardTab|בלוק=leaderboards|תיבה=נקודות
      |קטגוריית מפעל=ליגה|כמות=10|עונה=…}}

The name given here prefixes the page variables and every error message.
Documentation: .claude/lua_modules.md in the repository.
]]

local Queries = require('Module:BasketballQueries')

return require('Module:StatsBlock').new(
	Queries, mw.loadData('Module:BasketballStatsBlocks'), 'BasketballStatsBlock')
