--[[
Module:FootballQueries - one Cargo query from one filter set, for football.

Wiki page: Module:FootballQueries

The logic lives in Module:SportQueries, shared by every sport; this page binds
it to football's schema (Module:FootballQueries/Fields) and is the module the
templates and the other football modules invoke, exactly as before:

    {{#invoke:FootballQueries|count|שחקן=ערן זהבי|מספר אירוע=3}}

Every entry point (count, query, build, aggregate, leaderboard, gameDataCount,
playerEventCount, aggregateProbe …) comes from the shared module; its error
messages carry the schema's `name`, so they read `FootballQueries: …` as they
always did. Documentation: Module:FootballQueries/תיעוד and
.claude/lua_modules.md in the repository.
]]

return require('Module:SportQueries').new(mw.loadData('Module:FootballQueries/Fields'))
