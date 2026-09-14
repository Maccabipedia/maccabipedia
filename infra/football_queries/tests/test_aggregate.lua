--[[
Tests for the merge primitive: every cell of a block from one query.

This is the piece the whole design exists for - 32 queries become 1 - and it is
also where a wrong number hides best, because a conditional aggregate that
filters on the wrong thing still returns a plausible integer. Several of the
tests below exist because a review found exactly that.

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

local function cell(name, filters, grain)
	return { name = name, filters = filters, grain = grain or 'event' }
end

-- The real block: eight cells, each a different event or subtype.
local PLAYER_CELLS = {
	cell('appearances', { ['מספר אירוע'] = '1,5' }),
	cell('substitutions', { ['מספר אירוע'] = '5' }),
	cell('goals', { ['מספר אירוע'] = '3' }),
	cell('penaltyGoals', { ['מספר אירוע'] = '3', ['תת אירוע'] = '35' }),
	cell('assists', { ['מספר אירוע'] = '4' }),
	cell('yellows', { ['מספר אירוע'] = '7', ['תת אירוע'] = '71' }),
	cell('reds', { ['מספר אירוע'] = '7', ['תת אירוע'] = '72,73' }),
	cell('benchStarts', { ['מספר אירוע'] = '2' }),
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
		cell('goals', { ['מספר אירוע'] = '3' }),
		cell('assists', { ['מספר אירוע'] = '4' }),
	})
	equals(stub.calls[1].fields,
		'SUM(CASE WHEN Games_Events.EventType IN (3)'
		.. ' AND Games_Events.Team = 1 THEN 1 ELSE 0 END)=c1,'
		.. 'SUM(CASE WHEN Games_Events.EventType IN (4)'
		.. ' AND Games_Events.Team = 1 THEN 1 ELSE 0 END)=c2',
		'fields')
end)

-- Team belongs in the CASE, not the WHERE. In the WHERE it discards the NULL
-- row a LEFT JOIN makes for a game with no events, so a game-grain cell
-- undercounts - 3,439 instead of 3,504 games, measured on production.
check('the Team default goes into each event cell, not the WHERE',
	function(FootballQueries)
		stub.willReturn({ { c1 = '1' } })
		FootballQueries.aggregate({ ['שחקן'] = 'ערן זהבי' }, {
			cell('goals', { ['מספר אירוע'] = '3' }),
		})
		equals(stub.calls[1].options.where,
			'Games_Events.PlayerName = "ערן זהבי"', 'where has no Team')
		equals(stub.calls[1].fields:find('Games_Events.Team = 1', 1, true) ~= nil,
			true, 'the cell has it')
	end)

-- A game-grain cell with no event filters counts games, so it must NOT be
-- constrained to one side.
check('a game-grain cell with no event filters gets no Team condition',
	function(FootballQueries)
		stub.willReturn({ { c1 = '1', c2 = '2' } })
		FootballQueries.aggregate({ ['עונה'] = '2021/22' }, {
			cell('goals', { ['מספר אירוע'] = '3' }),
			cell('games', {}, 'game'),
		})
		local gameField = stub.calls[1].fields:match('COUNT%(DISTINCT[^,]+')
		equals(gameField,
			'COUNT(DISTINCT CASE WHEN 1=1 THEN Football_Games._pageID END)=c2',
			'distinct games, unconstrained')
	end)

-- But a game-grain cell whose OWN filters reach the events table does need it,
-- or it counts games in which either side did the thing. An earlier version
-- restricted the side constraint to event grain and this test pinned the
-- absence as if it were intended.
check('a game-grain cell that filters on events is still constrained to Maccabi',
	function(FootballQueries)
		stub.willReturn({ { c1 = '1' } })
		FootballQueries.aggregate({ ['עונה'] = '2021/22' }, {
			cell('gamesScoredIn', { ['מספר אירוע'] = '3' }, 'game'),
		})
		equals(stub.calls[1].fields,
			'COUNT(DISTINCT CASE WHEN Games_Events.EventType IN (3)'
			.. ' AND Games_Events.Team = 1 THEN Football_Games._pageID END)=c1',
			'side-constrained')
	end)

check('a game-grain cell may still ask for the opponent side explicitly',
	function(FootballQueries)
		stub.willReturn({ { c1 = '1' } })
		FootballQueries.aggregate({ ['עונה'] = '2021/22' }, {
			cell('gamesTheyScoredIn',
				{ ['מספר אירוע'] = '3', ['מכבי'] = 'לא' }, 'game'),
		})
		local fields = stub.calls[1].fields
		equals(fields:find('Games_Events.Team = 0', 1, true) ~= nil, true,
			'the cell asks for 0')
		equals(fields:find('Team = 1', 1, true), nil, 'and not also for 1')
	end)

-- Two cells asking for different date formats: the union as modifier scope let
-- the later one overwrite the earlier, so both rendered the same format.
check('each cell keeps its own modifier', function(FootballQueries)
	stub.willReturn({ { c1 = '1', c2 = '2' } })
	FootballQueries.aggregate({}, {
		{ name = 'dayMonth', grain = 'game',
		  filters = { ['תאריך'] = '2021-08-22', ['פורמט תאריך'] = '"%d-%m"' } },
		{ name = 'year', grain = 'game',
		  filters = { ['תאריך'] = '2021-08-22', ['פורמט תאריך'] = '"%Y"' } },
	})
	local fields = stub.calls[1].fields
	equals(select(2, fields:gsub('"%%d%-%%m"', '')), 2, 'the first cell keeps %d-%m')
	equals(select(2, fields:gsub('"%%Y"', '')), 2, 'and the second keeps %Y')
end)

-- The contradiction a review found: the WHERE demanded Team = 1 while the
-- cell demanded Team = 0, so the cell could only ever be 0.
check('a cell asking for the opponent side is not contradicted',
	function(FootballQueries)
		stub.willReturn({ { c1 = '5', c2 = '3' } })
		FootballQueries.aggregate({ ['שחקן'] = 'ערן זהבי' }, {
			cell('ours', { ['מספר אירוע'] = '3' }),
			cell('theirs', { ['מספר אירוע'] = '3', ['מכבי'] = 'לא' }),
		})
		local fields = stub.calls[1].fields
		equals(fields:find('Games_Events.Team = 0', 1, true) ~= nil, true,
			'the opponent cell asks for 0')
		equals(stub.calls[1].options.where:find('Team', 1, true), nil,
			'and the WHERE does not demand 1')
	end)

check('a shared מכבי still constrains the whole row set',
	function(FootballQueries)
		stub.willReturn({ { c1 = '1' } })
		FootballQueries.aggregate({ ['שחקן'] = 'ערן זהבי', ['מכבי'] = 'לא' }, {
			cell('goals', { ['מספר אירוע'] = '3' }),
		})
		equals(stub.calls[1].options.where,
			'Games_Events.Team = 0 AND Games_Events.PlayerName = "ערן זהבי"',
			'where')
		equals(stub.calls[1].fields:find('Team', 1, true), nil,
			'no per-cell default when shared said so')
	end)

-- A modifier can sit in the shared filters while the filter it modifies sits
-- in a cell. Read from the cell alone, פורמט תאריך vanished and the cell asked
-- a different question.
check('a modifier in the shared filters reaches a cell filter',
	function(FootballQueries)
		stub.willReturn({ { c1 = '1' } })
		FootballQueries.aggregate({ ['פורמט תאריך'] = '"%d-%m"' }, {
			cell('onThisDay', { ['תאריך'] = '2021-08-22' }, 'game'),
		})
		equals(stub.calls[1].fields,
			'COUNT(DISTINCT CASE WHEN DATE_FORMAT("2021-08-22", "%d-%m")'
			.. ' = DATE_FORMAT(Football_Games.Date, "%d-%m")'
			.. ' THEN Football_Games._pageID END)=c1', 'fields')
	end)

-- Both halves matter, and only this shape shows it: the shared filters touch
-- no event table, so a Team default derived from them alone never appears, and
-- the join a cell needs is never made.
check('a table only a cell mentions is still joined, and Team still applies',
	function(FootballQueries)
		stub.willReturn({ { c1 = '1' } })
		FootballQueries.aggregate({ ['עונה'] = '2021/22' }, {
			cell('goals', { ['מספר אירוע'] = '3' }),
		})
		equals(stub.calls[1].tables, 'Football_Games,Games_Events', 'tables')
		equals(stub.calls[1].options.join,
			'Football_Games._pageID = Games_Events._pageID', 'join')
		equals(stub.calls[1].fields,
			'SUM(CASE WHEN Games_Events.EventType IN (3)'
			.. ' AND Games_Events.Team = 1 THEN 1 ELSE 0 END)=c1',
			'the event cell still carries the Team default')
	end)

check('the shared filters still constrain the rows', function(FootballQueries)
	stub.willReturn({ { c1 = '1' } })
	FootballQueries.aggregate(
		{ ['עונה'] = '2021/22', ['קטגוריית מפעל'] = 'ליגה' },
		{ cell('games', {}, 'game') })
	equals(stub.calls[1].options.where,
		'Football_Games.Season = "2021/22" AND Competitions.League = 1', 'where')
end)

check('grain must be declared', function(FootballQueries)
	expectError('must declare grain', function()
		FootballQueries.aggregate({}, { { name = 'x', filters = {} } })
	end)
	expectError('must declare grain', function()
		FootballQueries.aggregate({}, {
			{ name = 'x', filters = {}, grain = 'season' },
		})
	end)
end)

check('two cells with the same name raise', function(FootballQueries)
	expectError('both named "goals"', function()
		FootballQueries.aggregate({}, {
			cell('goals', { ['מספר אירוע'] = '3' }),
			cell('goals', { ['מספר אירוע'] = '4' }),
		})
	end)
end)

-- Cargo rewrites HOLDS only in the where, so one in a field reaches MySQL.
check('a HOLDS filter in a cell raises with an explanation',
	function(FootballQueries)
		expectError('only rewrites in the where', function()
			FootballQueries.aggregate({}, {
				cell('withAssistant', { ['עוזר שופט'] = 'ג\'ון ביטון' }, 'game'),
			})
		end)
	end)

check('an unsupported filter inside a cell still raises',
	function(FootballQueries)
		expectError('unsupported filter "כרטיסים צהובים"', function()
			FootballQueries.aggregate({ ['שחקן'] = 'ערן זהבי' }, {
				cell('x', { ['כרטיסים צהובים'] = '1' }),
			})
		end)
	end)

check('a cell with no filters counts every row in scope',
	function(FootballQueries)
		stub.willReturn({ { c1 = '59' } })
		local cells = FootballQueries.aggregate({ ['עונה'] = '2021/22' },
			{ cell('all', {}, 'game') })
		equals(stub.calls[1].fields,
			'COUNT(DISTINCT CASE WHEN 1=1 THEN Football_Games._pageID END)=c1',
			'fields')
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

-- The grouped case was accepted and could not work: it never selected the
-- group column, so every group came back nil. It raises until the leaderboard
-- primitive is written.
-- Removing the grouped branch left orderBy, having and groupAlias accepted and
-- unread. An option that is taken and ignored is the failure this whole layer
-- is a reaction to, so every one of them raises.
check('grouping and its companions raise rather than being ignored',
	function(FootballQueries)
		for _, option in ipairs({ 'groupBy', 'orderBy', 'having',
		                          'groupAlias' }) do
			expectError('does not take "' .. option .. '"', function()
				FootballQueries.aggregate({ ['קטגוריית מפעל'] = 'ליגה' }, {
					cell('goals', { ['מספר אירוע'] = '3' }),
				}, { [option] = 'Games_Events.PlayerName' })
			end)
		end
	end)

-- The sport's facts come from the schema, and these two tests are the only
-- proof of it: while football is the only sport, a hardcoded 'Football_Games'
-- or a hardcoded side value of 1 behaves identically, so no ordinary test can
-- tell the difference. Patching the schema can.
check('the base table comes from the schema', function()
	stub.install()
	stub.dataPatch = function(data)
		data.baseTable = 'Basketball_Games'
		data.tables['Basketball_Games'] = { base = true }
		data.filters['עונה'].column = 'Basketball_Games.Season'
		data.columns['Basketball_Games.Season'] = 'strip'
	end
	local FootballQueries = stub.loadModule()

	stub.willReturn({ { c1 = '1' } })
	FootballQueries.aggregate({ ['עונה'] = '2024/25' },
		{ cell('games', {}, 'game') })
	equals(stub.calls[1].tables, 'Basketball_Games', 'tables follow the schema')
	equals(stub.calls[1].fields,
		'COUNT(DISTINCT CASE WHEN 1=1 THEN Basketball_Games._pageID END)=c1',
		'and so does the game-grain field')
end)

check('the side value comes from the schema - volleyball uses 2', function()
	stub.install()
	stub.dataPatch = function(data)
		data.sides.maccabi = 2
	end
	local FootballQueries = stub.loadModule()

	stub.willReturn({ { c1 = '1' } })
	FootballQueries.aggregate({ ['שחקן'] = 'מישהו' }, {
		cell('goals', { ['מספר אירוע'] = '3' }),
	})
	equals(stub.calls[1].fields,
		'SUM(CASE WHEN Games_Events.EventType IN (3)'
		.. ' AND Games_Events.Team = 2 THEN 1 ELSE 0 END)=c1',
		'the default side is whatever the schema says')
end)

check('the side COLUMN comes from the schema as well', function()
	stub.install()
	stub.dataPatch = function(data)
		data.roles.sideColumn = 'Games_Events.Side'
		data.columns['Games_Events.Side'] = 'number'
	end
	local FootballQueries = stub.loadModule()

	stub.willReturn({ { c1 = '1' } })
	FootballQueries.aggregate({ ['שחקן'] = 'מישהו' }, {
		cell('goals', { ['מספר אירוע'] = '3' }),
	})
	equals(stub.calls[1].fields:find('Games_Events.Side = 1', 1, true) ~= nil,
		true, 'the column follows the schema, not a literal')
end)

check('an explicit limit reaches the query', function(FootballQueries)
	stub.willReturn({ { c1 = '1' } })
	FootballQueries.aggregate({ ['עונה'] = '2021/22' },
		{ cell('games', {}, 'game') }, { limit = 40 })
	equals(stub.calls[1].options.limit, 40, 'limit passed through')
end)

check('a plain query takes its side value from the schema too', function()
	stub.install()
	stub.dataPatch = function(data)
		data.sides.maccabi = 2
	end
	local FootballQueries = stub.loadModule()

	equals(FootballQueries.build({ ['שחקן'] = 'מישהו' }).where,
		'Games_Events.PlayerName = "מישהו" AND Games_Events.Team = 2',
		'the single-query path, not just the merge')
end)

check('the same block always builds identical SQL', function(FootballQueries)
	local first
	for _ = 1, 10 do
		stub.install()
		stub.willReturn({ { c1 = '1' } })
		local module = stub.loadModule()
		module.aggregate({ ['שחקן'] = 'ערן זהבי' }, PLAYER_CELLS)
		local fields = stub.calls[1].fields
		first = first or fields
		equals(fields, first, 'stable fields')
	end
end)

-- A summing cell: goals for and against are not counts of rows, they are sums
-- of a column of the game row. Getting this wrong returns a count where a sum
-- was asked for, which looks like a plausible number on every page.
local DAY_CELLS = {
	{ name = 'games', grain = 'game', filters = {} },
	{ name = 'goalsFor', grain = 'game', sum = 'כיבושים', filters = {} },
	{ name = 'goalsAgainst', grain = 'game', sum = 'ספיגות', filters = {} },
}

check('a summing cell sums its column instead of counting rows',
	function(FootballQueries)
		stub.willReturn({ { c1 = '4', c2 = '9', c3 = '2' } })
		local cells = FootballQueries.aggregate(
			{ ['תאריך'] = '"2021-08-22"' }, DAY_CELLS)
		local fields = stub.calls[1].fields

		if not fields:find(
				'SUM(CASE WHEN 1=1 THEN Football_Games.ResultMaccabi ELSE NULL END)=c2',
				1, true) then
			error('goals for is not summed: ' .. fields, 0)
		end
		if not fields:find(
				'SUM(CASE WHEN 1=1 THEN Football_Games.ResultOpponent ELSE NULL END)=c3',
				1, true) then
			error('goals against is not summed: ' .. fields, 0)
		end
		equals(cells.goalsFor, 9, 'goals for')
		equals(cells.goalsAgainst, 2, 'goals against')
		equals(cells.games, 4, 'games still counted')
	end)

check('a summing cell returning nothing stays empty, a counting one is zero',
	function(FootballQueries)
		-- What Cargo answers for a date with no games at all: COUNT is 0 and
		-- SUM is NULL, and the template renders the NULL as an empty cell.
		stub.willReturn({ { c1 = '0', c2 = nil, c3 = nil } })
		local cells = FootballQueries.aggregate(
			{ ['תאריך'] = '"1900-01-01"' }, DAY_CELLS)

		equals(cells.games, 0, 'a count over no rows is 0')
		equals(cells.goalsFor, nil, 'a sum over no rows stays nil')
		equals(cells.goalsAgainst, nil, 'a sum over no rows stays nil')
	end)

check('summing an unknown value raises', function(FootballQueries)
	expectError('not a known summable value', function()
		FootballQueries.aggregate({}, {
			{ name = 'x', grain = 'game', sum = 'קרנות', filters = {} },
		})
	end)
end)

check('summing at event grain raises', function(FootballQueries)
	-- The grain says how the cell counts; a sum of a game column repeated once
	-- per event is multiplied, so the mismatch is refused, not adjusted.
	expectError('grain', function()
		FootballQueries.aggregate({}, {
			{ name = 'x', grain = 'event', sum = 'כיבושים', filters = {} },
		})
	end)
end)

check('summing while any cell joins the events table raises',
	function(FootballQueries)
		-- The join is the union of all cells, so one event-grain neighbour
		-- multiplies every game row and silently inflates the sum.
		expectError('multiply', function()
			FootballQueries.aggregate({}, {
				{ name = 'goals', grain = 'event',
				  filters = { ['מספר אירוע'] = '3' } },
				{ name = 'goalsFor', grain = 'game', sum = 'כיבושים',
				  filters = {} },
			})
		end)
	end)

check('a summing cell still honours its own filters', function(FootballQueries)
	stub.willReturn({ { c1 = '3' } })
	FootballQueries.aggregate({}, {
		{ name = 'homeGoals', grain = 'game', sum = 'כיבושים',
		  filters = { ['תוצאה'] = 'ניצחון' } },
	})
	local fields = stub.calls[1].fields
	if fields:find('WHEN 1=1', 1, true) then
		error('the cell filter was dropped from the sum: ' .. fields, 0)
	end
	if not fields:find('THEN Football_Games.ResultMaccabi', 1, true) then
		error('wrong column summed: ' .. fields, 0)
	end
end)

check('a summing cell that matches no row is NULL, not zero',
	function(FootballQueries)
		-- ELSE 0 would make the sum 0 as soon as the query matches ANY row,
		-- so a cup tab on a date with only league games printed "0" where the
		-- template prints nothing. Measured on the local wiki over 222 rows:
		-- ELSE 0 gives 0 and ELSE NULL gives NULL.
		stub.willReturn({ { c1 = '5' } })
		FootballQueries.aggregate({}, {
			{ name = 'cupGoals', grain = 'game', sum = 'כיבושים',
			  filters = { ['קטגוריית מפעל'] = 'גביע' } },
		})
		local fields = stub.calls[1].fields
		if fields:find('ELSE 0 END', 1, true) then
			error('the sum falls back to 0 where the template gives NULL: '
				.. fields, 0)
		end
		if not fields:find('ELSE NULL END', 1, true) then
			error('not a NULL-preserving sum: ' .. fields, 0)
		end
	end)

print(string.format('\n%d passed, %d failed', passed, failed))
os.exit(failed > 0 and 1 or 0)
