-- יחידה:שיאנים -- טבלאות שיאנים (מובילי כיבושים, בישולים, הופעות וכו').
--
-- מחליפה [[תבנית:סטטיסטיקה/שליפות/מתקדמות/שיאני כמות אירועי שחקן/עיצוב חדש]]
-- בקריאות שמגיעות מדפי קטגוריה ומפורטל השחקנים. כל הטבלאות בדף חולקות שליפה
-- אחת דרך [[יחידה:שיאנים/נתונים]] (mw.loadData).
--
-- הפלט זהה ל[[תבנית:סטטיסטיקות/הצגת שיאנים/הצגת שחקן/כדורגל]].
--
-- שינוי מכוון אחד: המיון כאן יציב. התבנית מיינה לפי COUNT(*) בלבד, כך
-- ששחקנים שווי-ניקוד הופיעו בסדר אקראי ושתי טעינות של אותו דף החזירו שמות
-- שונים. כאן שובר-שוויון הוא שם השחקן.

local p = {}

local function toSet(csv)
	local set, any = {}, false
	for item in tostring(csv or ''):gmatch('[^,%s]+') do
		set[item] = true
		any = true
	end
	return any and set or nil
end

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

--- סכימת האירועים לכל שחקן לפי הסינון שהתקבל.
local function totals(args)
	local wantEvents = toSet(args['מספר אירוע'])
	local wantSubs = toSet(args['תת אירוע'])
	local excludeSubs = toSet(args['ללא תת אירוע'])
	local category = args['קטגוריית מפעל']

	local byPlayer = {}
	for _, row in ipairs(mw.loadData('יחידה:שיאנים/נתונים')) do
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
	local name = mw.title.new(player) and mw.title.new(player).exists
		and ('[[' .. player .. '|' .. player .. ']]') or player
	return '<div class="atom-records-list-player-row">' ..
	       '<span class="player-name">\n' .. name .. '</span>' ..
	       '<div class="atom-recors-list-player-info">' ..
	       '<span class="record">' .. mw.getContentLanguage():formatNum(count) ..
	       '</span></div>\n</div>\n'
end

--- טבלת שיאנים.
--- פרמטרים: מספר אירוע, תת אירוע, ללא תת אירוע, קטגוריית מפעל, הגבלה
function p.top(frame)
	local args = frame.args
	local limit = tonumber(args['הגבלה']) or 10
	local list = sorted(totals(args))

	local parts = {}
	for index = 1, math.min(limit, #list) do
		table.insert(parts, playerRow(list[index].player, list[index].count))
	end
	return table.concat(parts)
end

--- מספר השחקנים השונים שעונים על הסינון (ל"כובשים שונים" וכד').
function p.distinctPlayers(frame)
	local count = 0
	for _ in pairs(totals(frame.args)) do
		count = count + 1
	end
	return count
end

return p
