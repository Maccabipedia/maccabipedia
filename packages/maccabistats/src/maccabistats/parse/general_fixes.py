import logging

from maccabistats.parse.add_manual_games import add_manual_games
from maccabistats.parse.teams_names_changer import teams_names_changer

logger = logging.getLogger(__name__)

# The format is like that:  ("real name", ["possible wrongs name", "another one"])
_referees_name_fixes = [("איתן שמואלביץ", ["איתן שמואלביץ'", "שמואלביץ איתן"]),
                        ("רועי ריינשרייבר", ["רועי רנשרייבר"]),
                        ("גל לייבוביץ", ["גל לייבוביץ'", "גל ליבוביץ'"]),
                        ("חיים ליפקוביץ", ["חיים ליפקוביץ'"]),
                        ("ג'ורג' אשקר", ["גורג' אשקר"]),
                        ("איבן בבק", ["איבאן בבק"]),
                        ("סרג' גומייני", ["סרג גומיני", "סרג' גאמייני"]),
                        ("רחמים דינאצ'י", ["רחמים דיאנצ'י"]),
                        ("משה מזרחי", ["משה מיזרחי"]),
                        ("חיים יעקב", ["חיים יעקוב"]),
                        ("יאיר טילינגר", ["יאיר טליגר"]),
                        ("אנדריס טרימאניס", ["אנדריס טריימאניס"]),
                        ("ליאור קורנפלד", ["ליאור קרונפלד"]),
                        ("יהושע לויה", ["יהושוע לויה"]),
                        ("סבי אלנקווה", ["בני אלנקווה"]),
                        ("מרכוס עוזיאל", ["מרקוס עוזיאל"]),
                        ]

# The format is like referees above.
_players_name_fixes = [("מיקו בלו", ["מנחם 'מיקו' בלו"]),
                       ("יוסף מרימוביץ'", ["יוסל'ה מרימוביץ'"]),
                       ("טל בן חיים (הבלם)", ["טל בן חיים"]),
                       ("איציק זוהר", ["זוהר"]),
                       ("בן בן יאיר", ["בן בן-יאיר"]),
                       ("שאול בן דוד", ["שאול בן דויד"]),
                       ("אלירן ג'ורג'", ["אלירן ג'ורג"]),
                       ("גונסאלו גארסיה", ["גונזאלו גארסיה"]),
                       ("וידאר קיארטאנסון", ["וידאר קיארטנסון"]),
                       ("עמוס זלוטולוב", ["זלוטולוב"]),
                       ("אופיר חיים", ["א.חיים"]),
                       ("רוברט סקארלט", ["סקארלט"]),
                       ("סהר חסון", ["סער חסון"]),
                       ("יוסי מזרחי (הקשר)", ["יוסי מזרחי"]),
                       ("גרינגרוס איזמן", ["גרינגרוס"]),
                       ("אלדו אדורנו", ["אוסמר"]),
                       ("עומרי בן הרוש", ["עמרי בן הרוש"]),
                       ("ברנדלי קובאס", ["בראנדלי קוואס", "בראנדלי קובאס"]),
                       ]

# The format is like players above.
_competitions_name_fixes = [("גביע אירופה למחזיקות גביע", ["גביע אירופה למחזיקות"]),
                            ("מוקדמות הליגה האירופית", ["מוקדמות ליגה אירופית"]),
                            ("גביע אסיה לאלופות", ["גביע אסיה"]),
                            ("פלייאוף הליגה האירופית", ["פלייאוף אירופה ליג"]),
                            ("גביע אופא", ['גביע אופ"א']),
                            ("הליגה האירופית", ["ליגה אירופית"]),
                            ("ליגת העל",
                             ["ליגת Winner", "ליגת הבורסה לניירות ערך", "ליגת ג׳פניקה", "ליגת one zero הבנק הדיגיטלי",
                              "ליגת WINNER"]),
                            ("ליגה לאומית", ["ליגת לאומית"]),
                            ("ליגה א", ["ליגה א'"]),
                            ("הליגה האזורית", ["מוקדמות קונפרנס ליג", "קונפרנס ליג"]),
                            ]

# the format is like the players above.
_stadiums_name_fixes = [("אצטדיון לוד", ["לוד"]),
                        ("אצטדיון נתניה", ["נתניה"]),
                        ("אצטדיון המושבה", ["המושבה"]),
                        ("מגרש גלי גיל", ["גלי גיל"]),
                        ("אצטדיון לוד הישן", ["לוד הישן"]),
                        ("מגרש קטמון", ["קטמון"]),
                        ("מגרש מכבי פתח תקווה", ["מכבי פת"]),
                        ("אצטדיון שכונת התקווה", ["שכונת התקווה"]),
                        ("נובה גוריצה", ["ספורטני פארק"]),
                        ("אצטדיון עילוט", ["עילוט"]),
                        ("ספורטק נס ציונה", ["נס ציונה הישן"]),
                        ("אצטדיון לויטה", ["לויטה"]),
                        ("אצטדיון גרופאמה", ["גרופאמה ארנה, בודפשט"]),
                        ("אצטדיון קריית אליעזר", ["קרית אליעזר"]),
                        ("אצטדיון סלה", ["אשקלון"]),
                        ("האיצטוני", ["מרמורק"]),
                        ("אצטדיון רמת גן", ["אצטדיון רג"]),
                        ("אצטדיון עירוני קריית שמונה", ["קריית שמונה"]),
                        ("אצטדיון הקופסה", ["הקופסה"]),
                        ("אצטדיון עירוני הרצליה", ["הרצליה"]),
                        ("אצטדיון גאון", ["גאון"]),
                        ("אצטדיון באסה", ["באסה"]),
                        ("אצטדיון קריית חיים", ["קרית חיים"]),
                        ('אצטדיון ימק"א', ["ימקא"]),
                        ("אצטדיון לה סרמיקה", ["לה סרמיקה"]),
                        ("אצטדיון דרובטה-טורנו סברין", ["דורבטה טורנו-סברין"]),
                        ("מגרש שעריים", ["שעריים"]),
                        ("אצטדיון מכבי חדרה", ["מכבי חדרה"]),
                        ('אצטדיון הי"א', ["היא"]),
                        ("אצטדיון רמת עמידר", ["רמת עמידר"]),
                        ("אצטדיון גרין", ["גרין"]),
                        ("אצטדיון טדי", ["טדי"]),
                        ("אצטדיון דוחה", ["דוחא"]),
                        ("אצטדיון טוברוק", ["טוברוק"]),
                        ("אצטדיון אנרגה גדאנסק", ["גדנסק, פולין"]),
                        ("האצטדיון העירוני נתניה", ["נתניה החדש"]),
                        ("אצטדיון וינטר", ["וינטר"]),
                        ("אצטדיון אלמטי", ["אלמטי סטאדיום"]),
                        ("מגרש הפחים", ["ראשלצ הישן"]),
                        ("אצטדיון עכו", ["טוטו - עכו"]),
                        ("אצטדיון האורווה", ["האורווה"]),
                        ("אצטדיון המכביה", ["המכביה"]),
                        ("האצטדיון העירוני קריית גת", ["קרית גת"]),
                        ("אצטדיון עכו", ["עכו החדש"]),
                        ("אצטדיון סמי עופר", ["סמי עופר"]),
                        ("אצטדיון המכתש", ["המכתש"]),
                        ("אצטדיון טרנר", ["טרנר"]),
                        ("אצטדיון הברפלד", ["הברפלד"]),
                        ("אצטדיון טיבולי נוי", ["איצטדיון טיבולי-נאו"]),
                        ("אצטדיון טלאגט", ["טאלגאט סטדיום"]),
                        ("מגרש הפרדסים", ["הפרדסים"]),
                        ("מגרש הפחים (יפו)", ["יפו הישן"]),
                        ("NSK אולימפיסקי", ["אולימפיסקי"]),
                        ("אצטדיון נפוליאון", ["נפוליאון"]),
                        ("אצטדיון וסרמיל", ["וסרמיל"]),
                        ("אצטדיון עירוני קריית שמונה", ["קרית שמונה"]),
                        ("אצטדיון גרונדמן", ["גרונדמן"]),
                        ("אצטדיון פוליוד", ["פוליוד"]),
                        ("קיי.אר. וולר", ["KR וולור"]),
                        ("אצטדיון בית שאן", ["בית שאן"]),
                        ("אצטדיון לנין", ["אצטדיון פטרובסקי"]),
                        ("מגרש הפועל (הבריכה)", ["פת הישן"]),
                        ("אצטדיון אפאס", ["אפאס סטדיון"]),
                        ("אצטדיון בלומפילד", ["בלומפילד"]),
                        ]


def __fix_teams_names(game):
    if game.not_maccabi_team.name in teams_names_changer:
        old_team_name = game.not_maccabi_team.name
        game.not_maccabi_team.current_name = teams_names_changer[old_team_name].current_name
        
        game.not_maccabi_team.name = teams_names_changer[old_team_name].change_name(game)
        # Some teams names wont be changed (because the mapping is between team original name and the team name along the years)
        if old_team_name != game.not_maccabi_team.name:
            logger.info(f"Changing {'Home' if game.is_maccabi_home_team else 'Away'} team name from: "
                        f"{old_team_name}-->{game.not_maccabi_team.name}")


def __fix_referees_names(game):
    for referee_best_name, referee_similar_names in _referees_name_fixes:
        if game.referee in referee_similar_names:
            logger.info("Changing referee name from :{old}-->{new}".format(old=game.referee, new=referee_best_name))
            game.referee = referee_best_name


def __fix_competitions_names(game):
    for competition_best_name, competition_similar_name in _competitions_name_fixes:
        if game.competition in competition_similar_name:
            logger.info(
                "Changing competition name from :{old}-->{new}".format(old=game.competition, new=competition_best_name))
            game.competition = competition_best_name


def __fix_maccabi_players_names(game):
    for player in game.maccabi_team.players:
        for player_best_name, player_similar_names in _players_name_fixes:
            # TODO: this is a huge patch, Maccabi tlv site doing balagan with Tal ben haim names, we can assume that the defender won't come back to maccabi anymore as a player:
            if player.name == 'טל בן חיים' and game.season >= '2020/21':
                logger.info("Changing Tel ben haim (Striker) player name (Special case)")
                player.name = 'טל בן חיים (החלוץ)'
                break
            elif player.name in player_similar_names:
                logger.info("Changing player name from :{old}->{new}".format(old=player.name, new=player_best_name))
                player.name = player_best_name
                break


def __fix_stadiums_names(game):
    for stadium_best_name, stadium_similar_names in _stadiums_name_fixes:
        if game.stadium in stadium_similar_names:
            logger.info("Changing stadium name from :{old}-->{new}".format(old=game.stadium, new=stadium_best_name))
            game.stadium = stadium_best_name


def __fix_fixtures(game):
    # If game played in the first league
    if game.competition in ["ליגת העל", "ליגה לאומית", "ליגת הבורסה לניירות ערך", "ליגת Winner", "ליגה א'"]:
        if isinstance(game.fixture, int):
            logger.info(f"Adding 'מחזור' prefix to the ame at {game.date})")
            game.fixture = f"מחזור {game.fixture}"


def __fix_seasons(game):
    """
    Remove ' - ' from season and replace it with ' / '.
    """

    if "-" in game.season:
        logger.info("Replacing '-' with '/' in game season")
        game.season = game.season.replace('-', '/')


def __remove_empty_players(game):
    """
    Remove all empty players (if exists), saw some on maccabi site.
    """

    before_removing_empty_players = len(game.maccabi_team.players)
    game.maccabi_team.players = [player for player in game.maccabi_team.players if player.name]

    if before_removing_empty_players != len(game.maccabi_team.players):
        logger.info(
            f"Removed {before_removing_empty_players - len(game.maccabi_team.players)} empty players from game played at :{game.date}")


def __remove_youth_games(maccabi_games_stats):
    # TODO: remove this when we start manipulating youth statistics
    youth_competitions_names = ['גביע המדינה לנוער', 'ליגת העל לנוער']
    logger.info("Removing youth games if exists:(")
    return maccabi_games_stats.create_maccabi_stats_from_games(
        [game for game in maccabi_games_stats.games if game.competition not in youth_competitions_names])


def run_general_fixes(maccabi_games_stats):
    """
    General fixes meant to be stuff like renaming of referees\players names and so on, they are does not depend on the source of maccabi games.
    :type maccabi_games_stats: maccabistats.stats.maccabi_games_stats.MaccabiGamesStats
    :rtype: maccabistats.stats.maccabi_games_stats.MaccabiGamesStats
    """

    for game in maccabi_games_stats.games:
        __fix_teams_names(game)
        __fix_referees_names(game)
        __fix_stadiums_names(game)
        __fix_competitions_names(game)
        __fix_maccabi_players_names(game)
        __fix_seasons(game)
        __fix_fixtures(game)
        __remove_empty_players(game)

    maccabi_games_stats = __remove_youth_games(maccabi_games_stats)

    add_manual_games(maccabi_games_stats)

    return maccabi_games_stats
