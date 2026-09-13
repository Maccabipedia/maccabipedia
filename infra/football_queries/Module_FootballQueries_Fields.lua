--[[
Module:FootballQueries/Fields - the declarative half of the football query layer.

Wiki page: Module:FootballQueries/Fields

Everything here is constant data, so Module:FootballQueries reads it with
mw.loadData. That matters: Scribunto keeps no module state between #invoke
calls, and mw.loadData is one of only two caches that survive the boundary, so
this table is parsed once per page no matter how many blocks are rendered.

No functions and no metatables may be added - mw.loadData rejects both.

Filter names are the Hebrew ones the existing templates accept. They are the
callers' contract and the Cargo values they match are Hebrew data, so they are
not translated; everything else in this layer is English.
]]

return {
	-- The sport's own facts, named by ROLE so the logic module contains no
	-- table, column or value belonging to football. This is what makes a second
	-- sport a new data page instead of an edit to shared code - the tables
	-- differ per sport anyway, and so do the side values: football marks
	-- Maccabi's events with 1 and the opponent's with 0, while volleyball uses
	-- 2. A logic module that hardcodes either is a football module wearing a
	-- general name.
	baseTable = 'Football_Games',
	roles = {
		events = 'Games_Events',
		sideColumn = 'Games_Events.Team',
	},
	sides = {
		maccabi = 1,
		opponent = 0,
		-- The parameter value that asks for the opponent's side.
		opponentValue = 'לא',
	},

	-- Which tables exist and how each reaches the base table.
	--
	-- Cargo emits LEFT JOIN for `join on`, verified on production: a game whose
	-- competition has no Competitions row survives with NULL columns (82 such
	-- games - ידידות and גביע מלצ'ט). So adding or omitting a join can never
	-- change a row count, and the layer is free to join only what was asked
	-- for. It is a cost decision, not a correctness one.
	tables = {
		Football_Games = { base = true },
		Games_Events = {
			join = 'Football_Games._pageID = Games_Events._pageID',
		},
		Games_Referees = {
			join = 'Football_Games._pageID = Games_Referees._pageID',
		},
		Football_Games_Uniforms = {
			join = 'Football_Games._pageID = Football_Games_Uniforms._pageID',
		},
		Competitions = {
			join = 'Football_Games.Competition = Competitions.OriginalName',
		},
	},

	-- Does this column store apostrophes and quote marks, or are they stripped
	-- before saving? Querying a stripped column with the raw name returns zero
	-- rows and no error, so every column a filter touches needs an entry here
	-- and a missing one is an error rather than a guess.
	--
	-- Measured against production per column, which corrects
	-- maccabipedia_structure_knowledge.md §16: Football_Games.Competition
	-- KEEPS quotes (גביע מלצ'ט), and so does CoachMaccabi (ג'ורדי קרויף).
	columns = {
		['Football_Games.Season'] = 'strip',
		['Football_Games.Competition'] = 'keep',
		['Football_Games.Opponent'] = 'strip',
		['Football_Games.Stadium'] = 'strip',
		['Football_Games.HomeAway'] = 'strip',
		['Football_Games.CoachMaccabi'] = 'keep',
		['Football_Games.Refs'] = 'keep',
		['Football_Games.Date'] = 'strip',
		['Football_Games.ResultOpt'] = 'number',
		['Football_Games.ResultMaccabi'] = 'number',
		['Football_Games.ResultOpponent'] = 'number',
		['Games_Events.PlayerName'] = 'keep',
		['Games_Events.EventType'] = 'number',
		['Games_Events.SubType'] = 'number',
		['Games_Events.Team'] = 'number',
		['Games_Referees.AssistantReferees'] = 'keep',
		['Football_Games_Uniforms.KitName'] = 'strip',
		['Competitions.OriginalName'] = 'strip',
		['Competitions.CurrentName'] = 'strip',
		['Opponents.OriginalName'] = 'keep',
		['Stadiums.CanonicalName'] = 'strip',
	},

	-- Every filter the statistics templates accept. `kind` names the handler in
	-- Module:FootballQueries; a parameter absent from this table is an error,
	-- never a silently dropped filter.
	filters = {
		['עונה'] = { column = 'Football_Games.Season', kind = 'text' },
		['מאמן'] = { column = 'Football_Games.CoachMaccabi', kind = 'text' },
		['שופט'] = { column = 'Football_Games.Refs', kind = 'text' },
		['עוזר שופט'] = { column = 'Games_Referees.AssistantReferees', kind = 'holds' },
		['שחקן'] = { column = 'Games_Events.PlayerName', kind = 'text' },
		['שחקנים'] = { column = 'Games_Events.PlayerName', kind = 'list' },
		['מפעל מקורי'] = { column = 'Competitions.OriginalName', kind = 'text' },
		['מפעל נוכחי'] = { column = 'Competitions.CurrentName', kind = 'text' },
		['מפעלים'] = { column = 'Football_Games.Competition', kind = 'list' },
		['קטגוריית מפעל'] = { kind = 'competitionCategory' },
		['יריבה'] = { column = 'Football_Games.Opponent', kind = 'opponentAliases' },
		['יריבות'] = { column = 'Football_Games.Opponent', kind = 'list' },
		['אצטדיון'] = { column = 'Football_Games.Stadium', kind = 'stadiumAliases' },
		['אצטדיונים'] = { column = 'Football_Games.Stadium', kind = 'list' },
		['תוצאה'] = { column = 'Football_Games.ResultOpt', kind = 'resultWord' },
		['תוצאה מכבי'] = { column = 'Football_Games.ResultMaccabi', kind = 'number' },
		['תוצאה יריבה'] = { column = 'Football_Games.ResultOpponent', kind = 'number' },
		['ביתחוץ'] = { column = 'Football_Games.HomeAway', kind = 'text' },
		['מספר אירוע'] = { column = 'Games_Events.EventType', kind = 'numberList' },
		['תת אירוע'] = { column = 'Games_Events.SubType', kind = 'numberList' },
		['ללא תת אירוע'] = { column = 'Games_Events.SubType', kind = 'numberNotEqual' },
		['מכבי'] = { column = 'Games_Events.Team', kind = 'maccabiSide' },
		['סט מדים'] = { column = 'Football_Games_Uniforms.KitName', kind = 'text' },
		['תאריך'] = { column = 'Football_Games.Date', kind = 'date' },
		-- Read by the תאריך handler rather than producing a condition itself.
		['פורמט תאריך'] = { kind = 'modifier' },
	},

	-- קטגוריית מפעל values, as the templates define them. יתר-רשמיים exists in
	-- כמות אירועי שחקן and is silently ignored by כמות נתוני משחק today, which
	-- hands that page the unfiltered total; here there is one definition.
	competitionCategories = {
		['ליגה'] = 'Competitions.League = 1',
		['גביע'] = 'Competitions.Trophy = 1',
		['בינלאומי'] = 'Competitions.International = 1',
		['רשמי'] = 'Competitions.Official = 1',
		['יתר-רשמיים'] = '(Competitions.Official = 1 AND Competitions.League = 0'
			.. ' AND Competitions.Trophy = 0 AND Competitions.International = 0)',
	},

	-- תוצאה in words to Football_Games.ResultOpt, read from the Games_Results
	-- table on production. תבנית:המרות/תוצאת משחק למספר spends a Cargo query to
	-- look these three rows up; they are constant, so this layer does not.
	resultWords = {
		['ניצחון'] = 1,
		['תיקו'] = 2,
		['הפסד'] = 3,
	},

	-- Alias expansion. One stadium or club is stored under several names, so a
	-- filter on either has to become an IN over every related name. Both are
	-- self-joins, and they are not symmetrical - the stadium table relates rows
	-- by page and matches on CanonicalName, the opponents table relates rows by
	-- CanonicalName and matches on OriginalName.
	-- `matchQuotes` is how the alias table stores the name being looked up, and
	-- it is declared here rather than read from `columns` because the SQL alias
	-- prefix (o1., s1.) is not a declared column name. It is NOT symmetrical
	-- with the games table: Opponents.OriginalName stores בית"ר ירושלים with a
	-- literal quote while Football_Games.Opponent stores ביתר ירושלים without
	-- one, so the lookup keeps the quote.
	--
	-- There is deliberately no `returnQuotes`. The names coming back are
	-- quoted by the rule of the column they are matched against, so a second
	-- knob here would be dead configuration that can silently disagree with
	-- `columns` - it was, and a mutation test proved it had no effect.
	aliases = {
		stadium = {
			tables = 'Stadiums=s1,Stadiums=s2',
			join = 's1._pageID = s2._pageID',
			matchColumn = 's1.CanonicalName',
			returnColumn = 's2.CanonicalName',
			matchQuotes = 'strip',
		},
		opponent = {
			tables = 'Opponents=o1,Opponents=o2',
			join = 'o1.CanonicalName = o2.CanonicalName',
			matchColumn = 'o1.OriginalName',
			returnColumn = 'o2.OriginalName',
			matchQuotes = 'keep',
		},
	},

	-- Template-facing parameters that choose what to compute rather than which
	-- rows to match. They are not filters, so they are named here and the
	-- unsupported-filter guard lets them through instead of rejecting them.
	optionParams = {
		['נתון משחק'] = 'aggregate',
		['הגבלה'] = 'limit',
	},

	-- נתון משחק values, from כמות נתוני משחק. Cargo's SUM returns a float, and
	-- the template casts it back with #number_format; this layer rounds instead.
	aggregates = {
		['כמות משחקים'] = 'COUNT(*)',
		['כיבושים'] = 'SUM(Football_Games.ResultMaccabi)',
		['ספיגות'] = 'SUM(Football_Games.ResultOpponent)',
	},

	-- What each #invoke entry point is allowed to be asked.
	--
	-- Every entry point used to accept the union of all 24 filters, which meant
	-- the drop-in for כמות נתוני משחק also accepted שחקן - and a player filter
	-- joins the events table, so it returned an EVENT count where the call
	-- site, its label and its documentation all say "number of games". No
	-- error, plausible number, wrong number.
	--
	-- So a replacement declares exactly the parameters of the template it
	-- replaces, taken from that template's own source, and anything else
	-- raises. `count` is the open entry point for new callers and has no list.
	entryPoints = {
		gameDataCount = {
			replaces = 'תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות נתוני משחק',
			filters = {
				'אצטדיון', 'אצטדיונים', 'יריבה', 'יריבות', 'מאמן',
				'מפעל מקורי', 'מפעל נוכחי', 'מפעלים', 'סט מדים', 'עוזר שופט',
				'עונה', 'פורמט תאריך', 'קטגוריית מפעל', 'שופט', 'תאריך',
				'תוצאה', 'תוצאה יריבה', 'תוצאה מכבי',
			},
			-- נתון משחק chooses the aggregate. הגבלה is NOT here: the template
			-- has no such parameter, and accepting one this entry point then
			-- ignores is the same sin in the other direction.
			options = { 'נתון משחק' },
		},
	},

	-- Cargo truncates at the row limit silently, so every query the layer runs
	-- carries a limit and is checked against it.
	defaultLimit = 500,
	maxLimit = 5000,
}
