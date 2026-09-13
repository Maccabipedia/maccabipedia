-- יחידה:שיאנים -- טבלאות שיאנים (מובילי כיבושים, בישולים, הופעות וכו').
--
-- מחליפה [[תבנית:סטטיסטיקה/שליפות/מתקדמות/שיאני כמות אירועי שחקן/עיצוב חדש]].
--
-- למה זה שווה: בדף שיאנים טיפוסי (פורטל שחקנים, דף אצטדיון, דף יריבה) יש
-- ארבע תבניות תצוגה, ולכל אחת ארבעה לשוניות; כל לשונית הריצה שתי שליפות --
-- אחת לטבלה ואחת רק כדי לספור כמה שחקנים שונים יש בה. 32 שליפות לדף.
-- p.section מרנדרת תבנית תצוגה שלמה -- ארבע הלשוניות והספירות שלהן --
-- משליפה אחת, ולכן הדף יורד ל-4. כשאין סינון כלל, ארבע השליפות האלה
-- מתאחדות גם הן לאחת דרך [[יחידה:שיאנים/נתונים]] (mw.loadData).
--
-- הפלט זהה ל[[תבנית:סטטיסטיקות/הצגת שיאנים/הצגת שחקן/כדורגל]].
--
-- שינוי מכוון אחד: המיון כאן יציב. התבנית מיינה לפי COUNT(*) בלבד, כך
-- ששחקנים שווי-ניקוד הופיעו בסדר אקראי ושתי טעינות של אותו דף החזירו שמות
-- שונים. כאן שובר-שוויון הוא שם השחקן.

local p = {}

-- ארבע הלשוניות, זהות בכל ארבע תבניות התצוגה.
local TABS = {
	{ id = 'tab1-content', label = 'משחקים רשמיים', category = 'רשמי' },
	{ id = 'tab2-content', label = 'ליגה', category = 'ליגה' },
	{ id = 'tab3-content', label = 'גביע המדינה', category = 'גביע' },
	{ id = 'tab4-content', label = 'בינלאומי', category = 'בינלאומי' },
}

-- סינונים שהיחידה יודעת לתרגם לשליפה. אלה כל הסינונים שתבניות התצוגה
-- מקבלות בפועל: דף קטגוריה/פורטל שולח שחקנים, דף אצטדיון שולח אצטדיונים,
-- דף יריבה שולח יריבות, דף עונה שולח עונה ודף שופט שולח שופטים.
-- היחיד שנשאר בחוץ הוא "עוזר שופט" (דורש צירוף ל-Games_Referees עם HOLDS),
-- ולו יש ממילא תבנית תצוגה נפרדת.
--
-- strip=true היכן שהערך נשמר ב-Cargo בלי גרש וגרשיים. זו אינה בחירה
-- אסתטית: Opponent, Stadium ו-Competition נשמרים מנוקים (בקארגו יש
-- "ביתר ירושלים", לא 'בית"ר ירושלים'), בעוד PlayerName ו-Refs שומרים את
-- הגרש כמו שהוא ("אביעזר ז'נו"). התבנית המקורית עשתה בדיוק את ההבחנה הזו
-- כשעטפה חלק מהרשימות ב[[תבנית:המרות/שם ללא גרש וגרשיים]] ולא את כולן.
local FILTERS = {
	['שחקנים'] = { column = 'Games_Events.PlayerName' },
	['שופטים'] = { column = 'Football_Games.Refs' },
	['עונה'] = { column = 'Football_Games.Season' },
	['אצטדיונים'] = { column = 'Football_Games.Stadium', strip = true },
	['יריבות'] = { column = 'Football_Games.Opponent', strip = true },
	['מפעלים'] = { column = 'Football_Games.Competition', strip = true },
}

--- פיצול רשימה מופרדת בפסיקים לערכים מספריים/קצרים (סוגי אירוע ותתי-אירוע).
local function toSet(csv)
	local set, any = {}, false
	for item in tostring(csv or ''):gmatch('[^,%s]+') do
		set[item] = true
		any = true
	end
	return any and set or nil
end

--- פיצול רשימת שמות. בניגוד ל-toSet שמות מכילים רווחים, ומגיעים בשלושה
--- פורמטים שונים לפי מי שבנה את הרשימה: חשופים, עטופים במרכאות (כך בונה
--- אותם [[תבנית:סטטיסטיקה/שמות דפים מקטגוריה מופרדים לשליפה]]), ולעיתים
--- כשכל הרשימה עטופה בסוגריים (כך מחזירות תבניות ההמרה, שבנו את הרשימה
--- מוכנה לאופרטור IN).
local function toNames(csv, strip)
	local names = {}
	local list = tostring(csv or ''):match('^%s*%((.*)%)%s*$') or csv or ''
	for item in tostring(list):gmatch('[^,]+') do
		local name = item:match('^%s*(.-)%s*$')
		name = name:match("^'(.*)'$") or name:match('^"(.*)"$') or name
		if strip then
			-- גם בקידוד HTML: כך מגיע השם מ-{{PAGENAME}}.
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

--- רשימת ערכים ל-IN, עם בריחה נכונה של גרש. התבנית המקורית פשוט מחקה
--- גרשיים מהשם, מה שלא התאים לערך השמור ב-Cargo.
local function sqlList(names)
	local quoted = {}
	for index, name in ipairs(names) do
		quoted[index] = "'" .. name:gsub("'", "''") .. "'"
	end
	return '(' .. table.concat(quoted, ',') .. ')'
end

--- רשימת ערכים ל-IN מתוך פרמטר מספרי (סוגי אירוע, תתי-אירוע).
local function sqlNumbers(csv)
	local values = {}
	for item in tostring(csv or ''):gmatch('[^,%s]+') do
		table.insert(values, (item:gsub("'", "''")))
	end
	return #values > 0 and ('(' .. table.concat(values, ',') .. ')') or nil
end

--- תנאי הסינון של הדף, כפי שהם נראים ב-SQL. משמשים גם לשליפה עצמה וגם
--- לבניית הקישור "עוד" שמוביל ל-Special:CargoQuery.
local function filterConditions(args)
	local conditions = {}
	for name, filter in pairs(FILTERS) do
		local names = toNames(args[name], filter.strip)
		if names then
			table.insert(conditions, filter.column .. ' IN ' .. sqlList(names))
		end
	end
	table.sort(conditions)  -- סדר יציב, כדי שהקישור "עוד" ייראה זהה בכל טעינה
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
	if category == 'רשמי' then return true end  -- הנתונים כבר מסוננים ל-Official
	if category == 'יתר רשמי' or category == 'יתר-רשמיים' then
		return row.league ~= '1' and row.trophy ~= '1' and row.intl ~= '1'
	end
	return true
end

--- כל ספירות האירועים לכל שחקן, תחת הסינון שהדף מבקש. שליפה אחת.
--- ללא סינון -- דרך mw.loadData, כך שכל הטבלאות בדף חולקות אותה.
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
			limit = 20000,
		}) or {}
end

--- סכימת האירועים לכל שחקן מתוך שורות שכבר נשלפו.
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
		return a.player < b.player  -- שובר שוויון יציב
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

--- הקישור "עוד" שמתחת לטבלה. השליפה בנתה אותו בעצמה כשקיבלה
--- |more results text=, וכאן הוא נבנה מאותם תנאים בדיוק כדי ששום דף לא יאבד
--- אותו. הוא מוביל לשליפה המלאה - כל השחקנים, לא רק העשרה הראשונים.
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
	-- קישור חיצוני בתחביר ויקי, לא <a>: פלט של #invoke עובר ניתוח ויקיטקסט,
	-- ותגית <a> גולמית הייתה מוברחת. השליפה עצמה יכלה לפלוט HTML ישירות.
	return '[' .. tostring(url) .. ' ' .. text .. ']'
end

local function renderTop(list, limit)
	local parts = {}
	for index = 1, math.min(limit, #list) do
		table.insert(parts, playerRow(list[index].player, list[index].count))
	end
	return table.concat(parts)
end

--- טבלת שיאנים בודדת (נשארת בשימוש קריאות שמבקשות לשונית אחת בלבד).
--- פרמטרים: מספר אירוע, תת אירוע, ללא תת אירוע, קטגוריית מפעל, הגבלה
function p.top(frame)
	local args = frame.args
	local limit = tonumber(args['הגבלה']) or 10
	local rows = fetchRows(args)
	return renderTop(sorted(totals(rows, args, args['קטגוריית מפעל'])), limit)
end

--- מספר השחקנים השונים שעונים על הסינון (ל"כובשים שונים" וכד').
function p.distinctPlayers(frame)
	local args = frame.args
	local count = 0
	for _ in pairs(totals(fetchRows(args), args, args['קטגוריית מפעל'])) do
		count = count + 1
	end
	return count
end

--- גוש שיאנים שלם: ארבע הלשוניות והספירות שלהן, משליפה אחת.
--- פרמטרים: כינוי (למשל "כובשים שונים"), מספר אירוע, תת אירוע,
--- ללא תת אירוע, הגבלה, ואחד מסינוני FILTERS.
function p.section(frame)
	local args = frame.args
	local limit = tonumber(args['הגבלה']) or 10
	local noun = args['כינוי'] or 'שחקנים שונים'
	local rows = fetchRows(args)

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
