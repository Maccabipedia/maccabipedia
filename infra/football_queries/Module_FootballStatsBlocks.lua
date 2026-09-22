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

local blocks = {
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

	-- The four assistant-referee leaderboard boxes on a referee page
	-- (תבנית:שופט כדורגל/עוזר שופט), from ONE grouped query where the templates
	-- run 32. Rendered by the `leaderboards` entry point; see
	-- .claude/referee_leaderboards_spec.md.
	['referee-assistant'] = {
		-- The one direct argument besides בלוק, and the filter it becomes. The
		-- entry point refuses an empty value: the query layer treats an empty
		-- filter as absent, which would rank every player in every game.
		entity = 'שופט',
		entityFilter = 'עוזר שופט',
		-- Every tab of the templates' query carries Competitions.Official = 1,
		-- the league tab included - so רשמי is SHARED, and each tab's own
		-- category joins it inside its column.
		shared = { ['קטגוריית מפעל'] = 'רשמי' },
		groupBy = 'player',
		top = 10,
		rowTemplate = 'סטטיסטיקות/הצגת שיאנים/הצגת שחקן/כדורגל',
		moreText = 'עוד',
		-- No default: a block declared without this raises rather than
		-- silently borrowing another block's wrapper markup.
		boxOpen = '<div class="records-list-tabs-container" id="שיאנים">',

		-- Tab order, labels and headings as the strips have them.
		tabStrip = {
			{ category = 'רשמי', label = 'משחקים רשמיים',
			  heading = 'משחקים רשמיים' },
			{ category = 'ליגה', label = 'ליגה', heading = 'ליגה' },
			{ category = 'גביע', label = 'גביע', heading = 'גביע המדינה' },
			{ category = 'בינלאומי', label = 'אירופה', heading = 'אירופה' },
		},
		tabHeading = '<div class="tab-header">%s (%s %s)</div>',

		-- In the section's order. Titles, nouns and filters are read from the
		-- production templates, not guessed: the cards box counts YELLOW cards
		-- only (type 7, subtype 71). A first version counted every card and the
		-- local comparison against the old boxes failed on 20 of 33 referees.
		boxes = {
			{ key = 'appearances', title = 'שיאני הופעות',
			  noun = 'מופיעים שונים',
			  filters = { ['מספר אירוע'] = '1,5' } },
			{ key = 'goals', title = 'שיאני כיבושים', noun = 'כובשים שונים',
			  -- Own goals out, for this box only. In the shared WHERE it
			  -- would also drop subtype-33 rows from the other boxes.
			  filters = { ['מספר אירוע'] = '3', ['ללא תת אירוע'] = '33' } },
			{ key = 'assists', title = 'שיאני בישולים', noun = 'שחקנים שונים',
			  filters = { ['מספר אירוע'] = '4' } },
			{ key = 'cards', title = 'שיאני צהובים', noun = 'שחקנים שונים',
			  filters = { ['מספר אירוע'] = '7', ['תת אירוע'] = '71' } },
		},
	},

	-- The four leaderboard boxes on a season page (תבנית:עונת כדורגל), from
	-- ONE grouped query where the season-only wrapper templates run 32. Same
	-- primitive as referee-assistant; differs only where production's own
	-- templates differ (read 2026-09-18, not copied from the sibling block):
	-- the cards box is titled שיאני מוצהבים (not צהובים), tab 4 reads
	-- בינלאומי on both the label and the heading (not אירופה), and the box
	-- wrapper carries no id - the season page puts id="שיאנים" on the parent
	-- players-records-container grid instead. See .claude/football_queries.md,
	-- "Leaderboards".
	['season'] = {
		entity = 'עונה',
		entityFilter = 'עונה',
		shared = { ['קטגוריית מפעל'] = 'רשמי' },
		groupBy = 'player',
		top = 10,
		rowTemplate = 'סטטיסטיקות/הצגת שיאנים/הצגת שחקן/כדורגל',
		moreText = 'עוד',
		boxOpen = '<div class="records-list-tabs-container">',

		tabStrip = {
			{ category = 'רשמי', label = 'משחקים רשמיים',
			  heading = 'משחקים רשמיים' },
			{ category = 'ליגה', label = 'ליגה', heading = 'ליגה' },
			{ category = 'גביע', label = 'גביע', heading = 'גביע המדינה' },
			{ category = 'בינלאומי', label = 'בינלאומי', heading = 'בינלאומי' },
		},
		tabHeading = '<div class="tab-header">%s (%s %s)</div>',

		boxes = {
			{ key = 'appearances', title = 'שיאני הופעות',
			  noun = 'מופיעים שונים',
			  filters = { ['מספר אירוע'] = '1,5' } },
			{ key = 'goals', title = 'שיאני כיבושים', noun = 'כובשים שונים',
			  filters = { ['מספר אירוע'] = '3', ['ללא תת אירוע'] = '33' } },
			{ key = 'assists', title = 'שיאני בישולים', noun = 'שחקנים שונים',
			  filters = { ['מספר אירוע'] = '4' } },
			{ key = 'cards', title = 'שיאני מוצהבים', noun = 'שחקנים שונים',
			  filters = { ['מספר אירוע'] = '7', ['תת אירוע'] = '71' } },
		},
	},

	-- The seasonal numbers at the top of a season page
	-- (תבנית:עונת כדורגל/הצגת מספרים עונתיים): eight numbers per tab, which
	-- the template fetched with eight query templates per tab - 32 queries.
	-- These two blocks only SUPPLY the numbers: the container primes both once
	-- and each tab reads them with `value`, keeping all of its own formatting
	-- (percentages, per-game ratios, #number_format, hide-at-zero) and its
	-- tab strip. So they declare no rows.
	--
	-- Two blocks, because goals are a SUM of a game column and the cards count
	-- events: in one query the events join would multiply every game's goals
	-- by its number of events, which the query layer refuses. 32 → 2.
	['season-results'] = {
		entity = 'עונה',
		tabs = { 'רשמי', 'ליגה', 'גביע', 'בינלאומי' },
		cells = {
			{ name = 'wins', grain = 'game', filters = { ['תוצאה'] = 'ניצחון' } },
			{ name = 'draws', grain = 'game', filters = { ['תוצאה'] = 'תיקו' } },
			{ name = 'losses', grain = 'game', filters = { ['תוצאה'] = 'הפסד' } },
			{ name = 'goalsFor', grain = 'game', sum = 'כיבושים', filters = {} },
			{ name = 'goalsAgainst', grain = 'game', sum = 'ספיגות', filters = {} },
			{ name = 'cleanSheets', grain = 'game', filters = { ['תוצאה יריבה'] = '0' } },
		},
	},
	['season-cards'] = {
		entity = 'עונה',
		tabs = { 'רשמי', 'ליגה', 'גביע', 'בינלאומי' },
		cells = {
			{ name = 'yellows', grain = 'event',
			  filters = { ['תת אירוע'] = '71', ['מכבי'] = 'כן' } },
			{ name = 'reds', grain = 'event',
			  filters = { ['תת אירוע'] = '72, 73', ['מכבי'] = 'כן' } },
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

local function copied(value)
	if type(value) ~= 'table' then
		return value
	end
	local copy = {}
	for key, item in pairs(value) do
		copy[key] = copied(item)
	end
	return copy
end

-- The four leaderboard boxes on a stadium page (תבנית:אצטדיון כדורגל). Its
-- boxes are the season page's: both call the same four
-- `סטטיסטיקה/תצוגה/שחקנים/שיאני …/עיצוב חדש` templates (read 2026-09-22), so
-- only the filter differs - the stadium's names, as the IN list the templates
-- build from אצטדיונים לשליפה. Derived rather than copied, so the two cannot
-- drift apart. A copy, not a shared reference: loadData hands the renderer a
-- proxy it materialises table by table.
blocks['stadium'] = copied(blocks['season'])
blocks['stadium'].entity = 'אצטדיונים'
blocks['stadium'].entityFilter = 'אצטדיונים'

return blocks
