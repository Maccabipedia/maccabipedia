--[[
Tests for Module:FootballSeasonTable.

Queries come in a fixed order: the (season, competition) pairs with their
results, then the competition catalogue.

Run from the repository root:
    lua5.1 infra/football_queries/tests/test_season_table.lua
]]

package.path = 'infra/football_queries/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0

local function check(name, body)
	stub.install()
	local ok, message = pcall(body, stub.loadModule('Module:FootballSeasonTable'))
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

local function pair(season, competition, wins, draws, losses)
	return { season = season, competition = competition,
		wins = wins, draws = draws, losses = losses }
end

local CATALOGUE = {
	{ name = 'ליגת העל', league = '1', trophy = '0' },
	{ name = 'גביע המדינה', league = '0', trophy = '1' },
	{ name = 'גביע הטוטו', league = '0', trophy = '0' },
}

local function render(module, opponents)
	return module.rows(stub.newFrame({}, { ['יריבות'] = opponents }))
end

check('two queries: the pairs with their results, then the catalogue', function(module)
	stub.willReturn({ pair('2025/26', 'ליגת העל', '2', '1', '1') })
	stub.willReturn(CATALOGUE)
	render(module, 'הפועל תל אביב')
	equals(#stub.calls, 2, 'one query for every row, one for the order')
	local call = stub.calls[1]
	contains(call.options.where, 'Football_Games.Opponent IN ("הפועל תל אביב")', 'the opponent filter')
	contains(call.fields, 'SUM(CASE WHEN Football_Games.ResultOpt = 1 THEN 1 ELSE 0 END)=wins', 'wins')
	contains(call.fields, 'SUM(CASE WHEN Football_Games.ResultOpt = 2 THEN 1 ELSE 0 END)=draws', 'draws')
	contains(call.fields, 'SUM(CASE WHEN Football_Games.ResultOpt = 3 THEN 1 ELSE 0 END)=losses', 'losses')
	equals(call.options.groupBy, 'Football_Games.Season, Football_Games.Competition', 'one row per pair')
	equals(call.options.orderBy, 'Football_Games.Season DESC', 'seasons newest first, as the template')
	equals(call.tables, 'Football_Games', 'no Competitions join: uncatalogued games count too')
	equals(call.options.limit, 500, 'a real limit, never Cargo\'s silent 100')
	equals(stub.calls[2].tables, 'Competitions', 'the catalogue')
end)

check('a row: season and competition linked, the three results', function(module)
	stub.willReturn({ pair('2025/26', 'ליגת העל', '2', '1', '1') })
	stub.willReturn(CATALOGUE)
	equals(render(module, 'הפועל תל אביב'),
		'<div class="table-row"><span>[[עונת 2025/26|2025/26]]</span>'
		.. '<span>[[ליגת העל|ליגת העל]]</span><span>2</span><span>1</span><span>1</span></div>',
		'the template\'s row, with its class attribute closed')
end)

check('a missing page is plain text, as #קיים rendered it', function(module)
	stub.missingPages = { ['עונת 1930/31'] = true, ['ידידות'] = true }
	stub.willReturn({ pair('1930/31', 'ידידות', '1', '0', '0') })
	stub.willReturn(CATALOGUE)
	equals(render(module, 'הפועל תל אביב'),
		'<div class="table-row"><span>1930/31</span><span>ידידות</span>'
		.. '<span>1</span><span>0</span><span>0</span></div>', 'no links')
end)

check('within a season: league, cup, the rest, then by name; seasons keep their order', function(module)
	stub.willReturn({
		pair('2025/26', 'ידידות', '1', '0', '0'),
		pair('2025/26', 'גביע המדינה', '1', '0', '0'),
		pair('2025/26', 'גביע הטוטו', '0', '1', '0'),
		pair('2025/26', 'ליגת העל', '2', '0', '0'),
		pair('2024/25', 'גביע המדינה', '0', '0', '1'),
		pair('2024/25', 'ליגת העל', '1', '1', '0'),
	})
	stub.willReturn(CATALOGUE)
	local html = render(module, 'הפועל תל אביב')
	local order = {}
	for competition in html:gmatch('<span>%[%[[^|]*|([^%]]*)%]%]</span><span>%d') do
		order[#order + 1] = competition
	end
	equals(table.concat(order, ' / '),
		'ליגת העל / גביע המדינה / גביע הטוטו / ידידות / ליגת העל / גביע המדינה',
		'the defined order inside each season')
	local seasons = {}
	for season in html:gmatch('%[%[עונת [^|]*|([^%]]*)%]%]') do
		seasons[#seasons + 1] = season
	end
	equals(table.concat(seasons, ' '), '2025/26 2025/26 2025/26 2025/26 2024/25 2024/25',
		'seasons in the order the database gave')
end)

check('an uncatalogued competition keeps its real results', function(module)
	stub.willReturn({ pair('1937', 'ידידות', '1', '0', '0') })
	stub.willReturn(CATALOGUE)
	contains(render(module, 'הפועל תל אביב'), '<span>1</span><span>0</span><span>0</span>',
		'not the template\'s 0/0/0')
end)

check('the names list: each name stripped, quoted, and an entity decoded', function(module)
	stub.willReturn({})
	stub.willReturn(CATALOGUE)
	render(module, 'בית&#34;ר ירושלים, ביתר תל אביב')
	contains(stub.calls[1].options.where,
		'Football_Games.Opponent IN ("ביתר ירושלים", "ביתר תל אביב")',
		'Football_Games.Opponent stores names without quotes')
end)

check('no names: no query and no rows, never every game on the wiki', function(module)
	equals(render(module, '  '), '', 'the template\'s IN ("") listed nothing')
	equals(#stub.calls, 0, 'an empty filter would have meant no filter')
end)

check('no games: no rows', function(module)
	stub.willReturn({})
	stub.willReturn(CATALOGUE)
	equals(render(module, 'קבוצה בלי משחקים'), '', 'an empty table body')
end)

check('a decimal sum prints as a whole number, as #number_format did', function(module)
	stub.willReturn({ pair('2025/26', 'ליגת העל', '3.0', '0.0', '1.0') })
	stub.willReturn(CATALOGUE)
	contains(render(module, 'הפועל תל אביב'), '<span>3</span><span>0</span><span>1</span>',
		'MySQL returns SUM as a decimal')
end)

check('rows are separated by a newline', function(module)
	stub.willReturn({ pair('2025/26', 'ליגת העל', '1', '0', '0'), pair('2024/25', 'ליגת העל', '1', '0', '0') })
	stub.willReturn(CATALOGUE)
	contains(render(module, 'הפועל תל אביב'), '</div>\n<div class="table-row">', 'one row per line')
end)

-- ------------------------------------------------------------ referee tables

-- Referee queries: the pairs, then one map lookup per distinct competition
-- (in sorted order), then the catalogue.
local function lookup(concentrated)
	return concentrated and { { concentrated = concentrated } } or {}
end

local function referee(module, args)
	return module.rows(stub.newFrame({}, args))
end

check('the main referee: the Refs filter, one map lookup per distinct competition', function(module)
	stub.willReturn({ pair('2025/26', 'ליגת העל', '2', '0', '1'), pair('2024/25', 'ליגת העל', '1', '0', '0') })
	stub.willReturn(lookup('הליגה הראשונה בכדורגל'))
	stub.willReturn(CATALOGUE)
	referee(module, { ['שופט'] = 'אלון יפת', ['קישור מפעל'] = 'מרכז' })
	equals(#stub.calls, 3, 'the pairs, ONE lookup for two ליגת העל rows, the catalogue')
	contains(stub.calls[1].options.where, 'Football_Games.Refs = "אלון יפת"', 'the referee')
	equals(stub.calls[2].tables, 'Football_Competitions_Map', 'the map')
	equals(stub.calls[2].options.where, 'Names HOLDS "ליגת העל"', 'the templates\' own lookup')
	equals(stub.calls[2].options.limit, 1, 'limit 1, as the templates')
end)

check('the assistant referee: a HOLDS on the assistants', function(module)
	stub.willReturn({})
	stub.willReturn(CATALOGUE)
	referee(module, { ['עוזר שופט'] = 'יוסי לוי', ['קישור מפעל'] = 'מרכז' })
	contains(stub.calls[1].options.where, 'AssistantReferees HOLDS "יוסי לוי"', 'the assistant')
end)

check('through the map: each competition links where its own lookup says', function(module)
	stub.willReturn({ pair('2025/26', 'ליגת העל', '1', '0', '0'), pair('2025/26', 'גביע המדינה', '1', '0', '0'),
		pair('1946/47', 'גביע המלחמה', '1', '0', '0') })
	stub.willReturn(lookup('גביע המדינה'))           -- גביע המדינה
	stub.willReturn(lookup('גביע המדינה (מרכז)'))    -- גביע המלחמה
	stub.willReturn(lookup('הליגה הראשונה בכדורגל')) -- ליגת העל
	stub.willReturn(CATALOGUE)
	local html = referee(module, { ['שופט'] = 'אלון יפת', ['קישור מפעל'] = 'מרכז' })
	contains(html, '<span>[[הליגה הראשונה בכדורגל|ליגת העל]]</span>', 'the grouping page, the competition text')
	contains(html, '<span>[[גביע המדינה|גביע המדינה]]</span>', 'its own page')
	contains(html, '<span>[[גביע המדינה (מרכז)|גביע המלחמה]]</span>', 'a grouping page')
end)

check('through the map: a missing page shows the grouping name, no map row shows nothing', function(module)
	stub.missingPages = { ['גביע הטוטו'] = true }
	stub.willReturn({ pair('2025/26', 'גביע הטוטו', '1', '0', '0'), pair('1936', "גביע מלצ'ט", '0', '1', '0') })
	stub.willReturn(lookup("גביע הטוטו"))   -- sorted: גביע הטוטו before גביע מלצ'ט
	stub.willReturn(lookup(nil))
	stub.willReturn(CATALOGUE)
	local html = referee(module, { ['שופט'] = 'אלון יפת', ['קישור מפעל'] = 'מרכז' })
	contains(html, '<span>גביע הטוטו</span><span>1', '#קיים false: the grouping name, unlinked')
	contains(html, '<span></span><span>0</span><span>1', 'the map lacks it: an empty cell, as today')
end)

check('a competition name with a double quote is refused, not looked up', function(module)
	stub.willReturn({ pair('2025/26', 'גביע "חדש"', '1', '0', '0') })
	local ok, message = pcall(referee, module, { ['שופט'] = 'אלון יפת', ['קישור מפעל'] = 'מרכז' })
	equals(ok, false, 'refused')
	contains(message, 'cannot look up', 'says why')
end)

check('one filter per table', function(module)
	local ok, message = pcall(referee, module, { ['שופט'] = 'אלון יפת', ['יריבות'] = 'הפועל תל אביב' })
	equals(ok, false, 'two filters refused')
	contains(message, 'rows takes one of', 'says why')
	equals(#stub.calls, 0, 'nothing queried')
end)

check('without קישור מפעל the competition links to itself, and no map is read', function(module)
	stub.willReturn({ pair('2025/26', 'ליגת העל', '1', '0', '0') })
	stub.willReturn(CATALOGUE)
	contains(referee(module, { ['שופט'] = 'אלון יפת' }), '[[ליגת העל|ליגת העל]]', 'the opponent style')
	equals(#stub.calls, 2, 'no map query')
end)

print(string.format('\n%d passed, %d failed', passed, failed))
os.exit(failed > 0 and 1 or 0)
