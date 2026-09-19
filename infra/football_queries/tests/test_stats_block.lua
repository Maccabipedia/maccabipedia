--[[
Tests for Module:FootballStatsBlock.

The output has to be byte-identical to the template it replaces, so these
assert exact strings - including the space before "(" on the first row, its
absence on the last, and the space before ")" in "ספסולים )". Those are the
template's oddities and reproducing them is the requirement, not a style
choice.

Run from the repository root:
    lua5.1 infra/football_queries/tests/test_player_events.lua
]]

package.path = 'infra/football_queries/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0

local function check(name, body)
	stub.install()
	local ok, message = pcall(body, stub.loadModule('Module:FootballStatsBlock'))
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

local function row(label, stat)
	return '<div class="Top10Row"><div class="Top10RowName">' .. label
		.. '</div><span class="Top10RowStat">' .. stat .. '</span></div>'
end

local ZAHAVI = {
	appearances = 100, substitutions = 23, goals = 52, penaltyGoals = 6,
	assists = 11, yellows = 12, reds = 1, benchStarts = 26,
}

check('the six rows render exactly as the template does', function(Events)
	local expected = table.concat({
		row('הופעות', '100 (23 חילופים)'),
		row('שערים', '52 (0.52 שערים למשחק, 6 פנדלים)'),
		row('בישולים', '11'),
		row('צהובים', '12'),
		row('אדומים', '1'),
		row('פתח בספסל', '26(3 ספסולים )'),
	}, '\n')
	equals(Events.renderRows('player-events', ZAHAVI), expected, 'block')
end)

--- The stat of one row, by its position in the block.
local function statOfRow(html, index)
	local lines = {}
	for line in (html .. '\n'):gmatch('(.-)\n') do
		lines[#lines + 1] = line
	end
	return (lines[index] or ''):match('<span class="Top10RowStat">(.*)</span>')
end

local function cellsWith(overrides)
	local cells = {
		appearances = 0, substitutions = 0, goals = 0, penaltyGoals = 0,
		assists = 0, yellows = 0, reds = 0, benchStarts = 0,
	}
	for name, value in pairs(overrides) do
		cells[name] = value
	end
	return cells
end

-- The template guards division by zero with #שווה and its branch is a bare 0.
check('no appearances prints a bare 0, not 0.00', function(Events)
	equals(statOfRow(Events.renderRows('player-events', cellsWith({})), 2),
		'0 (0 שערים למשחק, 0 פנדלים)', 'zero ratio')
end)

-- MediaWiki's #expr prints 0.5, not 0.50, and 1, not 1.00.
check('the ratio is formatted the way #expr formats it', function(Events)
	local cases = {
		{ goals = 50, appearances = 100, expected = '0.5' },
		{ goals = 100, appearances = 100, expected = '1' },
		{ goals = 52, appearances = 100, expected = '0.52' },
		{ goals = 1, appearances = 3, expected = '0.33' },
		{ goals = 2, appearances = 3, expected = '0.67' },
		{ goals = 150, appearances = 220, expected = '0.68' },
		-- Boundaries where binary representation and PHP's rounding disagree.
		-- 29/200 is 0.145: the template prints 0.15, and without the epsilon
		-- this printed 0.14. 26 pairs under 700 appearances diverge like this.
		{ goals = 29, appearances = 200, expected = '0.15' },
		{ goals = 23, appearances = 40, expected = '0.58' },
		{ goals = 1, appearances = 8, expected = '0.13' },
		-- Pins the epsilon's magnitude: a coarser 1e-3 rounds this to 0.51,
		-- where #expr says 0.5.
		{ goals = 253, appearances = 501, expected = '0.5' },
	}
	for _, case in ipairs(cases) do
		local stat = statOfRow(Events.renderRows('player-events', cellsWith({
			goals = case.goals, appearances = case.appearances,
		})), 2)
		equals(stat:match('%((.-) שערים למשחק'), case.expected,
			string.format('%d/%d', case.goals, case.appearances))
	end
end)

-- The ratio formatter refuses a negative rather than rounding it half-up,
-- which would disagree with #expr. Reachable only by a cell list that puts a
-- negative where a ratio is expected, which is a programming error.
check('a negative ratio raises rather than rounding the wrong way',
	function(Events)
		local ok, message = pcall(Events.renderRows, 'player-events', {
			appearances = -10, substitutions = 0, goals = 5, penaltyGoals = 0,
			assists = 0, yellows = 0, reds = 0, benchStarts = 0,
		})
		if ok then
			error('expected an error, none raised', 0)
		end
		if not tostring(message):find('non-negative ratios', 1, true) then
			error('wrong error: ' .. tostring(message), 0)
		end
	end)

check('benchings can be negative, as the arithmetic allows', function(Events)
	local stat = statOfRow(Events.renderRows('player-events', cellsWith({
		appearances = 10, substitutions = 9, benchStarts = 2,
	})), 6)
	equals(stat, '2(-7 ספסולים )', 'negative benchings')
end)

-- A nil cell means the row data names a cell the cell list does not produce.
-- Printing 0 for that would be a plausible number for a broken block.
check('a cell the block does not produce raises', function(Events)
	local ok, message = pcall(Events.renderRows, 'player-events', { appearances = 5 })
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find('no cell named', 1, true) then
		error('wrong error: ' .. tostring(message), 0)
	end
end)

check('the block asks one query for every cell', function(Events)
	stub.willReturn({ { c1 = '100', c2 = '23', c3 = '52', c4 = '6',
	                    c5 = '11', c6 = '12', c7 = '1', c8 = '26' } })
	local frame = {
		args = {},
		getParent = function()
			return { args = { ['שחקן'] = 'ערן זהבי',
			                  ['קטגוריית מפעל'] = 'ליגה' } }
		end,
	}
	local html = Events.block(frame)
	equals(#stub.calls, 1, 'one query')
	equals(html:match('<span class="Top10RowStat">(%d+) %(23'), '100',
		'appearances')
end)

check('arguments on the invoke itself are refused', function(Events)
	local frame = {
		args = { ['שחקן'] = 'ערן זהבי' },
		getParent = function() return { args = {} } end,
	}
	local ok, message = pcall(Events.block, frame)
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find('takes only בלוק', 1, true) then
		error('wrong error: ' .. tostring(message), 0)
	end
end)

--- Rows for one 32-cell query: eight cells times four tabs, named tab/cell.
local function thirtyTwoCells(perTab)
	local row = {}
	local index = 0
	for _, tabName in ipairs({ 'ליגה', 'גביע', 'בינלאומי', 'רשמי' }) do
		for _, cell in ipairs({ 'appearances', 'substitutions', 'goals',
		                        'penaltyGoals', 'assists', 'yellows', 'reds',
		                        'benchStarts' }) do
			index = index + 1
			row['c' .. index] = tostring(perTab[tabName][cell])
		end
	end
	return row
end

local PER_TAB = {
	['ליגה'] = { appearances = 100, substitutions = 23, goals = 52,
	             penaltyGoals = 6, assists = 11, yellows = 12, reds = 1,
	             benchStarts = 26 },
	['גביע'] = { appearances = 12, substitutions = 3, goals = 8,
	             penaltyGoals = 1, assists = 2, yellows = 1, reds = 0,
	             benchStarts = 4 },
	['בינלאומי'] = { appearances = 20, substitutions = 5, goals = 9,
	                 penaltyGoals = 0, assists = 3, yellows = 2, reds = 0,
	                 benchStarts = 6 },
	['רשמי'] = { appearances = 132, substitutions = 31, goals = 69,
	             penaltyGoals = 7, assists = 16, yellows = 15, reds = 1,
	             benchStarts = 36 },
}

check('prime renders all four tabs from one query', function(Events)
	stub.willReturn({ thirtyTwoCells(PER_TAB) })
	local frame = stub.newFrame({ ['שחקן'] = 'ערן זהבי' })

	equals(Events.prime(frame), '', 'prime outputs nothing')
	equals(#stub.calls, 1, 'one query for 32 cells')

	local fields = stub.calls[1].fields
	local count = 0
	for _ in fields:gmatch('SUM%(CASE WHEN') do
		count = count + 1
	end
	equals(count, 32, '32 conditional aggregates')
end)

check('each tab reads back its own numbers', function(Events)
	stub.willReturn({ thirtyTwoCells(PER_TAB) })
	local frame = stub.newFrame({ ['שחקן'] = 'ערן זהבי' })
	Events.prime(frame)

	for _, tabName in ipairs({ 'ליגה', 'גביע', 'בינלאומי', 'רשמי' }) do
		-- tab takes its arguments on the invoke itself, not from the parent.
		local html = Events.tab(stub.newFrameKeepingVariables({}, {
			['שחקן'] = 'ערן זהבי', ['קטגוריית מפעל'] = tabName,
		}))
		local expected = PER_TAB[tabName]
		equals(statOfRow(html, 1),
			string.format('%d (%d חילופים)', expected.appearances,
				expected.substitutions), tabName)
	end
end)

check('a tab with nothing primed raises rather than rendering empty',
	function(Events)
		local frame = stub.newFrame({}, { ['שחקן'] = 'ערן זהבי',
		                                  ['קטגוריית מפעל'] = 'ליגה' })
		local ok, message = pcall(Events.tab, frame)
		if ok then
			error('expected an error, none raised', 0)
		end
		if not tostring(message):find('nothing primed', 1, true) then
			error('wrong error: ' .. tostring(message), 0)
		end
	end)

check('variables are namespaced per entity, so two players cannot collide',
	function(Events)
		stub.willReturn({ thirtyTwoCells(PER_TAB) })
		local frame = stub.newFrame({ ['שחקן'] = 'ערן זהבי' })
		Events.prime(frame)

		local names = {}
		for name in pairs(stub.variables) do
			names[#names + 1] = name
		end
		table.sort(names)

		-- Four rendered tabs, plus each of the eight cells of each tab stashed
		-- on its own for a parent template that shows one outside the block.
		equals(#names, 4 + 4 * 8, 'four tabs and their cells')

		local prefix = 'FootballStatsBlock/player-events/ערן זהבי/'
		for _, name in ipairs(names) do
			-- Every one of them, not just the first: a single unkeyed name is
			-- enough for a comparison page to show one player's numbers under
			-- the other player's heading.
			if name:find(prefix, 1, true) ~= 1 then
				error('not keyed by block and player: ' .. name, 0)
			end
		end
	end)

-- A mutation that made prime put one constant category in every cell survived
-- the first suite: all four tabs then show the same numbers, which looks like
-- a player who only ever played in one competition.
check('each tab filters on its own category', function(Events)
	stub.willReturn({ thirtyTwoCells(PER_TAB) })
	Events.prime(stub.newFrame({ ['שחקן'] = 'ערן זהבי' }))

	local fields = stub.calls[1].fields
	for _, condition in ipairs({ 'Competitions.League = 1',
	                             'Competitions.Trophy = 1',
	                             'Competitions.International = 1',
	                             'Competitions.Official = 1' }) do
		local count = 0
		for _ in fields:gmatch(condition:gsub('%.', '%%.')) do
			count = count + 1
		end
		equals(count, 8, condition .. ' appears once per cell')
	end
end)

-- mw.loadData returns a proxy whose length is 0; a materialise that returned
-- it uncopied left the block with no cells, and the first suite did not notice
-- because a plain table behaves.
check('the block data survives an mw.loadData-style proxy', function()
	stub.install()
	stub.proxyLoadData = true
	local Events = stub.loadModule('Module:FootballStatsBlock')
	stub.willReturn({ thirtyTwoCells(PER_TAB) })

	Events.prime(stub.newFrame({ ['שחקן'] = 'ערן זהבי' }))
	local count = 0
	for _ in stub.calls[1].fields:gmatch('SUM%(CASE WHEN') do
		count = count + 1
	end
	equals(count, 32, '32 cells through a proxy')
end)

-- The cells are data, and a filter quietly dropped from one of them is a wrong
-- number with no other symptom. These are the eight the template asks for.
check('every block cell asks for exactly what the template asks for',
	function(Events)
		stub.willReturn({ thirtyTwoCells(PER_TAB) })
		Events.prime(stub.newFrame({ ['שחקן'] = 'ערן זהבי' }))
		local fields = stub.calls[1].fields

		local expected = {
			'Games_Events.EventType IN (1, 5)',      -- appearances
			'Games_Events.EventType IN (5)',         -- substitutions
			'Games_Events.EventType IN (3)',         -- goals
			'Games_Events.SubType IN (35)',          -- penalty goals
			'Games_Events.EventType IN (4)',         -- assists
			'Games_Events.SubType IN (71)',          -- yellows
			'Games_Events.SubType IN (72, 73)',      -- reds
			'Games_Events.EventType IN (2)',         -- bench starts
		}
		for _, condition in ipairs(expected) do
			if not fields:find(condition, 1, true) then
				error('missing from the query: ' .. condition, 0)
			end
		end
	end)

check('prime without a player raises', function(Events)
	local ok, message = pcall(Events.prime, stub.newFrame({}))
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find('needs שחקן', 1, true) then
		error('wrong error: ' .. tostring(message), 0)
	end
end)

-- The day block fixes its own date format, which is what makes it "this day in
-- any year" rather than "this exact date". It reaches the query from the block
-- definition, not from the page, so nothing on the page shows it is missing.
check('a block constant filter reaches the query', function(Blocks)
	stub.willReturn({ { c1 = '1', c2 = '1', c3 = '1', c4 = '1', c5 = '1',
	                    c6 = '1' } })
	Blocks.block(stub.newFrame(
		{ ['תאריך'] = '"2021-08-22"' }, { ['בלוק'] = 'day-results' }))

	-- The whole DATE_FORMAT, not just "%d-%m": that substring also appears
	-- in the DEFAULT format "%d-%m-%Y", so matching it alone stayed green
	-- with the block's constant removed - which is the regression this test
	-- exists to catch.
	local where = stub.calls[1].options.where
	local expected = 'DATE_FORMAT("2021-08-22", "%d-%m")'
		.. ' = DATE_FORMAT(Football_Games.Date, "%d-%m")'
	if not where:find(expected, 1, true) then
		error('the block date format never reached the query.\n'
			.. '        expected: ' .. expected .. '\n'
			.. '        actual:   ' .. where, 0)
	end
	if where:find('%d-%m-%Y', 1, true) then
		error('the default format won over the block constant: ' .. where, 0)
	end
end)

check('passing a filter the block fixes is refused', function(Blocks)
	local ok, message = pcall(Blocks.block, stub.newFrame(
		{ ['תאריך'] = '"2021-08-22"', ['פורמט תאריך'] = '"%Y"' },
		{ ['בלוק'] = 'day-results' }))
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find('cannot be passed in', 1, true) then
		error('wrong error: ' .. tostring(message), 0)
	end
end)

check('an empty summed cell renders empty, not zero', function(Blocks)
	-- A date with no games: the template prints nothing for כיבושים and
	-- ספיגות, and 0 for the counts.
	local html = Blocks.renderRows('day-results', {
		wins = 0, draws = 0, losses = 0, games = 0,
		goalsFor = nil, goalsAgainst = nil,
	})
	if not html:find('<div class="Top10RowName">כיבושים</div>\n'
			.. '<span class="Top10RowStat"></span>', 1, true) then
		error('כיבושים is not empty:\n' .. html, 0)
	end
	if not html:find('<span class="Top10RowStat">0</span>', 1, true) then
		error('the counting rows lost their zero:\n' .. html, 0)
	end
end)

check('a summed cell with a value renders it', function(Blocks)
	local html = Blocks.renderRows('day-results', {
		wins = 2, draws = 0, losses = 1, games = 3,
		goalsFor = 7, goalsAgainst = 2,
	})
	if not html:find('<span class="Top10RowStat">7</span>', 1, true) then
		error('כיבושים lost its value:\n' .. html, 0)
	end
end)

check('a row naming a cell the block does not produce raises', function(Blocks)
	-- Not "renders blank". An empty cell is what a summing cell with nothing
	-- to sum looks like, so a typo between the two data pages would be
	-- invisible on all 366 day pages.
	stub.dataPatch = function(data)
		if data['day-results'] then
			data['day-results'].rows[4].cell = 'goalzFor'
		end
	end
	local module = stub.loadModule('Module:FootballStatsBlock')
	local ok, message = pcall(module.renderRows, 'day-results', {
		wins = 2, draws = 0, losses = 1, games = 3,
		goalsFor = 7, goalsAgainst = 2,
	})
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find('no cell named "goalzFor"', 1, true) then
		error('wrong error: ' .. tostring(message), 0)
	end
end)

-- The day tab headers read "ליגה (N משחקים)". N comes from the same primed
-- query as the block below it, which is what takes a day page from eight
-- queries to one.
local DAY_CELLS_PER_TAB = { wins = 2, draws = 1, losses = 0,
                            goalsFor = 5, goalsAgainst = 2, games = 3 }

--- One row of 24 cells: six cells across four tabs, as prime asks for them.
local function twentyFourCells(per)
	local row = {}
	local index = 0
	for _ = 1, 4 do
		for _, name in ipairs({ 'wins', 'draws', 'losses', 'goalsFor',
		                        'goalsAgainst', 'games' }) do
			index = index + 1
			row['c' .. index] = tostring(per[name])
		end
	end
	return row
end

check('value reads a cell the same query already computed', function(Blocks)
	stub.willReturn({ twentyFourCells(DAY_CELLS_PER_TAB) })
	local frame = stub.newFrame({ ['תאריך'] = '"2021-08-22"' },
		{ ['בלוק'] = 'day-results' })
	Blocks.prime(frame)

	-- One query for the whole page: the four headers and the four blocks.
	equals(#stub.calls, 1, 'one query')

	local header = stub.newFrameKeepingVariables({}, {
		['בלוק'] = 'day-results', ['תא'] = 'games',
		['קטגוריית מפעל'] = 'ליגה', ['תאריך'] = '"2021-08-22"',
	})
	equals(Blocks.value(header), '3', 'games in the league tab')
	equals(#stub.calls, 1, 'still one query')
end)

check('value returns empty for a sum with nothing to sum', function(Blocks)
	-- The same rule the rows use: a header must not print 0 where the block
	-- below it prints nothing.
	local empty = twentyFourCells(DAY_CELLS_PER_TAB)
	empty.c4 = nil
	stub.willReturn({ empty })
	local frame = stub.newFrame({ ['תאריך'] = '"1900-01-01"' },
		{ ['בלוק'] = 'day-results' })
	Blocks.prime(frame)

	local header = stub.newFrameKeepingVariables({}, {
		['בלוק'] = 'day-results', ['תא'] = 'goalsFor',
		['קטגוריית מפעל'] = 'רשמי', ['תאריך'] = '"1900-01-01"',
	})
	equals(header and Blocks.value(header), '', 'empty, not 0')
end)

check('value without prime raises', function(Blocks)
	local header = stub.newFrame({}, {
		['בלוק'] = 'day-results', ['תא'] = 'games',
		['קטגוריית מפעל'] = 'ליגה', ['תאריך'] = '"2021-08-22"',
	})
	local ok, message = pcall(Blocks.value, header)
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find('nothing primed', 1, true) then
		error('wrong error: ' .. tostring(message), 0)
	end
end)

check('value refuses a cell the block does not declare', function(Blocks)
	stub.willReturn({ twentyFourCells(DAY_CELLS_PER_TAB) })
	local frame = stub.newFrame({ ['תאריך'] = '"2021-08-22"' },
		{ ['בלוק'] = 'day-results' })
	Blocks.prime(frame)

	local header = stub.newFrameKeepingVariables({}, {
		['בלוק'] = 'day-results', ['תא'] = 'gamez',
		['קטגוריית מפעל'] = 'ליגה', ['תאריך'] = '"2021-08-22"',
	})
	local ok, message = pcall(Blocks.value, header)
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find('no cell named "gamez"', 1, true) then
		error('wrong error: ' .. tostring(message), 0)
	end
end)

-- ---------------------------------------------------------------------------
-- render: the whole widget from one query and one #invoke.
--
-- The fixture gives every tab DIFFERENT numbers on purpose. With identical
-- numbers per tab - which is what twentyFourCells above does - a test cannot
-- tell a panel keyed to the wrong category from a correct one, and the display
-- order (ליגה first) is not the query order (רשמי first), so that is exactly
-- the mistake worth catching.
local DAY_BY_TAB = {
	['רשמי'] = { wins = 9, draws = 8, losses = 7, goalsFor = 30,
	             goalsAgainst = 20, games = 24 },
	['ליגה'] = { wins = 5, draws = 4, losses = 3, goalsFor = 16,
	             goalsAgainst = 11, games = 12 },
	['גביע'] = { wins = 2, draws = 1, losses = 1, goalsFor = 6,
	             goalsAgainst = 4, games = 4 },
	['בינלאומי'] = { wins = 2, draws = 3, losses = 3, goalsFor = 8,
	                 goalsAgainst = 5, games = 8 },
}

local DAY_CELL_ORDER = { 'wins', 'draws', 'losses', 'goalsFor',
                         'goalsAgainst', 'games' }

--- The single row a merged query returns, laid out in the order the cells were
--- asked for: the tabs in `order`, six cells each.
local function cellsForTabs(order, byTab)
	local row = {}
	local index = 0
	for _, tab in ipairs(order) do
		for _, name in ipairs(DAY_CELL_ORDER) do
			index = index + 1
			local value = byTab[tab][name]
			row['c' .. index] = value ~= nil and tostring(value) or nil
		end
	end
	return row
end

-- The order render asks in, which is the tab strip's display order.
local RENDER_ORDER = { 'ליגה', 'גביע', 'בינלאומי', 'רשמי' }

local function stackedRow(label, stat)
	return '<div class="Top10Row">\n<div class="Top10RowName">' .. label
		.. '</div>\n<span class="Top10RowStat">' .. stat .. '</span></div>'
end

--- The panel body the day block renders for one tab's numbers.
local function dayPanel(heading, values)
	return string.format('<div class="tab-header">%s (%d משחקים)</div>\n',
			heading, values.games)
		.. table.concat({
			stackedRow('נצחונות', values.wins),
			stackedRow('תיקו', values.draws),
			stackedRow('הפסדים', values.losses),
			stackedRow('כיבושים', values.goalsFor),
			stackedRow('ספיגות', values.goalsAgainst),
		}, '\n\n') .. '\n'
end

local function renderDay(Blocks, row, parentArgs)
	stub.willReturn({ row })
	local frame = stub.newFrame(
		parentArgs or { ['תאריך'] = '"2021-08-22"' },
		{ ['בלוק'] = 'day-results' })
	return Blocks.render(frame), frame
end

check('render emits the whole widget from one query', function(Blocks)
	local html = renderDay(Blocks, cellsForTabs(RENDER_ORDER, DAY_BY_TAB))

	equals(#stub.calls, 1, 'one query for the whole page')
	equals(#stub.extensionTags, 1, 'one tabber')
	equals(stub.extensionTags[1].name, 'tabber', 'the tag is a tabber')

	-- The skin hangs the icons and the strip spacing on this class, and scopes
	-- them to it so the wiki's other tabbers are untouched.
	if not html:find('^<div class="tabber%-converted">')
			or not html:find('</div>$') then
		error('the tabber is not wrapped for the skin:\n' .. html, 0)
	end

	-- No page variables: the whole point of one invoke is that nothing has to
	-- be handed across an #invoke boundary any more.
	for name in pairs(stub.variables) do
		error('render defined a page variable: ' .. name, 0)
	end
end)

check('render lays out the four panels in display order', function(Blocks)
	renderDay(Blocks, cellsForTabs(RENDER_ORDER, DAY_BY_TAB))

	-- Labels and headings differ on purpose: the גביע tab is headed
	-- גביע המדינה and the בינלאומי category is labelled אירופה, exactly as
	-- the template did.
	local expected = table.concat({
		'ליגה=' .. dayPanel('ליגה', DAY_BY_TAB['ליגה']),
		'|-|גביע=' .. dayPanel('גביע המדינה', DAY_BY_TAB['גביע']),
		'|-|אירופה=' .. dayPanel('אירופה', DAY_BY_TAB['בינלאומי']),
		'|-|כל המסגרות=' .. dayPanel('כל המסגרות', DAY_BY_TAB['רשמי']),
	})
	equals(stub.extensionTags[1].content, expected, 'tabber body')
end)

check('render keeps the empty cell empty in the panel and the heading',
		function(Blocks)
	-- A sum with nothing to sum is NULL, and the template prints nothing for
	-- it. The heading's own cell is a count, so it stays 0 - a heading reading
	-- "( משחקים)" would be the bug in the other direction.
	local quiet = {}
	for tab in pairs(DAY_BY_TAB) do
		quiet[tab] = { wins = 0, draws = 0, losses = 0, games = 0,
		               goalsFor = nil, goalsAgainst = nil }
	end
	renderDay(Blocks, cellsForTabs(RENDER_ORDER, quiet),
		{ ['תאריך'] = '"1900-01-01"' })

	local body = stub.extensionTags[1].content
	local _, blanks = body:gsub(
		'<div class="Top10RowName">כיבושים</div>\n'
		.. '<span class="Top10RowStat"></span>', '')
	equals(blanks, 4, 'four empty כיבושים cells')
	if not body:find('(0 משחקים)', 1, true) then
		error('the heading lost its zero count:\n' .. body, 0)
	end
end)

check('render sends the block constant filter to the query', function(Blocks)
	renderDay(Blocks, cellsForTabs(RENDER_ORDER, DAY_BY_TAB))

	local where = stub.calls[1].options.where
	local expected = 'DATE_FORMAT("2021-08-22", "%d-%m")'
		.. ' = DATE_FORMAT(Football_Games.Date, "%d-%m")'
	if not where:find(expected, 1, true) then
		error('the block date format never reached the query:\n' .. where, 0)
	end
	if where:find('%d-%m-%Y', 1, true) then
		error('the default format won over the block constant: ' .. where, 0)
	end
end)

check('render refuses a block with no tab strip', function(Blocks)
	-- player-events still renders through its own <shtml> strip, so asking
	-- render for it would silently produce a one-panel widget.
	local ok, message = pcall(Blocks.render, stub.newFrame(
		{ ['שחקן'] = 'אבי כהן' }, { ['בלוק'] = 'player-events' }))
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find('declares no tabStrip', 1, true) then
		error('wrong error: ' .. tostring(message), 0)
	end
end)

check('render refuses a label carrying a tabber separator', function(Blocks)
	-- Tabber explodes on "|-|" and on the first "=", and neither can be
	-- escaped, so such a label spills the rest of itself into the panel. That
	-- is how the first conversion of the old strips broke, when their
	-- class="fas fa-home" labels reached tabber unchanged.
	for _, bad in ipairs({ 'ליגה=x', 'ליגה|-|x' }) do
		stub.install()
		stub.dataPatch = function(data)
			if data['day-results'] then
				data['day-results'].tabStrip[1].label = bad
			end
		end
		local module = stub.loadModule('Module:FootballStatsBlock')
		stub.willReturn({ cellsForTabs(RENDER_ORDER, DAY_BY_TAB) })
		local ok, message = pcall(module.render, stub.newFrame(
			{ ['תאריך'] = '"2021-08-22"' }, { ['בלוק'] = 'day-results' }))
		if ok then
			error('expected an error for the label ' .. bad, 0)
		end
		if not tostring(message):find('tabber uses as separators', 1, true) then
			error('wrong error: ' .. tostring(message), 0)
		end
	end
end)

check('render refuses a heading naming a cell the block lacks', function(Blocks)
	-- The same rule the rows follow: a typo between the two data pages must
	-- raise, not render "ליגה ( משחקים)" on 366 pages.
	stub.install()
	stub.dataPatch = function(data)
		if data['day-results'] then
			data['day-results'].tabHeading.cell = 'gamez'
		end
	end
	local module = stub.loadModule('Module:FootballStatsBlock')
	stub.willReturn({ cellsForTabs(RENDER_ORDER, DAY_BY_TAB) })
	local ok, message = pcall(module.render, stub.newFrame(
		{ ['תאריך'] = '"2021-08-22"' }, { ['בלוק'] = 'day-results' }))
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find('no cell named "gamez"', 1, true) then
		error('wrong error: ' .. tostring(message), 0)
	end
end)

check('render refuses a tab strip with no heading declared', function()
	-- The next block converted will copy tabStrip and may forget tabHeading;
	-- it must get this module's message, not "attempt to index nil".
	stub.install()
	stub.dataPatch = function(data)
		if data['day-results'] then
			data['day-results'].tabHeading = nil
		end
	end
	local module = stub.loadModule('Module:FootballStatsBlock')
	stub.willReturn({ cellsForTabs(RENDER_ORDER, DAY_BY_TAB) })
	local ok, message = pcall(module.render, stub.newFrame(
		{ ['תאריך'] = '"2021-08-22"' }, { ['בלוק'] = 'day-results' }))
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find('must declare tabHeading', 1, true) then
		error('wrong error: ' .. tostring(message), 0)
	end
end)

check('render refuses a caller passing a filter the block fixes', function(Blocks)
	local ok, message = pcall(Blocks.render, stub.newFrame(
		{ ['תאריך'] = '"2021-08-22"', ['פורמט תאריך'] = '"%Y"' },
		{ ['בלוק'] = 'day-results' }))
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find('cannot be passed in', 1, true) then
		error('wrong error: ' .. tostring(message), 0)
	end
end)

-- ------------------------------------------------------- season numbers
-- תבנית:עונת כדורגל/הצגת מספרים עונתיים primes two blocks - games and cards,
-- which cannot share a query - and each tab reads its eight numbers with value.

local SEASON_RESULTS = { 'wins', 'draws', 'losses', 'goalsFor', 'goalsAgainst',
                         'cleanSheets' }

--- One row for a block's cells across the four tabs, c1..cN in prime's order.
local function seasonRow(names, per)
	local row, index = {}, 0
	for _ = 1, 4 do
		for _, name in ipairs(names) do
			index = index + 1
			row['c' .. index] = per[name] and tostring(per[name]) or nil
		end
	end
	return row
end

local function primeSeason(Blocks, block, row)
	stub.willReturn({ row })
	Blocks.prime(stub.newFrame({ ['עונה'] = '2023/24' }, { ['בלוק'] = block }))
end

local function seasonValue(Blocks, block, tab, cell)
	return Blocks.value(stub.newFrameKeepingVariables({}, {
		['בלוק'] = block, ['תא'] = cell, ['קטגוריית מפעל'] = tab,
		['עונה'] = '2023/24' }))
end

check('season results: one query for 24 numbers, filtered to the season', function(Blocks)
	primeSeason(Blocks, 'season-results', seasonRow(SEASON_RESULTS,
		{ wins = 34, draws = 9, losses = 12, goalsFor = 119, goalsAgainst = 61,
		  cleanSheets = 14 }))
	equals(#stub.calls, 1, 'one query')
	contains(stub.calls[1].options.where, 'Football_Games.Season = "2023/24"',
		'the season the container passes')
	contains(stub.calls[1].tables, 'Football_Games', 'the games table is queried')
	lacks(stub.calls[1].tables, 'Games_Events',
		'goals are summed, so the events table must not be joined')
	equals(seasonValue(Blocks, 'season-results', 'רשמי', 'wins'), '34', 'wins')
	equals(seasonValue(Blocks, 'season-results', 'רשמי', 'cleanSheets'), '14',
		'clean sheets')
	equals(seasonValue(Blocks, 'season-results', 'בינלאומי', 'goalsAgainst'), '61',
		'the fourth tab is read too')
end)

--- The SQL of each prime cell by alias: c1 = the first cell of the first tab.
local function fieldsByAlias(fields)
	local byAlias = {}
	for field, alias in (fields .. ','):gmatch('(.-%)=(c%d+)),') do
		byAlias[alias] = field
	end
	return byAlias
end

check('season results: each cell counts what its template counted', function(Blocks)
	-- The stub answers by position, whatever the SQL says, so each cell's own
	-- condition is asserted - "ResultOpt appears somewhere" would let wins
	-- quietly count draws.
	primeSeason(Blocks, 'season-results', seasonRow(SEASON_RESULTS, {}))
	local cell = fieldsByAlias(stub.calls[1].fields)
	contains(cell.c1, 'Football_Games.ResultOpt = 1 THEN', 'wins')
	contains(cell.c2, 'Football_Games.ResultOpt = 2 THEN', 'draws')
	contains(cell.c3, 'Football_Games.ResultOpt = 3 THEN', 'losses')
	contains(cell.c4, 'THEN Football_Games.ResultMaccabi ELSE NULL', 'goals for: a sum')
	contains(cell.c5, 'THEN Football_Games.ResultOpponent ELSE NULL', 'goals against')
	contains(cell.c6, 'Football_Games.ResultOpponent = 0 THEN', 'clean sheets')
	contains(cell.c1, 'Competitions.Official = 1', 'tab 1 is רשמי')
	contains(cell.c7, 'Competitions.League = 1', 'tab 2 is ליגה')
	contains(cell.c19, 'Competitions.International = 1', 'tab 4 is בינלאומי')
	equals(cell.c25, nil, 'six cells times four tabs, no more')
end)

check('season results: an empty season reads 0 games and no goals', function(Blocks)
	-- SUM over no games is NULL: value gives '', which the template itself
	-- turns into 0 - exactly what its own SUM query returned.
	primeSeason(Blocks, 'season-results', seasonRow(SEASON_RESULTS,
		{ wins = 0, draws = 0, losses = 0, cleanSheets = 0 }))
	equals(seasonValue(Blocks, 'season-results', 'רשמי', 'wins'), '0', 'no wins')
	equals(seasonValue(Blocks, 'season-results', 'רשמי', 'goalsFor'), '', 'empty, not 0')
end)

check('season cards: Maccabi yellows and reds, one query', function(Blocks)
	primeSeason(Blocks, 'season-cards', seasonRow({ 'yellows', 'reds' },
		{ yellows = 121, reds = 5 }))
	equals(#stub.calls, 1, 'one query')
	local cell = fieldsByAlias(stub.calls[1].fields)
	contains(cell.c1, 'Games_Events.SubType IN (71) THEN', 'yellows are subtype 71')
	contains(cell.c2, 'Games_Events.SubType IN (72, 73) THEN', 'reds are 72 and 73')
	contains(cell.c1, 'Games_Events.Team = 1', 'Maccabi\'s yellows, not the opponent\'s')
	contains(cell.c2, 'Games_Events.Team = 1', 'Maccabi\'s reds')
	contains(cell.c3, 'Competitions.League = 1', 'tab 2 is ליגה')
	equals(seasonValue(Blocks, 'season-cards', 'ליגה', 'yellows'), '121', 'yellows')
	equals(seasonValue(Blocks, 'season-cards', 'ליגה', 'reds'), '5', 'reds')
end)

check('a block without rows cannot be shown with tab', function(Blocks)
	primeSeason(Blocks, 'season-cards', seasonRow({ 'yellows', 'reds' },
		{ yellows = 1, reds = 0 }))
	local ok, message = pcall(Blocks.tab, stub.newFrameKeepingVariables({}, {
		['בלוק'] = 'season-cards', ['קטגוריית מפעל'] = 'ליגה', ['עונה'] = '2023/24' }))
	if ok then
		error('expected an error, none raised', 0)
	end
	contains(tostring(message), 'no rows to show', 'refused, not "primed" printed')
end)

print(string.format('\n%d passed, %d failed', passed, failed))
os.exit(failed > 0 and 1 or 0)
