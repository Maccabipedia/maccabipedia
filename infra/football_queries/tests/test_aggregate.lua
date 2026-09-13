--[[
Tests for the merge primitive: every cell of a block from one query.

This is the piece the whole design exists for - 32 queries become 1 - and it is
also where a wrong number hides best, because a conditional aggregate that
filters on the wrong thing still returns a plausible integer.

Run from the repository root:
    lua5.1 infra/football_queries/tests/test_aggregate.lua
]]

package.path = 'infra/football_queries/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0

local function check(name, body)
	stub.install()
	local ok, message = pcall(body, stub.loadModule())
	if ok then
		passed = passed + 1
	else
		failed = failed + 1
		print(string.format('FAIL  %s\n        %s', name, tostring(message)))
	end
end

local function equals(actual, expected, what)
	if actual ~= expected then
		error(string.format('%s\n        expected: %s\n        actual:   %s',
			what or 'mismatch', tostring(expected), tostring(actual)), 0)
	end
end

local function expectError(pattern, body)
	local ok, message = pcall(body)
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find(pattern, 1, true) then
		error(string.format('error did not mention "%s": %s',
			pattern, tostring(message)), 0)
	end
end

-- The real block: eight cells, each a different event or subtype.
local PLAYER_CELLS = {
	{ name = 'appearances', filters = { ['מספר אירוע'] = '1,5' } },
	{ name = 'substitutions', filters = { ['מספר אירוע'] = '5' } },
	{ name = 'goals', filters = { ['מספר אירוע'] = '3' } },
	{ name = 'penaltyGoals',
	  filters = { ['מספר אירוע'] = '3', ['תת אירוע'] = '35' } },
	{ name = 'assists', filters = { ['מספר אירוע'] = '4' } },
	{ name = 'yellows',
	  filters = { ['מספר אירוע'] = '7', ['תת אירוע'] = '71' } },
	{ name = 'reds',
	  filters = { ['מספר אירוע'] = '7', ['תת אירוע'] = '72,73' } },
	{ name = 'benchStarts', filters = { ['מספר אירוע'] = '2' } },
}

check('a whole block is one query', function(FootballQueries)
	stub.willReturn({ { c1 = '220', c2 = '29', c3 = '150', c4 = '35',
	                    c5 = '29', c6 = '35', c7 = '1', c8 = '32' } })
	local cells = FootballQueries.aggregate(
		{ ['שחקן'] = 'ערן זהבי', ['קטגוריית מפעל'] = 'ליגה' }, PLAYER_CELLS)

	equals(#stub.calls, 1, 'exactly one query for eight cells')
	equals(cells.appearances, 220, 'appearances')
	equals(cells.goals, 150, 'goals')
	equals(cells.benchStarts, 32, 'benchStarts')
end)

check('each cell becomes its own conditional aggregate', function(FootballQueries)
	stub.willReturn({ { c1 = '1', c2 = '2' } })
	FootballQueries.aggregate({ ['שחקן'] = 'ערן זהבי' }, {
		{ name = 'goals', filters = { ['מספר אירוע'] = '3' } },
		{ name = 'assists', filters = { ['מספר אירוע'] = '4' } },
	})
	equals(stub.calls[1].fields,
		'SUM(CASE WHEN Games_Events.EventType IN (3) THEN 1 ELSE 0 END)=c1,'
		.. 'SUM(CASE WHEN Games_Events.EventType IN (4) THEN 1 ELSE 0 END)=c2',
		'fields')
end)

-- The A4 finding: derive these from the shared filters alone and the merge
-- silently counts the opponent's events and drops a needed join.
check('the Team constraint stays in the WHERE, once', function(FootballQueries)
	stub.willReturn({ { c1 = '1' } })
	FootballQueries.aggregate({ ['שחקן'] = 'ערן זהבי' }, {
		{ name = 'goals', filters = { ['מספר אירוע'] = '3' } },
	})
	equals(stub.calls[1].options.where,
		'Games_Events.PlayerName = "ערן זהבי" AND Games_Events.Team = 1',
		'where')
	-- and not repeated inside the cell
	equals(stub.calls[1].fields:find('Team', 1, true), nil, 'not in fields')
end)

check('a table only a cell mentions is still joined', function(FootballQueries)
	stub.willReturn({ { c1 = '1' } })
	-- The shared filters touch only Football_Games; the cell needs the events
	-- table, so the join has to come from the union.
	FootballQueries.aggregate({ ['עונה'] = '2021/22' }, {
		{ name = 'goals', filters = { ['מספר אירוע'] = '3' } },
	})
	equals(stub.calls[1].tables, 'Football_Games,Games_Events', 'tables')
	equals(stub.calls[1].options.join,
		'Football_Games._pageID = Games_Events._pageID', 'join')
end)

check('the shared filters still constrain the rows', function(FootballQueries)
	stub.willReturn({ { c1 = '1' } })
	FootballQueries.aggregate(
		{ ['עונה'] = '2021/22', ['קטגוריית מפעל'] = 'ליגה' },
		{ { name = 'games', filters = {}, grain = 'game' } })
	equals(stub.calls[1].options.where,
		'Football_Games.Season = "2021/22" AND Competitions.League = 1', 'where')
end)

-- The A5 finding: a game-grain cell among event-grain cells.
check('a game-grain cell counts distinct games, not rows',
	function(FootballQueries)
		stub.willReturn({ { c1 = '3', c2 = '2' } })
		local cells = FootballQueries.aggregate({ ['שחקן'] = 'ערן זהבי' }, {
			{ name = 'goals', filters = { ['מספר אירוע'] = '3' } },
			{ name = 'gamesScoredIn', filters = { ['מספר אירוע'] = '3' },
			  grain = 'game' },
		})
		equals(stub.calls[1].fields,
			'SUM(CASE WHEN Games_Events.EventType IN (3) THEN 1 ELSE 0 END)=c1,'
			.. 'COUNT(DISTINCT CASE WHEN Games_Events.EventType IN (3)'
			.. ' THEN Football_Games._pageID END)=c2', 'fields')
		equals(cells.goals, 3, 'goals')
		equals(cells.gamesScoredIn, 2, 'games scored in')
	end)

check('an unknown grain raises instead of guessing', function(FootballQueries)
	expectError('unknown grain', function()
		FootballQueries.aggregate({}, {
			{ name = 'x', filters = {}, grain = 'season' },
		})
	end)
end)

check('an unsupported filter inside a cell still raises',
	function(FootballQueries)
		expectError('unsupported filter "כרטיסים צהובים"', function()
			FootballQueries.aggregate({ ['שחקן'] = 'ערן זהבי' }, {
				{ name = 'x', filters = { ['כרטיסים צהובים'] = '1' } },
			})
		end)
	end)

check('a cell with no filters counts every row in scope',
	function(FootballQueries)
		stub.willReturn({ { c1 = '59' } })
		local cells = FootballQueries.aggregate({ ['עונה'] = '2021/22' },
			{ { name = 'all', filters = {} } })
		equals(stub.calls[1].fields,
			'SUM(CASE WHEN 1=1 THEN 1 ELSE 0 END)=c1', 'fields')
		equals(cells.all, 59, 'all')
	end)

check('an empty result gives zeros, not nil', function(FootballQueries)
	stub.willReturn({ { c1 = nil, c2 = '4' } })
	local cells = FootballQueries.aggregate({ ['שחקן'] = 'מי שלא שיחק' },
		PLAYER_CELLS)
	equals(cells.appearances, 0, 'nil becomes 0')
end)

check('no cells at all is an error', function(FootballQueries)
	expectError('at least one cell', function()
		FootballQueries.aggregate({ ['עונה'] = '2021/22' }, {})
	end)
end)

check('grouping returns one entry per group', function(FootballQueries)
	stub.willReturn({
		{ g = 'ערן זהבי', c1 = '150' },
		{ g = 'אבי כהן', c1 = '5' },
	})
	local groups = FootballQueries.aggregate({ ['קטגוריית מפעל'] = 'ליגה' }, {
		{ name = 'goals', filters = { ['מספר אירוע'] = '3' } },
	}, { groupBy = 'Games_Events.PlayerName', groupAlias = 'g', limit = 50 })

	equals(#groups, 2, 'two groups')
	equals(groups[1].group, 'ערן זהבי', 'first group')
	equals(groups[1].cells.goals, 150, 'first value')
	equals(stub.calls[1].options.groupBy, 'Games_Events.PlayerName', 'groupBy')
end)

check('the same block always builds identical SQL', function(FootballQueries)
	local first
	for iteration = 1, 10 do
		stub.install()
		stub.willReturn({ { c1 = '1' } })
		local module = stub.loadModule()
		module.aggregate({ ['שחקן'] = 'ערן זהבי' }, PLAYER_CELLS)
		local fields = stub.calls[1].fields
		first = first or fields
		equals(fields, first, 'stable fields')
	end
end)

print(string.format('\n%d passed, %d failed', passed, failed))
os.exit(failed > 0 and 1 or 0)
