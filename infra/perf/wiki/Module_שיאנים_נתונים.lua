-- יחידה:שיאנים/נתונים -- per-player event counts, one query for the whole page.
--
-- A DATA module, loaded through mw.loadData, which is why the query below runs
-- once per page no matter how many leaderboards are on it. Scribunto executes a
-- loadData module once per parse and caches the table for the rest of it.
--
-- A plain module-local variable would not help: module state does NOT survive
-- between #invoke calls. Measured -- 1 call 0.035s CPU, 5 calls 0.100s, 20 calls
-- 0.341s, 65 calls 0.968s, exactly linear. mw.loadData is the only Scribunto
-- cache that crosses that boundary.
--
-- The catch is that it caches by MODULE NAME and a data module takes no
-- arguments, so this serves unfiltered pages only. A page that filters by
-- stadium, opponent, season or referee has nowhere to put the filter and runs
-- its own query in [[יחידה:שיאנים]] instead.
--
-- A players-portal render used to issue 32 separate queries. It issues this one.

local rows = mw.ext.cargo.query(
	'Football_Games,Games_Events,Competitions',
	table.concat({
		'Games_Events.PlayerName=player',
		'Games_Events.EventType=eventType',
		'Games_Events.SubType=subType',
		'Competitions.League=league',
		'Competitions.Trophy=trophy',
		'Competitions.International=intl',
		'COUNT(*)=n',
	}, ','),
	{
		join = 'Football_Games._pageID=Games_Events._pageID,' ..
		       'Football_Games.Competition=Competitions.OriginalName',
		where = 'Games_Events.Team=1 AND Competitions.Official=1 ' ..
		        "AND Games_Events.PlayerName IS NOT NULL " ..
		        "AND Games_Events.PlayerName != ''",
		groupBy = 'Games_Events.PlayerName,Games_Events.EventType,' ..
		          'Games_Events.SubType,Competitions.League,' ..
		          'Competitions.Trophy,Competitions.International',
		-- Must match ROW_LIMIT in [[יחידה:שיאנים]], which checks for truncation.
		limit = 20000,
	}) or {}

-- mw.loadData returns plain data only: no functions, no metatables.
local out = {}
for index, row in ipairs(rows) do
	out[index] = {
		player = row.player,
		eventType = row.eventType,
		subType = row.subType,
		league = row.league,
		trophy = row.trophy,
		intl = row.intl,
		n = tonumber(row.n) or 0,
	}
end
return out
