--[[
Module:FootballSeasonSquad - the squad block of a football season page.

Wiki page: Module:FootballSeasonSquad

תבנית:עונת כדורגל/הצגת סגל built the squad from one Cargo query per position
and then TWO per player - the profile fields, then the shirt number inside
the card - about 90 queries on a 42-player season. This renders the same
HTML from eight: the season's players, the five position lists, every
profile at once, and every shirt number at once.

Template body:
    {{#invoke:FootballSeasonSquad|render|עונה={{{עונה|}}}|שחקנים={{{שחקנים|}}}}}

The five position queries are kept exactly as the filter template wrote them
(same WHERE, same ORDER BY, no LIMIT). Most old profiles have no MainNumber,
so their order is MySQL's tie order, and a single combined query returns
those ties differently - measured against all 101 season pages. Only these
five keep today's card order.

The output must be byte-identical to the templates', so their oddities are
reproduced and marked where they are not obvious.
]]

local p = {}

-- Cargo applies its default limit to a query that names none. The season and
-- position queries keep that, so their SQL stays the templates'; these two
-- collapse many per-player queries and set their own.
local QUERY_LIMIT = 5000

local POSITIONS = {
	{ code = '1', title = '[[:קטגוריה: שוערים|שוערים]]' },
	{ code = '2', title = '[[:קטגוריה: שחקני הגנה|הגנה]]' },
	{ code = '3', title = '[[:קטגוריה: שחקני קישור|קישור]]' },
	{ code = '4', title = '[[:קטגוריה: שחקני התקפה|התקפה]]' },
	{ code = nil, title = 'ללא עמדה' },
}

local ICONS = {
	wholeCareer = '[[קובץ: player_property_maccabi_career.png |link=]]',
	captain = '[[קובץ: player_property_captain.png| 25px |link=]]',
	homePlayer = '[[קובץ: player_property_home.png |link=]]',
	rootedPlayer = '[[קובץ: player_property_star_of_david.png |link=]]',
	foreignPlayer = '[[קובץ: player_property_airport.png |link=]]',
}

local function trim(value)
	return mw.text.trim(value or '')
end

--- #arraydefine with its default delimiter: split on commas, trim each part.
local function splitList(value)
	local items = {}
	if trim(value) == '' then
		return items
	end
	for part in (value .. ','):gmatch('([^,]*),') do
		items[#items + 1] = trim(part)
	end
	return items
end

--- #arrayunique: first occurrence wins, and empty elements are dropped.
local function unique(items)
	local seen, result = {}, {}
	for _, item in ipairs(items) do
		if item ~= '' and not seen[item] then
			seen[item] = true
			result[#result + 1] = item
		end
	end
	return result
end

--- A season goes into the SQL as it is, as the templates did; anything but
--- digits and a slash is refused rather than quoted.
local function checkedSeason(season)
	season = trim(season)
	if not season:match('^[%d/]*$') then
		error('FootballSeasonSquad: not a season: ' .. season, 0)
	end
	return season
end

local function quoted(name)
	return '"' .. name:gsub('\\', '\\\\'):gsub('"', '\\"') .. '"'
end

local function inList(names)
	local literals = {}
	for index, name in ipairs(names) do
		literals[index] = quoted(name)
	end
	return table.concat(literals, ', ')
end

--- For the two queries that set a limit: a result that reached it is an
--- error, never a short answer - Cargo truncates silently.
local function limited(tables, fields, options)
	options.limit = QUERY_LIMIT
	local rows = mw.ext.cargo.query(tables, fields, options)
	if #rows >= QUERY_LIMIT then
		error(string.format('FootballSeasonSquad: %d rows hit the limit of %d',
			#rows, QUERY_LIMIT), 0)
	end
	return rows
end

local function seasonPlayers(season)
	local rows = mw.ext.cargo.query('Football_Games=fg, Games_Events=ge', 'ge.PlayerName=name', {
		join = 'fg._pageName=ge._pageName',
		where = '1=1 AND fg.Season="' .. season .. '" AND ge.Team=1',
		groupBy = 'ge.PlayerName',
	})
	local names = {}
	for index, row in ipairs(rows) do
		names[index] = trim(row.name)
	end
	return names
end

--- One position, as כדורגל/סינון רשימת שחקנים לפי עמדה asked for it, with
--- כדורגל/תיקון שם לרשימת שחקנים מסוננת's apostrophe fix.
local function positionPlayers(players, code)
	local condition
	if code then
		condition = ' And Position HOLDS "' .. code .. '"'
	else
		condition = ' AND Position HOLDS NOT "1" AND Position HOLDS NOT "2"'
			.. ' AND Position HOLDS NOT "3" AND Position HOLDS NOT "4"'
	end
	local rows = mw.ext.cargo.query('Profiles', '_pageName=pageName', {
		where = '_pageName IN (' .. inList(players) .. ')' .. condition,
		orderBy = 'MainNumber ASC',
	})
	local names = {}
	for index, row in ipairs(rows) do
		names[index] = trim((row.pageName or ''):gsub('&#39;', "'"))
	end
	return unique(names)
end

--- Every profile the cards need, first row per page - as `limit=1` took it.
local function profiles(names)
	local rows = limited('Profiles', '_pageName=page, FullHebName=fullName, '
		.. 'WholeCareer=wholeCareer, HomePlayer=homePlayer, '
		.. 'RootedPlayer=rootedPlayer, ForeignPlayer=foreignPlayer', {
			where = '_pageName IN (' .. inList(names) .. ')',
		})
	local byPage = {}
	for _, row in ipairs(rows) do
		local page = trim(row.page)
		byPage[page] = byPage[page] or row
	end
	return byPage
end

--- The number each player wore in most of the season's games, ties going to
--- the number worn in the earliest one; blanks never count.
local function shirtNumbers(season)
	local rows = limited('Football_Games=fg, Games_Events=ge',
		'ge.PlayerName=name, ge.PlayerNumber=number, COUNT(*)=games, MIN(fg.Date)=firstGame', {
			join = 'fg._pageName=ge._pageName',
			where = '1=1 AND ge.Team=1 AND fg.Season="' .. season
				.. '" AND ge.PlayerNumber != ""',
			groupBy = 'ge.PlayerName, ge.PlayerNumber',
		})
	local best = {}
	for _, row in ipairs(rows) do
		local name, games = trim(row.name), tonumber(row.games) or 0
		local firstGame = row.firstGame or ''
		local current = best[name]
		if not current or games > current.games
			or (games == current.games and firstGame < current.firstGame) then
			best[name] = { number = trim(row.number), games = games, firstGame = firstGame }
		end
	end
	local numbers = {}
	for name, entry in pairs(best) do
		numbers[name] = entry.number
	end
	return numbers
end

--- The card's #שווה compared its values as NUMBERS: a flag shows when it
--- equals 1, and a shirt number hides when it equals the 000 default - so a
--- recorded number 0 hides too.
local function numericallyEqual(value, target)
	local number = tonumber(value)
	if number then
		return number == target
	end
	return false
end

--- The card compared the variable's names against FullHebName as a template
--- argument saw it: with a double quote as &quot;.
local function isCaptain(captains, fullName)
	fullName = trim(fullName):gsub('"', '&quot;')
	if fullName == '' then
		return false
	end
	for _, captain in ipairs(captains) do
		if captain == fullName then
			return true
		end
	end
	return false
end

local function card(frame, page, profile, number, captains)
	local title = mw.title.new(page)
	local link = ''
	if title and title.exists then
		link = '[[' .. page .. ' |' .. frame:extensionTag('nowiki', ' ') .. ']]'
	end
	local numberHtml = ''
	if number and number ~= '' and not numericallyEqual(number, 0) then
		numberHtml = '<span class="number">#' .. number .. ' </span>'
	end
	local icons = {}
	if numericallyEqual(profile.wholeCareer, 1) then icons[#icons + 1] = ICONS.wholeCareer end
	if isCaptain(captains, profile.fullName) then icons[#icons + 1] = ICONS.captain end
	if numericallyEqual(profile.homePlayer, 1) then icons[#icons + 1] = ICONS.homePlayer end
	if numericallyEqual(profile.rootedPlayer, 1) then icons[#icons + 1] = ICONS.rootedPlayer end
	if numericallyEqual(profile.foreignPlayer, 1) then icons[#icons + 1] = ICONS.foreignPlayer end
	-- #arrayprint trims each card, so its closing newline is gone.
	return '<div class="player-container">' .. link
		.. '<span class="name">' .. numberHtml .. page .. '</span>'
		.. '<span class="props">' .. table.concat(icons) .. '\n</span>\n</div>'
end

function p.render(frame)
	local season = checkedSeason(frame.args['עונה'])
	local given = frame.args['שחקנים']
	local players = trim(given) ~= '' and splitList(given) or seasonPlayers(season)

	local lists = {}
	-- The template tested only the FIRST name: an empty one hides the list.
	if (players[1] or '') ~= '' then
		for index, position in ipairs(POSITIONS) do
			lists[index] = positionPlayers(players, position.code)
		end
	end

	local everyone = {}
	for _, names in pairs(lists) do
		for _, name in ipairs(names) do
			everyone[#everyone + 1] = name
		end
	end
	everyone = unique(everyone)

	local html = {}
	if #everyone > 0 then
		local byPage = profiles(everyone)
		local numbers = shirtNumbers(checkedSeason(
			frame:callParserFunction('#var', { 'עונה להצגה' })))
		local captains = splitList(frame:callParserFunction('#var', { 'קפטנים' }))
		for index, position in ipairs(POSITIONS) do
			local cards = {}
			for _, name in ipairs(lists[index]) do
				if byPage[name] then
					cards[#cards + 1] = card(frame, name, byPage[name], numbers[name], captains)
				end
			end
			if #lists[index] > 0 then
				html[#html + 1] = '<div class="position-list">\n<div class="position-title">'
					.. position.title .. '</div>\n<div class="position-players">'
					.. table.concat(cards) .. '</div>\n</div>'
			end
		end
	end

	local list = ''
	if (players[1] or '') ~= '' then
		list = '<div class="list">\n' .. table.concat(html) .. '</div>'
	end
	return '<div class="players-section-container" id="סגל שחקנים">\n'
		.. '<div class="title">סגל שחקנים</div>\n'
		.. '<div class="players-list-container">\n' .. list .. '\n</div>\n</div>'
end

return p
