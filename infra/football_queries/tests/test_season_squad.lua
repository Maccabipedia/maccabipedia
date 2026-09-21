--[[
Tests for Module:FootballSeasonSquad.

The output has to be byte-identical to the templates it replaces, so these
assert exact strings and the exact SQL. Queries come in a fixed order:
season players, the five positions (שוער, הגנה, קישור, התקפה, ללא עמדה),
profiles, shirt numbers.

Run from the repository root:
    lua5.1 infra/football_queries/tests/test_season_squad.lua
]]

package.path = 'infra/football_queries/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0

local function check(name, body)
	stub.install()
	local ok, message = pcall(body, stub.loadModule('Module:FootballSeasonSquad'))
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

local function count(text, piece)
	local found, from = 0, 1
	while true do
		local at = text:find(piece, from, true)
		if not at then
			return found
		end
		found, from = found + 1, at + #piece
	end
end

--- Renders a season. `data` holds the rows each query returns; `captains`
--- is the page's קפטנים variable.
local function render(squad, data, args, captains)
	stub.willReturn(data.season or {})
	for position = 1, 5 do
		stub.willReturn((data.positions or {})[position] or {})
	end
	stub.willReturn(data.profiles or {})
	stub.willReturn(data.numbers or {})
	local frame = stub.newFrame({}, args or { ['עונה'] = '2024/25', ['שחקנים'] = '' })
	stub.variables['עונה להצגה'] = (args and args['עונה']) or '2024/25'
	stub.variables['קפטנים'] = captains or ''
	return squad.render(frame)
end

local ZAHAVI = { page = 'ערן זהבי', fullName = 'ערן זהבי', wholeCareer = nil,
	homePlayer = '1', rootedPlayer = nil, foreignPlayer = nil }
local SHPIGLER = { page = 'מרדכי שפיגלר', fullName = 'מרדכי (מוטל\'ה) שפיגלר',
	wholeCareer = '1', homePlayer = '1', rootedPlayer = '1', foreignPlayer = '1' }

local function names(...)
	local rows = {}
	for index, name in ipairs({ ... }) do
		rows[index] = { name = name }
	end
	return rows
end

local function pages(...)
	local rows = {}
	for index, name in ipairs({ ... }) do
		rows[index] = { pageName = name }
	end
	return rows
end

local function number(name, shirt, games, firstGame)
	return { name = name, number = shirt, games = tostring(games), firstGame = firstGame }
end

-- One attacker, no number, no flags: the whole block, byte for byte.
check('the whole block for one player', function(squad)
	local html = render(squad, {
		season = names('ערן זהבי'),
		positions = { {}, {}, {}, pages('ערן זהבי'), {} },
		profiles = { { page = 'ערן זהבי', fullName = 'ערן זהבי' } },
	})
	equals(html, '<div class="players-section-container" id="סגל שחקנים">\n'
		.. '<div class="title">סגל שחקנים</div>\n'
		.. '<div class="players-list-container">\n'
		.. '<div class="list">\n'
		.. '<div class="position-list">\n'
		.. '<div class="position-title">[[:קטגוריה: שחקני התקפה|התקפה]]</div>\n'
		.. '<div class="position-players">'
		.. '<div class="player-container">[[ערן זהבי |<nowiki> </nowiki>]]'
		.. '<span class="name">ערן זהבי</span><span class="props">\n</span>\n</div>'
		.. '</div>\n</div>'
		.. '</div>\n</div>\n</div>', 'block')
end)

check('the season players query is the template\'s, with no limit', function(squad)
	render(squad, { season = names('ערן זהבי') })
	local query = stub.calls[1]
	equals(query.tables, 'Football_Games=fg, Games_Events=ge', 'tables')
	equals(query.fields, 'ge.PlayerName=name', 'fields')
	equals(query.options.join, 'fg._pageName=ge._pageName', 'join')
	equals(query.options.where, '1=1 AND fg.Season="2024/25" AND ge.Team=1', 'where')
	equals(query.options.groupBy, 'ge.PlayerName', 'group by')
	equals(query.options.limit, nil, 'limit')
end)

check('the five position queries are the filter template\'s', function(squad)
	render(squad, { season = names('ערן זהבי', "ג'וזף ולאחוביץ'") })
	local list = '_pageName IN ("ערן זהבי", "ג\'וזף ולאחוביץ\'")'
	equals(stub.calls[2].options.where, list .. ' And Position HOLDS "1"', 'שוער')
	equals(stub.calls[3].options.where, list .. ' And Position HOLDS "2"', 'הגנה')
	equals(stub.calls[4].options.where, list .. ' And Position HOLDS "3"', 'קישור')
	equals(stub.calls[5].options.where, list .. ' And Position HOLDS "4"', 'התקפה')
	equals(stub.calls[6].options.where, list .. ' AND Position HOLDS NOT "1"'
		.. ' AND Position HOLDS NOT "2" AND Position HOLDS NOT "3"'
		.. ' AND Position HOLDS NOT "4"', 'ללא עמדה')
	for call = 2, 6 do
		equals(stub.calls[call].tables, 'Profiles', 'tables')
		equals(stub.calls[call].fields, '_pageName=pageName', 'fields')
		equals(stub.calls[call].options.orderBy, 'MainNumber ASC', 'order')
		equals(stub.calls[call].options.limit, nil, 'limit')
	end
end)

check('a double quote in a name is escaped inside the IN list', function(squad)
	render(squad, { season = names('אלי "הקטן" דריקס') })
	contains(stub.calls[2].options.where, '("אלי \\"הקטן\\" דריקס")', 'escaped')
end)

check('profiles and shirt numbers are one query each, with a limit', function(squad)
	render(squad, {
		season = names('ערן זהבי', 'מרדכי שפיגלר'),
		positions = { {}, pages('ערן זהבי'), {}, pages('מרדכי שפיגלר'), {} },
		profiles = { ZAHAVI, SHPIGLER },
	})
	equals(#stub.calls, 8, 'queries')
	equals(stub.calls[7].tables, 'Profiles', 'profiles table')
	equals(stub.calls[7].fields, '_pageName=page, FullHebName=fullName, '
		.. 'WholeCareer=wholeCareer, HomePlayer=homePlayer, '
		.. 'RootedPlayer=rootedPlayer, ForeignPlayer=foreignPlayer', 'profile fields')
	equals(stub.calls[7].options.where, '_pageName IN ("ערן זהבי", "מרדכי שפיגלר")', 'profiles where')
	equals(stub.calls[7].options.limit, 5000, 'profiles limit')
	equals(stub.calls[8].fields, 'ge.PlayerName=name, ge.PlayerNumber=number, '
		.. 'COUNT(*)=games, MIN(fg.Date)=firstGame', 'number fields')
	equals(stub.calls[8].options.where, '1=1 AND ge.Team=1 AND fg.Season="2024/25"'
		.. ' AND ge.PlayerNumber != ""', 'number where')
	equals(stub.calls[8].options.groupBy, 'ge.PlayerName, ge.PlayerNumber', 'number group')
	equals(stub.calls[8].options.join, 'fg._pageName=ge._pageName', 'number join')
	equals(stub.calls[8].options.limit, 5000, 'number limit')
end)

check('the shirt-number season is the page variable, as the card read it', function(squad)
	stub.willReturn(names('ערן זהבי'))
	stub.willReturn(pages('ערן זהבי'))
	for _ = 1, 4 do stub.willReturn({}) end
	stub.willReturn({ ZAHAVI })
	local frame = stub.newFrame({}, { ['עונה'] = '2024/25', ['שחקנים'] = '' })
	stub.variables['עונה להצגה'] = '2023/24'
	squad.render(frame)
	contains(stub.calls[8].options.where, 'fg.Season="2023/24"', 'season variable')
	contains(stub.calls[1].options.where, 'fg.Season="2024/25"', 'season argument')
end)

check('no players: one query, and no list', function(squad)
	local html = render(squad, {})
	equals(#stub.calls, 1, 'queries')
	lacks(html, 'class="list"', 'list')
	contains(html, '<div class="players-list-container">\n\n</div>\n</div>', 'empty shell')
end)

check('an empty first name hides the whole list, as the template tested', function(squad)
	local html = render(squad, {
		positions = { pages('ערן זהבי'), {}, {}, {}, {} },
		profiles = { ZAHAVI },
	}, { ['עונה'] = '2024/25', ['שחקנים'] = ' , ערן זהבי' })
	lacks(html, 'class="list"', 'list')
	lacks(html, 'ערן זהבי', 'card')
end)

check('a hand-entered list replaces the season query and is trimmed', function(squad)
	stub.willReturn(pages('ערן זהבי'))
	for _ = 1, 4 do stub.willReturn({}) end
	stub.willReturn({ ZAHAVI })
	local frame = stub.newFrame({}, { ['עונה'] = '2024/25', ['שחקנים'] = ' ערן זהבי ,מרדכי שפיגלר ' })
	stub.variables['עונה להצגה'] = '2024/25'
	local html = squad.render(frame)
	equals(stub.calls[1].tables, 'Profiles', 'no season query')
	contains(stub.calls[1].options.where, '_pageName IN ("ערן זהבי", "מרדכי שפיגלר")', 'list')
	contains(html, 'ערן זהבי</span>', 'card')
end)

check('the apostrophe fix of the filter\'s output template', function(squad)
	local html = render(squad, {
		season = names("ג'וזף ולאחוביץ'"),
		positions = { {}, pages('ג&#39;וזף ולאחוביץ&#39;'), {}, {}, {} },
		profiles = { { page = "ג'וזף ולאחוביץ'", fullName = "ג'וזף ולאחוביץ'" } },
	})
	contains(html, "<span class=\"name\">ג'וזף ולאחוביץ'</span>", 'decoded')
end)

check('a position repeats nobody, but two positions both show a player', function(squad)
	local html = render(squad, {
		season = names('ערן זהבי'),
		positions = { {}, pages('ערן זהבי', 'ערן זהבי'), pages('ערן זהבי'), {}, {} },
		profiles = { ZAHAVI },
	})
	equals(count(html, 'class="player-container"'), 2, 'cards')
	contains(html, 'שחקני הגנה|הגנה', 'defence')
	contains(html, 'שחקני קישור|קישור', 'midfield')
	lacks(html, 'שוערים', 'empty position')
	equals(stub.calls[7].options.where, '_pageName IN ("ערן זהבי")', 'one profile lookup')
end)

check('positions render in their fixed order, cards in query order', function(squad)
	local html = render(squad, {
		season = names('ערן זהבי', 'מרדכי שפיגלר', 'אבי כהן'),
		positions = { pages('אבי כהן'), {}, {}, pages('מרדכי שפיגלר', 'ערן זהבי'),
			pages('רפי לוי') },
		profiles = { ZAHAVI, SHPIGLER, { page = 'אבי כהן', fullName = 'אבי כהן' },
			{ page = 'רפי לוי', fullName = 'רפי לוי' } },
	})
	local keeper = html:find('אבי כהן</span>', 1, true)
	local first = html:find('מרדכי שפיגלר</span>', 1, true)
	local second = html:find('ערן זהבי</span>', 1, true)
	local none = html:find('ללא עמדה', 1, true)
	if not (keeper < first and first < second and second < none) then
		error('order: keeper, then attack in query order, then ללא עמדה', 0)
	end
end)

check('an empty name is dropped, as #arrayunique dropped it', function(squad)
	local html = render(squad, {
		season = names('ערן זהבי'),
		positions = { pages(''), {}, {}, pages('ערן זהבי'), {} },
		profiles = { ZAHAVI },
	})
	lacks(html, 'שוערים', 'a position holding only an empty name')
	equals(stub.calls[7].options.where, '_pageName IN ("ערן זהבי")', 'no empty lookup')
end)

check('a duplicated profile row: the first wins', function(squad)
	local html = render(squad, {
		season = names('ערן זהבי'),
		positions = { {}, {}, {}, pages('ערן זהבי'), {} },
		profiles = { ZAHAVI, { page = 'ערן זהבי', fullName = 'ערן זהבי', wholeCareer = '1' } },
	})
	lacks(html, 'maccabi_career', 'second row ignored')
	contains(html, 'player_property_home', 'first row used')
end)

check('a name with no profile row renders no card', function(squad)
	local html = render(squad, {
		season = names('ערן זהבי'),
		positions = { {}, {}, {}, pages('ערן זהבי', 'אבי כהן'), {} },
		profiles = { ZAHAVI },
	})
	equals(count(html, 'class="player-container"'), 1, 'cards')
end)

local function numbered(squad, rows)
	return render(squad, {
		season = names('ערן זהבי'),
		positions = { {}, {}, {}, pages('ערן זהבי'), {} },
		profiles = { ZAHAVI },
		numbers = rows,
	})
end

check('the most-worn number wins', function(squad)
	local html = numbered(squad, { number('ערן זהבי', '29', 16, '2024-08-01'),
		number('ערן זהבי', '7', 49, '2024-09-01') })
	contains(html, '<span class="number">#7 </span>ערן זהבי', 'mode')
end)

check('a tie goes to the number worn first', function(squad)
	local html = numbered(squad, { number('ערן זהבי', '7', 5, '2024-09-01'),
		number('ערן זהבי', '29', 5, '2024-08-01') })
	contains(html, '#29 ', 'earliest')
	html = numbered(squad, { number('ערן זהבי', '29', 5, '2024-08-01'),
		number('ערן זהבי', '7', 5, '2024-09-01') })
	contains(html, '#29 ', 'earliest, other row order')
end)

check('games compare as numbers, not strings', function(squad)
	local html = numbered(squad, { number('ערן זהבי', '7', 9, '2024-08-01'),
		number('ערן זהבי', '29', 10, '2024-09-01') })
	contains(html, '#29 ', '10 > 9')
end)

check('another player\'s number is not taken', function(squad)
	local html = numbered(squad, { number('אבי כהן', '7', 9, '2024-08-01') })
	lacks(html, 'class="number"', 'no number')
end)

check('number 0 is hidden, as #שווה against 000 hid it', function(squad)
	lacks(numbered(squad, { number('ערן זהבי', '0', 3, '2024-08-01') }), 'class="number"', '0')
	contains(numbered(squad, { number('ערן זהבי', '10', 3, '2024-08-01') }), '#10 ', '10')
end)

local function flagged(squad, profile, captains)
	return render(squad, {
		season = names(profile.page),
		positions = { {}, {}, {}, pages(profile.page), {} },
		profiles = { profile },
	}, nil, captains)
end

check('every flag, in the card\'s order', function(squad)
	local html = flagged(squad, SHPIGLER, "אבי כהן, מרדכי (מוטל'ה) שפיגלר")
	contains(html, '<span class="props">'
		.. '[[קובץ: player_property_maccabi_career.png |link=]]'
		.. '[[קובץ: player_property_captain.png| 25px |link=]]'
		.. '[[קובץ: player_property_home.png |link=]]'
		.. '[[קובץ: player_property_star_of_david.png |link=]]'
		.. '[[קובץ: player_property_airport.png |link=]]'
		.. '\n</span>\n</div>', 'icons')
end)

check('a flag shows only when it is 1', function(squad)
	local html = flagged(squad, { page = 'אבי כהן', fullName = 'אבי כהן',
		wholeCareer = '0', homePlayer = '', rootedPlayer = nil, foreignPlayer = '2' })
	lacks(html, 'player_property', 'no icons')
end)

check('a captain matches on the full name, not the page name', function(squad)
	lacks(flagged(squad, SHPIGLER, 'מרדכי שפיגלר'), 'captain', 'page name')
	contains(flagged(squad, SHPIGLER, "מרדכי (מוטל'ה) שפיגלר"), 'captain', 'full name')
end)

check('a double quote in the full name compares as &quot;', function(squad)
	local profile = { page = 'אלי דריקס', fullName = 'אליעזר "אלי" דריקס' }
	lacks(flagged(squad, profile, 'אליעזר "אלי" דריקס'), 'captain', 'raw quote')
	contains(flagged(squad, profile, 'אליעזר &quot;אלי&quot; דריקס'), 'captain', 'entity')
end)

check('an empty full name is never a captain', function(squad)
	lacks(flagged(squad, { page = 'אבי כהן', fullName = '' }, ', אבי כהן'), 'captain', 'empty')
end)

check('a missing page gets no link', function(squad)
	stub.missingPages['ערן זהבי'] = true
	local html = numbered(squad, {})
	contains(html, '<div class="player-container"><span class="name">', 'no link')
end)

check('a truncated profiles or numbers answer is an error', function(squad)
	local many = {}
	for index = 1, 5000 do
		many[index] = number('ערן זהבי', tostring(index), 1, '2024-08-01')
	end
	local ok, message = pcall(numbered, squad, many)
	equals(ok, false, 'raised')
	contains(message, 'hit the limit of 5000', 'message')
end)

check('a season that is not a season is refused', function(squad)
	local ok, message = pcall(render, squad, {}, { ['עונה'] = '2024" OR 1', ['שחקנים'] = '' })
	equals(ok, false, 'raised')
	contains(message, 'not a season', 'message')
end)

print(string.format('%d passed, %d failed', passed, failed))
os.exit(failed == 0 and 0 or 1)
