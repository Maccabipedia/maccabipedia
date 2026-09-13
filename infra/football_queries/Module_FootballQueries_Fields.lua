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
	-- Which tables exist and how each reaches Football_Games.
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
	aliases = {
		stadium = {
			tables = 'Stadiums=s1,Stadiums=s2',
			join = 's1._pageID = s2._pageID',
			matchColumn = 's1.CanonicalName',
			returnColumn = 's2.CanonicalName',
			quotes = 'strip',
		},
		opponent = {
			tables = 'Opponents=o1,Opponents=o2',
			join = 'o1.CanonicalName = o2.CanonicalName',
			matchColumn = 'o1.OriginalName',
			returnColumn = 'o2.OriginalName',
			quotes = 'keep',
		},
	},

	-- Cargo truncates at the row limit silently, so every query the layer runs
	-- carries a limit and is checked against it.
	defaultLimit = 500,
	maxLimit = 5000,
}
