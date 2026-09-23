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
--- which is column index (box 2, category 2) = c6 with the 4 tab categories primed per box.
local function pointsLeague(name, value)
	return { g = name, c6 = value }
end

check('the portal: one query for all 8 boxes x the 4 tab categories, summed per player', function(module)
	stub.willReturn({ pointsLeague('דורון ג\'מצ\'י', '7490') })
	module.leaderboardTab(tabFrame())
	equals(#stub.calls, 1, 'one query')
	local call = stub.calls[1]
	equals(call.tables, 'Basketball_Games,Basketball_Competitions,' .. PLAYERS, 'tables')
	equals(call.options.groupBy, PLAYERS .. '.PlayerName', 'grouped by player')
	equals(call.options.where, PLAYERS .. '.Team = 1', 'Maccabi only, nothing else on the portal')
	local _, columns = call.fields:gsub('=c%d+', '')
	equals(columns, 32, '8 boxes x 4 tab categories, one aggregate each')
	-- The side constraint is in the WHERE (as the template had it), so the CASEs carry
	-- only the category; רשמי is no condition at all, an absent category is Official = 1.
	contains(call.fields, 'SUM(CASE WHEN Basketball_Competitions.League = 1 THEN COALESCE(' .. PLAYERS
		.. '.TotalPoints, 0) ELSE NULL END)=c6', 'points in the league; a NULL stat is 0, as the template had it')
	contains(call.fields, 'SUM(CASE WHEN 1=1 THEN COALESCE(' .. PLAYERS .. '.IsPlayed, 0) ELSE NULL END)=c1',
		'appearances in רשמי')
	lacks(call.fields, 'Basketball_Competitions.Official = 1 THEN', 'the default category is not in the first prime')
end)

check('a category outside the tab strips is primed on its own, once', function(module)
	stub.willReturn({ pointsLeague('דורון ג\'מצ\'י', '7490') })
	module.leaderboardTab(tabFrame())
	stub.willReturn({ { g = 'שרן ייני', c1 = '500' } })
	local html = module.leaderboardTab(tabFrame({ ['קטגוריית מפעל'] = 'ברירת מחדל' }, true))
	equals(#stub.calls, 2, 'a second query')
	local _, columns = stub.calls[2].fields:gsub('=c%d+', '')
	equals(columns, 8, 'the 8 boxes for that one category')
	contains(stub.calls[2].fields, 'SUM(CASE WHEN Basketball_Competitions.Official = 1 THEN COALESCE(' .. PLAYERS
		.. '.IsPlayed, 0) ELSE NULL END)=c1', 'the default category is Official = 1')
	module.leaderboardTab(tabFrame({ ['קטגוריית מפעל'] = 'ברירת מחדל', ['תיבה'] = 'נקודות' }, true))
	equals(#stub.calls, 2, 'and not again')
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

-- ------------------------------------------------------------ the numbers

local function cellFrame(args, keep)
	local direct = { ['בלוק'] = 'numbers', ['תא'] = 'אסיסטים', ['קטגוריית מפעל'] = 'ליגה', ['עונה'] = '2023/24' }
	for key, value in pairs(args or {}) do
		direct[key] = value
	end
	return keep and stub.newFrameKeepingVariables({}, direct) or stub.newFrame({}, direct)
end

--- The two priming queries answer in the order the grains are iterated; each
--- returns one row of cN aliases. Cells per grain: points x 4 categories (game),
--- 6 stats x 4 categories (event).
local function primeAnswers(gameRow, eventRow)
	stub.willReturn({ gameRow })
	stub.willReturn({ eventRow })
end

check('numbers: two queries prime 28 cells - the game-level points apart from the per-player sums',
	function(module)
		primeAnswers({ c1 = '3000', c2 = '1800', c3 = '400', c4 = '800' }, { c2 = '512' })
		local text = module.cell(cellFrame())
		equals(#stub.calls, 2, 'two queries')
		local game, event = stub.calls[1], stub.calls[2]
		if game.tables:find(PLAYERS, 1, true) then
			game, event = event, game
		end
		equals(game.tables, 'Basketball_Games,Basketball_Competitions', 'the game query joins no players')
		contains(game.fields, 'THEN COALESCE(Basketball_Games.TotalPointsMaccabi, 0) ELSE NULL END)=c1',
			"Maccabi's points, from the game")
		equals(game.options.where, 'Basketball_Games.Season = "2023/24"', 'and carries no side')
		equals(event.tables, 'Basketball_Games,Basketball_Competitions,' .. PLAYERS, 'the per-player query')
		-- aggregate() keeps the side out of the WHERE (a LEFT JOIN would turn inner) and
		-- puts it in every per-player CASE instead.
		contains(event.fields, PLAYERS .. '.Team = 1 THEN COALESCE(', "Maccabi's rows, in the CASE")
		local _, columns = event.fields:gsub('=c%d+', '')
		equals(columns, 24, '6 stats x 4 categories')
		equals(text, '512', 'assists in the league, as an integer')
	end)

check('numbers: later cells read what the first primed; an unmatched sum prints 0', function(module)
	primeAnswers({ c1 = '3000' }, { c2 = '512' })
	module.cell(cellFrame())
	equals(module.cell(cellFrame({ ['תא'] = 'נקודות', ['קטגוריית מפעל'] = 'רשמי' }, true)), '3000', 'points')
	equals(module.cell(cellFrame({ ['תא'] = 'חסימות' }, true)), '0', 'nothing summed prints 0, as COALESCE did')
	equals(#stub.calls, 2, 'no more queries')
end)

check("numbers: עבור יריבה=כן sums the opponent's column and the opponent's rows, under its own key",
	function(module)
		primeAnswers({ c1 = '2900' }, { c2 = '480' })
		module.cell(cellFrame())
		primeAnswers({ c1 = '2700' }, { c2 = '450' })
		local text = module.cell(cellFrame({ ['תא'] = 'נקודות', ['קטגוריית מפעל'] = 'רשמי', ['עבור יריבה'] = 'כן' }, true))
		equals(#stub.calls, 4, 'primed again for the other side')
		local game = stub.calls[3].tables:find(PLAYERS, 1, true) and stub.calls[4] or stub.calls[3]
		local event = game == stub.calls[3] and stub.calls[4] or stub.calls[3]
		contains(game.fields, 'COALESCE(Basketball_Games.TotalPointsOpponent, 0)', "the opponent's points column")
		equals(game.options.where, 'Basketball_Games.Season = "2023/24"', 'no side on the game query')
		contains(event.options.where, PLAYERS .. '.Team = 0', "the opponent's rows: asked for, so in the WHERE")
		equals(text, '2700', 'value')
	end)

check('games: one query counts games, wins and losses in the four categories', function(module)
	stub.willReturn({ { c1 = '40', c5 = '31', c9 = '9' } })
	local frame = stub.newFrame({}, { ['בלוק'] = 'games', ['תא'] = 'ניצחונות', ['קטגוריית מפעל'] = 'רשמי',
		['עונה'] = '2023/24' })
	equals(module.cell(frame), '31', 'wins')
	equals(#stub.calls, 1, 'one query')
	equals(stub.calls[1].tables, 'Basketball_Games,Basketball_Competitions', 'games only')
	contains(stub.calls[1].fields,
		'COUNT(DISTINCT CASE WHEN Basketball_Games.ResultOpt = 1 THEN Basketball_Games._pageID END)=c5',
		'a win in רשמי: the result, no category condition')
	local _, columns = stub.calls[1].fields:gsub('=c%d+', '')
	equals(columns, 12, '3 cells x 4 categories')
end)

check("games: the player pages' captain filter reaches the per-player table with its constants",
	function(module)
		-- ברירת מחדל is not a tab category, so it is primed alone: three cells, c1 the games.
		stub.willReturn({ { c1 = '12' } })
		local frame = stub.newFrame({}, { ['בלוק'] = 'games', ['תא'] = 'משחקים', ['קטגוריית מפעל'] = 'ברירת מחדל',
			['קפטן מכבי'] = 'שרן ייני' })
		equals(module.cell(frame), '12', 'games as captain')
		equals(stub.calls[1].tables, 'Basketball_Games,Basketball_Competitions,' .. PLAYERS, 'joined')
		local _, columns = stub.calls[1].fields:gsub('=c%d+', '')
		equals(columns, 3, 'the one category asked for, not the four tab ones')
		equals(stub.calls[1].options.where,
			PLAYERS .. '.PlayerName = "שרן ייני" AND ' .. PLAYERS .. '.Team = 1 AND ' .. PLAYERS .. '.IsCaptain = 1',
			'the name, the side and the flag - and no second side default')
	end)

check("games: the opponent's captain fixes the side, so the Maccabi default stays out", function()
	local Queries = stub.loadModule('Module:BasketballQueries')
	local query = Queries.build({ ['קפטן יריבה'] = 'ג\'ון שאייר' })
	equals(query.where,
		PLAYERS .. '.PlayerName = "ג\'ון שאייר" AND ' .. PLAYERS .. '.Team = 0 AND ' .. PLAYERS .. '.IsCaptain = 1',
		'Team = 0 from the filter, and no Team = 1 after it')
end)

check("numbers: a side word that is not the opponent's means Maccabi for BOTH grains", function(module)
	primeAnswers({ c1 = '2900' }, { c2 = '480' })
	module.cell(cellFrame({ ['תא'] = 'נקודות', ['קטגוריית מפעל'] = 'רשמי', ['עבור יריבה'] = 'לא' }))
	local game = stub.calls[1].tables:find(PLAYERS, 1, true) and stub.calls[2] or stub.calls[1]
	local event = game == stub.calls[1] and stub.calls[2] or stub.calls[1]
	contains(game.fields, 'COALESCE(Basketball_Games.TotalPointsMaccabi, 0)', "Maccabi's points column")
	contains(event.options.where, PLAYERS .. '.Team = 1', "Maccabi's rows - the query layer's own rule")
end)

check("leaderboard: the opponent's captain as a shared filter keeps Maccabi's side out", function()
	local Queries = stub.loadModule('Module:BasketballQueries')
	stub.willReturn({})
	Queries.leaderboard({ ['קפטן יריבה'] = 'ג\'ון שאייר' },
		{ { name = 'points', grain = 'event', sum = 'נקודות' } }, { groupBy = 'player', top = 5 })
	lacks(stub.calls[1].options.where, PLAYERS .. '.Team = 1', 'no contradiction injected')
	contains(stub.calls[1].options.where, PLAYERS .. '.Team = 0', "the captain's side")
end)

check('numbers: a grain that mixes cells with and without sides is refused', function(module)
	stub.dataPatch = function(data)
		if data['numbers'] then
			data['numbers'].cells[#data['numbers'].cells + 1] =
				{ key = 'games', word = 'משחקים', grain = 'game', filters = {} }
		end
	end
	-- The module read its blocks when it loaded; load it again with the patch in place.
	module = stub.loadModule('Module:BasketballStatsBlock')
	local ok, message = pcall(module.cell, cellFrame({ ['תא'] = 'נקודות', ['קטגוריית מפעל'] = 'רשמי' }))
	equals(ok, false)
	contains(message, 'mixes game-level cells with and without sides')
end)

check('numbers: an unknown cell or category is an error, and nothing is queried', function(module)
	local ok, message = pcall(module.cell, cellFrame({ ['תא'] = 'שערים' }))
	equals(ok, false)
	contains(message, 'has no cell "שערים"')
	ok, message = pcall(module.cell, cellFrame({ ['קטגוריית מפעל'] = 'טניס' }))
	equals(ok, false)
	contains(message, 'declares no category "טניס"')
	equals(#stub.calls, 0, 'nothing queried')
end)

print(string.format('%d passed, %d failed', passed, failed))
if failed > 0 then
	os.exit(1)
end
