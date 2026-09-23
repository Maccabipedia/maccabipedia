--[[
Module:BasketballQueries/Fields - basketball's schema for the shared query logic.

Wiki page: Module:BasketballQueries/Fields

Read with mw.loadData by Module:BasketballQueries, which is
    return require('Module:SportQueries').new(mw.loadData('Module:BasketballQueries/Fields'))
No functions and no metatables may be added.

Everything here is taken from תבנית:כדורסל/סטטיסטיקה/שיאנים לפי אירוע, the one
query template behind every basketball leaderboard (485 pages), and measured on
production 2026-09-23 where the template's SQL left a choice open.

Basketball's grain differs from football's: Basketball_Player_Game_Events_Summary
has ONE row per player per game, and a stat is the SUM of a column of it
(points, assists, rebounds; appearances = SUM(IsPlayed)). Football counts event
rows by type. The shared logic knows both through `grain` and `sumColumns`.
]]

return {
	name = 'BasketballQueries',

	baseTable = 'Basketball_Games',
	roles = {
		sideColumn = 'Basketball_Player_Game_Events_Summary.Team',
		-- The template: {{#תנאי: {{{האם עבור יריבה|}}} | AND bpges.Team=0 | AND bpges.Team=1}}
		sideFilter = 'האם עבור יריבה',
		-- No narrowFilter: a basketball leaderboard has no event types to narrow by.
	},

	groupKeys = {
		player = 'Basketball_Player_Game_Events_Summary.PlayerName',
	},
	sides = {
		maccabi = 1,
		opponent = 0,
		-- The template treats ANY value as "for the opponent"; here the word is
		-- כן, and לא is what the layer passes itself. No caller passes another
		-- word (checked: the box templates pass nothing).
		opponentValue = 'כן',
		maccabiValue = 'לא',
	},

	-- Joins as the template wrote them: the competition by name, the player
	-- summaries by page name (football joins its events by _pageID).
	-- Grain measured 2026-09-23: 57,298 summary rows over 3,388 games (~17 per
	-- game), so the summary table multiplies; the competition is 1:1.
	tables = {
		Basketball_Games = { base = true, grain = 'game' },
		Basketball_Competitions = {
			join = 'Basketball_Games.Competition = Basketball_Competitions.OriginalName',
			grain = 'game',
		},
		Basketball_Player_Game_Events_Summary = {
			join = 'Basketball_Games._pageName = Basketball_Player_Game_Events_Summary._pageName',
			grain = 'perPlayer',
		},
	},

	-- Quote rules, measured as rows containing the character (2026-09-23):
	-- Opponent 118 apostrophes / 123 quote marks, Stadium 52 / 13, PlayerName
	-- 11,897 / 39, Competition 13 / 0, MainReferee 251 / 0, CoachMaccabi 78 / 0,
	-- Competitions.OriginalName 2 / 0, Season none. Every text column keeps its
	-- quotes, which is also how the template quoted its IN lists (a value with
	-- an apostrophe went in double quotes, verbatim).
	columns = {
		['Basketball_Games.Season'] = 'keep',
		['Basketball_Games.Competition'] = 'keep',
		['Basketball_Games.Opponent'] = 'keep',
		['Basketball_Games.Stadium'] = 'keep',
		['Basketball_Games.MainReferee'] = 'keep',
		['Basketball_Games.AssistantReferees'] = 'keep',
		['Basketball_Games.ResultOpt'] = 'number',
		['Basketball_Player_Game_Events_Summary.PlayerName'] = 'keep',
		['Basketball_Player_Game_Events_Summary.Team'] = 'number',
		['Basketball_Player_Game_Events_Summary.IsPlayed'] = 'number',
		['Basketball_Player_Game_Events_Summary.TotalPoints'] = 'number',
		['Basketball_Player_Game_Events_Summary.Assists'] = 'number',
		['Basketball_Player_Game_Events_Summary.TotalRebounds'] = 'number',
		['Basketball_Player_Game_Events_Summary.Blocks'] = 'number',
		['Basketball_Player_Game_Events_Summary.Steals'] = 'number',
		['Basketball_Player_Game_Events_Summary.Turnovers'] = 'number',
		['Basketball_Player_Game_Events_Summary.TotalPersonalFouls'] = 'number',
		['Basketball_Competitions.OriginalName'] = 'keep',
	},

	-- The parameters of שיאנים לפי אירוע, under their names.
	filters = {
		['עונה'] = { column = 'Basketball_Games.Season', kind = 'text' },
		['מפעלים'] = { column = 'Basketball_Games.Competition', kind = 'list' },
		['יריבות'] = { column = 'Basketball_Games.Opponent', kind = 'list' },
		['מגרשים'] = { column = 'Basketball_Games.Stadium', kind = 'list' },
		-- The page builds this list from category members, so each name arrives
		-- as כדורסל:Name; the template stripped the prefix with #replace.
		['שחקנים'] = { column = 'Basketball_Player_Game_Events_Summary.PlayerName',
			kind = 'list', quoted = true, stripPrefix = 'כדורסל:' },
		['שופט ראשי'] = { column = 'Basketball_Games.MainReferee', kind = 'text' },
		['עוזר שופט'] = { column = 'Basketball_Games.AssistantReferees', kind = 'holds' },
		['האם עבור יריבה'] = { column = 'Basketball_Player_Game_Events_Summary.Team',
			kind = 'maccabiSide' },
		-- The template: הפסד → 3, and every other word (נצחון, ניצחון, or a
		-- typo) → 1. Here a typo is an error rather than a win.
		['תוצאה'] = { kind = 'resultWord', choices = {
			['הפסד'] = 'Basketball_Games.ResultOpt = 3',
			['נצחון'] = 'Basketball_Games.ResultOpt = 1',
			['ניצחון'] = 'Basketball_Games.ResultOpt = 1',
		} },
		-- The template's #בחר, including its two quirks kept on purpose (Roee,
		-- 2026-09-23: byte-identical today): רשמי adds NO condition, so the
		-- 8 games with no competitions row count in the "official" tab; an
		-- ABSENT category means Official = 1, which the wrapper template passes
		-- as the word ברירת מחדל.
		['קטגוריית מפעל'] = { kind = 'competitionCategory',
			tables = { 'Basketball_Competitions' }, choices = {
				['ליגה'] = 'Basketball_Competitions.League = 1',
				['גביע'] = 'Basketball_Competitions.Trophy = 1',
				['בינלאומי'] = 'Basketball_Competitions.International = 1',
				-- No parentheses: this lands inside CASE WHEN … THEN, and Cargo's
				-- field parser reads `WHEN (` as a call to a function WHEN() and
				-- refuses the query. An AND chain needs none.
				['יתר-רשמיים'] = 'Basketball_Competitions.Official = 1'
					.. ' AND Basketball_Competitions.League = 0'
					.. ' AND Basketball_Competitions.Trophy = 0'
					.. ' AND Basketball_Competitions.International = 0',
				['רשמי'] = '',
				['ברירת מחדל'] = 'Basketball_Competitions.Official = 1',
			} },
	},

	-- The אירוע words of the template, each the column it summed.
	sumColumns = {
		['הופעות'] = 'Basketball_Player_Game_Events_Summary.IsPlayed',
		['נקודות'] = 'Basketball_Player_Game_Events_Summary.TotalPoints',
		['אסיסטים'] = 'Basketball_Player_Game_Events_Summary.Assists',
		['ריבאונדים'] = 'Basketball_Player_Game_Events_Summary.TotalRebounds',
		['חסימות'] = 'Basketball_Player_Game_Events_Summary.Blocks',
		['חטיפות'] = 'Basketball_Player_Game_Events_Summary.Steals',
		['איבודים'] = 'Basketball_Player_Game_Events_Summary.Turnovers',
		['עבירות'] = 'Basketball_Player_Game_Events_Summary.TotalPersonalFouls',
	},

	-- No alias expansion, no כמות נתוני משחק-style aggregates, no template
	-- drop-ins yet: the leaderboards are the first basketball family.
	aliases = {},
	aggregates = {},
	optionParams = {},
	entryPoints = {},

	-- A leaderboard groups every player who ever had a row; ~1,000 players.
	maxLimit = 5000,
}
