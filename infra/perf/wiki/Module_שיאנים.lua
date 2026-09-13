-- יחידה:שיאנים -- leaderboards (top scorers, assists, appearances, cards).
--
-- Replaces [[תבנית:סטטיסטיקה/שליפות/מתקדמות/שיאני כמות אירועי שחקן/עיצוב חדש]].
-- Output is identical to [[תבנית:סטטיסטיקות/הצגת שיאנים/הצגת שחקן/כדורגל]].
--
-- Why it exists: a records page (players portal, stadium, opponent) shows four
-- display templates, each with four competition tabs, and every tab ran TWO
-- queries -- one for the table and one that re-ran the same query capped at
-- 2000 rows purely to count the distinct players named in the tab header.
-- 32 queries per page.
--
-- p.section renders a whole display template -- four tabs and their four counts
-- -- from one query, so a filtered page drops to 4. With no filter at all those
-- four collapse to 1 as well, through [[יחידה:שיאנים/נתונים]] and mw.loadData,
-- which is the only Scribunto cache that survives between #invoke calls.
--
-- One deliberate behaviour change: ordering is stable. The template sorted by
-- COUNT(*) alone, so players on equal totals came back in whatever order the
-- database chose and two loads of the same page listed different names. Ties
-- break by player name here.

local p = {}

-- The four competition tabs, identical across all four display templates.
local TABS = {
	{ id = 'tab1-content', label = 'משחקים רשמיים', category = 'רשמי' },
	{ id = 'tab2-content', label = 'ליגה', category = 'ליגה' },
	{ id = 'tab3-content', label = 'גביע המדינה', category = 'גביע' },
	{ id = 'tab4-content', label = 'בינלאומי', category = 'בינלאומי' },
}

-- Filters this module can push into SQL. These are every filter the display
-- templates are actually handed: a category or portal page sends שחקנים, a
-- stadium sends אצטדיונים, an opponent sends יריבות, a season sends עונה and a
-- referee page sends שופטים. The one left out is עוזר שופט, which needs a
-- HOLDS join to Games_Referees and has its own display template anyway.
--
-- strip=true marks the columns Cargo stores WITHOUT quote characters. This is
-- not cosmetic: Opponent, Stadium and Competition are stored cleaned -- Cargo
-- holds "ביתר ירושלים", never 'בית"ר ירושלים' -- while PlayerName and Refs keep
-- the apostrophe as written ("אביעזר ז'נו"). Query a stripped column with the
-- raw page name and you get zero rows and no error. The original template
-- encoded the same distinction by wrapping SOME of its IN lists in
-- [[תבנית:המרות/שם ללא גרש וגרשיים]] and not others.
local FILTERS = {
	['שחקנים'] = { column = 'Games_Events.PlayerName' },
	['שופטים'] = { column = 'Football_Games.Refs' },
	['עונה'] = { column = 'Football_Games.Season' },
	['אצטדיונים'] = { column = 'Football_Games.Stadium', strip = true },
	['יריבות'] = { column = 'Football_Games.Opponent', strip = true },
	['מפעלים'] = { column = 'Football_Games.Competition', strip = true },
}

--- Split a comma-separated list of short values (event and sub-event ids).
local function toSet(csv)
	local set, any = {}, false
	for item in tostring(csv or ''):gmatch('[^,%s]+') do
		set[item] = true
		any = true
	end
	return any and set or nil
end

--- Split a list of names. Unlike toSet these contain spaces, and they arrive
--- in three different shapes depending on which template built the list: bare,
--- individually quoted (that is how
--- [[תבנית:סטטיסטיקה/שמות דפים מקטגוריה מופרדים לשליפה]] emits them), or with
--- the whole list wrapped in parentheses (the המרות templates return it ready
--- for an SQL IN operator).
local function toNames(csv, strip)
	local names = {}
	local list = tostring(csv or ''):match('^%s*%((.*)%)%s*$') or csv or ''
	for item in tostring(list):gmatch('[^,]+') do
		local name = item:match('^%s*(.-)%s*$')
		name = name:match("^'(.*)'$") or name:match('^"(.*)"$') or name
		if strip then
			-- HTML-encoded too: that is how {{PAGENAME}} hands the name over.
			name = name:gsub('&#34;', ''):gsub('&quot;', '')
			           :gsub('&#39;', ''):gsub('&apos;', '')
			           :gsub("'", ''):gsub('"', '')
		end
		if name ~= '' then
			table.insert(names, name)
		end
	end
	return #names > 0 and names or nil
end

--- Values for an SQL IN list, with apostrophes escaped properly. The original
--- template simply deleted them from the name, which stopped matching whatever
--- Cargo had stored.
local function sqlList(names)
	local quoted = {}
	for index, name in ipairs(names) do
		quoted[index] = "'" .. name:gsub("'", "''") .. "'"
	end
	return '(' .. table.concat(quoted, ',') .. ')'
end

--- Values for an SQL IN list from a numeric parameter (event, sub-event).
local function sqlNumbers(csv)
	local values = {}
	for item in tostring(csv or ''):gmatch('[^,%s]+') do
		table.insert(values, (item:gsub("'", "''")))
	end
	return #values > 0 and ('(' .. table.concat(values, ',') .. ')') or nil
end

--- The page's filter conditions as SQL. Used both for the query itself and to
--- build the "עוד" link that leads to Special:CargoQuery.
local function filterConditions(args)
	local conditions = {}
	for name, filter in pairs(FILTERS) do
		local names = toNames(args[name], filter.strip)
		if names then
			table.insert(conditions, filter.column .. ' IN ' .. sqlList(names))
		end
	end
	table.sort(conditions)  -- stable order, so the "עוד" link URL does not
	                        -- change between renders of the same page
	return conditions
end

local CATEGORY_SQL = {
	['ליגה'] = 'Competitions.League=1',
	['גביע'] = 'Competitions.Trophy=1',
	['בינלאומי'] = 'Competitions.International=1',
}

local function matchesCategory(row, category)
	if category == nil or category == '' then return true end
	if category == 'ליגה' then return row.league == '1' end
	if category == 'גביע' then return row.trophy == '1' end
	if category == 'בינלאומי' then return row.intl == '1' end
	-- 'רשמי' needs no test here: BASE_WHERE already restricts the query to
	-- Competitions.Official=1, so every row in hand is official.
	if category == 'רשמי' then return true end
	if category == 'יתר רשמי' or category == 'יתר-רשמיים' then
		return row.league ~= '1' and row.trophy ~= '1' and row.intl ~= '1'
	end
	return true
end

-- Row cap for the grouped query. The largest aggregate in production is 9,569
-- rows, about half of this -- but Cargo truncates AT the cap silently, with no
-- error and no warning, and a leaderboard computed from a cut-off result looks
-- like a perfectly ordinary table of wrong numbers. So if a query comes back
-- holding exactly ROW_LIMIT rows, the data may be incomplete and the module
-- says so instead. Measure the real sizes with check_query_limits.py.
local ROW_LIMIT = 20000
local TRUNCATED = 'יחידה:שיאנים — השליפה הגיעה לתקרת ' .. ROW_LIMIT ..
                  ' שורות וייתכן שנקטעה. יש להעלות את ROW_LIMIT.'

local TABLES = 'Football_Games,Games_Events,Competitions'
local JOIN = 'Football_Games._pageID=Games_Events._pageID,' ..
             'Football_Games.Competition=Competitions.OriginalName'
local BASE_WHERE = 'Games_Events.Team=1 AND Competitions.Official=1 ' ..
                   "AND Games_Events.PlayerName IS NOT NULL " ..
                   "AND Games_Events.PlayerName != ''"

local function fetchRows(args)
	local conditions = filterConditions(args)
	if #conditions == 0 then
		return mw.loadData('יחידה:שיאנים/נתונים')
	end

	return mw.ext.cargo.query(
		TABLES,
		table.concat({
			'Games_Events.PlayerName=player',
			'Games_Events.EventType=eventType',
			'Games_Events.SubType=subType',
			'Competitions.League=league',
			'Competitions.Trophy=trophy',
			'Competitions.International=intl',
			'COUNT(*)=n',
		}, ','),
		{
			join = JOIN,
			where = BASE_WHERE .. ' AND ' .. table.concat(conditions, ' AND '),
			groupBy = 'Games_Events.PlayerName,Games_Events.EventType,' ..
			          'Games_Events.SubType,Competitions.League,' ..
			          'Competitions.Trophy,Competitions.International',
			limit = ROW_LIMIT,
		}) or {}
end

--- The page's rows, or nil plus an error string if the query may have been
--- truncated.
local function safeRows(args)
	local rows = fetchRows(args)
	if #rows >= ROW_LIMIT then
		return nil, TRUNCATED
	end
	return rows, nil
end

--- Sum each player's events from rows that have already been fetched.
local function totals(rows, args, category)
	local wantEvents = toSet(args['מספר אירוע'])
	local wantSubs = toSet(args['תת אירוע'])
	local excludeSubs = toSet(args['ללא תת אירוע'])

	local byPlayer = {}
	for _, row in ipairs(rows) do
		local ok = matchesCategory(row, category)
		if ok and wantEvents and not wantEvents[row.eventType] then ok = false end
		if ok and wantSubs and not wantSubs[row.subType] then ok = false end
		if ok and excludeSubs and excludeSubs[row.subType] then ok = false end
		if ok then
			byPlayer[row.player] = (byPlayer[row.player] or 0) + row.n
		end
	end
	return byPlayer
end

local function sorted(byPlayer)
	local list = {}
	for player, count in pairs(byPlayer) do
		table.insert(list, { player = player, count = count })
	end
	table.sort(list, function(a, b)
		if a.count ~= b.count then return a.count > b.count end
		return a.player < b.player  -- stable tiebreak
	end)
	return list
end

local function playerRow(player, count)
	local title = mw.title.new(player)
	local name = title and title.exists
		and ('[[' .. player .. '|' .. player .. ']]') or player
	return '<div class="atom-records-list-player-row">' ..
	       '<span class="player-name">\n' .. name .. '</span>' ..
	       '<div class="atom-recors-list-player-info">' ..
	       '<span class="record">' .. mw.getContentLanguage():formatNum(count) ..
	       '</span></div>\n</div>\n'
end

--- The "עוד" link under each table. The Cargo query used to emit this itself
--- when handed |more results text=, so it is rebuilt here from the same
--- conditions rather than quietly dropped. It leads to the full result -- every
--- player, not just the top ten.
local function moreLink(args, category, text)
	if text == nil or text == '' then return '' end

	local conditions = filterConditions(args)
	table.insert(conditions, 1, BASE_WHERE)
	if CATEGORY_SQL[category] then
		table.insert(conditions, CATEGORY_SQL[category])
	end
	local events = sqlNumbers(args['מספר אירוע'])
	if events then
		table.insert(conditions, 'Games_Events.EventType IN ' .. events)
	end
	local subs = sqlNumbers(args['תת אירוע'])
	if subs then
		table.insert(conditions, 'Games_Events.SubType IN ' .. subs)
	end
	local without = sqlNumbers(args['ללא תת אירוע'])
	if without then
		table.insert(conditions, 'Games_Events.SubType NOT IN ' .. without)
	end

	local url = mw.uri.fullUrl('Special:CargoQuery', {
		tables = TABLES,
		fields = 'Games_Events.PlayerName, COUNT(*)',
		where = table.concat(conditions, ' AND '),
		join_on = JOIN,
		['group by'] = 'Games_Events.PlayerName',
		['order by'] = 'COUNT(*) DESC',
		limit = '100',
	})
	-- A wikitext external link, not an <a> tag: #invoke output is parsed as
	-- wikitext and a raw <a> would be escaped. The query could emit HTML
	-- directly; Lua cannot.
	return '[' .. tostring(url) .. ' ' .. text .. ']'
end

local function renderTop(list, limit)
	local parts = {}
	for index = 1, math.min(limit, #list) do
		table.insert(parts, playerRow(list[index].player, list[index].count))
	end
	return table.concat(parts)
end

--- A single leaderboard table, for callers that want one tab only.
--- Parameters: מספר אירוע, תת אירוע, ללא תת אירוע, קטגוריית מפעל, הגבלה
function p.top(frame)
	local args = frame.args
	local limit = tonumber(args['הגבלה']) or 10
	local rows, err = safeRows(args)
	if err then return err end
	return renderTop(sorted(totals(rows, args, args['קטגוריית מפעל'])), limit)
end

--- How many distinct players match the filter (the "N כובשים שונים" count).
function p.distinctPlayers(frame)
	local args = frame.args
	local rows, err = safeRows(args)
	if err then return err end
	local count = 0
	for _ in pairs(totals(rows, args, args['קטגוריית מפעל'])) do
		count = count + 1
	end
	return count
end

--- A whole records block: four tabs and their four counts, from one query.
--- Parameters: כינוי (the noun for the count, e.g. "כובשים שונים"),
--- מספר אירוע, תת אירוע, ללא תת אירוע, הגבלה, and one of the FILTERS keys.
function p.section(frame)
	local args = frame.args
	local limit = tonumber(args['הגבלה']) or 10
	local noun = args['כינוי'] or 'שחקנים שונים'
	local rows, err = safeRows(args)
	if err then return err end

	local parts = {}
	for _, tab in ipairs(TABS) do
		local list = sorted(totals(rows, args, tab.category))
		table.insert(parts, table.concat({
			'<div id="', tab.id, '"><div class="tab-header">',
			tab.label, ' (', mw.getContentLanguage():formatNum(#list),
			' ', noun, ')</div>\n',
			renderTop(list, limit),
			moreLink(args, tab.category, args['עוד תוצאות']),
			'</div>',
		}))
	end
	return table.concat(parts)
end

return p
