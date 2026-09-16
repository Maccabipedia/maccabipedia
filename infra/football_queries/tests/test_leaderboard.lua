--[[
Tests for the leaderboard primitive and the referee `leaderboards` widget.

Run from the repository root:
    lua5.1 infra/football_queries/tests/test_leaderboard.lua

The primitive replaces 32 template queries on a referee page with one, so what
matters most is that each column still counts exactly what its template did:
the goals column without own goals, every tab under Official = 1, the referee
in the WHERE and nowhere else - and that the ranking, the distinct count and
the "עוד" rule computed in Lua match what the templates showed.
]]

package.path = 'infra/football_queries/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0

local function check(name, body)
	stub.install()
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
		error(string.format('%s\n        unexpected: %s\n        in: %s',
			what or 'found', piece, tostring(text)), 0)
	end
end

local function expectError(pattern, body)
	local ok, message = pcall(body)
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find(pattern, 1, true) then
		error('wrong error: ' .. tostring(message), 0)
	end
end

local function queries()
	return stub.loadModule('Module:FootballQueries')
end

local APPEARANCES = { name = 'apps', grain = 'event',
	filters = { ['מספר אירוע'] = '1,5', ['קטגוריית מפעל'] = 'ליגה' } }
local GOALS = { name = 'goals', grain = 'event',
	filters = { ['מספר אירוע'] = '3', ['ללא תת אירוע'] = '33',
	            ['קטגוריית מפעל'] = 'רשמי' } }
local SHARED = { ['עוזר שופט'] = 'דודו ביטון', ['קטגוריית מפעל'] = 'רשמי' }

-- ---------------------------------------------------------------- primitive

check('one grouped query, the group key selected and grouped', function()
	queries().leaderboard(SHARED, { APPEARANCES, GOALS }, { groupBy = 'player' })
	equals(#stub.calls, 1, 'queries')
	local call = stub.calls[1]
	contains(call.fields, 'Games_Events.PlayerName=g,', 'group key selected')
	equals(call.options.groupBy, 'Games_Events.PlayerName', 'group by')
	equals(call.options.orderBy, nil, 'no ORDER BY - ranking is in Lua')
	equals(call.options.limit, 5000, 'every group, under the maxLimit guard')
end)

check('the referee is in the WHERE, not in any column', function()
	queries().leaderboard(SHARED, { APPEARANCES, GOALS }, { groupBy = 'player' })
	local call = stub.calls[1]
	contains(call.options.where, 'HOLDS', 'HOLDS in the where')
	lacks(call.fields, 'HOLDS', 'HOLDS in a field reaches MySQL verbatim')
end)

check('every column runs under Official = 1, the league tab included',
		function()
	queries().leaderboard(SHARED, { APPEARANCES }, { groupBy = 'player' })
	contains(stub.calls[1].options.where, 'Official', 'official in the where')
	contains(stub.calls[1].fields, 'League', 'the league tab keeps its own flag')
end)

check('own goals are excluded in the goals column only', function()
	queries().leaderboard(SHARED, { APPEARANCES, GOALS }, { groupBy = 'player' })
	local call = stub.calls[1]
	lacks(call.options.where, 'SubType', 'subtype in the shared where')
	local columns = {}
	for column in (call.fields .. ',SUM('):gmatch('SUM%((.-)%)=c%d+,') do
		columns[#columns + 1] = column
	end
	equals(#columns, 2, 'two columns')
	lacks(columns[1], 'SubType', 'appearances column untouched')
	contains(columns[2], 'SubType != 33', 'goals column excludes own goals')
end)

check('the WHERE narrows to the union of the columns\' event types', function()
	queries().leaderboard(SHARED, { APPEARANCES, GOALS }, { groupBy = 'player' })
	contains(stub.calls[1].options.where, 'EventType IN (1, 5, 3)', 'union')
end)

check('Maccabi\'s side goes into the WHERE, so opponents are never grouped',
		function()
	queries().leaderboard(SHARED, { APPEARANCES, GOALS }, { groupBy = 'player' })
	contains(stub.calls[1].options.where, 'Games_Events.Team = 1', 'side in the where')
end)

check('...but not when a column asks for a side itself', function()
	local opponents = { name = 'opp', grain = 'event',
		filters = { ['מספר אירוע'] = '3', ['מכבי'] = 'לא' } }
	queries().leaderboard(SHARED, { APPEARANCES, opponents },
		{ groupBy = 'player' })
	lacks(stub.calls[1].options.where, 'Team', 'a Team = 1 WHERE would zero it')
	contains(stub.calls[1].fields, 'Games_Events.Team = 0', 'the column keeps its side')
end)

check('no union when a column has no event type', function()
	local anyEvent = { name = 'any', grain = 'event',
		filters = { ['קטגוריית מפעל'] = 'גביע', ['מכבי'] = 'כן' } }
	queries().leaderboard(SHARED, { APPEARANCES, anyEvent },
		{ groupBy = 'player' })
	lacks(stub.calls[1].options.where, 'EventType', 'no union then')
end)

local function rowsOf(counts)
	local rows = {}
	for name, count in pairs(counts) do
		rows[#rows + 1] = { g = name, c1 = tostring(count) }
	end
	return rows
end

check('ranking: count DESC, ties by name, zeroes dropped', function()
	stub.willReturn(rowsOf({ ['ערן זהבי'] = 32, ['אייל גולסה'] = 32,
	                         ['שרן ייני'] = 71, ['אף אחד'] = 0 }))
	local result = queries().leaderboard(SHARED, { APPEARANCES },
		{ groupBy = 'player' }).apps
	equals(result.players, 3, 'distinct players, zero dropped')
	equals(result.rows[1].name, 'שרן ייני', 'highest first')
	equals(result.rows[2].name, 'אייל גולסה', 'tie broken by name')
	equals(result.rows[3].name, 'ערן זהבי', 'tie broken by name')
	equals(result.more, false, 'three players, no link')
end)

check('top N, and "more" only when there are MORE than N', function()
	local ten, eleven = {}, {}
	for index = 1, 11 do
		eleven['שחקן ' .. index] = 100 - index
		if index <= 10 then
			ten['שחקן ' .. index] = 100 - index
		end
	end
	stub.willReturn(rowsOf(ten))
	stub.willReturn(rowsOf(eleven))
	local module = queries()
	local exactlyTen = module.leaderboard(SHARED, { APPEARANCES },
		{ groupBy = 'player' }).apps
	equals(#exactlyTen.rows, 10, 'ten rows')
	equals(exactlyTen.more, false, 'exactly ten: no link to an empty page')
	local elevenPlayers = module.leaderboard(SHARED, { APPEARANCES },
		{ groupBy = 'player' }).apps
	equals(#elevenPlayers.rows, 10, 'cut to ten')
	equals(elevenPlayers.players, 11, 'but counts eleven')
	equals(elevenPlayers.more, true, 'eleven: link')
end)

check('no rows: every column empty, not an error', function()
	local result = queries().leaderboard(SHARED, { APPEARANCES, GOALS },
		{ groupBy = 'player' })
	equals(result.apps.players, 0, 'no players')
	equals(#result.goals.rows, 0, 'no rows')
end)

check('a blank group name is kept, not a crash', function()
	stub.willReturn({ { c1 = '4' }, { g = 'שרן ייני', c1 = '4' } })
	local result = queries().leaderboard(SHARED, { APPEARANCES },
		{ groupBy = 'player' }).apps
	equals(result.players, 2, 'both counted')
	equals(result.rows[1].name, '', 'blank sorts first on a tie')
end)

check('refusals', function()
	local module = queries()
	expectError('does not take "orderBy"', function()
		module.leaderboard(SHARED, { APPEARANCES },
			{ groupBy = 'player', orderBy = 'x' })
	end)
	expectError('needs groupBy', function()
		module.leaderboard(SHARED, { APPEARANCES }, {})
	end)
	expectError('top must be a positive whole number', function()
		module.leaderboard(SHARED, { APPEARANCES },
			{ groupBy = 'player', top = 0 })
	end)
	expectError('needs at least one column', function()
		module.leaderboard(SHARED, {}, { groupBy = 'player' })
	end)
	expectError('uses a HOLDS filter', function()
		module.leaderboard({}, { { name = 'x', grain = 'event',
			filters = { ['מספר אירוע'] = '1', ['עוזר שופט'] = 'x' } } },
			{ groupBy = 'player' })
	end)
end)

check('a truncated result raises instead of ranking a cut-off list', function()
	local many = {}
	for index = 1, 5000 do
		many[index] = { g = 'p' .. index, c1 = '1' }
	end
	stub.willReturn(many)
	expectError('hit the limit', function()
		queries().leaderboard(SHARED, { APPEARANCES }, { groupBy = 'player' })
	end)
end)

-- ------------------------------------------------------------------- widget

local function widget()
	return stub.loadModule('Module:FootballStatsBlock')
end

local function refereeFrame(name, extra)
	local direct = { ['בלוק'] = 'referee-assistant', ['שופט'] = name }
	for key, value in pairs(extra or {}) do
		direct[key] = value
	end
	-- The caller's own parameters are hostile on purpose: the real section
	-- carries שם להצגה and הסתר הערת סוג עמוד, and neither may reach the query.
	return stub.newFrame({ ['שם להצגה'] = 'לא זה', ['הסתר הערת סוג עמוד'] = 'כן' },
		direct)
end

-- 16 columns: appearances, goals, assists, cards x רשמי, ליגה, גביע, בינלאומי.
local function column(box, tab)
	return 'c' .. ((box - 1) * 4 + tab)
end

check('the widget: one query, four boxes, four tabbers', function()
	local html = widget().leaderboards(refereeFrame('דודו ביטון'))
	equals(#stub.calls, 1, 'one query for all 16 leaderboards')
	equals(#stub.extensionTags, 4, 'a tabber per box')
	local _, boxes = html:gsub('records%-list%-tabs%-container', '')
	equals(boxes, 4, 'four box wrappers')
	contains(html, '<div class="title">שיאני הופעות</div>', 'appearances title')
	contains(html, '<div class="title">שיאני צהובים</div>', 'cards title, as-is')
	contains(stub.calls[1].options.where, 'HOLDS "דודו ביטון"',
		'the direct argument, not the caller\'s שם להצגה')
	contains(stub.calls[1].options.where, 'Competitions.Official = 1',
		'every tab under Official = 1, as the templates had it')
end)

check('the widget: a league link keeps the league', function()
	local rows = {}
	for index = 1, 11 do
		rows[index] = { g = 'שחקן ' .. index, [column(1, 2)] = '3' }
	end
	stub.willReturn(rows)
	widget().leaderboards(refereeFrame('דודו ביטון'))
	local leagueTab = stub.extensionTags[1].content:match('|%-|ליגה=(.-)|%-|')
	contains(leagueTab, 'ViewData', 'eleven league players: a link')
	contains(leagueTab, 'League', 'the link counts the league, not all official')
	-- The templates' league query carries Official = 1 AND League = 1, and so
	-- does the box. A link rebuilt from filter names lost Official, because
	-- the tab's category overwrote the shared רשמי under the same name.
	contains(leagueTab, 'Competitions.Official = 1', 'the link keeps Official')
	contains(leagueTab, 'HOLDS', 'the link keeps the referee')
end)

check('the widget: tab order, labels, headings with counts and nouns', function()
	local row = { g = 'שרן ייני' }
	for box = 1, 4 do
		for tab = 1, 4 do
			row[column(box, tab)] = '0'
		end
	end
	row[column(1, 1)] = '71'
	row[column(1, 2)] = '59'
	stub.willReturn({ row, { g = 'דור מיכה', [column(1, 1)] = '60' } })
	widget().leaderboards(refereeFrame('דודו ביטון'))

	local appearances = stub.extensionTags[1].content
	contains(appearances, 'משחקים רשמיים=<div class="tab-header">משחקים רשמיים '
		.. '(2 מופיעים שונים)</div>', 'first tab heading')
	contains(appearances, '|-|ליגה=<div class="tab-header">ליגה (1 מופיעים שונים)',
		'league tab heading')
	contains(appearances, '|-|גביע=<div class="tab-header">גביע המדינה (0 ',
		'cup heading differs from its label')
	contains(appearances, '|-|אירופה=<div class="tab-header">אירופה (0 ',
		'international labelled אירופה')
	contains(appearances, 'ROW(שרן ייני|71)\nROW(דור מיכה|60)', 'rows in rank order')
	contains(stub.extensionTags[2].content, 'כובשים שונים', 'goals noun')
	contains(stub.extensionTags[3].content, 'שחקנים שונים', 'assists noun')
end)

check('the widget: rows go through the display template, positionally', function()
	stub.willReturn({ { g = 'ערן זהבי', [column(1, 1)] = '3' } })
	widget().leaderboards(refereeFrame('דודו ביטון'))
	equals(stub.expanded[1].title, 'סטטיסטיקות/הצגת שיאנים/הצגת שחקן/כדורגל',
		'display template')
	equals(stub.expanded[1].args[1], 'ערן זהבי', 'name is arg 1')
	equals(stub.expanded[1].args[2], '3', 'count is arg 2')
end)

check('the widget: "עוד" only past ten, pointing at rows 11-110', function()
	local rows = {}
	for index = 1, 11 do
		rows[index] = { g = 'שחקן ' .. index, [column(1, 1)] = tostring(50 - index),
		                [column(1, 2)] = index <= 10 and '5' or '0' }
	end
	stub.willReturn(rows)
	widget().leaderboards(refereeFrame('דודו ביטון'))
	local appearances = stub.extensionTags[1].content
	local officialTab = appearances:match('^(.-)|%-|ליגה=')
	local leagueTab = appearances:match('|%-|ליגה=(.-)|%-|')
	contains(officialTab, 'מיוחד:ViewData', 'eleven players: a link')
	contains(officialTab, 'offset=10', 'from row 11')
	contains(officialTab, 'limit=100', 'a hundred rows')
	contains(officialTab, 'order_by=COUNT(*) DESC, Games_Events.PlayerName',
		'the same tiebreak as the tab')
	contains(officialTab, 'HOLDS', 'the link keeps the referee')
	contains(officialTab, ' עוד]', 'link text')
	lacks(leagueTab, 'ViewData', 'exactly ten players: no link')
end)

check('the widget: each box counts exactly its template\'s events', function()
	widget().leaderboards(refereeFrame('דודו ביטון'))
	local fields = stub.calls[1].fields
	local columns = {}
	for column in (fields .. ',SUM('):gmatch('SUM%((.-)%)=c%d+,') do
		columns[#columns + 1] = column
	end
	equals(#columns, 16, 'four boxes of four tabs')
	contains(columns[1], 'EventType IN (1, 5)', 'appearances')
	contains(columns[5], 'EventType IN (3)', 'goals')
	contains(columns[5], 'SubType != 33', 'goals without own goals')
	contains(columns[9], 'EventType IN (4)', 'assists')
	contains(columns[13], 'EventType IN (7)', 'cards')
	contains(columns[13], 'SubType IN (71)', 'yellow cards only')
end)

check('the widget: the goals link excludes own goals too', function()
	local rows = {}
	for index = 1, 11 do
		rows[index] = { g = 'כובש ' .. index, [column(2, 1)] = '2' }
	end
	stub.willReturn(rows)
	widget().leaderboards(refereeFrame('דודו ביטון'))
	contains(stub.extensionTags[2].content, 'SubType != 33', 'goals link')
end)

check('the widget refuses what would silently mislead', function()
	local module = widget()
	expectError('needs a non-empty שופט', function()
		module.leaderboards(refereeFrame('  '))
	end)
	expectError('takes only בלוק and שופט', function()
		module.leaderboards(refereeFrame('דודו ביטון', { ['עונה'] = '2020/21' }))
	end)
	expectError('no leaderboard block declared as "day-results"', function()
		module.leaderboards(stub.newFrame({}, { ['בלוק'] = 'day-results' }))
	end)
	equals(#stub.calls, 0, 'nothing queried on a refusal')
end)

print(string.format('\n%d passed, %d failed', passed, failed))
os.exit(failed > 0 and 1 or 0)
