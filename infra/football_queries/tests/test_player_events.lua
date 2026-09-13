--[[
Tests for Module:FootballPlayerEvents.

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
	local ok, message = pcall(body, stub.loadModule('Module:FootballPlayerEvents'))
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
	equals(Events.renderRows(ZAHAVI), expected, 'block')
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
	equals(statOfRow(Events.renderRows(cellsWith({})), 2),
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
	}
	for _, case in ipairs(cases) do
		local stat = statOfRow(Events.renderRows(cellsWith({
			goals = case.goals, appearances = case.appearances,
		})), 2)
		equals(stat:match('%((.-) שערים למשחק'), case.expected,
			string.format('%d/%d', case.goals, case.appearances))
	end
end)

check('benchings can be negative, as the arithmetic allows', function(Events)
	local stat = statOfRow(Events.renderRows(cellsWith({
		appearances = 10, substitutions = 9, benchStarts = 2,
	})), 6)
	equals(stat, '2(-7 ספסולים )', 'negative benchings')
end)

-- A nil cell means the row data names a cell the cell list does not produce.
-- Printing 0 for that would be a plausible number for a broken block.
check('a cell the block does not produce raises', function(Events)
	local ok, message = pcall(Events.renderRows, { appearances = 5 })
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
	if not tostring(message):find('takes none of its own', 1, true) then
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
		equals(#names, 4, 'four variables')
		equals(names[1]:find('FootballPlayerEvents/ערן זהבי/', 1, true), 1,
			'prefixed and keyed by player')
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

print(string.format('\n%d passed, %d failed', passed, failed))
os.exit(failed > 0 and 1 or 0)
