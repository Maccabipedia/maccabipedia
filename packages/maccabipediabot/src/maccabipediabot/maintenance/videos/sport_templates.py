"""Which wiki template and parameters hold a game's video links, per sport.

The sports differ more than they look:

* Football keeps its video links in the Cargo table ``Games_Videos``; ``Football_Games``
  has no video columns at all. Its template has one full-game parameter and two
  highlight ones.
* Basketball and volleyball keep theirs on their own game tables, with two of each.

The basketball template also accepts a third and fourth slot of each kind for DISPLAY,
but passes only the first two to Cargo, so only those two are listed here: a link in
slot three would render on the page and be invisible to every Cargo-driven tool.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SportTemplate:
    """The game template of one sport and the video parameters it stores in Cargo."""
    sport: str
    template_name: str
    page_prefix: str
    full_game_params: tuple[str, ...]
    highlights_params: tuple[str, ...]

    @property
    def video_params(self) -> tuple[str, ...]:
        return self.full_game_params + self.highlights_params


FOOTBALL = SportTemplate(
    sport="football",
    template_name="קטלוג משחקים",
    page_prefix="משחק:",
    full_game_params=("משחק מלא",),
    highlights_params=("תקציר וידאו", "תקציר וידאו2"),
)

BASKETBALL = SportTemplate(
    sport="basketball",
    template_name="משחק כדורסל",
    page_prefix="כדורסל:",
    full_game_params=("משחק מלא", "משחק מלא2"),
    highlights_params=("תקציר וידאו", "תקציר וידאו2"),
)

SPORT_TEMPLATES: dict[str, SportTemplate] = {
    FOOTBALL.sport: FOOTBALL,
    BASKETBALL.sport: BASKETBALL,
}


def sport_for_page(page_name: str) -> str | None:
    """Which sport a game page belongs to, judged by its namespace prefix."""
    for sport_template in SPORT_TEMPLATES.values():
        if page_name.startswith(sport_template.page_prefix):
            return sport_template.sport
    return None
