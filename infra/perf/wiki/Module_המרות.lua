-- יחידה:המרות -- רשימות שמות מקושרים (אצטדיונים, יריבות).
--
-- מחליפה שליפת קארגו נפרדת לכל חיפוש. הנתונים נטענים דרך
-- [[יחידה:המרות/נתונים]] עם mw.loadData, כך שכל החיפושים בדף חולקים שליפה
-- אחת - גם כשהם מגיעים מקריאות #invoke נפרדות.
--
-- הפלט זהה לתבניות המקוריות: רשימה מופרדת בפסיקים, כל שם במרכאות, מוכנה
-- לשימוש בתוך IN (...) בשליפת קארגו.

local p = {}

local function quotedList(names)
	if not names then
		return ''
	end
	local quoted = {}
	for _, name in ipairs(names) do
		table.insert(quoted, '"' .. name .. '"')
	end
	return table.concat(quoted, ',  ')
end

--- כל שמות האצטדיון השייכים לאותו דף אצטדיון.
--- מחליפה [[תבנית:המרות/המרות אצטדיון/אצטדיון לרשימת אצטדיונים מקושרים]].
function p.stadiumAliases(frame)
	local name = tostring(frame.args['אצטדיון'] or '')
	if name == '' then
		return ''
	end
	local data = mw.loadData('יחידה:המרות/נתונים')
	local pageId = data.stadiumPageOfName[name]
	if not pageId then
		return ''
	end
	return quotedList(data.stadiumsByPage[pageId])
end

--- כל שמות היריבה החולקים את אותו שם קנוני.
--- מחליפה [[תבנית:המרות/המרות יריבה/יריבה לרשימת יריבות מקושרות]].
function p.opponentAliases(frame)
	local name = tostring(frame.args['יריבה'] or '')
	if name == '' then
		return ''
	end
	local data = mw.loadData('יחידה:המרות/נתונים')
	local canonical = data.opponentCanonicalOf[name]
	if not canonical then
		return ''
	end
	return quotedList(data.opponentsByCanonical[canonical])
end

return p
