import contextlib
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from maccabipediabot.common.page_names import build_football_game_page_name
from maccabipediabot.common.wiki_login import get_site

import math
import pywikibot as pw
from mwparserfromhell.nodes.template import Template

from maccabistats import load_from_maccabipedia_source
from maccabistats.models.game_data import GameData
from maccabistats.stats.maccabi_games_stats import MaccabiGamesStats

from maccabipediabot.common.logging_setup import setup_logging
setup_logging(level=logging.INFO)

# Paper name format:
# {שם_עיתון}_{תאריך_המשחק}_{שם_היריבה}_{מספר_עיתון_אם_יש_כמה}_({תאריך_פרסום_העיתון})

_logger = logging.getLogger(__name__)

_CURRENT_FOLDER = Path(__file__).absolute().parent

_PAPER_TAG_TEMPLATE_NAME = "תיוג עיתונים"

_PAPER_NAME_PARAM_NAME = "שם עיתון"
_PAPER_PUBLISH_DATE_PARAM_NAME = "תאריך פרסום"
_PAPER_RELATED_GAME_PARAM_NAME = "שיוך משחק"

_PAPER_NAME_ENV_VAR_NAME = "PAPER_NAME"

site = get_site()

SHOULD_SAVE = True


@dataclass
class PaperGameDetails:
    paper_name: str
    paper_related_game_date: datetime
    paper_publish_date: Optional[datetime] = None

    def to_mediawiki_template(self, maccabi_games: MaccabiGamesStats) -> str:
        tag_paper_template = Template(f'{_PAPER_TAG_TEMPLATE_NAME}\n')

        tag_paper_template.add(_PAPER_NAME_PARAM_NAME, f'{self.paper_name}\n')

        if self.paper_publish_date is not None:
            tag_paper_template.add(_PAPER_PUBLISH_DATE_PARAM_NAME, f'{self.paper_publish_date.strftime("%d-%m-%Y")}\n')

            if math.fabs((self.paper_publish_date - self.paper_related_game_date).days) > 7:
                raise RuntimeError(f'There is more than a week between the publish and the game date, is it an error?')

        potential_games = maccabi_games.played_at(self.paper_related_game_date)
        if len(potential_games) != 1:
            raise RuntimeError(f'Could not match exactly one game for date: {self.paper_related_game_date}, '
                               f'found these games: {potential_games}')

        game_page_name = _generate_page_name_from_game(potential_games[0])
        tag_paper_template.add(_PAPER_RELATED_GAME_PARAM_NAME, f'{game_page_name}')

        return str(tag_paper_template)


class DuplicateMaccabipediaPageException(Exception):
    pass


def _generate_page_name_from_game(game: GameData):
    page_name = build_football_game_page_name(
        game_date=game.date,
        home_team=game.home_team.name,
        away_team=game.away_team.name,
        competition=game.competition,
    )

    return page_name


def _try_to_cast_date_str_to_datetime(date_str: str) -> datetime:
    """
    Try the options we support (from _parse_paper_file_name) by the same order we try to parse them
    """
    formats = ['%d-%m-%Y', '%Y-%m-%d', '%d.%m.%Y', '%Y.%m.%d']

    for date_format in formats:
        with contextlib.suppress(ValueError):
            parsed_date = datetime.strptime(date_str, date_format)

            return parsed_date

    raise ValueError(f'no valid date format found for: {date_str}')


def _parse_paper_file_name(paper_file_name: str) -> PaperGameDetails:
    potential_dates = re.findall(r'\d{2}-\d{2}-\d{4}', paper_file_name)
    potential_publish_date = re.findall(r'\d{2}\.\d{2}\.\d{4}', paper_file_name)

    if len(potential_dates) > 2:
        raise RuntimeError(
            f'Found too much dates ({len(potential_dates)}) in this paper name: {paper_file_name}')

    if not potential_dates:
        raise TypeError(f'Could not find game date in this paper name: {paper_file_name}')

    game_date = _try_to_cast_date_str_to_datetime(potential_dates[0])

    # We want the paper name without any underscores (if such exists to avoid mediawiki files correcting)
    # Take the part before the first date and remove paddings
    paper_name = os.environ.get(_PAPER_NAME_ENV_VAR_NAME,
                                paper_file_name.split(potential_dates[0])[0].replace("_", " ").strip())
    if not paper_name.strip():
        raise RuntimeError("Paper name is empty!")

    publish_date = None
    if potential_publish_date:
        publish_date = _try_to_cast_date_str_to_datetime(potential_publish_date[0])

    return PaperGameDetails(paper_name=paper_name,
                            paper_related_game_date=game_date,
                            paper_publish_date=publish_date)


class UploadGamesPapers:

    def __init__(self, base_papers_folder: Path):
        self.base_papers_folder = base_papers_folder
        self.maccabi_games = load_from_maccabipedia_source()

    def upload_papers(self) -> None:
        _logger.info(f'Starting to upload papers, base folder: {self.base_papers_folder}')
        self._validate_folders_exists()

        for paper_file in self.input_folder.iterdir():
            _logger.info(f'Handling paper: {paper_file}')

            # noinspection PyBroadException
            try:
                self._handle_paper(paper_file)
                _logger.info(f'successfully uploaded paper: {paper_file}, moving to: {self.passed_folder}')
                paper_file.rename(self.passed_folder / paper_file.name)
            except DuplicateMaccabipediaPageException:
                _logger.exception(f'This paper: {paper_file} already exists, '
                                  f'moving paper to: {self.failed_folder}')
                paper_file.rename(self.duplicate_folder / paper_file.name)
            except Exception:
                _logger.exception(f'Unhandled error while handling paper: {paper_file}, '
                                  f'moving paper to: {self.failed_folder}')
                paper_file.rename(self.failed_folder / paper_file.name)

    def _handle_paper(self, paper_file: Path) -> None:
        # In case we have override paper name for all of this chunk, let's add it to the paper name
        override_paper_name = f'{os.environ[_PAPER_NAME_ENV_VAR_NAME]} ' if _PAPER_NAME_ENV_VAR_NAME in os.environ else ''
        if not override_paper_name:
            raise Exception("Comment this if you are you want to upload without an overriding paper name")

        final_paper_name = paper_file.name
        if override_paper_name and not final_paper_name.startswith(override_paper_name):
            raise Exception(f"File: {paper_file} don't start with the paper name")
            # final_paper_name = f'{override_paper_name}{final_paper_name}'

        paper_maccabipedia_page = pw.FilePage(site, final_paper_name)

        if paper_maccabipedia_page.exists():
            raise DuplicateMaccabipediaPageException(f'{paper_file}, {paper_maccabipedia_page.title()}')

        paper_details = _parse_paper_file_name(paper_file.stem)
        tag_paper_template = paper_details.to_mediawiki_template(self.maccabi_games)

        paper_maccabipedia_page.text = str(tag_paper_template)
        _logger.info(f'Page text: {paper_maccabipedia_page.text}')

        if SHOULD_SAVE:
            paper_maccabipedia_page.upload(str(paper_file),
                                           comment="Upload paper game with MaccabiPediaBot",
                                           ignore_warnings=True)
            _logger.info(f'Uploaded: {paper_file}')

    def _validate_folders_exists(self) -> None:
        _logger.info("Validating folders exist")
        self.base_papers_folder.mkdir(parents=True, exist_ok=True)

        self.input_folder.mkdir(parents=True, exist_ok=True)
        self.failed_folder.mkdir(parents=True, exist_ok=True)
        self.passed_folder.mkdir(parents=True, exist_ok=True)
        self.duplicate_folder.mkdir(parents=True, exist_ok=True)

    @property
    def input_folder(self):
        return self.base_papers_folder / 'input'

    @property
    def failed_folder(self):
        return self.base_papers_folder / 'failed'

    @property
    def passed_folder(self):
        return self.base_papers_folder / 'passed'

    @property
    def duplicate_folder(self):
        return self.base_papers_folder / 'duplicate'


if __name__ == '__main__':
    # Format example:
    # מעריב 29-09-1973 הפועל בני נצרת (30.09.1973).jpg
    if _PAPER_NAME_ENV_VAR_NAME in os.environ:
        _logger.info(f'Found Paper name env var: {os.environ[_PAPER_NAME_ENV_VAR_NAME]}, '
                     f'override this as the only paper name in this chunk')

    upload_games_papers_bot = UploadGamesPapers(_CURRENT_FOLDER.parent.parent / 'games_papers_to_upload')
    upload_games_papers_bot.upload_papers()
