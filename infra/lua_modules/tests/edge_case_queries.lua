--[[
Prints the SQL Module:FootballQueries builds for each edge case.

The local wiki holds only 2021/22-2024/25, and every one of these cases lives
in the old data, so they cannot be rendered locally. Instead this prints the
exact query the module would issue and verify_edge_cases.py runs it against
production read-only, comparing it with an independently written expectation.

    lua5.1 infra/lua_modules/tests/edge_case_queries.lua

Output is one line per case: name<TAB>tables<TAB>join<TAB>where<TAB>fields
]]

package.path = 'infra/lua_modules/tests/?.lua;' .. package.path
local stub = require('stub_mw')

-- Alias expansion issues its own query; these are the names production
-- actually stores for the two clubs, so the expansion is fed real values.
local ALIASES = {
	['בית"ר ירושלים'] = { { name = 'בית"ר ירושלים' } },
	["צ'לסי"] = { { name = "צ'לסי" } },
	-- One club, three spellings across its history, all under the canonical
	-- name מ.ס. אשדוד (משוכלל). Production has 1 game under the first, 81
	-- under the second and 11 under the third, so a page that asks about any
	-- one of them must be answered for all 93.
	['מכבי עירוני אשדוד'] = {
		{ name = 'הפועל אשדוד' },
		{ name = 'מ.ס. אשדוד' },
		{ name = 'מכבי עירוני אשדוד' },
	},
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
-- A club stored under several names through its history: asking by the rarest
-- spelling (11 games) must answer for the whole club (93).
addCase('opponent-many-historical-names',
	{ ['יריבה'] = 'מכבי עירוני אשדוד' }, nil, 'מכבי עירוני אשדוד')

-- 2. The same player NAME on both teams IN ONE GAME. Pinned to that one game
-- by its date, because career totals would not show the confusion: on
-- 1986-05-24 אלון נתן has 2 events for Maccabi and 1 against, and on
-- 1975-03-01 אברהם לוי has 2 and 2.
addCase('same-name-both-teams-maccabi',
	{ ['שחקן'] = 'אלון נתן', ['תאריך'] = '1986-05-24' }, nil)
addCase('same-name-both-teams-opponent',
	{ ['שחקן'] = 'אלון נתן', ['תאריך'] = '1986-05-24',
	  ['מכבי'] = 'לא' }, nil)
addCase('same-name-both-teams-even-split',
	{ ['שחקן'] = 'אברהם לוי', ['תאריך'] = '1975-03-01' }, nil)

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

-- 4. Metadata queries - wins, draws, goals - which are about the game and not
-- about any player. They must count games that have no events at all and
-- technical results, and must not join the events table to do it. 1941/42 has
-- 31 games, 6 of them eventless and 1 technical, and its results split 24/3/4.
addCase('metadata-wins', { ['עונה'] = '1941/42',
                           ['תוצאה'] = 'ניצחון' }, nil)
addCase('metadata-draws', { ['עונה'] = '1941/42', ['תוצאה'] = 'תיקו' }, nil)
addCase('metadata-losses', { ['עונה'] = '1941/42', ['תוצאה'] = 'הפסד' }, nil)
addCase('metadata-results-in-one-query', { ['עונה'] = '1941/42' }, {
	{ name = 'wins', filters = { ['תוצאה'] = 'ניצחון' }, grain = 'game' },
	{ name = 'draws', filters = { ['תוצאה'] = 'תיקו' }, grain = 'game' },
	{ name = 'losses', filters = { ['תוצאה'] = 'הפסד' }, grain = 'game' },
	{ name = 'all', filters = {}, grain = 'game' },
})

-- The same season mixing a metadata cell with a player-event cell: the games
-- with no events must still be counted by the first.
addCase('metadata-and-events-together', { ['עונה'] = '1941/42' }, {
	{ name = 'games', filters = {}, grain = 'game' },
	{ name = 'goals', filters = { ['מספר אירוע'] = '3' }, grain = 'event' },
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
