-- יחידה:סטטיסטיקה משחקים -- מספרים מצטברים ברמת המשחק.
--
-- מחליפה קריאות חוזרות ל[[תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות נתוני משחק]].
-- עמוד עונה קורא לה 6 פעמים לכל קטגוריית מפעל (ניצחונות, תיקו, הפסדים,
-- כיבושים, ספיגות, שער נקי) - 24 שליפות בסך הכל. כאן נעשית שליפה אחת
-- המקובצת לפי כל הממדים הרלוונטיים, וכל המספרים מחושבים ממנה בזיכרון.

local p = {}
local cargo = mw.ext.cargo

local cache = {}

-- כל פרמטר שהתבנית המקורית מקבלת. פרמטר לא מוכר יחזיר שגיאה גלויה במקום
-- מספר שגוי שנראה סביר.
local SUPPORTED = {
	['עונה'] = true, ['קטגוריית מפעל'] = true, ['תוצאה'] = true,
	['תוצאה יריבה'] = true, ['תוצאה מכבי'] = true, ['נתון משחק'] = true,
}

local RESULT_TO_OPT = { ['ניצחון'] = '1', ['תיקו'] = '2', ['הפסד'] = '3' }

local function sanitize(value)
	return (tostring(value or ''):gsub('["\\]', ''))
end

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

--- שליפה אחת לעונה, מקובצת לפי כל הממדים שהתבנית מסננת לפיהם.
local function fetchGames(season)
	local key = season or ''
	if cache[key] then
		return cache[key]
	end
	local conditions = {}
	if season and season ~= '' then
		table.insert(conditions, 'Football_Games.Season="' .. sanitize(season) .. '"')
	end
	cache[key] = cargo.query(
		'Football_Games,Competitions',
		table.concat({
			'Competitions.League=league',
			'Competitions.Trophy=trophy',
			'Competitions.International=intl',
			'Competitions.Official=official',
			'Football_Games.ResultOpt=resultOpt',
			'Football_Games.ResultMaccabi=scored',
			'Football_Games.ResultOpponent=conceded',
			'COUNT(*)=games',
		}, ','),
		{
			join = 'Football_Games.Competition=Competitions.OriginalName',
			where = #conditions > 0 and table.concat(conditions, ' AND ') or nil,
			groupBy = 'Competitions.League,Competitions.Trophy,' ..
			          'Competitions.International,Competitions.Official,' ..
			          'Football_Games.ResultOpt,Football_Games.ResultMaccabi,' ..
			          'Football_Games.ResultOpponent',
			limit = 20000,
		}
	) or {}
	return cache[key]
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

--- מספר משחקים, שערים או ספיגות לפי הסינון שהתקבל.
--- נתון משחק: "כיבושים" לשערים, "ספיגות" לספיגות, ריק לספירת משחקים.
function p.gameStat(frame)
	local args = frame.args
	local unknown = unsupportedArgs(args)
	if #unknown > 0 then
		return 'יחידה:סטטיסטיקה משחקים — פרמטר לא נתמך: ' ..
		       table.concat(unknown, ', ')
	end

	local measure = args['נתון משחק'] or ''
	local wantResult = RESULT_TO_OPT[args['תוצאה'] or '']
	local wantConceded = args['תוצאה יריבה']
	local wantScored = args['תוצאה מכבי']
	local category = args['קטגוריית מפעל']

	local total = 0
	for _, row in ipairs(fetchGames(args['עונה'])) do
		local ok = matchesCategory(row, category)
		if ok and wantResult and row.resultOpt ~= wantResult then ok = false end
		if ok and wantConceded and wantConceded ~= ''
			and row.conceded ~= wantConceded then ok = false end
		if ok and wantScored and wantScored ~= ''
			and row.scored ~= wantScored then ok = false end
		if ok then
			local games = tonumber(row.games) or 0
			if measure == 'כיבושים' then
				total = total + (tonumber(row.scored) or 0) * games
			elseif measure == 'ספיגות' then
				total = total + (tonumber(row.conceded) or 0) * games
			else
				total = total + games
			end
		end
	end
	return total
end

return p
