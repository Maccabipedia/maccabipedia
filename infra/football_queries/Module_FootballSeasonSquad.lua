--[[
Module:FootballSeasonSquad - the squad block of a football season page.

Wiki page: Module:FootballSeasonSquad

תבנית:עונת כדורגל/הצגת סגל built the squad from one Cargo query per position
and then TWO per player - the profile fields, then the shirt number inside
the card - about 90 queries on a 42-player season. This renders the same
cards from three: the season's players with their games, every profile at
once, and every shirt number at once.

Template body:
    {{#invoke:FootballSeasonSquad|render|עונה={{{עונה|}}}|שחקנים={{{שחקנים|}}}}}

Card order within a position: MainNumber ascending, a missing one first (as
MySQL sorted it); then most games that season; then the name. The templates
stopped at MainNumber, and most old profiles have none, so their order was
whatever MySQL returned - the games-then-name tie-break is a deliberate
change, decided 2026-09-21. Wherever MainNumbers differ, the order is today's.

Everything else must be byte-identical to the templates', so their oddities
are reproduced and marked where they are not obvious.
]]

local p = {}

-- Cargo truncates silently at a query's limit, so every query sets one and a
-- result that reaches it is an error.
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

--- A season goes into the SQL as it is, as the templates did, so anything but
--- digits and a slash never reaches a query: it gives nil, and nil means no
--- rows - what the templates showed for a season that matched nothing (a
--- draft or /ארגז חול copy of a season page, whose name is not a season).
local function checkedSeason(season)
	season = trim(season)
	if not season:match('^[%d/]*$') then
		return nil
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

--- Every query goes through here: a result that reached the limit is an
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

--- The season's Maccabi players in the query's (name) order, and the number
--- of games each one has an event in.
local function seasonPlayers(season)
	if not season then
		return {}, {}
	end
	local rows = limited('Football_Games=fg, Games_Events=ge',
		'ge.PlayerName=name, COUNT(DISTINCT fg._pageName)=games', {
			join = 'fg._pageName=ge._pageName',
			where = '1=1 AND fg.Season="' .. season .. '" AND ge.Team=1',
			groupBy = 'ge.PlayerName',
		})
	local names, games = {}, {}
	for index, row in ipairs(rows) do
		names[index] = trim(row.name)
		games[names[index]] = tonumber(row.games) or 0
	end
	return names, games
end

--- Every profile the cards need, first row per page - as `limit=1` took it.
--- The filter template's output passed through a `&#39;` fix; so does this.
local function profiles(names)
	local rows = limited('Profiles', '_pageName=page, FullHebName=fullName, '
		.. 'WholeCareer=wholeCareer, HomePlayer=homePlayer, '
		.. 'RootedPlayer=rootedPlayer, ForeignPlayer=foreignPlayer, '
		.. 'Position=position, MainNumber=mainNumber', {
			where = '_pageName IN (' .. inList(names) .. ')',
		})
	local byPage, pages = {}, {}
	for _, row in ipairs(rows) do
		local page = trim((row.page or ''):gsub('&#39;', "'"))
		if page ~= '' and not byPage[page] then
			byPage[page] = row
			pages[#pages + 1] = page
		end
	end
	return byPage, pages
end

--- The position codes a profile holds (Position is a list field).
local function heldCodes(profile)
	local held = {}
	for _, code in ipairs(splitList(profile.position or '')) do
		held[code] = true
	end
	return held
end

--- MainNumber ascending with a missing one first, as MySQL sorted it; then
--- most games this season; then the name.
local function cardOrder(byPage, games)
	return function(first, second)
		local firstNumber = tonumber(byPage[first].mainNumber)
		local secondNumber = tonumber(byPage[second].mainNumber)
		if firstNumber ~= secondNumber then
			if firstNumber == nil then return true end
			if secondNumber == nil then return false end
			return firstNumber < secondNumber
		end
		local firstGames, secondGames = games[first] or 0, games[second] or 0
		if firstGames ~= secondGames then
			return firstGames > secondGames
		end
		return first < second
	end
end

--- The players of each position, in card order. ללא עמדה holds none of 1-4.
local function positionLists(byPage, pages, games)
	local lists = {}
	for index, position in ipairs(POSITIONS) do
		local list = {}
		for _, page in ipairs(pages) do
			local held = heldCodes(byPage[page])
			local inPosition
			if position.code then
				inPosition = held[position.code]
			else
				inPosition = not (held['1'] or held['2'] or held['3'] or held['4'])
			end
			if inPosition then
				list[#list + 1] = page
			end
		end
		table.sort(list, cardOrder(byPage, games))
		lists[index] = list
	end
	return lists
end

--- The number each player wore in most of the season's games, ties going to
--- the number worn in the earliest one; blanks never count. GAMES, not event
--- rows: a game has one row per event, so COUNT(*) would weigh a number by
--- the goals and cards scored in it.
local function shirtNumbers(season)
	if not season then
		return {}
	end
	local rows = limited('Football_Games=fg, Games_Events=ge',
		'ge.PlayerName=name, ge.PlayerNumber=number, '
			.. 'COUNT(DISTINCT fg._pageName)=games, MIN(fg.Date)=firstGame', {
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
	-- Games order the cards even when the page hands over its own list.
	local seasonNames, games = seasonPlayers(season)
	local players = trim(given) ~= '' and splitList(given) or seasonNames

	-- The template tested only the FIRST name: an empty one hides the list.
	local listed = (players[1] or '') ~= ''
	local everyone = unique(players)

	local html = {}
	if listed and #everyone > 0 then
		local byPage, pages = profiles(everyone)
		local lists = positionLists(byPage, pages, games)
		local numbers = shirtNumbers(checkedSeason(
			frame:callParserFunction('#var', { 'עונה להצגה' })))
		local captains = splitList(frame:callParserFunction('#var', { 'קפטנים' }))
		for index, position in ipairs(POSITIONS) do
			local cards = {}
			for _, name in ipairs(lists[index]) do
				cards[#cards + 1] = card(frame, name, byPage[name], numbers[name], captains)
			end
			if #lists[index] > 0 then
				html[#html + 1] = '<div class="position-list">\n<div class="position-title">'
					.. position.title .. '</div>\n<div class="position-players">'
					.. table.concat(cards) .. '</div>\n</div>'
			end
		end
	end

	local list = ''
	if listed then
		list = '<div class="list">\n' .. table.concat(html) .. '</div>'
	end
	return '<div class="players-section-container" id="סגל שחקנים">\n'
		.. '<div class="title">סגל שחקנים</div>\n'
		.. '<div class="players-list-container">\n' .. list .. '\n</div>\n</div>'
end

-- ------------------------------------------------------------ players portal

local PORTAL_CARD = 'פורטל שחקני כדורגל/הצגת סגל נוכחי/הצגת שחקן'

--- A value as `#cargo_query format=template` handed it to a template:
--- htmlspecialchars with PHP's default flags - `"` becomes &quot;, and an
--- apostrophe stays as it is (ג'יימס טברנייר renders with a plain ').
local function asTemplateArgument(value)
	return (tostring(value or ''):gsub('&', '&amp;'):gsub('<', '&lt;'):gsub('>', '&gt;')
		:gsub('"', '&quot;'))
end

--- MainNumber ascending, a missing one first (as MySQL sorted NULL); ties,
--- which MySQL left in any order, by name.
local function byMainNumber(profileOf)
	return function(first, second)
		local firstNumber = tonumber(profileOf[first][1].mainNumber)
		local secondNumber = tonumber(profileOf[second][1].mainNumber)
		if firstNumber ~= secondNumber then
			if firstNumber == nil then return true end
			if secondNumber == nil then return false end
			return firstNumber < secondNumber
		end
		return first < second
	end
end

--- `פורטל שחקני כדורגל/הצגת סגל נוכחי` from ONE query. The template ran one
--- Profiles query per position (five) and one per player for the card - 32
--- on today's squad. The card itself is still the template, fed the same
--- named values `format=template` gave it, so its markup cannot drift.
---   {{#invoke:FootballSeasonSquad|portal|סגל נוכחי={{{סגל נוכחי|}}}}}
function p.portal(frame)
	local squad = unique(splitList(frame.args['סגל נוכחי']))
	local profileOf, pages = {}, {}
	if #squad > 0 then
		local rows = limited('Profiles', '_pageName=page, FullHebName=fullName, '
			.. 'ProfilePicture=picture, DoB=born, Height=height, MainNumber=mainNumber, '
			.. 'Position=position, WholeCareer=wholeCareer, HomePlayer=homePlayer, '
			.. 'RootedPlayer=rootedPlayer, ForeignPlayer=foreignPlayer', {
				where = '_pageName IN (' .. inList(squad) .. ')',
			})
		-- Every row, as the card query rendered every row of a page.
		for _, row in ipairs(rows) do
			local page = trim(row.page)
			if not profileOf[page] then
				profileOf[page] = {}
				pages[#pages + 1] = page
			end
			table.insert(profileOf[page], row)
		end
	end

	local function cards(list)
		local out = {}
		for _, page in ipairs(list) do
			local rendered = {}
			for _, profile in ipairs(profileOf[page]) do
				rendered[#rendered + 1] = frame:expandTemplate{ title = PORTAL_CARD, args = {
					PageName = asTemplateArgument(page),
					PlayerName = asTemplateArgument(profile.fullName),
					ProfilePicture = asTemplateArgument(profile.picture),
					DoB = asTemplateArgument(profile.born),
					Height = asTemplateArgument(profile.height),
					MainNumber = asTemplateArgument(profile.mainNumber),
					Position = asTemplateArgument(profile.position),
					WholeCareer = asTemplateArgument(profile.wholeCareer),
					HomePlayer = asTemplateArgument(profile.homePlayer),
					RootedPlayer = asTemplateArgument(profile.rootedPlayer),
					ForeignPlayer = asTemplateArgument(profile.foreignPlayer),
				} }
			end
			-- #arrayprint trimmed each item.
			out[#out + 1] = trim(table.concat(rendered))
		end
		return table.concat(out)
	end

	local html = {}
	for _, position in ipairs(POSITIONS) do
		local list = {}
		for _, page in ipairs(pages) do
			local held = heldCodes(profileOf[page][1])
			local inPosition
			if position.code then
				inPosition = held[position.code]
			else
				inPosition = not (held['1'] or held['2'] or held['3'] or held['4'])
			end
			if inPosition then
				list[#list + 1] = page
			end
		end
		table.sort(list, byMainNumber(profileOf))
		if position.code then
			html[#html + 1] = '<div class="position-list-container">\n<div class="list-title">'
				.. position.title .. '</div>\n<div class="list-container">' .. cards(list)
				.. '</div>\n</div>'
		elseif #list > 0 then
			-- The template listed these by name only.
			html[#html + 1] = '<div class="position-list-container">\n<div class="list-title">'
				.. position.title .. '</div>\n<div class="list-container">'
				.. table.concat(list, ', ') .. '</div>\n</div>'
		end
	end
	return table.concat(html)
end

return p
