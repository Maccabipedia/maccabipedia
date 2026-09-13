-- יחידה:המרות/נתונים -- טבלאות המרה, נטענות פעם אחת לכל דף.
--
-- זו יחידת נתונים: היא מוחזרת כטבלה פשוטה ונטענת דרך mw.loadData.
-- זה הרכיב היחיד ב-Scribunto ששומר מצב בין קריאות #invoke - משתנה מקומי
-- ביחידה רגילה נבנה מחדש בכל קריאה, ולכן "מטמון" כזה לא מועיל כלל.
--
-- נמדד (2026-09-13) על 60 קריאות: דרך mw.loadData 0.051 שניות מעבד,
-- דרך מטמון ביחידה רגילה 0.9 שניות. השליפה כאן רצה פעם אחת.
--
-- שימוש:
--   local data = mw.loadData('יחידה:המרות/נתונים')
--   data.stadiumsByPage[pageId]      -- כל שמות האצטדיון באותו דף
--   data.stadiumPageOfName[name]     -- מזהה הדף של שם אצטדיון
--   data.opponentsByCanonical[name]  -- כל שמות היריבה תחת אותו שם קנוני
--   data.opponentCanonicalOf[name]   -- השם הקנוני של שם יריבה

local function stadiums()
	local rows = mw.ext.cargo.query(
		'Stadiums',
		'Stadiums._pageID=pageId,Stadiums.CanonicalName=name',
		{ limit = 5000 }) or {}
	local byPage, pageOfName = {}, {}
	for _, row in ipairs(rows) do
		if row.name and row.name ~= '' then
			byPage[row.pageId] = byPage[row.pageId] or {}
			table.insert(byPage[row.pageId], row.name)
			pageOfName[row.name] = row.pageId
		end
	end
	return byPage, pageOfName
end

local function opponents()
	local rows = mw.ext.cargo.query(
		'Opponents',
		'Opponents.OriginalName=original,Opponents.CanonicalName=canonical',
		{ limit = 5000 }) or {}
	local byCanonical, canonicalOf = {}, {}
	for _, row in ipairs(rows) do
		if row.original and row.original ~= '' then
			local canonical = row.canonical or row.original
			byCanonical[canonical] = byCanonical[canonical] or {}
			table.insert(byCanonical[canonical], row.original)
			canonicalOf[row.original] = canonical
		end
	end
	return byCanonical, canonicalOf
end

local stadiumsByPage, stadiumPageOfName = stadiums()
local opponentsByCanonical, opponentCanonicalOf = opponents()

return {
	stadiumsByPage = stadiumsByPage,
	stadiumPageOfName = stadiumPageOfName,
	opponentsByCanonical = opponentsByCanonical,
	opponentCanonicalOf = opponentCanonicalOf,
}
