--[[
Tests for Module:FootballDate.

What #time printed for these dates is checked against production by
compare_opponent_dates.py; these pin the shape and the fallback.

Run from the repository root:
    lua5.1 infra/football_queries/tests/test_date.lua
]]

package.path = 'infra/football_queries/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0

local function check(name, body)
	stub.install()
	local ok, message = pcall(body, stub.loadModule('Module:FootballDate'))
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

local function full(module, date)
	return module.full(stub.newFrame({}, { date }))
end

check('a day below 10 keeps its zero in the link and drops it in the text', function(module)
	equals(full(module, '1931-10-05'), '[[05 באוקטובר|5 באוקטובר]] [[1931]]')
end)

check('a two-digit day', function(module)
	equals(full(module, '2026-09-19'), '[[19 בספטמבר|19 בספטמבר]] [[2026]]')
end)

check('every month by its number', function(module)
	local months = { 'ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
		'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר' }
	for number, name in ipairs(months) do
		equals(full(module, string.format('1990-%02d-01', number)),
			string.format('[[01 ב%s|1 ב%s]] [[1990]]', name, name), 'month ' .. number)
	end
end)

check('the first and last day of a month', function(module)
	equals(full(module, '1922-11-01'), '[[01 בנובמבר|1 בנובמבר]] [[1922]]')
	equals(full(module, '1999-12-31'), '[[31 בדצמבר|31 בדצמבר]] [[1999]]')
end)

check('surrounding spaces are trimmed', function(module)
	equals(full(module, '  1949-10-15 '), '[[15 באוקטובר|15 באוקטובר]] [[1949]]')
end)

local function fallsBack(module, date)
	local output = full(module, date)
	equals(output, 'ROW(nil|nil)', 'expanded the template for "' .. date .. '"')
	equals(#stub.expanded, 1, 'one expansion')
	equals(stub.expanded[1].title, 'המרות/המרות תאריך/תאריך מלא לפורמט הצגה', 'template')
	equals(stub.expanded[1].args['תאריך'], mw.text.trim(date), 'its date argument')
end

check('an empty date goes through the template (its error text)', function(module)
	fallsBack(module, '')
end)

check('a date with a time goes through the template', function(module)
	fallsBack(module, '1931-10-05 16:00')
end)

check('month 00 and 13 go through the template', function(module)
	fallsBack(module, '1931-00-05')
	stub.expanded = {}
	fallsBack(module, '1931-13-05')
end)

check('day 00 and 32 go through the template', function(module)
	fallsBack(module, '1931-10-00')
	stub.expanded = {}
	fallsBack(module, '1931-10-32')
end)

check('a plain date expands nothing', function(module)
	full(module, '1931-10-05')
	equals(#stub.expanded, 0, 'expansions')
end)

print(string.format('%d passed, %d failed', passed, failed))
if failed > 0 then
	os.exit(1)
end
