--[[
Module:FootballStatsBlock - a football statistics block from one query.

Wiki page: Module:FootballStatsBlock

The renderer lives in Module:StatsBlock, shared by every sport; this page
binds it to football's query module and block data and is the module the
templates invoke, exactly as before:

    {{#invoke:FootballStatsBlock|leaderboards|בלוק=season|עונה=2023/24}}
    {{#invoke:FootballStatsBlock|render|בלוק=day-results}}

The name given here prefixes the page variables `prime` stores and every
error message, so both read as they always did. Documentation:
Module:FootballStatsBlock/תיעוד and .claude/lua_modules.md in the repository.
]]

local Queries = require('Module:FootballQueries')

return require('Module:StatsBlock').new(
	Queries, mw.loadData('Module:FootballStatsBlocks'), 'FootballStatsBlock')
