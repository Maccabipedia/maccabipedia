"""Set a video-link parameter on a football or basketball game page.

Which template and which parameters are valid comes from SPORT_TEMPLATES, so the same
writer serves both sports. A parameter that already holds a link is never overwritten:
the caller has to notice and decide.
"""
import argparse
import logging

import mwparserfromhell as mw
import pywikibot as pw

from maccabipediabot.common.logging_setup import setup_logging
from maccabipediabot.common.wiki_login import get_site
from maccabipediabot.maintenance.videos.sport_templates import SPORT_TEMPLATES, sport_for_page

logger = logging.getLogger(__name__)

DEFAULT_SPORT = "football"


def default_summary(video_url: str) -> str:
    return f"MaccabiBot - Restore video link from backup upload ({video_url})"


def set_video_field(site: pw.Site, page_title: str, field: str, url: str,
                    summary: str | None = None, sport: str = DEFAULT_SPORT) -> None:
    """Write `url` into the `field` parameter of `page_title`'s game template."""
    if sport not in SPORT_TEMPLATES:
        raise ValueError(f"sport must be one of {sorted(SPORT_TEMPLATES)}, got {sport!r}")
    sport_template = SPORT_TEMPLATES[sport]
    if field not in sport_template.video_params:
        raise ValueError(
            f"field must be one of {list(sport_template.video_params)} for {sport}, got {field!r}"
        )

    page = pw.Page(site, page_title)
    if not page.exists():
        raise LookupError(f"Page not found: {page_title}")

    parsed = mw.parse(page.text)
    templates = parsed.filter_templates(
        matches=lambda template: template.name.strip() == sport_template.template_name)
    if not templates:
        raise LookupError(f"Template '{sport_template.template_name}' not found on {page_title}")
    template = templates[0]

    existing = str(template.get(field).value).strip() if template.has(field) else ""
    if existing:
        raise ValueError(f"Field '{field}' already has a value on {page_title}: {existing}")

    # mwparserfromhell's `add` replaces an existing parameter in place — same pattern
    # as football/gamesbot.py and volleyball/gamesbot_volleyball.py.
    template.add(field, f"{url}\n")
    page.text = str(parsed)
    page.save(summary=summary or default_summary(url), bot=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", required=True,
                        help="Full page title incl. namespace (e.g. 'משחק:16-02-2009 ...')")
    parser.add_argument("--sport", choices=sorted(SPORT_TEMPLATES), default=None,
                        help="Default: inferred from the page's namespace prefix.")
    parser.add_argument("--field", required=True, help="Template parameter to set.")
    parser.add_argument("--url", required=True, help="YouTube URL to set")
    parser.add_argument("--summary", default=None, help="Edit summary (default: from the URL)")
    args = parser.parse_args()

    sport = args.sport or sport_for_page(args.page)
    if sport is None:
        raise SystemExit(f"Cannot tell which sport {args.page!r} belongs to; pass --sport.")

    setup_logging(level=logging.INFO)
    pw.config.verbose_output = False
    set_video_field(get_site(), args.page, args.field, args.url, args.summary, sport=sport)
    logger.info("Updated %s on %s", args.field, args.page)


if __name__ == "__main__":
    main()
