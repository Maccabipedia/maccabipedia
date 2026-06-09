import logging
from collections.abc import Iterable

import pywikibot as pw

logger = logging.getLogger(__name__)

# MediaWiki caps the number of titles accepted by a single purge request
# (50 for regular accounts, 500 for bots). Stay at 50 so the bulk call works
# regardless of the account's rights.
_PURGE_CHUNK_SIZE = 50


def purge_pages(
    site: pw.Site,
    pages: Iterable[str | pw.Page],
    *,
    dry_run: bool = False,
    chunk_size: int = _PURGE_CHUNK_SIZE,
) -> int:
    """Purge pages in bulk so DPL/Cargo caches refresh.

    Accepts page titles or ``Page`` objects, dedups them, and submits them to
    the MediaWiki purge API with ``forcelinkupdate=True`` in chunks of
    ``chunk_size``. This issues one HTTP request per chunk instead of one per
    page (the per-page approach the football/volleyball bots used to carry).

    Returns the number of unique pages submitted for purging.
    """
    # Dedup + sort here (not just relying on purgepages' own set()) so the
    # chunk boundaries below are deterministic and the returned count is accurate.
    titles = sorted({page if isinstance(page, str) else page.title() for page in pages})
    if not titles:
        return 0

    if dry_run:
        logger.info("[DRY-RUN] Would purge %d pages with forcelinkupdate=true", len(titles))
        return len(titles)

    logger.info("Purging %d pages with forcelinkupdate=true", len(titles))
    for start in range(0, len(titles), chunk_size):
        chunk = titles[start:start + chunk_size]
        if not site.purgepages(chunk, forcelinkupdate=True):
            # purgepages returns False when a title in the chunk wasn't
            # purged/link-updated — almost always because the page doesn't
            # exist yet, which is harmless here.
            logger.info("Some of %d pages in this chunk were not purged (likely don't exist yet)", len(chunk))

    return len(titles)
