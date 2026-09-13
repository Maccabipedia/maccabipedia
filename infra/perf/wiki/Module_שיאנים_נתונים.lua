-- יחידה:שיאנים/נתונים -- ספירות אירועים לכל שחקן, בשליפה אחת לכל הדף.
--
-- יחידת נתונים הנטענת דרך mw.loadData, ולכן השליפה רצה פעם אחת בלבד גם אם
-- יש בדף עשרות טבלאות שיאנים. משתנה מקומי ביחידה רגילה לא היה עוזר - מצב
-- של יחידה אינו נשמר בין קריאות #invoke.
--
-- עמוד שיאנים טיפוסי (פורטל שחקנים) הריץ 32 שליפות נפרדות; כאן אחת.

local rows = mw.ext.cargo.query(
	'Football_Games,Games_Events,Competitions',
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
		join = 'Football_Games._pageID=Games_Events._pageID,' ..
		       'Football_Games.Competition=Competitions.OriginalName',
		where = 'Games_Events.Team=1 AND Competitions.Official=1 ' ..
		        "AND Games_Events.PlayerName IS NOT NULL " ..
		        "AND Games_Events.PlayerName != ''",
		groupBy = 'Games_Events.PlayerName,Games_Events.EventType,' ..
		          'Games_Events.SubType,Competitions.League,' ..
		          'Competitions.Trophy,Competitions.International',
		-- חייב להישאר זהה ל-ROW_LIMIT ב[[יחידה:שיאנים]], שבודקת קטיעה.
		limit = 20000,
	}) or {}

-- mw.loadData מחזירה טבלה פשוטה בלבד: ללא פונקציות וללא מטא-טבלאות.
local out = {}
for index, row in ipairs(rows) do
	out[index] = {
		player = row.player,
		eventType = row.eventType,
		subType = row.subType,
		league = row.league,
		trophy = row.trophy,
		intl = row.intl,
		n = tonumber(row.n) or 0,
	}
end
return out
