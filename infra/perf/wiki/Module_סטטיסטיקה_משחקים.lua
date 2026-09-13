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
	['עונה'] = true, ['יריבות'] = true, ['קטגוריית מפעל'] = true,
	['תוצאה'] = true, ['תוצאה יריבה'] = true, ['תוצאה מכבי'] = true,
	['נתון משחק'] = true,
}

local RESULT_TO_OPT = { ['ניצחון'] = '1', ['תיקו'] = '2', ['הפסד'] = '3' }

local function sanitize(value)
	return (tostring(value or ''):gsub('["\\]', ''))
end

--- רשימת יריבות ל-IN. Opponent נשמר ב-Cargo בלי גרש וגרשיים
--- (יש בו "ביתר ירושלים"), ולכן גם כאן צריך לנקות לפני ההשוואה.
local function opponentList(csv)
	local quoted = {}
	local list = tostring(csv or ''):match('^%s*%((.*)%)%s*$') or csv or ''
	for item in tostring(list):gmatch('[^,]+') do
		local name = item:match('^%s*(.-)%s*$')
		name = name:match("^'(.*)'$") or name:match('^"(.*)"$') or name
		name = name:gsub('&#34;', ''):gsub('&quot;', '')
		           :gsub('&#39;', ''):gsub('&apos;', '')
		           :gsub("'", ''):gsub('"', '')
		if name ~= '' then
			table.insert(quoted, "'" .. name .. "'")
		end
	end
	return #quoted > 0 and ('(' .. table.concat(quoted, ',') .. ')') or nil
end

--- תנאי ה-WHERE של הדף: עונה (דף עונה) או יריבות (דף יריבה).
local function pageConditions(args)
	local conditions = {}
	local season = args['עונה']
	if season and season ~= '' then
		table.insert(conditions,
			'Football_Games.Season="' .. sanitize(season) .. '"')
	end
	local opponents = opponentList(args['יריבות'])
	if opponents then
		table.insert(conditions, 'Football_Games.Opponent IN ' .. opponents)
	end
	return conditions
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

--- שליפה אחת לסינון הדף, מקובצת לפי כל הממדים שהתבנית מסננת לפיהם.
local function fetchGames(args)
	local conditions = pageConditions(args)
	local key = table.concat(conditions, ' AND ')
	if cache[key] then
		return cache[key]
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
	for _, row in ipairs(fetchGames(args)) do
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

-- ==========================================================================
-- גוש "מספרים כלליים": ארבע לשוניות, תשע שורות בכל אחת, בשתי שליפות.
--
-- דף יריבה ודף עונה מציגים את אותו גוש בדיוק, ושניהם בנו אותו כך: שש
-- קריאות ל[[תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות נתוני משחק]] ועוד שתיים
-- ל[[תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות אירועי שחקן]] לכל קטגוריית מפעל --
-- 32 שליפות לדף. כאן: שליפה אחת למשחקים, אחת לכרטיסים, וכל 36 המספרים
-- מחושבים מהן.
-- ==========================================================================

local TABS = {
	{ id = 'tab1-content', label = 'משחקים רשמיים', category = 'רשמי' },
	{ id = 'tab2-content', label = 'ליגה', category = 'ליגה' },
	{ id = 'tab3-content', label = 'גביע', category = 'גביע' },
	{ id = 'tab4-content', label = 'בינלאומי', category = 'בינלאומי' },
}

local YELLOW, REDS = '71', { ['72'] = true, ['73'] = true }

--- כרטיסים של מכבי, מקובצים לפי אותם ממדים כמו שליפת המשחקים.
local function fetchCards(args)
	local conditions = pageConditions(args)
	table.insert(conditions, 'Games_Events.Team=1')
	table.insert(conditions, 'Games_Events.SubType IN (71,72,73)')
	return cargo.query(
		'Football_Games,Games_Events,Competitions',
		table.concat({
			'Competitions.League=league',
			'Competitions.Trophy=trophy',
			'Competitions.International=intl',
			'Competitions.Official=official',
			'Games_Events.SubType=subType',
			'COUNT(*)=n',
		}, ','),
		{
			join = 'Football_Games._pageID=Games_Events._pageID,' ..
			       'Football_Games.Competition=Competitions.OriginalName',
			where = table.concat(conditions, ' AND '),
			groupBy = 'Competitions.League,Competitions.Trophy,' ..
			          'Competitions.International,Competitions.Official,' ..
			          'Games_Events.SubType',
			limit = 20000,
		}) or {}
end

--- עיגול כלפי מעלה בחצי, כמו #expr ו-#number_format. string.format ב-Lua
--- מעגל חצי לזוגי, ולכן 0.125 היה הופך ל-0.12 במקום ל-0.13.
local function roundTo(value, places)
	local factor = 10 ^ places
	return math.floor(value * factor + 0.5) / factor
end

local function decimals(value, places)
	return string.format('%.' .. places .. 'f', roundTo(value, places))
end

--- אחוז, בדיוק כמו [[תבנית:סטטיסטיקה/אחוזים]] ואחריה #number_format:
--- קודם עיגול לשתי ספרות, ואז לפי הדיוק המבוקש.
local function percent(part, whole, places)
	if whole == 0 then return '0' end
	local value = roundTo(part / whole * 100, 2)
	if places == 0 then
		return mw.getContentLanguage():formatNum(roundTo(value, 0))
	end
	return decimals(value, places)
end

local function statRow(label, value, note)
	local shown = mw.getContentLanguage():formatNum(value)
	local small = (value > 0 and note) and
		(' <span class="small">' .. note .. '</span>') or ''
	return table.concat({
		'<div>\n<span class="describe">', label, '</span>\n',
		'<span class="info">', shown, small, '</span>\n</div>',
	})
end

--- גוש המספרים של קטגוריית מפעל אחת, מתוך שורות שכבר נשלפו.
local function numbersList(games, cards, category)
	local total = { wins = 0, draws = 0, losses = 0, scored = 0,
	                conceded = 0, cleanSheets = 0, yellow = 0, red = 0 }
	for _, row in ipairs(games) do
		if matchesCategory(row, category) then
			local count = tonumber(row.games) or 0
			if row.resultOpt == '1' then total.wins = total.wins + count
			elseif row.resultOpt == '2' then total.draws = total.draws + count
			elseif row.resultOpt == '3' then total.losses = total.losses + count
			end
			total.scored = total.scored + (tonumber(row.scored) or 0) * count
			total.conceded = total.conceded + (tonumber(row.conceded) or 0) * count
			if row.conceded == '0' then
				total.cleanSheets = total.cleanSheets + count
			end
		end
	end
	for _, row in ipairs(cards) do
		if matchesCategory(row, category) then
			local count = tonumber(row.n) or 0
			if row.subType == YELLOW then total.yellow = total.yellow + count
			elseif REDS[row.subType] then total.red = total.red + count
			end
		end
	end

	local played = total.wins + total.draws + total.losses
	local perGame = function(value)
		return played > 0 and (decimals(value / played, 2) .. ' למשחק') or nil
	end

	return '<div class="general-stats-list">\n' .. table.concat({
		statRow('משחקים', played),
		statRow('ניצחונות', total.wins, percent(total.wins, played, 0) .. '%'),
		statRow('תיקו', total.draws, percent(total.draws, played, 0) .. '%'),
		statRow('הפסדים', total.losses, percent(total.losses, played, 0) .. '%'),
		statRow('שערים', total.scored, perGame(total.scored)),
		statRow('ספיגות', total.conceded, perGame(total.conceded)),
		statRow('שער נקי', total.cleanSheets,
		        percent(total.cleanSheets, played, 2) .. '%'),
		statRow('צהובים', total.yellow, perGame(total.yellow)),
		statRow('אדומים', total.red, perGame(total.red)),
	}, '<!--\n\n-->') .. '\n</div>'
end

--- ארבע הלשוניות של גוש המספרים הכלליים. פרמטרים: עונה או יריבות.
function p.numbersBlock(frame)
	local args = frame.args
	local games = fetchGames(args)
	local cards = fetchCards(args)

	local parts = {}
	for _, tab in ipairs(TABS) do
		table.insert(parts, table.concat({
			'<div id="', tab.id, '"><div class="tab-header">', tab.label,
			'</div>\n', numbersList(games, cards, tab.category), '</div>',
		}))
	end
	return table.concat(parts, '\n')
end

return p
