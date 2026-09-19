import re
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1024)
def normalize_name(name):
    """
    Try to normalize name as possible.
    Remove duplicated spaces, remove ltr nd rtl unicode marks.
    :param name: The name to normalize.
    :type name: str
    :rtype: str
    """

    # Remove special rtl and ltr marks
    stripped_name = name.replace("\u202a", "").replace("\u200f", "").strip()
    if stripped_name != name:
        logger.debug('stripped_name: {new_name}--->{old_name}'.format(new_name=stripped_name, old_name=name))

    # Remove backslash
    name_without_special_chars = stripped_name.replace("\\", "").strip()
    if name_without_special_chars != stripped_name:
        logger.debug('name_without_special_chars: {new_name}--->{old_name}'.format(new_name=name_without_special_chars, old_name=name))

    # Remove duplicated spaces
    normalized_name = re.sub('\s+', ' ', name_without_special_chars)
    if normalized_name != name_without_special_chars:
        logger.debug('normalized_name: {new_name}--->{old_name}'.format(new_name=normalized_name, old_name=name))

    # Hebrew geresh (ג׳יימס) to apostrophe (ג'יימס), the way MaccabiPedia writes names
    name_with_apostrophe = normalized_name.replace("׳", "'")
    if name_with_apostrophe != normalized_name:
        logger.debug('name_with_apostrophe: {new_name}--->{old_name}'.format(new_name=name_with_apostrophe, old_name=name))

    return name_with_apostrophe
