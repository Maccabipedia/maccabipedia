-- יחידה:סטטיסטיקה שחקן -- LOCAL EXPERIMENT ONLY, not deployed to prod.
--
-- Replaces three query families on a football player page with two cached
-- Cargo queries plus in-memory aggregation:
--
--   כמות אירועי שחקן                   ~50 calls  -> events query
--   כמות משחקים המכילים אירוע שחקן     ~15 calls  -> same events query
--   אצטדיון לרשימת אצטדיונים מקושרים   ~66 calls  -> stadiums query
--
-- One row per event is fetched rather than a GROUP BY, because counting
-- DISTINCT games needs game identity, which grouping discards. Cargo's Lua
-- interface calls CargoSQLQuery::run() directly, bypassing CargoQuery.php --
-- so unlike the parser function it performs no backlinks second-query, no
-- DELETE and no INSERTs, grouped or not.

local p = {}
local cargo = mw.ext.cargo

local eventCache = {}
local stadiumCache = nil

-- Cargo builds raw SQL from these strings, so a quote would break out of the
-- literal. Strip rather than trust the caller.
local function sanitize(value)
	return (tostring(value or ''):gsub('["\\]', ''))
end

-- "3, 5" -> { ['3']=true, ['5']=true }; nil when empty, meaning "no filter".
local function toSet(csv)
	local set, any = {}, false
	for item in tostring(csv or ''):gmatch('[^,%s]+') do
		set[item] = true
		any = true
	end
	return any and set or nil
end

-- ---------------------------------------------------------------------------
-- Events: one row per event, fetched once per player per page render.
-- ---------------------------------------------------------------------------

-- Every parameter the wikitext templates accept. Anything outside this set
-- would be silently ignored and produce a plausible-looking wrong number, so
-- callers using an unsupported filter get a visible error instead.
local SUPPORTED = {
	['שחקן'] = true, ['מספר אירוע'] = true, ['תת אירוע'] = true,
	['ללא תת אירוע'] = true, ['קטגוריית מפעל'] = true, ['תוצאה'] = true,
	['עונה'] = true, ['מכבי'] = true,
}
-- אצטדיון אינו ברשימה בכוונה: count ו-countGames אינן מסננות לפיו (רק
-- stadiumAliases נוגעת באצטדיונים), ולכן הוא חייב להחזיר שגיאה ולא מספר.
-- כשהוא הופיע כאן הבדיקה מול השליפה המקורית נתנה 433 במקום 208.

local function unsupportedArgs(args)
	local unknown = {}
	for name, value in pairs(args) do
		if not SUPPORTED[name] and tostring(value or '') ~= '' then
			table.insert(unknown, name)
		end
	end
	table.sort(unknown)
	return unknown
end

-- Player and season are pushed into SQL (they bound the result set); everything
-- else is filtered in Lua over the cached rows. An empty player means "no
-- filter", matching the templates, which is how season pages get team totals.
local function fetchEvents(player, season, maccabiSide)
	local key = table.concat({ player or '', season or '', maccabiSide }, '|')
	if eventCache[key] then
		return eventCache[key]
	end
	local conditions = { 'Games_Events.Team=' .. maccabiSide }
	if player and player ~= '' then
		table.insert(conditions, 'Games_Events.PlayerName="' .. sanitize(player) .. '"')
	end
	if season and season ~= '' then
		table.insert(conditions, 'Football_Games.Season="' .. sanitize(season) .. '"')
	end
	eventCache[key] = cargo.query(
		'Football_Games,Games_Events,Competitions',
		table.concat({
			'Football_Games._pageID=gameId',
			'Games_Events.EventType=eventType',
			'Games_Events.SubType=subType',
			'Football_Games.ResultOpt=resultOpt',
			'Football_Games.Season=season',
			'Competitions.League=league',
			'Competitions.Trophy=trophy',
			'Competitions.International=intl',
			'Competitions.Official=official',
		}, ','),
		{
			join = 'Football_Games._pageID=Games_Events._pageID,' ..
			       'Football_Games.Competition=Competitions.OriginalName',
			where = table.concat(conditions, ' AND '),
			limit = 20000,
		}
	) or {}
	return eventCache[key]
end

local function rowsFor(args)
	local unknown = unsupportedArgs(args)
	if #unknown > 0 then
		return nil, 'יחידה:סטטיסטיקה שחקן — פרמטר לא נתמך: ' ..
		            table.concat(unknown, ', ')
	end
	local maccabiSide = (args['מכבי'] == 'לא') and '0' or '1'
	return fetchEvents(args['שחקן'], args['עונה'], maccabiSide), nil
end

local function matchesCategory(row, category)
	if category == nil or category == '' then return true end
	if category == 'ליגה' then return row.league == '1' end
	if category == 'גביע' then return row.trophy == '1' end
	if category == 'בינלאומי' then return row.intl == '1' end
	if category == 'רשמי' then return row.official == '1' end
	if category == 'יתר-רשמיים' then
		return row.official == '1' and row.league ~= '1'
		   and row.trophy ~= '1' and row.intl ~= '1'
	end
	return true
end

-- Mirrors the wikitext template's result mapping.
local RESULT_TO_OPT = { ['ניצחון'] = '1', ['תיקו'] = '2', ['הפסד'] = '3' }

local function matches(row, args)
	local wantEvents = toSet(args['מספר אירוע'])
	local wantSubs = toSet(args['תת אירוע'])
	local excludeSubs = toSet(args['ללא תת אירוע'])
	local wantResult = RESULT_TO_OPT[args['תוצאה'] or '']

	if not matchesCategory(row, args['קטגוריית מפעל']) then return false end
	if wantEvents and not wantEvents[row.eventType] then return false end
	if wantSubs and not wantSubs[row.subType] then return false end
	if excludeSubs and excludeSubs[row.subType] then return false end
	if wantResult and row.resultOpt ~= wantResult then return false end
	return true
end

--- Number of matching events. Replaces כמות אירועי שחקן.
function p.count(frame)
	local rows, err = rowsFor(frame.args)
	if err then return err end
	local total = 0
	for _, row in ipairs(rows) do
		if matches(row, frame.args) then
			total = total + 1
		end
	end
	return total
end

--- Number of DISTINCT games containing a matching event.
--- Replaces כמות משחקים המכילים אירוע שחקן (and the כמות רשומות wrapping it).
function p.countGames(frame)
	local rows, err = rowsFor(frame.args)
	if err then return err end
	local seen, total = {}, 0
	for _, row in ipairs(rows) do
		if matches(row, frame.args) and row.gameId and not seen[row.gameId] then
			seen[row.gameId] = true
			total = total + 1
		end
	end
	return total
end

-- ---------------------------------------------------------------------------
-- Stadium aliases. The template self-joins Stadiums on _pageID to find every
-- name belonging to the same stadium page, once per lookup. The whole table is
-- small, so fetch it once and answer all lookups from memory.
-- ---------------------------------------------------------------------------

local function stadiumsByPage()
	if stadiumCache then
		return stadiumCache
	end
	local rows = cargo.query('Stadiums', 'Stadiums._pageID=pageId,Stadiums.CanonicalName=name',
	                         { limit = 5000 }) or {}
	local byPage, pageOfName = {}, {}
	for _, row in ipairs(rows) do
		if row.name and row.name ~= '' then
			byPage[row.pageId] = byPage[row.pageId] or {}
			table.insert(byPage[row.pageId], row.name)
			pageOfName[row.name] = row.pageId
		end
	end
	stadiumCache = { byPage = byPage, pageOfName = pageOfName }
	return stadiumCache
end

--- Comma-separated quoted alias list, matching the template's
--- {{#arrayprint: stadiums |,  |@ |"@" }} output exactly.
function p.stadiumAliases(frame)
	local name = tostring(frame.args['אצטדיון'] or '')
	if name == '' then
		return ''
	end
	local data = stadiumsByPage()
	local pageId = data.pageOfName[name]
	if not pageId then
		return ''
	end
	local quoted = {}
	for _, alias in ipairs(data.byPage[pageId] or {}) do
		table.insert(quoted, '"' .. alias .. '"')
	end
	return table.concat(quoted, ',  ')
end

-- Diagnostics.
function p.eventRowCount(frame)
	local rows, err = rowsFor(frame.args)
	return err or #rows
end

-- ---------------------------------------------------------------------------
-- עמודת הסטטיסטיקה של שחקן, בקריאה אחת.
--
-- למה בקריאה אחת ולא נתון-נתון?
-- מצב של מודול ב-Scribunto אינו נשמר בין קריאות #invoke - נמדד: קריאה אחת
-- עלתה 0.035 שניות מעבד ו-65 קריאות עלו 0.968, כלומר ליניארי לחלוטין. לכן
-- כל קריאה חוזרת הייתה מריצה מחדש את שליפת הקארגו, וה"מטמון" שבמודול לא
-- הועיל. קריאה אחת שמחזירה את כל העמודה = שליפה אחת לכל העמודה.
--
-- הנתונים מוגדרים בטבלה למטה במקום 89 שורות של #vardefine חוזרות.
-- ---------------------------------------------------------------------------

local HTML_ROW = '<div>\n<span class="describe">%s</span>\n' ..
                 '<span class="info">%s</span>\n</div>'

--- עיצוב מספר עם שתי ספרות אחרי הנקודה, כמו {{#number_format:...|2}}.
--- מדיה-ויקי מעגלת חצי כלפי מעלה; string.format ב-Lua מעגלת חצי לזוגי,
--- כך ש-0.125 היה הופך ל-0.12 במקום 0.13. לכן העיגול נעשה במפורש.
local function twoDecimals(value)
	return string.format('%.2f', math.floor(value * 100 + 0.5) / 100)
end

--- אחוז, כמו [[תבנית:סטטיסטיקה/אחוזים]]: עיגול לשתי ספרות ואז עיצוב
local function percentOf(part, whole)
	if not whole or whole == 0 then return '0.00' end
	return twoDecimals((part / whole) * 100)
end

--- שורה אחת בעמודה. `small` הוא הטקסט המשני, ומוצג רק אם יש הופעות.
local function row(label, value, small, appearances)
	local info = tostring(value)
	if small and appearances and appearances > 0 then
		info = info .. ' <span class="small">' .. small .. '</span>'
	else
		info = info .. ' '
	end
	return string.format(HTML_ROW, label, info)
end

--- עמודת הסטטיסטיקה המלאה.
--- פרמטרים: שם להצגה, קטגוריית מפעל, האם שוער
function p.column(frame)
	local args = frame.args
	local player = args['שם להצגה'] or ''
	local category = args['קטגוריית מפעל'] or ''
	local isKeeper = (args['האם שוער'] or '') ~= ''

	-- שליפה אחת שממנה מחושבים כל הנתונים
	local rows = fetchEvents(player, '', '1')

	local function events(filters)
		filters['שחקן'] = player
		filters['קטגוריית מפעל'] = category
		local total = 0
		for _, item in ipairs(rows) do
			if matches(item, filters) then total = total + 1 end
		end
		return total
	end

	local function games(filters)
		filters['שחקן'] = player
		filters['קטגוריית מפעל'] = category
		local seen, total = {}, 0
		for _, item in ipairs(rows) do
			if matches(item, filters) and item.gameId and not seen[item.gameId] then
				seen[item.gameId] = true
				total = total + 1
			end
		end
		return total
	end

	local appearances = games({ ['מספר אירוע'] = '1,5' })
	local substitute = games({ ['מספר אירוע'] = '5' })
	local goals = events({ ['מספר אירוע'] = '3', ['ללא תת אירוע'] = '33' })
	local penaltyGoals = events({ ['מספר אירוע'] = '3', ['תת אירוע'] = '35' })
	local assists = events({ ['מספר אירוע'] = '4' })
	local penaltyWon = events({ ['מספר אירוע'] = '4', ['תת אירוע'] = '44' })
	local yellows = events({ ['מספר אירוע'] = '7', ['תת אירוע'] = '71' })
	local reds = events({ ['מספר אירוע'] = '7', ['תת אירוע'] = '72, 73' })
	local wins = events({ ['מספר אירוע'] = '1, 5', ['תוצאה'] = 'ניצחון' })
	local draws = events({ ['מספר אירוע'] = '1, 5', ['תוצאה'] = 'תיקו' })
	local losses = events({ ['מספר אירוע'] = '1, 5', ['תוצאה'] = 'הפסד' })

	local parts = {}
	table.insert(parts, row('הופעות', appearances,
		substitute .. ' כמחליף', 1))

	if isKeeper then
		-- ספיגות נשארות בתבניות הקיימות: הן נשענות על SUM של תוצאת היריבה
		-- ועל אירועי היריבה, שאינם בשליפה הזו.
		local conceded = tonumber(frame:expandTemplate{
			title = 'פרופיל כדורגל/שוער/כמות ספיגות',
			args = { ['שחקן'] = player, ['קטגוריית מפעל'] = category } }) or 0
		local penaltiesConceded = frame:expandTemplate{
			title = 'פרופיל כדורגל/שוער/כמות ספיגות פנדל',
			args = { ['שחקן'] = player, ['קטגוריית מפעל'] = category } }
		local cleanSheets = games({ ['מספר אירוע'] = '1, 5', ['תוצאה יריבה'] = '0' })
		local penaltySaves = events({ ['מספר אירוע'] = '8', ['תת אירוע'] = '83' })

		table.insert(parts, row('ספיגות', conceded,
			twoDecimals(appearances > 0 and conceded / appearances or 0) ..
			' למשחק, ' .. penaltiesConceded .. ' בפנדל', appearances))
		table.insert(parts, row('שער נקי', cleanSheets,
			percentOf(cleanSheets, appearances) .. '%', appearances))
		table.insert(parts, row('הדיפות פנדלים', penaltySaves,
			percentOf(penaltySaves, appearances) .. '%', appearances))
	end

	local function perGame(value)
		return twoDecimals(appearances > 0 and value / appearances or 0)
	end

	table.insert(parts, row('שערים', goals,
		perGame(goals) .. ' למשחק, ' .. penaltyGoals .. ' בפנדל', appearances))
	table.insert(parts, row('בישולים', assists,
		perGame(assists) .. ' למשחק, ' .. penaltyWon .. ' סחיטות פנדל', appearances))
	table.insert(parts, row('צהובים', yellows, perGame(yellows) .. ' למשחק', appearances))
	table.insert(parts, row('אדומים', reds, perGame(reds) .. ' למשחק', appearances))
	table.insert(parts, row('ניצחונות', wins, percentOf(wins, appearances) .. '%', appearances))
	table.insert(parts, row('תיקו', draws, percentOf(draws, appearances) .. '%', appearances))
	table.insert(parts, row('הפסדים', losses, percentOf(losses, appearances) .. '%', appearances))

	return '<div class="text two-column">' .. table.concat(parts) .. '</div>'
end

return p
