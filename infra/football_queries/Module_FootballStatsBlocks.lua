--[[
Module:FootballStatsBlocks - what a statistics block is made of, as data.

Wiki page: Module:FootballStatsBlocks

Read with mw.loadData, so it is parsed once per page however many blocks
render. No functions and no metatables: `format` is the NAME of a formatter
that lives in the renderer, because a loadData page cannot hold one.

Separating the cells from the rendering is what lets the harness check 32 cell
definitions without rendering anything - and a merged block gets a cell's
filter wrong far more easily than it gets the HTML wrong.

Cells are the numbers to fetch. Rows are what the block displays; they are not
one-to-one, because one row can show several cells (appearances with
substitutions in brackets) and some show a value derived from others.

`grain` says whether a cell counts events or games. Omitted means events.
Getting it wrong multiplies a count by the number of events on the page, so it
is declared per cell rather than inferred.
]]

return {
	-- תבנית:סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים לפי מפעל
	['player-events'] = {
		-- The four competition categories the parent template renders as tabs.
		-- They overlap - רשמי is a superset of the other three - so they cannot
		-- be produced by GROUP BY, only by conditional aggregates.
		tabs = { 'ליגה', 'גביע', 'בינלאומי', 'רשמי' },

		cells = {
			{ name = 'appearances', filters = { ['מספר אירוע'] = '1,5' } },
			{ name = 'substitutions', filters = { ['מספר אירוע'] = '5' } },
			{ name = 'goals', filters = { ['מספר אירוע'] = '3' } },
			{ name = 'penaltyGoals',
			  filters = { ['מספר אירוע'] = '3', ['תת אירוע'] = '35' } },
			{ name = 'assists', filters = { ['מספר אירוע'] = '4' } },
			{ name = 'yellows',
			  filters = { ['מספר אירוע'] = '7', ['תת אירוע'] = '71' } },
			{ name = 'reds',
			  filters = { ['מספר אירוע'] = '7', ['תת אירוע'] = '72,73' } },
			{ name = 'benchStarts', filters = { ['מספר אירוע'] = '2' } },
		},

		-- The rows, in the order the template emits them. `format` names a
		-- formatter in Module:FootballPlayerEvents.
		rows = {
			{ label = 'הופעות', format = 'appearancesWithSubstitutions' },
			{ label = 'שערים', format = 'goalsWithRatio' },
			{ label = 'בישולים', format = 'plain', cell = 'assists' },
			{ label = 'צהובים', format = 'plain', cell = 'yellows' },
			{ label = 'אדומים', format = 'plain', cell = 'reds' },
			{ label = 'פתח בספסל', format = 'benchStartsWithBenchings' },
		},
	},
}
