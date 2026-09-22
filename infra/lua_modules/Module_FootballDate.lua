--[=[
Module:FootballDate - a game's date as the games lists show it, without #time.

Wiki page: Module:FootballDate

תבנית:המרות/המרות תאריך/תאריך מלא לפורמט הצגה formats a date with
    {{#time:[[d "ב"F|j "ב"F]] [[Y]]| date }}
ParserFunctions allows one page ~6000 bytes of #time format strings, about 240
of these; past that every date on the page becomes "יותר מדי קריאות ל#זמן".
הפועל תל אביב's all-games list has 242 games. This builds the same text from
the date's digits and a month table, so no page runs out.

    {{#invoke:FootballDate|full|{{{Date|}}}}}

Only a plain YYYY-MM-DD (every Football_Games.Date) is built here. Anything
else - an empty value included - goes through the template exactly as before.
]=]

local p = {}

local MONTHS = {
	'ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
	'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר',
}

local TEMPLATE = 'המרות/המרות תאריך/תאריך מלא לפורמט הצגה'

function p.full(frame)
	local date = mw.text.trim(frame.args[1] or '')
	local year, month, day = date:match('^(%d%d%d%d)%-(%d%d)%-(%d%d)$')
	local monthName = month and MONTHS[tonumber(month)]
	if not monthName or tonumber(day) < 1 or tonumber(day) > 31 then
		return frame:expandTemplate({ title = TEMPLATE, args = { ['תאריך'] = date } })
	end
	return string.format('[[%s ב%s|%d ב%s]] [[%s]]', day, monthName, tonumber(day), monthName, year)
end

return p
