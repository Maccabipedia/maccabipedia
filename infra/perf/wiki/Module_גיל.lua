-- יחידה:גיל -- גיל במועד נתון, ברירת המחדל היא היום.
--
-- למה Lua ולא {{שנה נוכחית}}?
-- מילות הקסם CURRENTYEAR/CURRENTMONTH/CURRENTDAY מסמנות לתוכנה שהדף תלוי-זמן,
-- ולכן מדיה-ויקי מקצרת את מטמון המפענח לשעה אחת בלבד. גיל משתנה פעם בשנה,
-- כך שדף שנשמר במטמון ליממה מספיק לחלוטין - וכך הוא נבנה מחדש פי 24 פחות.
-- קריאה ל-os.date מתוך Lua לא מסמנת תלות-זמן, ולכן המטמון נשאר מלא.
--
-- הערה: כשנשלח תאריך ייחוס מפורש (פרמטרים 4-6, למשל תאריך פטירה) אין כאן
-- תלות בזמן בכלל - החישוב דטרמיניסטי לגמרי.

local p = {}

--- גיל בשנים שלמות.
--- פרמטרים 1-3: שנה, חודש, יום של הלידה.
--- פרמטרים 4-6 (רשות): תאריך הייחוס. ללא הם - היום.
function p.age(frame)
	local args = frame.args
	local birthYear = tonumber(args[1])
	local birthMonth = tonumber(args[2])
	local birthDay = tonumber(args[3])
	if not (birthYear and birthMonth and birthDay) then
		return ''
	end

	local today = os.date('*t')
	local refYear = tonumber(args[4]) or today.year
	local refMonth = tonumber(args[5]) or today.month
	local refDay = tonumber(args[6]) or today.day

	local years = refYear - birthYear
	-- טרם חלף יום ההולדת בשנת הייחוס
	if refMonth < birthMonth
		or (refMonth == birthMonth and refDay < birthDay) then
		years = years - 1
	end
	return years
end

return p
