--[[
Tests for Module:SportQueries with a per-player schema - the shape basketball
and volleyball have: one row per player per game, stats as SUM of a column.

Football's suites prove the shared logic still does what it did; this one
proves the parts football never exercises: a sum over the multiplying table,
grain from the column's table, a side filter under another name, a choice that
means "no condition", a list that carries a namespace prefix, zero rows kept.
The schema is hand-built here, so no basketball data page is needed to run it.

Run from the repository root:
    lua5.1 infra/lua_modules/tests/test_perplayer_schema.lua
]]

package.path = 'infra/lua_modules/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0

--- A basketball-shaped schema. `patch` may alter it before the module binds it.
local function schema(patch)
	local fields = {
		name = 'HoopQueries',
		baseTable = 'Basketball_Games',
		roles = {
			sideColumn = 'Basketball_Player_Game_Events_Summary.Team',
			sideFilter = 'האם עבור יריבה',
			-- No narrowFilter: nothing narrows a leaderboard's WHERE here.
		},
		groupKeys = { player = 'Basketball_Player_Game_Events_Summary.PlayerName' },
		-- The template: any value asks for the opponent, none for Maccabi.
		sides = { maccabi = 1, opponent = 0, opponentValue = 'כן', maccabiValue = 'לא' },
		tables = {
			Basketball_Games = { base = true, grain = 'game' },
			Basketball_Competitions = {
				join = 'Basketball_Games.Competition = Basketball_Competitions.OriginalName',
				grain = 'game',
			},
			Basketball_Player_Game_Events_Summary = {
				join = 'Basketball_Games._pageName = Basketball_Player_Game_Events_Summary._pageName',
				grain = 'perPlayer',
			},
			Basketball_Other_Per_Player = {
				join = 'Basketball_Games._pageName = Basketball_Other_Per_Player._pageName',
				grain = 'perPlayer',
			},
		},
		columns = {
			['Basketball_Games.Season'] = 'strip',
			['Basketball_Games.TotalPointsMaccabi'] = 'number',
			['Basketball_Player_Game_Events_Summary.PlayerName'] = 'keep',
			['Basketball_Player_Game_Events_Summary.Team'] = 'number',
			['Basketball_Player_Game_Events_Summary.TotalPoints'] = 'number',
			['Basketball_Player_Game_Events_Summary.IsPlayed'] = 'number',
			['Basketball_Other_Per_Player.Thing'] = 'number',
		},
		filters = {
			['עונה'] = { column = 'Basketball_Games.Season', kind = 'text' },
			['שחקנים'] = { column = 'Basketball_Player_Game_Events_Summary.PlayerName',
				kind = 'list', stripPrefix = 'כדורסל:' },
			['דבר'] = { column = 'Basketball_Other_Per_Player.Thing', kind = 'number' },
			['האם עבור יריבה'] = { column = 'Basketball_Player_Game_Events_Summary.Team',
				kind = 'maccabiSide' },
			['קטגוריית מפעל'] = { kind = 'competitionCategory',
				tables = { 'Basketball_Competitions' }, choices = {
					['ליגה'] = 'Basketball_Competitions.League = 1',
					-- The basketball templates' רשמי tab: no condition at all.
					['רשמי'] = '',
				} },
		},
		sumColumns = {
			['נקודות'] = 'Basketball_Player_Game_Events_Summary.TotalPoints',
			['הופעות'] = 'Basketball_Player_Game_Events_Summary.IsPlayed',
			['סל מכבי'] = 'Basketball_Games.TotalPointsMaccabi',
		},
		aggregates = {},
		aliases = {},
		optionParams = {},
		entryPoints = {},
		maxLimit = 5000,
	}
	if patch then
		patch(fields)
	end
	return fields
end

local function check(name, body, patch)
	stub.install()
	local ok, message = pcall(function()
		local module = stub.loadModule('Module:SportQueries').new(schema(patch))
		body(module)
	end)
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
		error(string.format('error did not mention "%s": %s', pattern, tostring(message)), 0)
	end
end

local PLAYERS = 'Basketball_Player_Game_Events_Summary'

check('a points cell joins the per-player table even when only the game is filtered',
	function(Queries)
		stub.willReturn({ { c1 = '2413' } })
		local values = Queries.aggregate({ ['עונה'] = '2023/24' },
			{ { name = 'points', grain = 'event', sum = 'נקודות' } })
		equals(values.points, 2413, 'value')
		equals(stub.calls[1].tables, 'Basketball_Games,' .. PLAYERS, 'tables')
		equals(stub.calls[1].options.join,
			'Basketball_Games._pageName = ' .. PLAYERS .. '._pageName', 'join')
		-- The side constraint lands in the CASE, so only Maccabi's rows are summed.
		equals(stub.calls[1].fields,
			'SUM(CASE WHEN ' .. PLAYERS .. '.Team = 1 THEN ' .. PLAYERS .. '.TotalPoints ELSE NULL END)=c1',
			'fields')
	end)

check('a per-player sum declared as game grain is refused', function(Queries)
	expectError('sums a per-player column, so its grain must be "event"', function()
		Queries.aggregate({}, { { name = 'points', grain = 'game', sum = 'נקודות' } })
	end)
end)

check('a game-column sum is still refused when the per-player table is joined',
	function(Queries)
		expectError('sums a game column while the query joins ' .. PLAYERS, function()
			Queries.aggregate({ ['שחקנים'] = 'שרן ייני' },
				{ { name = 'scored', grain = 'game', sum = 'סל מכבי' } })
		end)
	end)

check('an event count with no multiplying table joined is refused', function(Queries)
	expectError('counts events, but the query joins no multiplying table', function()
		Queries.aggregate({ ['עונה'] = '2023/24' }, { { name = 'rows', grain = 'event' } })
	end)
end)

check('two multiplying tables in one query are refused', function(Queries)
	expectError('joins two multiplying tables', function()
		Queries.build({ ['שחקנים'] = 'שרן ייני', ['דבר'] = '1' })
	end)
end)

check('the side filter under its own name: the opponent word and the default',
	function(Queries)
		equals(Queries.build({ ['שחקנים'] = 'שרן ייני', ['האם עבור יריבה'] = 'כן' }).where,
			-- Filters are sorted by name, and האם sorts before שחקנים.
			PLAYERS .. '.Team = 0 AND ' .. PLAYERS .. '.PlayerName IN ("שרן ייני")', 'opponent')
		equals(Queries.build({ ['שחקנים'] = 'שרן ייני' }).where,
			PLAYERS .. '.PlayerName IN ("שרן ייני") AND ' .. PLAYERS .. '.Team = 1', 'default')
	end)

check('a leaderboard narrows to Maccabi through the side filter, and nothing else',
	function(Queries)
		stub.willReturn({ { g = 'שרן ייני', c1 = '500' } })
		Queries.leaderboard({ ['עונה'] = '2023/24' },
			{ { name = 'points', grain = 'event', sum = 'נקודות' } },
			{ groupBy = 'player', top = 5 })
		equals(stub.calls[1].options.where,
			PLAYERS .. '.Team = 1 AND Basketball_Games.Season = "2023/24"', 'where')
	end)

check('the list filter drops the namespace prefix the page put on each name',
	function(Queries)
		equals(Queries.build({ ['שחקנים'] = 'כדורסל:שרן ייני, כדורסל:טל בורשטיין' }).where,
			PLAYERS .. '.PlayerName IN ("שרן ייני", "טל בורשטיין") AND ' .. PLAYERS .. '.Team = 1',
			'where')
	end)

check('a choice that means "no condition" still joins its table', function(Queries)
	local query = Queries.build({ ['קטגוריית מפעל'] = 'רשמי' })
	equals(query.where, '1=1', 'no condition')
	equals(query.tables, 'Basketball_Games,Basketball_Competitions', 'tables')
	equals(Queries.build({ ['קטגוריית מפעל'] = 'ליגה' }).where,
		'Basketball_Competitions.League = 1', 'a real one')
	expectError('unknown קטגוריית מפעל "טניס"', function()
		Queries.build({ ['קטגוריית מפעל'] = 'טניס' })
	end)
end)

check('keepZero keeps the players with nothing, ranked last', function(Queries)
	stub.willReturn({ { g = 'שרן ייני', c1 = '0' }, { g = 'טל בורשטיין', c1 = '12' } })
	local kept = Queries.leaderboard({}, { { name = 'points', grain = 'event', sum = 'נקודות' } },
		{ groupBy = 'player', top = 5, keepZero = true })
	equals(#kept.points.rows, 2, 'kept')
	equals(kept.points.rows[2].name, 'שרן ייני', 'zero last')
	stub.willReturn({ { g = 'שרן ייני', c1 = '0' }, { g = 'טל בורשטיין', c1 = '12' } })
	local dropped = Queries.leaderboard({}, { { name = 'points', grain = 'event', sum = 'נקודות' } },
		{ groupBy = 'player', top = 5 })
	equals(#dropped.points.rows, 1, 'dropped by default')
end)

check('a NULL sum is a player who was not in that tab; a zero is one who was', function(Queries)
	-- The templates put the tab's category in the WHERE, so a player with no
	-- cup game never appeared in the cup tab. A merged query answers NULL for
	-- them and 0 for a player who played and scored nothing.
	stub.willReturn({ { g = 'שרן ייני', c1 = '0' }, { g = 'טל בורשטיין' }, { g = 'ג\'ייק כהן', c1 = '9' } })
	local result = Queries.leaderboard({}, { { name = 'points', grain = 'event', sum = 'נקודות' } },
		{ groupBy = 'player', top = 5, keepZero = true })
	equals(#result.points.rows, 2, 'the NULL player is absent, the zero one present')
	equals(result.points.rows[2].name, 'שרן ייני', 'zero ranked last')
	equals(result.points.players, 2, 'and not counted')
end)

check('errors carry the schema name', function(Queries)
	expectError('HoopQueries: unsupported filter "שחקן"', function()
		Queries.build({ ['שחקן'] = 'שרן ייני' })
	end)
end)

check('a table without a grain is refused as soon as it is joined', function(Queries)
	expectError('declares no grain', function()
		Queries.build({ ['שחקנים'] = 'שרן ייני' })
	end)
end, function(fields)
	fields.tables[PLAYERS].grain = nil
end)

print(string.format('%d passed, %d failed', passed, failed))
if failed > 0 then
	os.exit(1)
end
