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

`grain` says whether a cell counts events or games, and it is REQUIRED - an
omitted grain raises rather than defaulting. Guessing "event" would multiply a
game count by the number of events on the page, up to 43x, and the result looks
like a plausible number.
]]

return {
	-- תבנית:סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים לפי מפעל
	['player-events'] = {
		-- The parameter that identifies WHAT the block is about, and therefore
		-- keys its page variables: a player here, a date in day-results.
		entity = 'שחקן',
		layout = 'inline',

		-- The four competition categories the parent template renders as tabs.
		-- They overlap - רשמי is a superset of the other three - so they cannot
		-- be produced by GROUP BY, only by conditional aggregates.
		tabs = { 'ליגה', 'גביע', 'בינלאומי', 'רשמי' },

		cells = {
			{ name = 'appearances', grain = 'event',
			  filters = { ['מספר אירוע'] = '1,5' } },
			{ name = 'substitutions', grain = 'event',
			  filters = { ['מספר אירוע'] = '5' } },
			{ name = 'goals', grain = 'event',
			  filters = { ['מספר אירוע'] = '3' } },
			{ name = 'penaltyGoals', grain = 'event',
			  filters = { ['מספר אירוע'] = '3', ['תת אירוע'] = '35' } },
			{ name = 'assists', grain = 'event',
			  filters = { ['מספר אירוע'] = '4' } },
			{ name = 'yellows', grain = 'event',
			  filters = { ['מספר אירוע'] = '7', ['תת אירוע'] = '71' } },
			{ name = 'reds', grain = 'event',
			  filters = { ['מספר אירוע'] = '7', ['תת אירוע'] = '72,73' } },
			{ name = 'benchStarts', grain = 'event',
			  filters = { ['מספר אירוע'] = '2' } },
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

	-- תבנית:סטטיסטיקה/תצוגה/ימים/סיכום תוצאות לפי מפעל, and the tab strip
	-- above it. Transcluded by 366 pages - one per day of the year - which
	-- makes it the first block with real reach.
	--
	-- Every cell here is game-grain and none touches the events table, which is
	-- what a metadata block looks like: counting games and summing goals, never
	-- counting events. Two of them SUM a column rather than counting rows.
	['day-results'] = {
		entity = 'תאריך',
		-- The block's own constant filters, applied to every cell. The
		-- template hardcodes this format in each of its five calls, and it is
		-- what makes the block "this day in any year" rather than "this exact
		-- date": without it the default %d-%m-%Y matches one year only, which
		-- is right for some dates by luck and wrong for the rest.
		filters = { ['פורמט תאריך'] = '"%d-%m"' },
		-- The template stacks the label and the value and separates rows with
		-- a blank line, where the player block puts a row on one line.
		layout = 'stacked',

		tabs = { 'רשמי', 'ליגה', 'גביע', 'בינלאומי' },

		-- The tab strip, for the `render` entry point that emits the whole
		-- widget. Three things differ and all three are load bearing:
		--
		--   * the DISPLAY order is not the `tabs` order above - the strip
		--     shows ליגה first and רשמי last;
		--   * the tab's label is not its heading - the גביע tab is headed
		--     גביע המדינה, and the בינלאומי category is labelled אירופה;
		--   * the label is what the skin keys the icon on, and what ends up
		--     in the URL, so it stays plain text.
		tabStrip = {
			{ category = 'ליגה', label = 'ליגה', heading = 'ליגה' },
			{ category = 'גביע', label = 'גביע', heading = 'גביע המדינה' },
			{ category = 'בינלאומי', label = 'אירופה', heading = 'אירופה' },
			{ category = 'רשמי', label = 'כל המסגרות',
			  heading = 'כל המסגרות' },
		},

		-- The heading inside each panel: the tab's heading, and a number the
		-- block already computes. `cell` names it rather than the renderer
		-- hardcoding `games`, so a block whose header shows something else
		-- says so here.
		tabHeading = {
			format = '<div class="tab-header">%s (%s משחקים)</div>',
			cell = 'games',
		},

		cells = {
			{ name = 'wins', grain = 'game',
			  filters = { ['תוצאה'] = 'ניצחון' } },
			{ name = 'draws', grain = 'game',
			  filters = { ['תוצאה'] = 'תיקו' } },
			{ name = 'losses', grain = 'game',
			  filters = { ['תוצאה'] = 'הפסד' } },
			{ name = 'goalsFor', grain = 'game', sum = 'כיבושים',
			  filters = {} },
			{ name = 'goalsAgainst', grain = 'game', sum = 'ספיגות',
			  filters = {} },
			-- The parent's tab header shows this one: "ליגה (N משחקים)".
			{ name = 'games', grain = 'game', filters = {} },
		},

		rows = {
			{ label = 'נצחונות', format = 'plain', cell = 'wins' },
			{ label = 'תיקו', format = 'plain', cell = 'draws' },
			{ label = 'הפסדים', format = 'plain', cell = 'losses' },
			{ label = 'כיבושים', format = 'plainOrEmpty', cell = 'goalsFor' },
			{ label = 'ספיגות', format = 'plainOrEmpty',
			  cell = 'goalsAgainst' },
		},
	},
}
