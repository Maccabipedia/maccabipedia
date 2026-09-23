--[[
Tests for the basketball binding: Module:BasketballStatsBlock's leaderboardTab
through the real basketball schema and block data.

What one tab prints on production is checked byte for byte by
compare_basketball_tabs.py; these pin the query and the priming.

Run from the repository root:
    lua5.1 infra/lua_modules/tests/test_basketball.lua
]]

package.path = 'infra/lua_modules/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0

local function check(name, body)
	stub.install()
	local ok, message = pcall(body, stub.loadModule('Module:BasketballStatsBlock'))
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

local function contains(text, piece, what)
	if not tostring(text):find(piece, 1, true) then
		error(string.format('%s\n        missing: %s\n        in:      %s',
			what or 'not found', piece, tostring(text)), 0)
	end
end

local function lacks(text, piece, what)
	if tostring(text):find(piece, 1, true) then
		error(string.format('%s\n        found: %s', what or 'unexpected', piece), 0)
	end
end

local PLAYERS = 'Basketball_Player_Game_Events_Summary'

local function tabFrame(args, keep)
	local direct = { ['בלוק'] = 'leaderboards', ['תיבה'] = 'נקודות', ['קטגוריית מפעל'] = 'ליגה', ['כמות'] = '10' }
	for key, value in pairs(args or {}) do
		direct[key] = value
	end
	return keep and stub.newFrameKeepingVariables({}, direct) or stub.newFrame({}, direct)
end

--- A grouped-query row: the player and a value for the points/league column,
--- which is column index (box 2, category 2) = c8 with 6 categories per box.
local function pointsLeague(name, value)
	return { g = name, c8 = value }
end

check('the portal: one query for all 8 boxes x 6 categories, summed per player', function(module)
	stub.willReturn({ pointsLeague('דורון ג\'מצ\'י', '7490') })
	module.leaderboardTab(tabFrame())
	equals(#stub.calls, 1, 'one query')
	local call = stub.calls[1]
	equals(call.tables, 'Basketball_Games,Basketball_Competitions,' .. PLAYERS, 'tables')
	equals(call.options.groupBy, PLAYERS .. '.PlayerName', 'grouped by player')
	equals(call.options.where, PLAYERS .. '.Team = 1', 'Maccabi only, nothing else on the portal')
	local _, columns = call.fields:gsub('=c%d+', '')
	equals(columns, 48, '8 boxes x 6 categories, one aggregate each')
	-- The side constraint is in the WHERE (as the template had it), so the CASEs carry
	-- only the category; רשמי is no condition at all, an absent category is Official = 1.
	contains(call.fields, 'SUM(CASE WHEN Basketball_Competitions.League = 1 THEN ' .. PLAYERS
		.. '.TotalPoints ELSE NULL END)=c8', 'points in the league')
	contains(call.fields, 'SUM(CASE WHEN 1=1 THEN ' .. PLAYERS .. '.IsPlayed ELSE NULL END)=c1',
		'appearances in רשמי')
	contains(call.fields, 'SUM(CASE WHEN Basketball_Competitions.Official = 1 THEN ' .. PLAYERS
		.. '.IsPlayed ELSE NULL END)=c6', 'the absent-category default')
end)

check('a tab renders the row template with named args, and the more link at the limit',
	function(module)
		local rows = {}
		for index = 1, 10 do
			rows[index] = pointsLeague('שחקן ' .. index, tostring(100 - index))
		end
		stub.willReturn(rows)
		local html = module.leaderboardTab(tabFrame())
		-- The fixture fills one column only, so every other tab is empty (NULL = absent).
		equals(#stub.expanded, 10, 'the ten rows of the one tab with players')
		contains(html, 'ROW(nil|nil)', 'the stub prints positional args; named ones go to the template')
		equals(stub.expanded[1].args.PlayerName, 'שחקן 1', 'PlayerName')
		equals(stub.expanded[1].args.Record, 99, 'Record')
		equals(stub.expanded[1].title, 'כדורסל/סטטיסטיקה/כמות משחקים/הצגת שחקן', 'the row template')
		contains(html, ' עוד...]\n', 'the more link, on its own line')
		contains(html, 'offset=10', 'past the ten shown')
		contains(html, 'fields=SUM(' .. PLAYERS .. '.TotalPoints)=Record, ' .. PLAYERS
			.. '.PlayerName=PlayerName', 'ranking the same sum')
	end)

check('below the limit there is no more link', function(module)
	stub.willReturn({ pointsLeague('דורון ג\'מצ\'י', '7490') })
	lacks(module.leaderboardTab(tabFrame()), 'עוד...', 'no link')
end)

check('an empty tab prints the sentence the template printed', function(module)
	stub.willReturn({})
	equals(module.leaderboardTab(tabFrame()), 'לא נמצאו שיאנים להצגה', 'empty')
end)

check('the second tab on the page reads what the first primed', function(module)
	stub.willReturn({ pointsLeague('דורון ג\'מצ\'י', '7490') })
	module.leaderboardTab(tabFrame())
	module.leaderboardTab(tabFrame({ ['קטגוריית מפעל'] = 'גביע' }, true))
	module.leaderboardTab(tabFrame({ ['תיבה'] = 'ריבאונדים' }, true))
	equals(#stub.calls, 1, 'still one query')
end)

check('a different filter set or limit primes again', function(module)
	stub.willReturn({ pointsLeague('דורון ג\'מצ\'י', '7490') })
	module.leaderboardTab(tabFrame())
	stub.willReturn({})
	module.leaderboardTab(tabFrame({ ['עונה'] = '2023/24' }, true))
	equals(#stub.calls, 2, 'a season is another query')
	contains(stub.calls[2].options.where, 'Basketball_Games.Season = "2023/24"', 'with the season')
	stub.willReturn({})
	module.leaderboardTab(tabFrame({ ['כמות'] = '5' }, true))
	equals(#stub.calls, 3, 'another limit is another query')
end)

check('a player list from category members loses its prefix', function(module)
	stub.willReturn({})
	-- As the category-members helper hands it over: quoted, prefixed, with a trailing "".
	module.leaderboardTab(tabFrame({ ['שחקנים'] = '"כדורסל:שרן ייני", "כדורסל:ג\'ייק כהן", ""' }))
	contains(stub.calls[1].options.where,
		PLAYERS .. '.PlayerName IN ("שרן ייני", "ג\'ייק כהן")', 'stripped')
end)

check('an empty filter is not a filter, in the query or in the cache key', function(module)
	stub.willReturn({})
	module.leaderboardTab(tabFrame({ ['עונה'] = '', ['יריבות'] = ' ' }))
	equals(stub.calls[1].options.where, PLAYERS .. '.Team = 1', 'nothing added')
	-- The box templates pass every parameter whether set or not; a later box
	-- passing none must read what the first primed, not query again.
	module.leaderboardTab(tabFrame({}, true))
	equals(#stub.calls, 1, 'same key')
end)

check('a player with zero in a tab is shown, as the template showed (no HAVING)', function(module)
	stub.willReturn({ pointsLeague('שרן ייני', '0'), pointsLeague('ג\'ייק כהן', '12') })
	module.leaderboardTab(tabFrame())
	equals(#stub.expanded, 2, 'both rendered')
	equals(stub.expanded[2].args.PlayerName, 'שרן ייני', 'the zero last')
end)

check('refusals: an unknown box, category, limit or filter', function(module)
	local function raises(pattern, args)
		local ok, message = pcall(module.leaderboardTab, tabFrame(args))
		equals(ok, false, 'raised for ' .. pattern)
		contains(message, pattern, 'message')
	end
	raises('has no box "שערים"', { ['תיבה'] = 'שערים' })
	raises('declares no category "טניס"', { ['קטגוריית מפעל'] = 'טניס' })
	raises('כמות must be a positive whole number', { ['כמות'] = 'הרבה' })
	raises('unsupported filter "שחקן"', { ['שחקן'] = 'שרן ייני' })
	equals(#stub.calls, 0, 'nothing queried')
end)

check('errors carry the basketball name', function(module)
	local ok, message = pcall(module.leaderboardTab, tabFrame({ ['שחקן'] = 'x' }))
	equals(ok, false)
	contains(message, 'BasketballQueries: unsupported filter', 'prefix from the schema')
end)

print(string.format('%d passed, %d failed', passed, failed))
if failed > 0 then
	os.exit(1)
end
