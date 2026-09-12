"""Render the review page: every proposed match, with links, before anything is written.

Read in a browser from ~/served_reports, so it follows the look of the reports already
there (Maccabi blue and yellow, right-to-left, one section per season).
"""
import html
from collections import Counter, defaultdict
from datetime import date

from maccabipediabot.basketball.videos.confidence import MAX_SCORE, MIN_SCORE
from maccabipediabot.basketball.videos.matcher import Bucket, VideoMatch

WIKI_BASE_URL = "https://www.maccabipedia.co.il"

_BUCKET_LABELS = {
    Bucket.EXACT: "התאמה ודאית",
    Bucket.AMBIGUOUS: "דורש הכרעה",
    Bucket.UNMATCHED: "ללא התאמה",
    Bucket.ALREADY_PRESENT: "כבר קיים בדף",
    Bucket.OVERFLOW: "אין מקום פנוי",
}

_STYLE = """
:root{--blue:#0a2a66;--yellow:#ffe000;--line:#e3e6eb;--bg:#f6f7f9;--card:#fff;--muted:#5b6470}
*{box-sizing:border-box}
body{margin:0;padding:18px;background:var(--bg);color:#1b1f24;
     font:15px/1.5 "Segoe UI",Arial,sans-serif}
.wrap{max-width:1100px;margin:0 auto}
h1{color:var(--blue);margin:0 0 4px;font-size:1.5rem}
.sub{color:var(--muted);margin:0 0 18px;font-size:.9rem}
.counts{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 20px;padding:0;list-style:none}
.counts li{background:var(--card);border:1px solid var(--line);border-radius:10px;
           padding:9px 14px;min-width:130px}
.counts .n{display:block;font-size:1.35rem;font-weight:700;color:var(--blue)}
.counts .k{font-size:.8rem;color:var(--muted)}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;
        margin:0 0 11px;padding:10px 14px}
summary{cursor:pointer;font-weight:600;color:var(--blue)}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:.87rem}
th,td{text-align:right;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;white-space:nowrap}
a{color:var(--blue)}
.b-exact{border-right:4px solid #1a7f37}
.b-ambiguous{border-right:4px solid #bf8700}
.b-unmatched{border-right:4px solid #b35900}
.b-already_present,.b-overflow{border-right:4px solid var(--line)}
.tag{display:inline-block;padding:1px 7px;border-radius:20px;background:#eef1f6;
     font-size:.76rem;color:var(--muted);white-space:nowrap}
.score{font-variant-numeric:tabular-nums;white-space:nowrap}
"""


def wiki_url(page_name: str) -> str:
    """Maccabipedia serves articles on a bare path."""
    return f"{WIKI_BASE_URL}/{page_name.replace(' ', '_')}"


def _escape(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def _page_link(page_name: str) -> str:
    return f'<a href="{_escape(wiki_url(page_name))}" target="_blank">{_escape(page_name)}</a>'


def _target_cell(match: VideoMatch) -> str:
    if match.page_name:
        return _page_link(match.page_name)
    if match.candidates:
        return "<br>".join(_page_link(candidate) for candidate in match.candidates)
    return "—"


_SCORE_HEADINGS = {
    10: "10 — ודאי: תוצאה ייחודית לעונה, שם היריבה תואם, והסרטון הועלה בתוך ימים מהמשחק",
    9: "9 — חזק: כל הראיות מסכימות, אך ללא אישור ברמת היום — העלאה מאוחרת או ארכיונית "
       "שהשנה בכותרת מאששת",
    8: "8 — דורש עין: ראיה אחת חסרה או סותרת, למשל שם יריבה שאינו תואם לדף",
    7: "7 — העלאה ארכיונית ללא שנה בכותרת: אין אות תאריך כלל",
    6: "6 — חסרות שתי ראיות",
    5: "5 — בינוני",
    4: "4 — חלש",
    3: "3 — חלש מאוד",
    2: "2 — השנה בכותרת סותרת את שנת המשחק",
    1: "1 — לא לכתוב: הסרטון הועלה לפני שהמשחק שוחק",
}


def _match_row(match: VideoMatch) -> str:
    parsed = match.parsed
    score = (f"{parsed.maccabi_points}:{parsed.opponent_points}" if parsed else "—")
    opponent = parsed.opponent_raw if parsed else "—"
    kind = match.kind.value if match.kind else "—"
    days = "—" if match.days_after_game is None else f"{match.days_after_game:+d}"
    return (
        f'<tr class="b-{match.bucket.value}">'
        f'<td class="score"><b>{_escape(match.confidence if match.confidence else "—")}</b></td>'
        f'<td><a href="{_escape(match.url)}" target="_blank">{_escape(match.entry.title)}</a></td>'
        f"<td>{_escape(match.entry.season)}</td>"
        f'<td><span class="tag">{_escape(match.source)}</span></td>'
        f'<td><span class="tag">{_escape(kind)}</span></td>'
        f'<td class="score">{_escape(score)}</td>'
        f"<td>{_escape(opponent)}</td>"
        f'<td class="score">{_escape(days)}</td>'
        f'<td><span class="tag">{_escape(_BUCKET_LABELS.get(match.bucket, match.bucket.value))}</span></td>'
        f"<td>{_escape(match.reason)}</td>"
        f"<td>{_target_cell(match)}</td>"
        f"<td>{_escape(match.slot or '—')}</td>"
        f"</tr>"
    )


_TABLE_HEAD = (
    "<table><thead><tr>"
    "<th>ציון</th><th>סרטון</th><th>עונה</th><th>ערוץ</th><th>סוג</th><th>תוצאה</th>"
    "<th>יריבה</th><th>ימים מהמשחק</th><th>סטטוס</th><th>סיבה</th>"
    "<th>דף המשחק</th><th>פרמטר</th>"
    "</tr></thead><tbody>"
)


def _score_section(score: int, matches: list[VideoMatch], open_by_default: bool) -> str:
    rows = "\n".join(_match_row(match) for match in matches)
    heading = _SCORE_HEADINGS.get(score, str(score))
    return (
        f"<details{' open' if open_by_default else ''}>"
        f"<summary>{_escape(heading)} — {len(matches)} סרטונים</summary>"
        f"{_TABLE_HEAD}{rows}</tbody></table></details>"
    )


def _unwritable_section(matches: list[VideoMatch]) -> str:
    if not matches:
        return ""
    counts = Counter(match.bucket for match in matches)
    summary_bits = ", ".join(
        f"{_BUCKET_LABELS.get(bucket, bucket.value)}: {count}"
        for bucket, count in sorted(counts.items(), key=lambda item: item[0].value)
    )
    rows = "\n".join(_match_row(match) for match in
                     sorted(matches, key=lambda match: (match.bucket.value, match.entry.season)))
    return (
        f"<details><summary>לא ייכתב — {len(matches)} סרטונים ({_escape(summary_bits)})"
        f"</summary>{_TABLE_HEAD}{rows}</tbody></table></details>"
    )


_VERDICT_LABELS = {
    "confirmed": "אושר",
    "late upload": "הועלה באיחור",
    "date mismatch": "תאריך לא תואם",
    "no date signal": "אין אות תאריך",
}


def render_sample_section(checks: list) -> str:
    """The verification sample, pinned above the per-season detail.

    Each row pairs what the matcher decided with the video's real upload date, which
    the matcher never saw.
    """
    if not checks:
        return ""
    counts = Counter(check.verdict.value for check in checks)
    summary = " · ".join(f"{_VERDICT_LABELS.get(verdict, verdict)}: {count}"
                         for verdict, count in sorted(counts.items()))
    rows = []
    for check in checks:
        match = check.match
        days = "—" if check.days_apart is None else f"{check.days_apart:+d}"
        rows.append(
            f"<tr>"
            f'<td><a href="{_escape(match.url)}" target="_blank">{_escape(match.entry.title)}</a></td>'
            f"<td>{_page_link(match.page_name)}</td>"
            f"<td>{_escape(check.game_date)}</td>"
            f"<td>{_escape(check.opponent)}</td>"
            f"<td>{_escape(check.home_away)}</td>"
            f'<td class="score">{_escape(match.parsed.maccabi_points if match.parsed else "")}'
            f':{_escape(match.parsed.opponent_points if match.parsed else "")}</td>'
            f"<td>{_escape(check.upload_date or '—')}</td>"
            f'<td class="score">{_escape(days)}</td>'
            f'<td><span class="tag">{_escape(_VERDICT_LABELS.get(check.verdict.value, check.verdict.value))}</span></td>'
            f"</tr>"
        )
    return (
        '<details open><summary>בדיקת מדגם — 20 התאמות מול תאריך ההעלאה האמיתי '
        f"({_escape(summary)})</summary>"
        '<p class="sub">תאריך ההעלאה הוא אות עצמאי: המתאם לא רואה אותו. סרטון שהועלה '
        "ביום המשחק מאשר את ההתאמה; סרטון ארכיוני שהועלה שנים אחר כך לא מעיד לכאן ולכאן.</p>"
        "<table><thead><tr>"
        "<th>סרטון</th><th>דף המשחק</th><th>תאריך המשחק</th><th>יריבה</th><th>בית/חוץ</th>"
        "<th>תוצאה בכותרת</th><th>הועלה</th><th>הפרש ימים</th><th>ממצא</th>"
        "</tr></thead><tbody>"
        f"{''.join(rows)}"
        "</tbody></table></details>"
    )


def _score_counts_list(writable: list[VideoMatch], unwritable: list[VideoMatch],
                       skipped_non_game: int) -> str:
    counts = Counter(match.confidence for match in writable)
    items = [
        f'<li><span class="n">{counts.get(score, 0)}</span>'
        f'<span class="k">ציון {score}</span></li>'
        for score in range(MAX_SCORE, 0, -1) if counts.get(score)
    ]
    items.append(f'<li><span class="n">{len(writable)}</span>'
                 f'<span class="k">ייכתבו לוויקי</span></li>')
    items.append(f'<li><span class="n">{len(unwritable)}</span>'
                 f'<span class="k">לא ייכתבו</span></li>')
    items.append(f'<li><span class="n">{skipped_non_game}</span>'
                 f'<span class="k">סרטונים שאינם משחק</span></li>')
    return f'<ul class="counts">{"".join(items)}</ul>'


def render_report(matches: list[VideoMatch], skipped_non_game: int,
                  sample_section: str = "") -> str:
    """The full review page, ordered by confidence so the weakest matches are findable."""
    writable = [match for match in matches if match.bucket == Bucket.EXACT and match.slot]
    unwritable = [match for match in matches if match not in writable]

    by_score: dict[int, list[VideoMatch]] = defaultdict(list)
    for match in writable:
        by_score[match.confidence or MIN_SCORE].append(match)

    sections = "\n".join(
        _score_section(score,
                       sorted(by_score[score], key=lambda match: match.entry.season, reverse=True),
                       open_by_default=score < MAX_SCORE)
        for score in sorted(by_score, reverse=True)
    )
    perfect = len(by_score.get(MAX_SCORE, []))

    return (
        "<!doctype html>"
        '<html lang="he" dir="rtl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>סרטוני משחקי כדורסל — דוח התאמה</title>"
        f"<style>{_STYLE}</style></head><body><div class=\"wrap\">"
        "<h1>סרטוני משחקי כדורסל — דוח התאמה</h1>"
        f'<p class="sub">נוצר ב-{date.today().strftime("%d-%m-%Y")} · '
        f"{len(writable)} סרטונים מוכנים לכתיבה, מתוכם {perfect} בציון 10 · "
        "שום דבר עדיין לא נכתב לוויקי</p>"
        '<p class="sub">הציון נבנה מראיות בלתי תלויות: האם התוצאה ייחודית לעונה, האם שם '
        "היריבה זוהה במפורש, והאם תאריך ההעלאה תומך — הראיה היחידה שאינה מגיעה מכותרת "
        "הסרטון. הקבוצות הפתוחות למטה הן אלה שכדאי לעבור עליהן.</p>"
        f"{_score_counts_list(writable, unwritable, skipped_non_game)}"
        f"{sample_section}"
        f"{sections}"
        f"{_unwritable_section(unwritable)}"
        "</div></body></html>"
    )
