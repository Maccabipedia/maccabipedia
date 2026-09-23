--[[
Tests for Module:SeasonTrophies.

One query per sport per page, its SQL, and the list each season gets from it.
What the old templates actually printed is checked against production by
compare_season_trophies.py; these pin the shape.

Run from the repository root:
    lua5.1 infra/lua_modules/tests/test_season_trophies.lua
]]

package.path = 'infra/lua_modules/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0

local function check(name, body)
	stub.install()
	local ok, message = pcall(body, stub.loadModule('Module:SeasonTrophies'))
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

local function won(season, competition)
	return { season = season, competition = competition }
end

--- The list for one season, with the given rows waiting for the sport's query.
local function list(module, sport, season, rows)
	stub.willReturn(rows or {})
	return module.list(stub.newFrame({}, { ['ענף'] = sport, ['עונה'] = season }))
end

check('football asks its two tables, joined and ordered by competition', function(module)
	list(module, 'כדורגל', '2024/25', { won('2024/25', 'ליגת העל') })
	equals(#stub.calls, 1, 'one query')
	equals(stub.calls[1].tables, 'Achievements=a, Competitions=c', 'tables')
	equals(stub.calls[1].fields, 'a.Season=season, a.Competition=competition', 'fields')
	equals(stub.calls[1].options.join, 'a.Competition=c.OriginalName', 'join')
	equals(stub.calls[1].options.orderBy, 'a.Competition', 'order')
	equals(stub.calls[1].options.where, 'c.Official AND a.Achievement="זכיה"', 'where')
end)

check('the query asks for more rows than any sport has won', function(module)
	-- Cargo's own default is 100 and it truncates in silence; basketball has ~125.
	list(module, 'כדורגל', '2024/25', {})
	equals(stub.calls[1].options.limit, 500, 'limit')
end)

check('basketball and volleyball ask their own tables', function(module)
	list(module, 'כדורסל', '2023/24', {})
	equals(stub.calls[1].tables, 'Basketball_Achievements=a, Basketball_Competitions=c', 'basketball')
	list(module, 'כדורעף', '2023/24', {})
	equals(stub.calls[2].tables, 'Volleyball_Achievements=a, Volleyball_Competitions=c', 'volleyball')
end)

check('volleyball excludes הליגה הארצית, the others exclude nothing', function(module)
	list(module, 'כדורעף', '2023/24', {})
	contains(stub.calls[1].options.where, 'a.Competition != "הליגה הארצית"', 'volleyball exclusion')
	list(module, 'כדורגל', '2023/24', {})
	equals(stub.calls[2].options.where, 'c.Official AND a.Achievement="זכיה"', 'football has none')
end)

check("a season's wins are joined with a comma and two spaces, in query order", function(module)
	equals(list(module, 'כדורגל', '2024/25', {
		won('2024/25', 'אלוף האלופים'), won('2024/25', 'גביע הטוטו'),
		won('2024/25', 'ליגת העל'), won('2023/24', 'ליגת העל'),
	}), 'אלוף האלופים,  גביע הטוטו,  ליגת העל')
end)

check('a season with no wins gives an empty list', function(module)
	equals(list(module, 'כדורגל', '1950/51', { won('2024/25', 'ליגת העל') }), '')
end)

check('the sport is queried once a page, not once a season', function(module)
	local rows = { won('2024/25', 'ליגת העל'), won('2023/24', 'גביע המדינה') }
	stub.willReturn(rows)
	local first = module.list(stub.newFrame({}, { ['ענף'] = 'כדורגל', ['עונה'] = '2024/25' }))
	local second = module.list(stub.newFrameKeepingVariables({},
		{ ['ענף'] = 'כדורגל', ['עונה'] = '2023/24' }))
	equals(first, 'ליגת העל', 'first season')
	equals(second, 'גביע המדינה', 'second season, no second query')
	equals(#stub.calls, 1, 'queries')
end)

check('each sport is primed on its own, and they do not share lists', function(module)
	stub.willReturn({ won('2024/25', 'ליגת העל') })
	local football = module.list(stub.newFrame({}, { ['ענף'] = 'כדורגל', ['עונה'] = '2024/25' }))
	stub.willReturn({ won('2024/25', 'גביע המדינה') })
	local basketball = module.list(stub.newFrameKeepingVariables({},
		{ ['ענף'] = 'כדורסל', ['עונה'] = '2024/25' }))
	equals(football, 'ליגת העל', 'football')
	equals(basketball, 'גביע המדינה', 'basketball')
	equals(#stub.calls, 2, 'one query per sport')
end)

check('an unknown sport is an error, never an empty list', function(module)
	local ok, message = pcall(list, module, 'טניס', '2024/25', {})
	equals(ok, false, 'raised')
	contains(message, 'unknown ענף', 'names the problem')
	equals(#stub.calls, 0, 'queried nothing')
end)

check('no sport at all is an error', function(module)
	equals(pcall(list, module, '', '2024/25', {}), false)
end)

check('an empty season gives an empty list and queries nothing', function(module)
	equals(list(module, 'כדורגל', '', {}), '')
	equals(#stub.calls, 0, 'queries')
end)

check('a result that reached the row limit is an error', function(module)
	local rows = {}
	for index = 1, 500 do
		rows[index] = won('2024/25', 'competition ' .. index)
	end
	local ok, message = pcall(list, module, 'כדורגל', '2024/25', rows)
	equals(ok, false, 'raised')
	contains(message, 'row limit', 'says why')
end)

check('the sport and season are trimmed', function(module)
	equals(list(module, ' כדורגל ', ' 2024/25 ', { won('2024/25', 'ליגת העל') }), 'ליגת העל')
end)

print(string.format('%d passed, %d failed', passed, failed))
if failed > 0 then
	os.exit(1)
end
