--[[
Tests for Module:FootballQueries.

Run from the repository root:
    lua5.1 infra/football_queries/tests/test_football_queries.lua

Names in the fixtures are real players, clubs and stadiums, so a quoting bug
shows up as a name that would actually break rather than as "test1".
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

-- A season filter touches only Football_Games, so nothing else is joined. The
-- templates join four tables here regardless.
check('joins only the tables the filters need', function(FootballQueries)
	local query = FootballQueries.build({ ['עונה'] = '2021/22' })
	equals(query.tables, 'Football_Games', 'tables')
	equals(query.join, '', 'join')
	equals(query.where, 'Football_Games.Season = "2021/22"', 'where')
end)

check('a player filter reaches Games_Events, and only it', function(FootballQueries)
	local query = FootballQueries.build({
		['שחקן'] = 'ערן זהבי',
		['מספר אירוע'] = '3',
	})
	equals(query.tables, 'Football_Games,Games_Events', 'tables')
	equals(query.join, 'Football_Games._pageID = Games_Events._pageID', 'join')
	equals(query.where,
		'Games_Events.EventType IN (3) AND Games_Events.PlayerName = "ערן זהבי"',
		'where')
end)

check('קטגוריית מפעל brings in Competitions', function(FootballQueries)
	local query = FootballQueries.build({ ['קטגוריית מפעל'] = 'ליגה' })
	equals(query.tables, 'Football_Games,Competitions', 'tables')
	equals(query.join,
		'Football_Games.Competition = Competitions.OriginalName', 'join')
	equals(query.where, 'Competitions.League = 1', 'where')
end)

-- Silently ignored by כמות נתוני משחק today, which returns the unfiltered total.
check('יתר-רשמיים is a real filter here', function(FootballQueries)
	local query = FootballQueries.build({ ['קטגוריית מפעל'] = 'יתר-רשמיים' })
	equals(query.where,
		'(Competitions.Official = 1 AND Competitions.League = 0'
		.. ' AND Competitions.Trophy = 0 AND Competitions.International = 0)',
		'where')
end)

check('an unsupported filter is an error, not a dropped condition',
	function(FootballQueries)
		expectError('unsupported filter "כרטיסים צהובים"', function()
			FootballQueries.build({ ['כרטיסים צהובים'] = '1' })
		end)
	end)

check('an empty value means not provided', function(FootballQueries)
	local query = FootballQueries.build({
		['שחקן'] = '',
		['עונה'] = '2021/22',
	})
	equals(query.tables, 'Football_Games', 'tables')
	equals(query.where, 'Football_Games.Season = "2021/22"', 'where')
end)

-- Games_Events.PlayerName keeps apostrophes; Football_Games.Opponent does not.
check('quoting follows the column, not the value', function(FootballQueries)
	local query = FootballQueries.build({ ['שחקן'] = "אביעזר ז'נו" })
	equals(query.where, 'Games_Events.PlayerName = "אביעזר ז\'נו"', 'kept')

	query = FootballQueries.build({ ['יריבות'] = 'בית"ר ירושלים' })
	equals(query.where, 'Football_Games.Opponent IN ("ביתר ירושלים")', 'stripped')
end)

check('HTML-encoded quotes from PAGENAME are normalised', function(FootballQueries)
	local query = FootballQueries.build({ ['יריבות'] = 'בית&#34;ר ירושלים' })
	equals(query.where, 'Football_Games.Opponent IN ("ביתר ירושלים")', 'where')
end)

check('a double quote in a quote-keeping column is refused',
	function(FootballQueries)
		expectError('contains a double quote', function()
			FootballQueries.build({ ['שחקן'] = 'ערן "הצבר" זהבי' })
		end)
	end)

check('תוצאה maps to ResultOpt, and a wrong word is an error',
	function(FootballQueries)
		local query = FootballQueries.build({ ['תוצאה'] = 'ניצחון' })
		equals(query.where, 'Football_Games.ResultOpt = 1', 'win')

		expectError('must be ניצחון', function()
			FootballQueries.build({ ['תוצאה'] = 'נצחון' })
		end)
	end)

check('מכבי=לא asks for the opponent side', function(FootballQueries)
	equals(FootballQueries.build({ ['מכבי'] = 'לא' }).where,
		'Games_Events.Team = 0', 'opponent')
	equals(FootballQueries.build({ ['מכבי'] = 'כן' }).where,
		'Games_Events.Team = 1', 'maccabi')
end)

check('עוזר שופט uses HOLDS on the list field', function(FootballQueries)
	local query = FootballQueries.build({ ['עוזר שופט'] = 'ג\'ון ביטון' })
	equals(query.tables, 'Football_Games,Games_Referees', 'tables')
	equals(query.where,
		'Games_Referees.AssistantReferees HOLDS "ג\'ון ביטון"', 'where')
end)

check('a stadium filter expands to every related name', function(FootballQueries)
	stub.willReturn({
		{ name = 'אצטדיון בלומפילד' },
		{ name = 'בלומפילד' },
	})
	local query = FootballQueries.build({ ['אצטדיון'] = 'בלומפילד' })
	equals(query.where,
		'Football_Games.Stadium IN ("אצטדיון בלומפילד", "בלומפילד")', 'where')
	equals(stub.calls[1].tables, 'Stadiums=s1,Stadiums=s2', 'alias tables')
end)

check('a stadium that matches nothing is an error', function(FootballQueries)
	stub.willReturn({})
	expectError('matched no known name', function()
		FootballQueries.build({ ['אצטדיון'] = 'אצטדיון שלא קיים' })
	end)
end)

check('a date is quoted and formatted on both sides', function(FootballQueries)
	local query = FootballQueries.build({ ['תאריך'] = '2021-08-22' })
	equals(query.where,
		'DATE_FORMAT("2021-08-22", "%d-%m-%Y")'
		.. ' = DATE_FORMAT(Football_Games.Date, "%d-%m-%Y")', 'where')
end)

check('an unsafe date format is refused', function(FootballQueries)
	expectError('unsafe פורמט תאריך', function()
		FootballQueries.build({
			['תאריך'] = '2021-08-22',
			['פורמט תאריך'] = '%Y") OR 1=1 -- ',
		})
	end)
end)

-- The guard that matters most: Cargo truncates at the limit with no warning.
check('a result that hit the row limit is an error', function(FootballQueries)
	local rows = {}
	for index = 1, 500 do
		rows[index] = { n = index }
	end
	stub.willReturn(rows)

	expectError('hit the limit', function()
		FootballQueries.query({ ['עונה'] = '2021/22' }, { limit = 500 })
	end)
end)

check('count returns the number', function(FootballQueries)
	stub.willReturn({ { n = '220' } })
	equals(FootballQueries.count({ ['שחקן'] = 'ערן זהבי' }), 220, 'count')
end)

check('the same filter set always builds identical SQL', function(FootballQueries)
	local filters = {
		['שחקן'] = 'ערן זהבי',
		['קטגוריית מפעל'] = 'ליגה',
		['עונה'] = '2021/22',
		['מספר אירוע'] = '3',
	}
	local first = FootballQueries.build(filters)
	for _ = 1, 20 do
		local again = FootballQueries.build(filters)
		equals(again.where, first.where, 'where is stable')
		equals(again.tables, first.tables, 'tables are stable')
	end
end)

print(string.format('\n%d passed, %d failed', passed, failed))
os.exit(failed > 0 and 1 or 0)
