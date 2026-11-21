"""Save the loaded basketball games to a pickle and read them back, like football's serialized_games."""
import datetime
import logging
import pickle
from pathlib import Path
from typing import Optional

from maccabistats.basketball.stats import BasketballGamesStats
from maccabistats.version import version

logger = logging.getLogger(__name__)

_serialized_basketball_games_folder_path = Path.home() / "maccabistats" / "basketball"
_serialized_basketball_games_file_name_pattern = "basketball-{version}-{date}.games"


def serialize_basketball_games(basketball_games_stats: BasketballGamesStats,
                               folder_path: Path | str = _serialized_basketball_games_folder_path) -> Path:
    if not isinstance(basketball_games_stats, BasketballGamesStats):
        raise RuntimeError("You should serialize only a BasketballGamesStats object")

    folder_path = Path(folder_path)
    folder_path.mkdir(parents=True, exist_ok=True)
    file_path = folder_path / _serialized_basketball_games_file_name_pattern.format(
        version=basketball_games_stats.version, date=datetime.date.today())
    with open(file_path, "wb") as f:
        pickle.dump(basketball_games_stats, f)

    logger.info(f"Serialized basketball games to {file_path}")
    return file_path


def get_basketball_stats(file_name: Optional[Path | str] = None) -> BasketballGamesStats:
    """
    :param file_name: Pickled basketball games. When no file is given, the newest basketball-*.games
                      from the default folder is loaded.

    A pickle written by another maccabistats version is refused: the game model may have changed
    since, and an old pickle would answer with the old fields. Load again from MaccabiPedia instead.
    """
    if file_name is None:
        files_in_default_folder = list(_serialized_basketball_games_folder_path.glob(
            _serialized_basketball_games_file_name_pattern.format(version="*", date="*")))
        if not files_in_default_folder:
            raise RuntimeError(f"No basketball-*.games in {_serialized_basketball_games_folder_path}, use "
                               f"serialize_basketball_games(load_basketball_from_maccabipedia()) to make one")
        file_name = max(files_in_default_folder, key=lambda file_path: file_path.stat().st_ctime)
    elif not Path(file_name).is_file():
        raise RuntimeError(f"No such file: {file_name}, use "
                           f"serialize_basketball_games(load_basketball_from_maccabipedia()) to make one")

    with open(file_name, "rb") as f:
        logger.info(f"Loading basketball games from {file_name}")
        basketball_games_stats = pickle.load(f)

    if basketball_games_stats.version != version:
        raise RuntimeError(f"{file_name} was written by maccabistats {basketball_games_stats.version} and this is "
                           f"{version}, load again with load_basketball_from_maccabipedia()")
    return basketball_games_stats
