--[[
Module:FootballPlayerStats - the numbers of a player page's statistics column.

Wiki page: Module:FootballPlayerStats

תבנית:פרופיל כדורגל/הצגת עמודת סטטיסטיקה/שחקן/הצגה (one per tab: רשמי, ליגה,
גביע, בינלאומי, יתר-רשמיים) #vardefine'd 15 numbers, each from its own query
template: 75 queries, ~2.3 of a player page's ~3.5 s. Each call is now
    {{#invoke:FootballPlayerStats|value|שחקן=…|קטגוריית מפעל=…|תא=…}}
and the template keeps every #vardefine and all of its formatting.

The first call for a player runs ONE query for every outfield number of all
five tabs and stores them in page variables (Scribunto keeps nothing between
invokes); the first keeper number runs the two keeper queries the same way.
Three queries a page instead of 75.

Each number mirrors its template exactly:
  appearances, substitutions, cleanSheets - games CONTAINING the events
      (the templates listed the games, grouped by page, and counted them);
  goals … losses - event ROWS (כמות אירועי שחקן): a player with two
      appearance events in one game counts that game twice in wins, as there;
  conceded - ROUND(SUM(ResultOpponent)) over the appearance rows of
      non-technical games; no rows gives an EMPTY value, as the template did;
  penaltiesConceded - opponent penalty goals in those games (a self-join of
      the events table); none gives 0.
The one departure: a player name carrying a double quote is escaped here, where
the templates put it into their SQL as it was (אמנון חרל"פ).
]]

local p = {}

local CATEGORIES = {
	['רשמי'] = 'Competitions.Official = 1',
	['ליגה'] = 'Competitions.League = 1',
	['גביע'] = 'Competitions.Trophy = 1',
	['בינלאומי'] = 'Competitions.International = 1',
	['יתר-רשמיים'] = '(Competitions.Official = 1 AND Competitions.League = 0'
		.. ' AND Competitions.Trophy = 0 AND Competitions.International = 0)',
}
local CATEGORY_ORDER = { 'רשמי', 'ליגה', 'גביע', 'בינלאומי', 'יתר-רשמיים' }

-- grain 'games' counts distinct game pages, 'events' counts event rows.
local CELLS = {
	{ name = 'appearances', grain = 'games', condition = 'Games_Events.EventType IN (1,5)' },
	{ name = 'substitutions', grain = 'games', condition = 'Games_Events.EventType IN (5)' },
	{ name = 'cleanSheets', grain = 'games',
	  condition = 'Games_Events.EventType IN (1, 5) AND Football_Games.ResultOpponent = 0' },
	{ name = 'goals', grain = 'events',
	  condition = 'Games_Events.EventType IN (3) AND Games_Events.SubType != 33' },
	{ name = 'penaltyGoals', grain = 'events',
	  condition = 'Games_Events.EventType IN (3) AND Games_Events.SubType IN (35)' },
	{ name = 'assists', grain = 'events', condition = 'Games_Events.EventType IN (4)' },
	{ name = 'penaltiesWon', grain = 'events',
	  condition = 'Games_Events.EventType IN (4) AND Games_Events.SubType IN (44)' },
	{ name = 'penaltySaves', grain = 'events',
	  condition = 'Games_Events.EventType IN (8) AND Games_Events.SubType IN (83)' },
	{ name = 'yellows', grain = 'events',
	  condition = 'Games_Events.EventType IN (7) AND Games_Events.SubType IN (71)' },
	{ name = 'reds', grain = 'events',
	  condition = 'Games_Events.EventType IN (7) AND Games_Events.SubType IN (72, 73)' },
	{ name = 'wins', grain = 'events',
	  condition = 'Games_Events.EventType IN (1, 5) AND Football_Games.ResultOpt = 1' },
	{ name = 'draws', grain = 'events',
	  condition = 'Games_Events.EventType IN (1, 5) AND Football_Games.ResultOpt = 2' },
	{ name = 'losses', grain = 'events',
	  condition = 'Games_Events.EventType IN (1, 5) AND Football_Games.ResultOpt = 3' },
}
local KEEPER_CELLS = { conceded = true, penaltiesConceded = true }

local function trim(value)
	return mw.text.trim(value or '')
end

--- The name as the templates' SQL saw it: PAGENAME's entities decoded (Cargo
--- decoded them in their WHERE), then escaped for a double-quoted literal.
--- Any other ampersand is refused - Cargo would decode it inside the query.
local function literal(name)
	name = name:gsub('&#34;', '"'):gsub('&quot;', '"'):gsub('&#39;', "'"):gsub('&#039;', "'")
	if name:find('&', 1, true) then
		error('FootballPlayerStats: a player name with an ampersand cannot be queried: ' .. name, 0)
	end
	return '"' .. name:gsub('\\', '\\\\'):gsub('"', '\\"') .. '"'
end

--- A number as the templates printed it: a whole number (#number_format then
--- the comma removed). `empty` is what NULL becomes.
local function whole(value, empty)
	local number = tonumber(value)
	if number == nil then
		return empty
	end
	return string.format('%d', math.floor(number + 0.5))
end

local function variable(player, category, cell)
	return 'FootballPlayerStats|' .. player .. '|' .. category .. '|' .. cell
end

local function store(frame, name, value)
	frame:callParserFunction('#vardefine', { name, value })
end

local function stored(frame, name)
	return frame:callParserFunction('#var', { name })
end

local function query(tables, fields, options)
	options.limit = 5
	local rows = mw.ext.cargo.query(tables, fields, options)
	if #rows ~= 1 then
		error(string.format('FootballPlayerStats: an aggregate returned %d rows', #rows), 0)
	end
	return rows[1]
end

--- Every outfield number of all five tabs, one query.
local function primeOutfield(frame, player)
	local fields = {}
	for categoryIndex, category in ipairs(CATEGORY_ORDER) do
		for cellIndex, cell in ipairs(CELLS) do
			local condition = cell.condition .. ' AND ' .. CATEGORIES[category]
			local expression
			if cell.grain == 'games' then
				expression = 'COUNT(DISTINCT CASE WHEN ' .. condition .. ' THEN Football_Games._pageName END)'
			else
				expression = 'SUM(CASE WHEN ' .. condition .. ' THEN 1 ELSE 0 END)'
			end
			fields[#fields + 1] = expression .. '=c' .. categoryIndex .. '_' .. cellIndex
		end
	end
	local row = query('Football_Games, Games_Events, Competitions', table.concat(fields, ', '), {
		join = 'Football_Games._pageID=Games_Events._pageID, Football_Games.Competition=Competitions.OriginalName',
		where = 'Games_Events.PlayerName = ' .. literal(player) .. ' AND Games_Events.Team = 1',
	})
	for categoryIndex, category in ipairs(CATEGORY_ORDER) do
		for cellIndex, cell in ipairs(CELLS) do
			-- COUNT gives 0 over nothing; SUM gives NULL, which the templates'
			-- COUNT(*) never did.
			store(frame, variable(player, category, cell.name),
				whole(row['c' .. categoryIndex .. '_' .. cellIndex], '0'))
		end
	end
end

--- The two keeper numbers of all five tabs, two queries.
local function primeKeeper(frame, player)
	local conceded, penalties = {}, {}
	for categoryIndex, category in ipairs(CATEGORY_ORDER) do
		conceded[#conceded + 1] = 'ROUND(SUM(CASE WHEN ' .. CATEGORIES[category]
			.. ' THEN Football_Games.ResultOpponent ELSE NULL END))=c' .. categoryIndex
		penalties[#penalties + 1] = 'SUM(CASE WHEN ' .. CATEGORIES[category]:gsub('Competitions%.', 'c.')
			.. ' THEN 1 ELSE 0 END)=c' .. categoryIndex
	end
	local concededRow = query('Football_Games, Games_Events, Competitions', table.concat(conceded, ', '), {
		join = 'Football_Games._pageName=Games_Events._pageName, Football_Games.Competition=Competitions.OriginalName',
		where = 'Games_Events.PlayerName = ' .. literal(player) .. ' AND Games_Events.Team = 1'
			.. ' AND Games_Events.EventType IN (1, 5) AND Football_Games.Technical = -1',
	})
	local penaltyRow = query('Football_Games=fg, Games_Events=ge1, Games_Events=ge2, Competitions=c',
		table.concat(penalties, ', '), {
			join = 'fg._pageName=ge1._pageName, fg._pageName=ge2._pageName, fg.Competition=c.OriginalName',
			where = 'ge1.PlayerName = ' .. literal(player) .. ' AND ge1.Team = 1 AND ge1.EventType IN (1, 5)'
				.. ' AND ge2.Team = 0 AND ge2.SubType = 35 AND fg.Technical = -1',
		})
	for categoryIndex, category in ipairs(CATEGORY_ORDER) do
		-- ROUND(SUM()) over nothing is NULL, and the template printed nothing.
		store(frame, variable(player, category, 'conceded'), whole(concededRow['c' .. categoryIndex], ''))
		store(frame, variable(player, category, 'penaltiesConceded'), whole(penaltyRow['c' .. categoryIndex], '0'))
	end
end

local KNOWN = {}
for _, cell in ipairs(CELLS) do
	KNOWN[cell.name] = true
end

function p.value(frame)
	local player = trim(frame.args['שחקן'])
	local category = trim(frame.args['קטגוריית מפעל'])
	local cell = trim(frame.args['תא'])
	if not CATEGORIES[category] then
		error('FootballPlayerStats: unknown קטגוריית מפעל "' .. category .. '"', 0)
	end
	local keeper = KEEPER_CELLS[cell]
	if not (keeper or KNOWN[cell]) then
		error('FootballPlayerStats: unknown תא "' .. cell .. '"', 0)
	end
	if player == '' then
		error('FootballPlayerStats: value needs a שחקן', 0)
	end
	local marker = variable(player, keeper and 'keeper' or 'outfield', 'primed')
	if stored(frame, marker) == '' then
		if keeper then
			primeKeeper(frame, player)
		else
			primeOutfield(frame, player)
		end
		store(frame, marker, '1')
	end
	return stored(frame, variable(player, category, cell))
end

return p
