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
	-- The numbers behind כדורסל/סטטיסטיקה/סך אירועים: eight per category, one query
	-- template call each on 475 pages (32 per season or opponent page). Its body is now
	--   {{#invoke:BasketballStatsBlock|cell|בלוק=numbers|תא={{{אירוע}}}|קטגוריית מפעל=…|…}}
	-- Points are a GAME column - a team's total for the game, or the opponent's when
	-- עבור יריבה is given - and cannot share a query with the per-player sums (the
	-- join would multiply them), so the block primes with two queries, not one.
	-- The template printed COALESCE(…, 0) with default=0: a plain integer, 0 for nothing.
	['numbers'] = {
		categories = { 'רשמי', 'ליגה', 'גביע', 'בינלאומי', 'יתר-רשמיים', 'ברירת מחדל' },
		primeCategories = { 'רשמי', 'ליגה', 'גביע', 'בינלאומי' },
		sideFilter = 'עבור יריבה',
		nullValue = '0',
		cells = {
			{ key = 'points', word = 'נקודות', grain = 'game',
			  sides = { maccabi = 'נקודות קבוצה', opponent = 'נקודות יריבה' }, filters = {} },
			{ key = 'assists', word = 'אסיסטים', grain = 'event', sum = 'אסיסטים', filters = {} },
			{ key = 'rebounds', word = 'ריבאונדים', grain = 'event', sum = 'ריבאונדים', filters = {} },
			{ key = 'blocks', word = 'חסימות', grain = 'event', sum = 'חסימות', filters = {} },
			{ key = 'steals', word = 'חטיפות', grain = 'event', sum = 'חטיפות', filters = {} },
			{ key = 'turnovers', word = 'איבודים', grain = 'event', sum = 'איבודים', filters = {} },
			{ key = 'fouls', word = 'עבירות', grain = 'event', sum = 'עבירות', filters = {} },
		},
	},
	-- The counts behind כדורסל/סטטיסטיקה/כמות משחקים: games, wins, losses per category -
	-- its body is now
	--   {{#invoke:BasketballStatsBlock|cell|בלוק=games|תא=<משחקים|ניצחונות|הפסדים>|…}}
	-- with the wrapper turning the template's תוצאה into the cell (any word but הפסד
	-- meant a win there, as in the template's #בחר). A block of its own, apart from
	-- `numbers`: its callers include the player pages' captain check, whose filter
	-- reaches the per-player table - fine for a count, refused for a team-points sum.
	-- Game grain: COUNT(DISTINCT game), as the template's COUNT(DISTINCT bg._pageName).
	['games'] = {
		categories = { 'רשמי', 'ליגה', 'גביע', 'בינלאומי', 'יתר-רשמיים', 'ברירת מחדל' },
		primeCategories = { 'רשמי', 'ליגה', 'גביע', 'בינלאומי' },
		nullValue = '0',
		cells = {
			{ key = 'games', word = 'משחקים', grain = 'game', filters = {} },
			{ key = 'wins', word = 'ניצחונות', grain = 'game', filters = { ['תוצאה'] = 'ניצחון' } },
			{ key = 'losses', word = 'הפסדים', grain = 'game', filters = { ['תוצאה'] = 'הפסד' } },
		},
	},
	['leaderboards'] = {
		groupBy = 'player',
		rowTemplate = 'כדורסל/סטטיסטיקה/כמות משחקים/הצגת שחקן',
		-- Cargo's format=template passed the fields as named arguments.
		rowArgs = { 'PlayerName', 'Record' },
		emptyText = 'לא נמצאו שיאנים להצגה',
		moreText = 'עוד...',
		keepZero = true,
		-- Every value of קטגוריית מפעל a caller may pass (the schema's choices).
		categories = { 'רשמי', 'ליגה', 'גביע', 'בינלאומי', 'יתר-רשמיים', 'ברירת מחדל' },
		-- The four the box templates' tab strips show: the first call primes each
		-- box in each of these from one query (32 sums, ~0.55 s over 57k rows,
		-- measured); the other two are primed on their own when a page asks.
		primeCategories = { 'רשמי', 'ליגה', 'גביע', 'בינלאומי' },
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
