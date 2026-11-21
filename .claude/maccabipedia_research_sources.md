# MaccabiPedia Research Sources

**This list and the live wiki page [`מקורות שימושיים`](https://www.maccabipedia.co.il/מקורות_שימושיים) are one list in two places.**
Every source sits in both. Add or remove a source in one, and do the same in the other in the same change.
- **Wiki side:** a terse Hebrew line in the right `{{קופסת עיצוב}}` box (כללי / כדורגל / כדורסל / כדורעף / כדוריד) and sub-group. The page is an outward-facing edit, so reproduce the rest of it unchanged.
- **Repo side:** the matching section below.
- **What only the doc carries:** how-to detail (APIs, query tricks, traps). It does not carry sources the wiki lacks.
- **Check they still match** before the PR:
  `uv run python .claude/scripts/research_sources_sync.py`
  It compares the two lists by source and prints whatever is on one side only.

## Tips for searching a source for MaccabiPedia

Prefer slow and complete over fast. A search that finds everything beats a quick one
that misses items.

- **Search broad, then filter by eye.** Search inside the source's own collection or
  category with broad terms: `maccabi`, `makkabi`, `makabi`, `tel aviv`, `מכבי`, and
  the club's historical names such as "Maccabi Israel" and "Maccabi Elite". List every
  hit and decide relevance by looking, not with a title pattern or regex. If a script
  has to filter, have it print what it dropped too.
- **Iterate on leads.** Each page or item you find points to more: the collection it
  belongs to, the seller's other items, related items, names and dates it mentions.
  Follow them and search again until no new leads turn up.
- **Open every item.** Titles and descriptions are often wrong or incomplete. Look at
  every image and every file in the item, and read the date, teams and venue from the
  object itself.
- **Check the wiki before calling something new.** Query the Cargo table where there is
  one. Where there isn't, search File pages by the match date. A game with no page at
  all is a finding in itself.
- **A data fix needs a primary source** unless the error is nonsense: a newspaper of
  the time (`.claude/newspaper_archives.md`), with the quote and the PDF path. Anything
  else is a lead, not proof. A search miss does not prove absence.
- **When a site blocks bots, ask the user to save the page.** Don't retry in a loop.
- **When a site is a JavaScript app,** record its network calls and query the JSON API
  directly.
- **Save finds somewhere durable right away:** a Drive folder per source, with a file
  listing each item's link. Track anything not yet on the wiki in a Trello card.

## Cross-sport sources

**Old Maccabi websites (Wayback Machine):**
- maccabita.co.il (~2002): https://web.archive.org/web/20021201114805/http://www.maccabita.co.il/default.asp — old official site, useful for rosters across all sports
- maccabifans.co.il (~2004–2007): https://web.archive.org/web/20070508213837/http://www.maccabifans.co.il/ — roster pages: https://web.archive.org/web/20040310150332/http://www.maccabifans.co.il/segel_show.asp?num=15
- Ultras 96: https://web.archive.org/web/20040822043201/http://www.ultras.co.il/one_news.asp?IDNews=1028
- hamaccabim.net (~2021): https://web.archive.org/web/*/hamaccabim.net — fan/information site (check snapshots for rosters & match data)
- tzahevet.co.il (~2002): https://web.archive.org/web/20020120161603/http://tzahevet.co.il/ — fan site (צהבת = "Yellow", Maccabi colors)
- gate11.co.il (~2006): https://web.archive.org/web/20060613183922/http://www.gate11.co.il/ — fan site/forum "Gate 11" (check for photos, match reports)

**National archives:**
- Israel State Archives: https://catalog.archives.gov.il/
- NLI — JPress (historical Jewish press): http://web.nli.org.il/sites/jpress/Hebrew/pages/default.aspx — browse by year: https://jpress.org.il/Olive/APA/NLI_heb/
- NLI — Jrayed (enhanced search, Arabic+Hebrew): https://jrayed.org/en/newspapers/home
- NLI — Ephemera/posters: http://primo.nli.org.il/primo-explore/search?query=any,contains,%D7%9E%D7%9B%D7%91%D7%99%20%D7%AA%22%D7%90&tab=default_tab&search_scope=Ephemera1&vid=NNL_Ephemera&sortby=rank&lang=iw_IL
- NLI — Hadashot newspaper (color): https://www.nli.org.il/he/newspapers/
- Israeli Museums Portal: https://museums.gov.il/he/items/Pages/default.aspx
- Harvard Digital Collections: https://digitalcollections.library.harvard.edu/catalog
- Israeli Film Archive: https://jfc.org.il/
- GPO National Photo Collection: https://gpophoto.gov.il/ — 160K+ digitized photos since pre-1948
- Maccabi World Union Archive: https://www.maccabi.org/who-we-are/archive — ~30K photos, posters, films from early 20th century
- Israel State Archives on YouTube: https://www.youtube.com/user/israelarchive/search
- Kan (public broadcaster) sports archive: https://www.kan.org.il/lobby/kan_sport/
- Vanished heritage stadiums of Tel Aviv-Jaffa (PDF, Avnei Moreshet / Prof. Eliyahu Stern, 2026): https://hamoreshet.org.il/viewer.php?file=/wp-content/pdf/present-based-past/Tel_Aviv_Disappeared_Stadiums.pdf — visual essay on the football & basketball grounds that disappeared from the city, incl. Maccabi TLV historical home grounds, with photos and dates

**Press:**
- Ynet archive: https://www.ynet.co.il/home/0,7340,L-4269-77-57,00.html
- Walla Sports: https://sports.walla.co.il/
- Pendel magazines: http://www.pendelmag.com/index.html
- HaOlam HaZeh (weekly magazine archive): https://thisworld.online/
- Children's reading booklets (hpt.co.il): https://www.hpt.co.il/?Reading=1
- Trove (Australian newspapers — Maccabi tours): https://trove.nla.gov.au/
- Newspapers.com (US — Maccabi tours): https://www.newspapers.com/
- British Newspaper Archive (UK — Mandate-era + European matches): https://www.britishnewspaperarchive.co.uk/
- Europeana (European newspapers 1618–1996): https://www.europeana.eu/
- Yedioth Ahronoth full archive (**requires TAU access**): http://192.115.83.120.rproxy.tau.ac.il/Olive/APA/Test/
- ProQuest Global (**requires TAU access**): https://www.proquest.com/?accountid=14765

**Local newspaper scans (MaccabiPedia shared Google Drive, `ארכיונים/ארכיון עיתונים/`):**
- Yedioth Ahronoth single sports pages 1939–2021 and full issues 1940–2019 (both text-searchable), Hadashot HaSport full daily issues 1954–84 (image-only), plus Sport HaBoker 1936–46, Aspaklaria 1947–48, Sport Israel 1949–50, Maariv 1994. Layout, search script and how to date a game from them: `.claude/newspaper_archives.md`.

**Memorabilia (tickets, programmes) and recorded games:**
- Internet Archive items (not the Wayback Machine): https://archive.org/ — collection `historicalbasketballguides` holds scans of about 34 Maccabi basketball programmes (1988–2004) and tickets. Movie collections (`opensource_movies`, `folksoundomy`, `sportstelevision`) hold full TV recordings of Maccabi football and basketball games from 2012 to 2026, often bundled several games to an item. Search API: `archive.org/advancedsearch.php?q=collection:<c> AND (maccabi OR ...)`. Files per item: `archive.org/metadata/<id>`.
- Bidspirit (aggregates Israeli auction houses): https://il.bidspirit.com/ — the house "הפעם השלישית" (`third-time`) sells Israeli sports memorabilia. Most of its Maccabi basketball tickets are already on the wiki. API details: search `il.bidspirit.com/services/search/searchItemsWithSearchServer/?...&time=PAST&token=<text>`, then full lot text from `getLotItemInfo?catalogKey=<ownerKey>&idInApp=<id>`.
- eBay, Kedem auctions: have Maccabi tickets, but both block bots, even headless Chromium. Ask the user to save the search page as HTML.

**Photos:**
- Getty Images: https://www.gettyimages.com/photos/maccabi-tel-aviv
- Facebook old photos album: https://www.facebook.com/media/set/?set=a.10201605865284990&type=3
- Retro blog 1: https://futboltelevisionretro.blogspot.com/2015/07/maccabi-tel-aviv-tv.html
- Retro blog 2: https://lagaleriadelfutbol.blogspot.com/2015/07/maccabitelaviv.html
- Alamy (including B&W historical): https://www.alamy.com/stock-photo/maccabi-tel-aviv.html
- Yoash Alroei blog: https://yoashtvblog.co.il/ — personal Israeli sport/history archive (research, vintage photos, first-hand recollections), incl. Maccabi TLV history posts
- 12p forum thread of old photos, mostly 1980s: https://forum.12p.co.il/index.php?app=forums&module=forums&controller=topic&id=175399
- Maccabiah exhibition photo (Ben Gurion airport): https://www.maccabiah.com/he/maccabiah/%D7%AA%D7%A2%D7%A8%D7%95%D7%9B%D7%AA-%D7%94%D7%9E%D7%9B%D7%91%D7%99%D7%94-%D7%91%D7%A0%D7%AA%D7%91%D7%92/%D7%9C%D7%90-%D7%A8%D7%A7-%D7%91%D7%A1%D7%A4%D7%95%D7%A8%D7%98-%D7%91%D7%94%D7%9B%D7%9C

**Forums:**
- 12p forum (songs, tifos, photos, all sports): https://forum.12p.co.il/
- 12p tifos page: https://12p.co.il/%D7%AA%D7%A4%D7%90%D7%95%D7%A8%D7%95%D7%AA/ (an older copy on the Wayback Machine: https://web.archive.org/web/20140803090116/http://www.12p.co.il/%D7%AA%D7%A4%D7%90%D7%95%D7%A8%D7%95%D7%AA)
- 12p gallery on YouTube (songs, tifos, atmosphere): https://www.youtube.com/@12pgallery
- **12p offline archive**: Full dump (98K topics, 3.7M posts) as SQLite DB + raw HTML on MaccabiPedia shared Google Drive. See `README.md` next to the DB for schema and queries. Searchable offline without accessing the forum.

**Tools:**
- List of club wikis and official sites worldwide: https://docs.ufpr.br/~mmsabino/sstatistics/fontes_pesquisa.html
- Ironi Ashdod's page on Maccabi: http://ironi-ashdod.co.il/team/%D7%9E%D7%9B%D7%91%D7%99-%D7%AA%D7%9C-%D7%90%D7%91%D7%99%D7%91

## Football

**Stats & results:**
- RSSSF league tables: http://www.rsssf.com/tablesi/israhist.html
- RSSSF top scorers: http://www.rsssf.com/tablesi/isratops.html
- RSSSF Israel in European Cups: https://www.rsssf.org/tablesi/isra-ec.html
- Football Association Archive: http://archive.football.org.il/
- football.co.il (the league's own site): https://www.football.co.il/stats/ — current tables with IFA rulings and deductions applied; the data is a JSON API with no captcha (`.claude/season_page_tables.md`). Its archive is unreliable (2025/26 broken), so prefer it for the current season only
- WildStat: http://wildstat.com/p/5015/club/ISR_Maccabi_Tel_Aviv
- Transfermarkt: https://www.transfermarkt.us/maccabi-tel-aviv/startseite/verein/119 — squads, transfers, market values, all seasons
- FBref: https://fbref.com/en/squads/04c011d8/history/Maccabi-Tel-Aviv-FC-Stats-and-History — advanced stats (xG etc.) from 1992-93
- WorldFootball.net: https://www.worldfootball.net/teams/maccabi-tel-aviv/ — all results + all-time player list
- Wikipedia — International Football: https://en.wikipedia.org/wiki/Maccabi_Tel_Aviv_F.C._in_international_football
- Wikipedia — season category (partial, 1920–1923): https://en.wikipedia.org/wiki/Category:Maccabi_Tel_Aviv_F.C._seasons
- American Soccer History Archives (ASHA): https://ussoccerhistory.org/ASHA/ASHA/ — one plain-HTML page per US season (`year/<YYYY>.html`, no search box) listing every foreign team's US tour: dates, opponents, scores, cities and a tour roster. To search, open the year page and look for `Maccabi`, `Palestine`, `Israel` and `Hapoel`. It lists Maccabi tours in 1927 ("Maccabi F.C. of Tel Aviv") and 1936, a US all-star game against "Maccabi" in Jaffa (19.10.1951), and Israeli teams in 1947–1970. It has no crowds or scorers, and it misses the fall 1956 tour. Its 1936 opponent names, dates and scores already changed the wiki: on 21.11.2026 the Detroit game title moved to אולסטארס מישיגן. The opponent-city pages it leads to carry the rest, e.g. Frank Dell'Apa's Boston Globe-based page (Boston crowd 25000 → 8000) and soccermadeinstlouis.com (the St. Louis line-up clipping). It is a secondary compilation and several of its 1936 dates differ from the wiki's, so treat it as a lead and settle each fact from the press of the day.

**Squads & players:**
- Transfer dates thread (X/Twitter): https://twitter.com/austurgi/status/1424947619260862468

**External club-history archives (opponent POV):**
- Scored catalog of ~130 per-club archives / meta-league databases — see [external_club_history_sites.md](./external_club_history_sites.md). Use these to find Maccabi TLV match details from the opponent's side (lineups, attendance, reports).

**Video:**
- maccabi-videos Vimeo: https://vimeo.com/428829885
- maccabi-videos YouTube: https://www.youtube.com/channel/UCxnAYpW-2OJUXbrSil5EeQQ
- maccabifullgame: https://www.youtube.com/channel/UCD5xM1VeIT7VaMhqv3xOZVw
- mtaarchive: https://m.youtube.com/user/mtaarchive
- oren211180: https://www.youtube.com/@oren211180 — mostly basketball (see the Basketball **Video** section), plus short football clips, mainly 1955–1995: goals, cup finals and derbies
- Fan and archive channels (YouTube unless noted):
  - NirHoori: https://www.youtube.com/@NirHoori-ii2vk
  - Old VHS tapes: https://www.youtube.com/@old-vhs-cassettes
  - Maccabi Netanya museum: https://www.youtube.com/channel/UCYU6tubzlzCofhIyV6gtPbw
  - Rak Maccabi: https://www.youtube.com/user/talhollander/videos
  - RAFI457 (Dailymotion): https://www.dailymotion.com/RAFI457/videos
  - Moshiko8: https://www.youtube.com/user/moshiko8/videos
  - Igal3232: https://www.youtube.com/user/IGAL3232
  - Unnamed channel: https://www.youtube.com/channel/UCGASJb2eN4q3myh8X3puSlg
  - King12: https://www.youtube.com/channel/UChNvpb-46shCJ46HpGcrpKw
  - Ultras 96 gallery: https://www.youtube.com/user/ULTRAS96Gallery/videos
  - MTAGold: https://www.youtube.com/user/eman12b/videos
  - 12p (השחקן ה-12): https://www.youtube.com/channel/UC_99ZaTojdch76HejJUkcVw
  - history0811: https://www.youtube.com/user/history0811/search?query=%D7%9E%D7%9B%D7%91%D7%99
  - YellowEmpire: https://www.youtube.com/channel/UCV0hd-MvTxjvWGik_O0emuQ/videos
  - Sport archive 1: https://www.youtube.com/channel/UC3fmhtLpKrJ525atoWJ4CCA
  - Sport archive 2: https://www.youtube.com/user/GamesSportsHD
  - arikezra: https://www.youtube.com/user/arikez/
  - maccabi videos (Dailymotion): https://www.dailymotion.com/maccabivid
  - pizz: https://www.youtube.com/user/pizz121987
  - "מלכת השכונה": https://www.youtube.com/channel/UCN2Sg4EFuIoxqcsN9gR1vqA
  - roei91g11: https://www.youtube.com/@roei91g11/videos
  - takzirim: https://www.youtube.com/@takzirim-f6b
- Maccabi TLV in Europe blog: https://mtainuefa.weebly.com/

**Songs:**
- 12p forum threads (2003–2014): https://forum.12p.co.il/index.php?showtopic=157350
- 12p player songs 2013/14: https://forum.12p.co.il/index.php?showtopic=151107
- 12p new songs 2009: https://forum.12p.co.il/index.php?showtopic=111646
- 12p old songs (2003): https://forum.12p.co.il/index.php?app=forums&module=forums&controller=topic&id=1224

## Basketball

**Stats & results:**
- Hebrew Wikipedia (league seasons): https://he.wikipedia.org/wiki/עונת_2002/2003_בליגת_העל_בכדורסל
- Hebrew Wikipedia (state cup): https://he.wikipedia.org/wiki/גביע_המדינה_בכדורסל_2002/2003
- Safsal history archive (hub): https://www.safsal.co.il/history — Israeli basketball history pages (scores cross-verified 100% vs Wikipedia + our data; **venues sometimes wrong**; older `?page_id=` URLs are dead). Key Maccabi-relevant sub-pages:
  - State Cup finals (from 1955/56): https://www.safsal.co.il/h2575
  - Premier League milestones: https://www.safsal.co.il/h2555
  - Israeli teams in European cups (early decades): https://www.safsal.co.il/h2554
  - Season awards 1980–2002 (POY/Coach/Rookie/All-Star): https://www.safsal.co.il/h2552
  - National League champions: https://www.safsal.co.il/h2580
  - National League historic records: https://www.safsal.co.il/h2576
- EuroLeague Official: https://www.euroleaguebasketball.net/en/euroleague/teams/maccabi-rapyd-tel-aviv/tel/ — stats, rosters, results, records
- EuroLeague data API (plain JSON, no Vercel challenge, works for old seasons back to at least `E2003`): `https://api-live.euroleague.net/v2/competitions/E/seasons/E<start-year>/games/<gameCode>` gives `localDate` (tip-off in local time), `audience`, `referee1..3` (1 = main) and quarter partials; `.../v3/competitions/E/seasons/E<start-year>/games/<gameCode>/stats` gives the full box score per player. The `gameCode` is the number at the end of the game-center URL (e.g. the 2004 final is `E2003/220`). The old `live.euroleague.net/api/Boxscore` returns an empty body for old seasons.
- basket.co.il (Israeli Basketball Association): https://basket.co.il/team.asp?TeamId=1096&lang=en — official league stats per season (~2000-01+). The team page's games table lists the league and the Winner Cup (`גביע ווינר סל`, the league cup) but **never the State Cup**. Decode pages as UTF-8 yourself (`resp.content.decode("utf-8")`); `requests` guesses Latin-1 and the Hebrew comes out as mojibake.
- ibasketball.co.il (IBBA, the association's WordPress/SportsPress site): https://ibasketball.co.il/ — **the State Cup source from 2022/23**: each game has a match page with quarter scores (`table.sp-event-results`) and both full box scores (`table.sp-event-performance`), and links its league (`/league/<year>-900-גביע-המדינה-לגברים/`, year = season start). The site has no match pages for the 2020/21 and 2021/22 State Cups; for those, the association's own game reports (`/news/YYYY/MM/...`) give the score, half-time and scorers.
  - Finding a past game is not obvious: `wp-json/sportspress/v2/events` lists only the current season (its league/season/team filters return nothing for older ones), league pages and their RSS feeds list teams rather than games, and the `sp_event` sitemaps hold number-only URLs. What works: `wp-json/wp/v2/search?search=<text>&subtype=sp_event` reaches every season and returns post ids, then `wp-json/sportspress/v2/events/<post id>` gives the event's `leagues`, so keep the ones in a State Cup league. Event titles carry the team's current name, so search the senior team by its sponsor text (`פלייטיקה`, `Rapyd`); plain "מכבי תל אביב" matches thousands of youth games. A match's post id differs from the number in its URL.
  - State Cup league ids (`sp_league`): 2017→17426, 2018→17425, 2019→17421, 2020→14454, 2021→18037, 2022→18501, 2023→18905, 2024→19224, 2025→119809, 2026→120223.
  - Reports and previews (`wp-json/wp/v2/posts?search=גביע המדינה&after=…&before=…`) give dates, halls and the draw. A preview's referees are the planned ones, not proof of who officiated.
- linguasport (Wayback only; the bare domain is now a gambling spam site, never link it): every European club game with scores, half-time scores, round dates and footnotes (neutral venues, forfeits, replays, played-on dates). Covers Maccabi's Champions Cup / EuroLeague seasons 1958–2022/23, the Cup Winners' Cup (1966/67, 1969/70) and the Korać Cup (1993/94). The only 2023/24 capture is from September 2023, before the season, so it has no games. Finals overview: https://web.archive.org/web/20160519102508/http://linguasport.com/baloncesto/internacional/clubes/c1/palmares.htm ; season example: https://web.archive.org/web/20220123223023/http://www.linguasport.com:80/baloncesto/internacional/clubes/c1/C1_81.htm
  - Folders: `c1/C1_YY.htm` Champions Cup / European League / FIBA EuroLeague / SuproLeague (to 2000/01), `c2/C2_YY.htm` Cup Winners' Cup, `c3/C3_YY.htm` Korać, `EL/EL_YY.htm` EuroLeague from 2000/01 (`YY` = ending year; English Wikipedia does not link these, so find them through CDX). Find a working snapshot with the CDX API (`web.archive.org/cdx/search/cdx?url=...&filter=statuscode:200&output=json`), and fetch it before linking.
  - Scores are home team first: in `A - B | s1 | s2`, s1 was played at A. Checked against Yedioth scans in October 2026 (card #597), it was right in all 12 games where it disagreed with the wiki.
  - Every European game page 1958–2000/01 links its season's page in the first free article slot (`כתבה2` on most, `כתבה1` where that was empty). The 561 EuroLeague game pages 2001/02–2022/23 got theirs in October 2026 too (card #597), as a new `כתבהN` line after the last used one; the game template renders `כתבה1`–`כתבה10`.
  - Reading the `EL_YY.htm` pages (Word tables, flatten `<tr>` → cells): a round header `Competition Day N (date) / Competition Day M (date)` gives the dates of the two legs, and from 2016/17 a row holds two different games side by side (`A - B | score | C - D | score`), one per header date. A `(*)` on a score means played a day before (or after — read the section's note row, which may start with `NOTE :` rather than `*`) the header date. In "best of N" playoff rows the cell background colour marks the home court (`same color means same home court`); the first cell's colour is the first-named team's home. Playoff and semi-final rows start with a seed prefix (`4-5 (4):`, `2-3 :`) that looks like a score, so recognise team cells before score cells. `FINAL STAGE (city)` sections are neutral venues; the final's teams and score sit on two rows after a `VENUE: … DATE: …` row. Lettered footnotes carry postponements ("played on", "suspended") and overtimes. Compared in October 2026 against all 561 wiki EuroLeague games: one score disagreement (17-02-2011 at Olimpija: linguasport 83-65, but the wiki's 83-62 is confirmed quarter by quarter by the EuroLeague API, game `E2010/147`), the rest matched once postponements were accounted for (linguasport lists a postponed game under its original date with a footnote). The 2002 Ülker forfeit, then 20-0 on the wiki, was set to linguasport's official 2:0.

**Rosters & players:**
- Kadorsela dictionary: http://www.cadursela.co.il/Dictionary.asp
- maccabifans roster pages (Wayback): see cross-sport section
- maccabi.co.il Official Club Site: https://maccabi.co.il/data.asp?id=153&lang=en — rosters back to 1986-87, hall of fame, video archive
- Wikipedia Past Rosters: https://en.wikipedia.org/wiki/Maccabi_Tel_Aviv_B.C._past_rosters

**Video:**
- Maccabi Tel Aviv Basketball official YouTube: https://www.youtube.com/channel/UCqxNoI856R_vgs7aQolQhlg — ~6,000 videos in a `Season YYYY/YY` playlist per season, 1979/80 to now, plus dedicated `Games Highlights` / `Full Games` playlists from 2013/14. Titles carry the two teams and the final score but no date. **Hebrew titles read right to left** (the first team named takes the second number); English titles read in order, and the channel publishes both orders for the same game. Pre-2010 uploads use `<competition> <year>, <stage>, <teams> <score>` with no keyword at all. `תרכיז` / "Condensed Game" is a 15-minute condensed replay, distinct from a 3-minute `תקציר`.
- EuroLeague official YouTube: https://www.youtube.com/@EuroLeague — per-round highlights titled `Maccabi - <opponent> | R24 BASKETBALL HIGHLIGHTS 2025-26`, which match games via the `Leg` column (`מחזור 24`), plus `EUROLEAGUE CLASSIC GAMES` full replays. One channel-search request returns every video mentioning Maccabi.
- oren211180 YouTube: https://www.youtube.com/@oren211180 (`UCELBvjBJUq3utCLzDXUoyQA`) — about 1,000 videos from Israeli TV broadcasts, mostly Maccabi basketball 1967–2005: full European Cup / Euroleague games, cup finals, playoff series, and league games from the 1980s–90s. It also has exhibition games and preseason tournaments the wiki has no page for. Uploads from 2025 on follow one format: `<competition> <season> <stage>: <home> - <away> <score>`. **The Hebrew score reads right to left**, as on the club channel, so the first team named takes the second number. The description starts with an English line whose score reads in order, then `<venue>, D/M/YY` and the scorers. That date is the strongest match key, but in the early-1980s finals it is often a few days away from the date on the game page, then the stage in the title or description decides (rules in `.claude/basketball_videos.md`, "Deciding a match the matcher calls uncertain"). Older uploads are short clips with free-form titles (`מכבי ת"א-בני השרון 92:94 בהרצליה, 2007`) and name the home team in no fixed order. The same game is sometimes uploaded twice, once as an old clip and once as a new full broadcast. Also has player features, news items and national-team games, which are not Maccabi game videos.
- The club and EuroLeague channels are matched to game pages automatically by `basketball/videosbot_basketball.py`; see `.claude/basketball_videos.md`.

**Songs:**
- Old songs, Gate 11 forum (Wayback): https://web.archive.org/web/20151129024227/https://www.gate11.co.il/forum/index.php?showtopic=11217

**Photos, posters & tickets:**
- Tickets vs Maccabi Haifa, 1990s (archive.org item): https://archive.org/details/11-ISRAEL-MACCABI-HAIFA-BASKETBALL-TICKETS-STUBS-PC-80-90s-HAPOEL-TEL-AVIV-moka18
- Programmes and tickets in the `historicalbasketballguides` collection: https://archive.org/details/historicalbasketballguides?query=maccabi — about 34 programmes, 1988–2004

**Books:**
- "The Israeli Basketball Book" by Eliyahu Shochat: https://www.yumpu.com/ar/document/read/61848121/-

## Volleyball

**Stats & results:**
- IVA Premier League (from 2010/11 only): https://iva-web.dataproject.com/History.aspx?ID=29
- Walla Sports Volleyball archive (from ~2006): https://sports.walla.co.il/archive/191?year=2006&month=3

**Players & video:**
- Volleybox players: https://volleybox.net/maccabi-tel-aviv-t1631/players
- Volleybox videos: https://volleybox.net/maccabi-tel-aviv-t1631/movies
- Maccabi TLV VC Official YouTube: https://www.youtube.com/@maccabitelavivvc
- Israel Volleyball Association YouTube: https://www.youtube.com/@israelvolleyballassociation — full match broadcasts
- CEV (European Volleyball) YouTube: https://www.youtube.com/@CEVolleyball — Champions League highlights
- Josh Ayzenberg (Maccabi player) YouTube: https://www.youtube.com/@joshayzenberg2259
- Eliezer Kagan YouTube: https://www.youtube.com/@lotemk/videos

**History:**
- Wincol PDF (pre-establishment): https://www.wincol.ac.il/wincol.ac.il/originals/netunim-caduraf.pdf
- Facebook group "כדורעף ושאר סיפורים": https://www.facebook.com/groups/254545287973398

## Handball

Few dedicated sources.
- Fan songs, 12p forum 2009/10: https://forum.12p.co.il/index.php?app=forums&module=forums&controller=topic&id=107974
- Fan songs, 12p forum 2010/11: https://forum.12p.co.il/index.php?app=forums&module=forums&controller=topic&id=126273
- Handball association roster page (2025/26, with a few earlier seasons): https://handballisr.co.il/team.asp?TId=5&cYear=2026

For older rosters/players, try maccabita.co.il and maccabifans via Wayback Machine (see cross-sport section).

## Key coverage gaps

- **Handball**: no stats or video; rosters only for recent seasons
- **Volleyball 1960s–2010**: IVA starts at 2010/11, Wincol PDF covers pre-establishment — middle decades undocumented
- **Football pre-1950s**: RSSSF has tables but no lineups/match details; JPress is the best bet
- **Basketball video pre-1980**: the club's channel starts at 1979/80, so the 1950s-1970s have no known video source. Later decades are covered — see the Basketball **Video** section above.
