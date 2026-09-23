--[[
Tests for Module:BasketballSeasonTable - the same shared Module:SeasonTable
football's table runs on, bound to basketball.

What basketball has to get right that football did not: two result columns
instead of three (there is no draw), and season and competition pages in the
`כדורסל:` namespace.

Queries come in a fixed order: the (season, competition) pairs with their
results, then the competition catalogue.

Run from the repository root:
    lua5.1 infra/lua_modules/tests/test_basketball_season_table.lua
]]

package.path = 'infra/lua_modules/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0

local function check(name, body)
	stub.install()
	local ok, message = pcall(body, stub.loadModule('Module:BasketballSeasonTable'))
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

local function pair(season, competition, wins, losses)
	return { season = season, competition = competition, wins = wins, losses = losses }
end

local CATALOGUE = {
	{ name = 'ליגת העל בכדורסל', league = '1', trophy = '0' },
	{ name = 'גביע המדינה בכדורסל', league = '0', trophy = '1' },
	{ name = 'היורוליג', league = '0', trophy = '0' },
}

local function render(module, opponents)
	return module.rows(stub.newFrame({}, { ['יריבות'] = opponents }))
end

check('two queries: the pairs with their results, then the catalogue', function(module)
	stub.willReturn({ pair('2023/24', 'ליגת העל בכדורסל', '2', '1') })
	stub.willReturn(CATALOGUE)
	render(module, 'הפועל תל אביב')
	equals(#stub.calls, 2, 'one query for every row, one for the order')
	local call = stub.calls[1]
	contains(call.options.where, 'Basketball_Games.Opponent IN ("הפועל תל אביב")', 'the opponent')
	contains(call.fields, 'SUM(CASE WHEN Basketball_Games.ResultOpt = 1 THEN 1 ELSE 0 END)=wins', 'wins')
	contains(call.fields, 'SUM(CASE WHEN Basketball_Games.ResultOpt = 3 THEN 1 ELSE 0 END)=losses', 'losses')
	-- There is no draw in basketball: a draws column would be a column of zeroes.
	lacks(call.fields, 'draws', 'no draws column')
	lacks(call.fields, 'ResultOpt = 2', 'and nothing counts a draw')
	equals(call.options.groupBy, 'Basketball_Games.Season, Basketball_Games.Competition', 'one row per pair')
	equals(call.options.orderBy, 'Basketball_Games.Season DESC', 'seasons newest first')
	equals(call.tables, 'Basketball_Games', 'no catalogue join: uncatalogued games count too')
	equals(call.options.limit, 5000, 'a real limit, never Cargo\'s silent 100')
	equals(stub.calls[2].tables, 'Basketball_Competitions', 'the catalogue')
end)

check('a row: season and competition linked in the כדורסל namespace', function(module)
	stub.willReturn({ pair('2023/24', 'ליגת העל בכדורסל', '2', '1') })
	stub.willReturn(CATALOGUE)
	equals(render(module, 'הפועל תל אביב'),
		'<div class="table-row"><span>[[כדורסל: עונת 2023/24|2023/24]]</span>'
		.. '<span>[[כדורסל: ליגת העל בכדורסל|ליגת העל בכדורסל]]</span>'
		.. '<span>2</span><span>1</span></div>',
		'two counts, and the row template\'s own links')
end)

check('a missing page is plain text, as #קיים rendered it', function(module)
	stub.missingPages = { ['כדורסל: עונת 1954/55'] = true, ['כדורסל: ידידות'] = true }
	stub.willReturn({ pair('1954/55', 'ידידות', '1', '0') })
	stub.willReturn(CATALOGUE)
	equals(render(module, 'הפועל תל אביב'),
		'<div class="table-row"><span>1954/55</span><span>ידידות</span>'
		.. '<span>1</span><span>0</span></div>', 'no links')
end)

check('within a season: league, then cup, then the rest by name', function(module)
	stub.willReturn({
		pair('2023/24', 'היורוליג', '1', '1'),
		pair('2023/24', 'גביע המדינה בכדורסל', '2', '0'),
		pair('2023/24', 'ליגת העל בכדורסל', '3', '1'),
		pair('2022/23', 'ליגת העל בכדורסל', '4', '2'),
	})
	stub.willReturn(CATALOGUE)
	local html = render(module, 'הפועל תל אביב')
	local order = {}
	for competition in html:gmatch('|([^|%]]*)%]%]</span><span>%d') do
		order[#order + 1] = competition
	end
	equals(table.concat(order, ' / '),
		'ליגת העל בכדורסל / גביע המדינה בכדורסל / היורוליג / ליגת העל בכדורסל',
		'the newer season regrouped, the older one left where it was')
end)

check('a competition with no catalogue row keeps its real numbers', function(module)
	stub.willReturn({ pair('2023/24', 'גביע ווינר', '5', '2') })
	stub.willReturn(CATALOGUE)
	contains(render(module, 'הפועל תל אביב'), '<span>5</span><span>2</span>',
		'counted from the games, not through the catalogue')
end)

check('no opponent lists nothing, and asks nothing', function(module)
	equals(render(module, ''), '', 'empty')
	equals(#stub.calls, 0, 'no query for an empty filter')
end)

check('an argument that is not one of this sport\'s entities is ignored', function(module)
	-- Basketball's entities are יריבות and the two referee filters. Football's
	-- head-referee filter is plain `שופט`, which basketball does not declare, so
	-- it does not become a filter and does not raise; asked for alone it yields
	-- the empty table, which is what the templates' IN ("") gave.
	equals(module.rows(stub.newFrame({}, { ['שופט'] = 'דן' })), '', 'nothing listed')
	equals(#stub.calls, 0, 'and nothing queried')
end)

check('the head referee table: one filter, and the grouping link', function(module)
	-- In call order: the pairs, then the grouping lookup (one per distinct
	-- competition), then the catalogue that ranks them.
	stub.willReturn({ pair('2023/24', 'ליגת העל בכדורסל', '2', '1') })
	stub.willReturn({ { concentrated = 'ליגת העל בכדורסל' } })
	stub.willReturn(CATALOGUE)
	local html = module.rows(stub.newFrame({},
		{ ['שופט ראשי'] = 'אור זרור', ['קישור מפעל'] = 'מרכז' }))
	contains(stub.calls[1].options.where, 'אור זרור', 'the referee reached the query')
	local lookup = stub.calls[2]
	equals(lookup.tables, 'Basketball_Competitions_Map', 'basketball\'s own map')
	contains(lookup.options.where, 'Names HOLDS "ליגת העל בכדורסל"', 'the rows\' own lookup')
	contains(html, '<div class="table-row">', 'a row came back')
end)

check('the assistant referee is a filter of its own', function(module)
	stub.willReturn({ pair('2023/24', 'ליגת העל בכדורסל', '2', '1') })
	stub.willReturn(CATALOGUE)
	module.rows(stub.newFrame({}, { ['עוזר שופט'] = 'יוסף עטיה' }))
	contains(stub.calls[1].options.where, 'יוסף עטיה', 'the assistant reached the query')
end)

check('two entities at once are refused', function(module)
	local ok, message = pcall(module.rows, stub.newFrame({},
		{ ['יריבות'] = 'הפועל תל אביב', ['שופט ראשי'] = 'אור זרור' }))
	equals(ok, false, 'raised')
	contains(message, 'rows takes one of', 'said why')
	equals(#stub.calls, 0, 'nothing queried')
end)

check('errors carry the basketball name', function(module)
	local ok, message = pcall(module.rows, stub.newFrame({},
		{ ['יריבות'] = 'הפועל תל אביב', ['שופט ראשי'] = 'אור זרור' }))
	equals(ok, false)
	contains(message, 'BasketballSeasonTable:', 'the binding\'s own name')
end)

print(string.format('%d passed, %d failed', passed, failed))
if failed > 0 then
	os.exit(1)
end
