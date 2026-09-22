--[[
Module:BasketballQueries - one Cargo query from one filter set, for basketball.

Wiki page: Module:BasketballQueries

The logic lives in Module:SportQueries, shared by every sport; this page binds
it to basketball's schema (Module:BasketballQueries/Fields). The sport's
statistics templates and Module:BasketballStatsBlock go through it.
Documentation: .claude/lua_modules.md in the repository.
]]

return require('Module:SportQueries').new(mw.loadData('Module:BasketballQueries/Fields'))
