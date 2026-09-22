--[[
Module:BasketballStatsBlocks - basketball's block declarations for Module:StatsBlock.

Wiki page: Module:BasketballStatsBlocks

Read with mw.loadData by Module:BasketballStatsBlock. No functions, no metatables.

`leaderboards` is the one block so far: the eight statistics the box templates
(כדורסל/סטטיסטיקה/שיאני נקודות …) ask for through כדורסל/סטטיסטיקה/שיאנים לפי
אירוע, whose body is now
    {{#invoke:BasketballStatsBlock|leaderboardTab|בלוק=leaderboards|תיבה={{{אירוע}}}|…}}
The box templates keep their signed <shtml> tab strips; the module fills the
tabs. Everything a tab prints mirrors the old query template (2026-09-23):
the row template with named args, `לא נמצאו שיאנים להצגה` for an empty tab,
Cargo's "עוד..." link when the rows reach the limit, and players with a zero
kept (the template had no HAVING).
]]

return {
	['leaderboards'] = {
		groupBy = 'player',
		rowTemplate = 'כדורסל/סטטיסטיקה/כמות משחקים/הצגת שחקן',
		-- Cargo's format=template passed the fields as named arguments.
		rowArgs = { 'PlayerName', 'Record' },
		emptyText = 'לא נמצאו שיאנים להצגה',
		moreText = 'עוד...',
		keepZero = true,
		-- Every value of קטגוריית מפעל a caller may pass (the schema's choices).
		-- The first call primes each box in each of these from one query.
		categories = { 'רשמי', 'ליגה', 'גביע', 'בינלאומי', 'יתר-רשמיים', 'ברירת מחדל' },
		-- `word` is the template's אירוע value; `sum` the schema's summable value.
		boxes = {
			{ key = 'appearances', word = 'הופעות', sum = 'הופעות', filters = {} },
			{ key = 'points', word = 'נקודות', sum = 'נקודות', filters = {} },
			{ key = 'assists', word = 'אסיסטים', sum = 'אסיסטים', filters = {} },
			{ key = 'rebounds', word = 'ריבאונדים', sum = 'ריבאונדים', filters = {} },
			{ key = 'blocks', word = 'חסימות', sum = 'חסימות', filters = {} },
			{ key = 'steals', word = 'חטיפות', sum = 'חטיפות', filters = {} },
			{ key = 'turnovers', word = 'איבודים', sum = 'איבודים', filters = {} },
			{ key = 'fouls', word = 'עבירות', sum = 'עבירות', filters = {} },
		},
	},
}
