--[[
Tests for Module:FootballSeasonSquad.

The cards have to be byte-identical to the templates', so these assert exact
strings and the exact SQL; only the card order within a position is new.
Queries come in a fixed order: season players (with games), profiles, shirt
numbers.

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
	stub.willReturn(data.profiles or {})
	stub.willReturn(data.numbers or {})
	local frame = stub.newFrame({}, args or { ['עונה'] = '2024/25', ['שחקנים'] = '' })
	stub.variables['עונה להצגה'] = (args and args['עונה']) or '2024/25'
	stub.variables['קפטנים'] = captains or ''
	return squad.render(frame)
end

local ZAHAVI = { page = 'ערן זהבי', fullName = 'ערן זהבי', wholeCareer = nil,
	homePlayer = '1', rootedPlayer = nil, foreignPlayer = nil, position = '4',
	mainNumber = '7' }
local SHPIGLER = { page = 'מרדכי שפיגלר', fullName = 'מרדכי (מוטל\'ה) שפיגלר',
	wholeCareer = '1', homePlayer = '1', rootedPlayer = '1', foreignPlayer = '1',
	position = '4', mainNumber = '9' }

--- Season rows: names, each with one game unless given as { name, games }.
local function names(...)
	local rows = {}
	for index, entry in ipairs({ ... }) do
		if type(entry) == 'table' then
			rows[index] = { name = entry[1], games = tostring(entry[2]) }
		else
			rows[index] = { name = entry, games = '1' }
		end
	end
	return rows
end

--- A bare profile: a page in a position, optionally with a MainNumber.
local function profile(page, position, mainNumber)
	return { page = page, fullName = page, position = position, mainNumber = mainNumber }
end

--- Card names in page order, for cards rendered without a shirt number.
local function cardNames(html)
	local found = {}
	for name in html:gmatch('<span class="name">([^<]+)</span>') do
		found[#found + 1] = name
	end
	return table.concat(found, ' | ')
end

local function number(name, shirt, games, firstGame)
	return { name = name, number = shirt, games = tostring(games), firstGame = firstGame }
end

-- One attacker, no number, no flags: the whole block, byte for byte.
check('the whole block for one player', function(squad)
	local html = render(squad, {
		season = names('ערן זהבי'),
		profiles = { profile('ערן זהבי', '4') },
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

check('the season players query: the template\'s, plus games per player', function(squad)
	render(squad, { season = names('ערן זהבי') })
	local query = stub.calls[1]
	equals(query.tables, 'Football_Games=fg, Games_Events=ge', 'tables')
	equals(query.fields, 'ge.PlayerName=name, COUNT(DISTINCT fg._pageName)=games', 'fields')
	equals(query.options.join, 'fg._pageName=ge._pageName', 'join')
	equals(query.options.where, '1=1 AND fg.Season="2024/25" AND ge.Team=1', 'where')
	equals(query.options.groupBy, 'ge.PlayerName', 'group by')
	equals(query.options.limit, 5000, 'limit')
end)

check('a double quote in a name is escaped inside the IN list', function(squad)
	render(squad, { season = names('אלי "הקטן" דריקס') })
	contains(stub.calls[2].options.where, '("אלי \\"הקטן\\" דריקס")', 'escaped')
end)

check('three queries: players, profiles, shirt numbers', function(squad)
	render(squad, {
		season = names('ערן זהבי', 'מרדכי שפיגלר'),
		profiles = { ZAHAVI, SHPIGLER },
	})
	equals(#stub.calls, 3, 'queries')
	equals(stub.calls[2].tables, 'Profiles', 'profiles table')
	equals(stub.calls[2].fields, '_pageName=page, FullHebName=fullName, '
		.. 'WholeCareer=wholeCareer, HomePlayer=homePlayer, '
		.. 'RootedPlayer=rootedPlayer, ForeignPlayer=foreignPlayer, '
		.. 'Position=position, MainNumber=mainNumber', 'profile fields')
	equals(stub.calls[2].options.where, '_pageName IN ("ערן זהבי", "מרדכי שפיגלר")', 'profiles where')
	equals(stub.calls[2].options.limit, 5000, 'profiles limit')
	equals(stub.calls[3].fields, 'ge.PlayerName=name, ge.PlayerNumber=number, '
		.. 'COUNT(*)=games, MIN(fg.Date)=firstGame', 'number fields')
	equals(stub.calls[3].options.where, '1=1 AND ge.Team=1 AND fg.Season="2024/25"'
		.. ' AND ge.PlayerNumber != ""', 'number where')
	equals(stub.calls[3].options.groupBy, 'ge.PlayerName, ge.PlayerNumber', 'number group')
	equals(stub.calls[3].options.join, 'fg._pageName=ge._pageName', 'number join')
	equals(stub.calls[3].options.limit, 5000, 'number limit')
end)

check('the shirt-number season is the page variable, as the card read it', function(squad)
	stub.willReturn(names('ערן זהבי'))
	stub.willReturn({ ZAHAVI })
	local frame = stub.newFrame({}, { ['עונה'] = '2024/25', ['שחקנים'] = '' })
	stub.variables['עונה להצגה'] = '2023/24'
	squad.render(frame)
	contains(stub.calls[3].options.where, 'fg.Season="2023/24"', 'season variable')
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
		profiles = { ZAHAVI },
	}, { ['עונה'] = '2024/25', ['שחקנים'] = ' , ערן זהבי' })
	lacks(html, 'class="list"', 'list')
	lacks(html, 'ערן זהבי', 'card')
	equals(#stub.calls, 1, 'no profile query')
end)

check('a hand-entered list replaces the season names and is trimmed', function(squad)
	local html = render(squad, {
		season = names('אבי כהן'),
		profiles = { ZAHAVI },
	}, { ['עונה'] = '2024/25', ['שחקנים'] = ' ערן זהבי ,מרדכי שפיגלר ' })
	equals(stub.calls[2].options.where, '_pageName IN ("ערן זהבי", "מרדכי שפיגלר")', 'list')
	contains(html, 'ערן זהבי</span>', 'card')
end)

check('a hand-entered list still orders by the season\'s games', function(squad)
	local html = render(squad, {
		season = names({ 'אבי כהן', 3 }, { 'רפי לוי', 9 }),
		profiles = { profile('אבי כהן', '3'), profile('רפי לוי', '3') },
	}, { ['עונה'] = '2024/25', ['שחקנים'] = 'אבי כהן, רפי לוי' })
	equals(cardNames(html), 'רפי לוי | אבי כהן', 'games order')
end)

check('the apostrophe fix of the filter\'s output template', function(squad)
	local html = render(squad, {
		season = names("ג'וזף ולאחוביץ'"),
		profiles = { profile('ג&#39;וזף ולאחוביץ&#39;', '2') },
	})
	contains(html, "<span class=\"name\">ג'וזף ולאחוביץ'</span>", 'decoded')
end)

check('a player holding two positions shows in both', function(squad)
	local html = render(squad, {
		season = names('ערן זהבי'),
		profiles = { profile('ערן זהבי', '2, 3') },
	})
	equals(count(html, 'class="player-container"'), 2, 'cards')
	contains(html, 'שחקני הגנה|הגנה', 'defence')
	contains(html, 'שחקני קישור|קישור', 'midfield')
	lacks(html, 'שוערים', 'empty position')
end)

check('no position, or none of 1-4, is ללא עמדה', function(squad)
	local html = render(squad, {
		season = names('אבי כהן', 'רפי לוי', 'ערן זהבי'),
		profiles = { profile('אבי כהן', nil), profile('רפי לוי', '5'), profile('ערן זהבי', '4') },
	})
	local none = html:find('<div class="position-title">ללא עמדה</div>', 1, true)
	local attack = html:find('שחקני התקפה|התקפה', 1, true)
	if not (none and attack and attack < none) then
		error('ללא עמדה must exist and come after התקפה', 0)
	end
	equals(cardNames(html), 'ערן זהבי | אבי כהן | רפי לוי', 'cards')
end)

check('positions render in their fixed order', function(squad)
	local html = render(squad, {
		season = names('רפי לוי', 'ערן זהבי', 'אבי כהן', 'שלמה כהן', 'דוד פרימו'),
		profiles = { profile('רפי לוי', nil), profile('ערן זהבי', '4'),
			profile('אבי כהן', '3'), profile('שלמה כהן', '2'), profile('דוד פרימו', '1') },
	})
	equals(cardNames(html), 'דוד פרימו | שלמה כהן | אבי כהן | ערן זהבי | רפי לוי', 'positions')
end)

check('order: MainNumber ascending, a missing one first', function(squad)
	local html = render(squad, {
		season = names({ 'אבי כהן', 1 }, { 'רפי לוי', 1 }, { 'ערן זהבי', 1 }, { 'שלמה כהן', 1 }),
		profiles = { profile('אבי כהן', '3', '10'), profile('רפי לוי', '3', '9'),
			profile('ערן זהבי', '3', nil), profile('שלמה כהן', '3', '2') },
	})
	equals(cardNames(html), 'ערן זהבי | שלמה כהן | רפי לוי | אבי כהן', 'numbers as numbers')
end)

check('order: a MainNumber tie goes to more games, then the name', function(squad)
	local html = render(squad, {
		season = names({ 'רפי לוי', 4 }, { 'אבי כהן', 12 }, { 'דוד פרימו', 4 },
			{ 'שלמה כהן', 30 }),
		profiles = { profile('רפי לוי', '3'), profile('אבי כהן', '3'),
			profile('דוד פרימו', '3'), profile('שלמה כהן', '3', '5') },
	})
	equals(cardNames(html), 'אבי כהן | דוד פרימו | רפי לוי | שלמה כהן', 'games, then name')
end)

check('an empty page name is dropped, as #arrayunique dropped it', function(squad)
	local html = render(squad, {
		season = names('ערן זהבי'),
		profiles = { profile('', '1'), ZAHAVI },
	})
	lacks(html, 'שוערים', 'a position holding only an empty name')
	equals(count(html, 'class="player-container"'), 1, 'cards')
end)

check('a repeated player name is looked up once', function(squad)
	render(squad, { season = names('ערן זהבי'), profiles = { ZAHAVI } },
		{ ['עונה'] = '2024/25', ['שחקנים'] = 'ערן זהבי, ערן זהבי, ' })
	equals(stub.calls[2].options.where, '_pageName IN ("ערן זהבי")', 'unique, no empty')
end)

check('a duplicated profile row: the first wins', function(squad)
	local html = render(squad, {
		season = names('ערן זהבי'),
		profiles = { ZAHAVI, { page = 'ערן זהבי', fullName = 'ערן זהבי', wholeCareer = '1',
			position = '4' } },
	})
	lacks(html, 'maccabi_career', 'second row ignored')
	contains(html, 'player_property_home', 'first row used')
	equals(count(html, 'class="player-container"'), 1, 'one card')
end)

check('a name with no profile row renders no card', function(squad)
	local html = render(squad, {
		season = names('ערן זהבי', 'אבי כהן'),
		profiles = { ZAHAVI },
	})
	equals(count(html, 'class="player-container"'), 1, 'cards')
end)

check('players but no profiles: the list shell, no position', function(squad)
	local html = render(squad, { season = names('אבי כהן') })
	contains(html, '<div class="list">\n</div>', 'empty list')
end)

local function numbered(squad, rows)
	return render(squad, {
		season = names('ערן זהבי'),
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
