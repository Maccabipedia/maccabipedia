--[[
Prints the ONE Cargo query the day block issues for a given date, so it can be
timed against production without any page there invoking the module.

    lua5.1 infra/lua_modules/print_day_query.lua '"2021-08-22"'

Output: tables<TAB>join<TAB>where<TAB>fields, the same triple the module hands
to mw.ext.cargo.query. Compare with the template, which issues 28 queries for
the same page.
]]

package.path = 'infra/lua_modules/tests/?.lua;' .. package.path
local stub = require('stub_mw')
stub.install()

local date = arg[1] or '"2021-08-22"'

-- prime computes all four tabs at once; one query, 24 conditional aggregates.
stub.willReturn({ {} })
local StatsBlock = stub.loadModule('Module:FootballStatsBlock')
pcall(StatsBlock.prime, stub.newFrame({ ['תאריך'] = date },
	{ ['בלוק'] = 'day-results' }))

local call = stub.calls[1]
if not call then
	error('no query was built', 0)
end

print(table.concat({
	call.tables,
	call.options.join or '',
	call.options.where or '',
	call.fields,
}, '\t'))
