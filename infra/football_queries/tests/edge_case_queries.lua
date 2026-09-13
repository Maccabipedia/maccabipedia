--[[
Prints the SQL Module:FootballQueries builds for each edge case.

The local wiki holds only 2021/22-2024/25, and every one of these cases lives
in the old data, so they cannot be rendered locally. Instead this prints the
exact query the module would issue and verify_edge_cases.py runs it against
production read-only, comparing it with an independently written expectation.

    lua5.1 infra/football_queries/tests/edge_case_queries.lua

Output is one line per case: name<TAB>tables<TAB>join<TAB>where<TAB>fields
]]

package.path = 'infra/football_queries/tests/?.lua;' .. package.path
local stub = require('stub_mw')

-- Alias expansion issues its own query; these are the names production
-- actually stores for the two clubs, so the expansion is fed real values.
local ALIASES = {
	['בית"ר ירושלים'] = { { name = 'בית"ר ירושלים' } },
	["צ'לסי"] = { { name = "צ'לסי" } },
}

local cases = {}

local function addCase(name, shared, cells, aliasFor)
	cases[#cases + 1] = {
		name = name, shared = shared, cells = cells, aliasFor = aliasFor,
	}
end

-- 1. Opponents carrying a quote, each spelling separately.
addCase('opponent-double-quote-list', { ['יריבות'] = 'בית"ר ירושלים' }, nil)
addCase('opponent-apostrophe-list', { ['יריבות'] = "צ'לסי" }, nil)
addCase('opponent-double-quote-alias', { ['יריבה'] = 'בית"ר ירושלים' }, nil,
	'בית"ר ירושלים')
addCase('opponent-apostrophe-alias', { ['יריבה'] = "צ'לסי" }, nil, "צ'לסי")

-- 2. A player whose name appears on both teams in one game: only Maccabi's
-- events may count.
addCase('player-on-both-teams', { ['שחקן'] = 'אברהם לוי' }, nil)
addCase('player-on-both-teams-opponent-side',
	{ ['שחקן'] = 'אברהם לוי', ['מכבי'] = 'לא' }, nil)

-- 3. One subtype from each main event category.
for _, pair in ipairs({ { '1', '111' }, { '2', '211' }, { '3', '35' },
                        { '4', '41' }, { '7', '71' }, { '8', '81' },
                        { '13', '131' } }) do
	addCase('subtype-' .. pair[1] .. '-' .. pair[2],
		{ ['מספר אירוע'] = pair[1], ['תת אירוע'] = pair[2] }, nil)
end

-- The exclusion form, which drops NULL subtypes as well - 79% of all events.
addCase('subtype-excluded', { ['מספר אירוע'] = '3',
                              ['ללא תת אירוע'] = '35' }, nil)

-- 4. Games with no events at all: a game-grain cell must still count them,
-- an event-grain cell must not.
addCase('eventless-games-by-grain', { ['עונה'] = '1951/52' }, {
	{ name = 'games', filters = {}, grain = 'game' },
	{ name = 'events', filters = { ['מספר אירוע'] = '3' }, grain = 'event' },
})
addCase('technical-results', { ['עונה'] = '1951/52' }, {
	{ name = 'games', filters = {}, grain = 'game' },
})

for _, case in ipairs(cases) do
	stub.install()
	if case.aliasFor then
		stub.willReturn(ALIASES[case.aliasFor])
	end
	local FootballQueries = stub.loadModule()

	local ok, result
	if case.cells then
		-- aggregate runs the query itself, so capture what it asked for.
		stub.willReturn({ { c1 = '0', c2 = '0' } })
		ok, result = pcall(FootballQueries.aggregate, case.shared, case.cells)
		if ok then
			local call = stub.calls[#stub.calls]
			result = {
				tables = call.tables, join = call.options.join,
				where = call.options.where, fields = call.fields,
			}
		end
	else
		ok, result = pcall(FootballQueries.build, case.shared)
		if ok then
			result.fields = 'COUNT(*)=n'
		end
	end

	if not ok then
		print(string.format('%s\tERROR\t\t%s\t', case.name, tostring(result)))
	else
		print(string.format('%s\t%s\t%s\t%s\t%s', case.name, result.tables,
			result.join or '', result.where, result.fields))
	end
end
