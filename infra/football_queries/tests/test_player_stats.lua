--[[
Tests for Module:FootballPlayerStats.

Run from the repository root:
    lua5.1 infra/football_queries/tests/test_player_stats.lua
]]

package.path = 'infra/football_queries/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0
local module

local function check(name, body)
	stub.install()
	module = stub.loadModule('Module:FootballPlayerStats')
	local ok, message = pcall(body)
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
		error(string.format('%s\n        unexpected: %s', what or 'found', piece), 0)
	end
end

-- Categories 1-5 = רשמי, ליגה, גביע, בינלאומי, יתר-רשמיים; cells 1-13 in the module's order.
local CELL = { appearances = 1, substitutions = 2, cleanSheets = 3, goals = 4, penaltyGoals = 5,
	assists = 6, penaltiesWon = 7, penaltySaves = 8, yellows = 9, reds = 10, wins = 11,
	draws = 12, losses = 13 }

local frame
local function value(player, category, cell)
	return module.value(stub.newFrameKeepingVariables({}, {
		['שחקן'] = player, ['קטגוריית מפעל'] = category, ['תא'] = cell }))
end

local function fresh()
	frame = stub.newFrame({}, {})
end

check('the first value runs ONE query for every outfield number of all five tabs', function()
	fresh()
	stub.willReturn({ { c2_4 = '150', c1_1 = '220' } })
	equals(value('ערן זהבי', 'ליגה', 'goals'), '150', 'league goals')
	equals(#stub.calls, 1, 'one query')
	local _, columns = stub.calls[1].fields:gsub('=c%d_%d+', '')
	equals(columns, 65, 'thirteen numbers for each of five tabs')
	contains(stub.calls[1].options.where, 'Games_Events.PlayerName = "ערן זהבי"', 'the player')
	contains(stub.calls[1].options.where, 'Games_Events.Team = 1', 'Maccabi\'s events, as every template')
	equals(stub.calls[1].tables, 'Football_Games, Games_Events, Competitions', 'the templates\' tables')
	equals(value('ערן זהבי', 'רשמי', 'appearances'), '220', 'another number of the same row')
	equals(#stub.calls, 1, 'read back from the page variables, no second query')
end)

check('each number is its template\'s: games containing events, or event rows', function()
	fresh()
	stub.willReturn({ {} })
	value('ערן זהבי', 'רשמי', 'goals')
	local fields = stub.calls[1].fields
	contains(fields, 'COUNT(DISTINCT CASE WHEN Games_Events.EventType IN (1,5) AND Competitions.Official = 1'
		.. ' THEN Football_Games._pageName END)=c1_1', 'appearances: distinct games')
	contains(fields, 'COUNT(DISTINCT CASE WHEN Games_Events.EventType IN (1, 5) AND Football_Games.ResultOpponent = 0'
		.. ' AND Competitions.League = 1 THEN Football_Games._pageName END)=c2_3', 'clean sheets: games, 0 conceded')
	contains(fields, 'SUM(CASE WHEN Games_Events.EventType IN (3) AND Games_Events.SubType != 33'
		.. ' AND Competitions.Trophy = 1 THEN 1 ELSE 0 END)=c3_4', 'goals: rows, no own goals')
	contains(fields, 'SUM(CASE WHEN Games_Events.EventType IN (7) AND Games_Events.SubType IN (72, 73)'
		.. ' AND Competitions.International = 1 THEN 1 ELSE 0 END)=c4_10', 'reds: both kinds')
	contains(fields, 'SUM(CASE WHEN Games_Events.EventType IN (1, 5) AND Football_Games.ResultOpt = 3'
		.. ' AND Competitions.Official = 1 AND Competitions.League = 0 AND Competitions.Trophy = 0'
		.. ' AND Competitions.International = 0 THEN 1 ELSE 0 END)=c5_13', 'losses in other official games')
	lacks(fields, 'WHEN (', 'Cargo reads WHEN ( as a function')
end)

check('no events: counts are 0, never empty; decimals are whole numbers', function()
	fresh()
	stub.willReturn({ { c1_1 = '0', c1_9 = '3.0' } })
	equals(value('שחקן בלי משחקים', 'רשמי', 'goals'), '0', 'SUM over nothing is NULL; the template said 0')
	equals(value('שחקן בלי משחקים', 'רשמי', 'yellows'), '3', 'no decimal point')
end)

check('keeper numbers: two more queries, only when a keeper number is asked for', function()
	fresh()
	stub.willReturn({ { c1_1 = '10' } })
	value('רפי כהן', 'רשמי', 'appearances')
	equals(#stub.calls, 1, 'an outfield number needs one query')
	stub.willReturn({ { c1 = '12.0', c2 = nil } })
	stub.willReturn({ { c1 = '2' } })
	equals(value('רפי כהן', 'רשמי', 'conceded'), '12', 'conceded goals')
	equals(#stub.calls, 3, 'the two keeper queries')
	equals(value('רפי כהן', 'ליגה', 'conceded'), '', 'ROUND(SUM()) over nothing: empty, as the template')
	equals(value('רפי כהן', 'ליגה', 'penaltiesConceded'), '0', 'COUNT over nothing: 0')
	equals(value('רפי כהן', 'רשמי', 'penaltiesConceded'), '2', 'penalty goals conceded')
	equals(#stub.calls, 3, 'no more queries')
	local conceded, penalties = stub.calls[2], stub.calls[3]
	contains(conceded.fields, 'ROUND(SUM(CASE WHEN Competitions.Official = 1 THEN Football_Games.ResultOpponent'
		.. ' ELSE NULL END))=c1', 'the conceded sum')
	contains(conceded.options.where, 'Games_Events.EventType IN (1, 5) AND Football_Games.Technical = -1',
		'appearance rows of non-technical games')
	equals(conceded.options.join, 'Football_Games._pageName=Games_Events._pageName, '
		.. 'Football_Games.Competition=Competitions.OriginalName', 'joined on the page name, as the template')
	equals(penalties.tables, 'Football_Games=fg, Games_Events=ge1, Games_Events=ge2, Competitions=c', 'self-join')
	contains(penalties.options.where, 'ge2.Team = 0 AND ge2.SubType = 35 AND fg.Technical = -1',
		'the opponent\'s penalty goals in non-technical games')
	contains(penalties.fields, 'SUM(CASE WHEN c.League = 1 THEN 1 ELSE 0 END)=c2', 'categories on the alias')
end)

check('players do not share numbers', function()
	fresh()
	stub.willReturn({ { c1_4 = '5' } })
	stub.willReturn({ { c1_4 = '9' } })
	equals(value('א', 'רשמי', 'goals'), '5', 'first player')
	equals(value('ב', 'רשמי', 'goals'), '9', 'second player queried separately')
	equals(value('א', 'רשמי', 'goals'), '5', 'the first player kept')
end)

check('a name as PAGENAME gave it: entities decoded, a double quote escaped, & refused', function()
	fresh()
	stub.willReturn({ {} })
	value('ג&#39;ורדי קרויף', 'רשמי', 'goals')
	contains(stub.calls[1].options.where, 'PlayerName = "ג\'ורדי קרויף"', 'the apostrophe decoded')
	stub.willReturn({ {} })
	value('אמנון חרל&#34;פ', 'רשמי', 'goals')
	contains(stub.calls[2].options.where, 'PlayerName = "אמנון חרל\\"פ"', 'the quote escaped')
	local ok, message = pcall(value, 'א &amp; ב', 'רשמי', 'goals')
	equals(ok, false, 'an ampersand refused')
	contains(message, 'ampersand', 'says why')
end)

check('an unknown tab or number, or no player, is an error', function()
	fresh()
	for _, args in ipairs({ { 'ערן זהבי', 'ידידות', 'goals' }, { 'ערן זהבי', 'רשמי', 'shots' },
		{ '', 'רשמי', 'goals' } }) do
		local ok = pcall(value, args[1], args[2], args[3])
		equals(ok, false, 'refused: ' .. table.concat(args, '/'))
	end
	equals(#stub.calls, 0, 'nothing queried')
end)

check('an aggregate that does not return exactly one row is an error', function()
	fresh()
	stub.willReturn({})
	local ok, message = pcall(value, 'ערן זהבי', 'רשמי', 'goals')
	equals(ok, false, 'refused')
	contains(message, 'returned 0 rows', 'says why')
end)

print(string.format('\n%d passed, %d failed', passed, failed))
os.exit(failed > 0 and 1 or 0)
