--[[
Tests for Module:FootballCompetition - the game tables of a competition page.

What the old templates rendered is compared page by page by
compare_competition_pages.py; these pin the SQL and the guards.

Run from the repository root:
    lua5.1 infra/lua_modules/tests/test_football_competition.lua
]]

package.path = 'infra/lua_modules/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0

local function check(name, body)
	stub.install()
	local ok, message = pcall(body, stub.loadModule('Module:FootballCompetition'))
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

local function expectError(pattern, body)
	local ok, message = pcall(body)
	if ok then
		error('expected an error, none raised', 0)
	end
	contains(tostring(message), pattern, 'the error names the problem')
end

local MELCHETT = "גביע מלצ'ט"
local MELCHETT_SQL = 'Football_Games.Competition IN ("גביע מלצ\'ט")'

local function invoke(Competition, entry, args)
	return Competition[entry](stub.newFrame({}, args))
end

check('biggest wins: the apostrophe is kept, the wins ranked by margin', function(Competition)
	stub.willReturn({ { PageName = 'משחק:21-09-1940', Season = '1940' } })
	local out = invoke(Competition, 'biggest', { ['תוצאה'] = 'ניצחון', ['מפעלים'] = MELCHETT })
	local call = stub.calls[1]
	equals(call.tables, 'Football_Games', 'the games table only')
	equals(call.options.where, MELCHETT_SQL .. ' AND Football_Games.ResultOpt = 1', 'wins of Melchett')
	equals(call.options.orderBy,
		'(Football_Games.ResultMaccabi-Football_Games.ResultOpponent) DESC', 'by margin')
	equals(call.options.limit, 10, 'ten rows, as the template showed')
	contains(call.fields, 'Football_Games.Leg=Leg', 'the stage column the row shows')
	equals(stub.expanded[1].title, 'מפעל כדורגל/הצגת הניצחונות הגדולים/הצגת משחק', 'the wins row')
	equals(stub.expanded[1].args.Season, '1940', 'named args, as the template had')
	equals(out, 'ROW(nil|nil)', 'one row per game')
end)

check('biggest losses: ranked the other way, through the losses row', function(Competition)
	stub.willReturn({ {} })
	invoke(Competition, 'biggest', { ['תוצאה'] = 'הפסד', ['מפעלים'] = MELCHETT })
	equals(stub.calls[1].options.where, MELCHETT_SQL .. ' AND Football_Games.ResultOpt = 3', 'losses')
	equals(stub.calls[1].options.orderBy,
		'(Football_Games.ResultOpponent-Football_Games.ResultMaccabi) DESC', 'by margin against')
	equals(stub.expanded[1].title, 'מפעל כדורגל/הצגת ההפסדים הגדולים/הצגת משחק', 'the losses row')
end)

check('biggest: a draw or a typo is refused', function(Competition)
	expectError('תוצאה=ניצחון or הפסד', function()
		invoke(Competition, 'biggest', { ['תוצאה'] = 'תיקו', ['מפעלים'] = MELCHETT })
	end)
	expectError('unknown argument "מפעל"', function()
		invoke(Competition, 'biggest', { ['תוצאה'] = 'ניצחון', ['מפעל'] = MELCHETT })
	end)
end)

check('no competition names means no rows, not every game', function(Competition)
	equals(invoke(Competition, 'biggest', { ['תוצאה'] = 'ניצחון', ['מפעלים'] = ' ' }), '', 'biggest')
	equals(invoke(Competition, 'seasons', { ['מפעלים'] = '' }), '', 'seasons')
	equals(#stub.calls, 0, 'nothing queried')
end)

check('seasons: per season and competition, joined to its achievement', function(Competition)
	stub.willReturn({ { Season = '1940', Achievement = 'זכיה', WinningCount = '3' } })
	invoke(Competition, 'seasons', { ['מפעלים'] = 'גביע אופ"א, ' .. MELCHETT })
	local call = stub.calls[1]
	equals(call.tables, 'Football_Games,Achievements', 'games and achievements')
	equals(call.options.join, 'Football_Games.Season=Achievements.Season, '
		.. 'Football_Games.Competition=Achievements.Competition', 'by season and competition')
	equals(call.options.where,
		'Football_Games.Competition IN ("גביע אופא", "גביע מלצ\'ט")', 'both names, as stored')
	equals(call.options.groupBy,
		'Football_Games.Season, Football_Games.Competition, Achievements.Achievement', 'grouped')
	equals(call.options.orderBy, 'Football_Games.Season DESC', 'latest season first')
	contains(call.fields, 'COUNT(CASE WHEN Football_Games.ResultOpt=1 THEN 1 ELSE NULL END)=WinningCount', 'wins')
	contains(call.fields, 'COUNT(CASE WHEN Football_Games.ResultOpt=2 THEN 2 ELSE NULL END)=TieCount', 'draws')
	contains(call.fields, 'COUNT(CASE WHEN Football_Games.ResultOpt=3 THEN 3 ELSE NULL END)=LoosingCount', 'losses')
	contains(call.fields, 'Achievements.Competition=Competition', 'the trophy icon reads it')
	equals(stub.expanded[1].title, 'מפעל כדורגל/הצגת מספרים עונתיים/הצגת נתונים', 'the row template')
	equals(stub.expanded[1].args.WinningCount, '3', 'named args')
end)

check('seasons: a full page of rows is an error, not a short table', function(Competition)
	local rows = {}
	for index = 1, 500 do
		rows[index] = {}
	end
	stub.willReturn(rows)
	expectError('reached the limit', function()
		invoke(Competition, 'seasons', { ['מפעלים'] = MELCHETT })
	end)
end)

print(string.format('\n%d passed, %d failed', passed, failed))
os.exit(failed > 0 and 1 or 0)
