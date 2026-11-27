"""Assistant tools: Sun Peaks lift and run status for the hub's voice/chat assistant.

Two read-only lookups for every mode, from the resort's lift and trail status
page: which lifts are running (or one lift, named loosely) with today's hours,
and how many runs are open and groomed (for an area, or one run). Answers are
small dicts of speech-ready strings with times in lodge time ("open until 4 pm").
"""
from __future__ import annotations

import difflib
import logging
import re
from datetime import date, datetime, time, timedelta, timezone

from bdh_sdk import ALL_MODES
from bdh_sdk.tools import Tool, ToolError

from .scraper import SUBZONES, ZONES, get_lift_status

log = logging.getLogger(__name__)

LIFT_STATUS = "lift_status"
RUN_STATUS = "run_status"

UNAVAILABLE = "The Sun Peaks lift status page isn't answering right now."
OFF_SEASON = "Sun Peaks isn't posting lift status right now; it's probably between seasons."
NO_LIFTS = "No lifts are running right now."
# Sun Peaks keeps UTC-7 all year.
LODGE_TZ = timezone(timedelta(hours=-7))
AREAS = [label for _, label in ZONES] + [label for _, label, _ in SUBZONES]
# Most names a run answer lists; the rest are counted.
MAX_RUNS = 15
MAX_MATCHES = 5
DIFFICULTY = {
    "1-easiest": "green (easiest)",
    "2-more-difficult": "blue (more difficult)",
    "3-most-difficult": "black diamond",
    "4-experts-only": "double black diamond",
    "5-park": "terrain park",
    "5-black-diamond-park": "terrain park",
    "6-glades": "glades",
}
LIFT_FILLER = frozenset({"the", "a", "is", "are", "lift", "lifts", "chair", "chairs", "chairlift", "chairlifts",
                         "express", "quad", "magic", "open", "running", "yet", "today", "status"})
# "Express", "chair" and "quad" in a request point at the chairlift when a name is shared.
CHAIR_WORDS = frozenset({"express", "chair", "chairs", "chairlift", "chairlifts", "quad"})
RUN_FILLER = frozenset({"the", "is", "run", "runs", "trail", "trails", "open", "groomed"})
# How close a misheard word or name must be (difflib ratio); lift words are few, so lifts allow more.
LIFT_FUZZY_WORD = 0.65
RUN_FUZZY_WORD = 0.75
FUZZY_NAME = 0.75
# Speech gives "five mile"; the trail list says "5 Mile".
NUMBERS = dict(zip(("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"),
                   map(str, range(1, 11))))

_HOURS = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\s*(?:to|-|–)\s*(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?",
                    re.I)
_STARTING = re.compile(r",?\s*starting\s+([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?", re.I)


def utc_now():
    return datetime.now(timezone.utc)


def tools(mode=None):
    return [
        Tool(LIFT_STATUS, "Lift status",
             "Which Sun Peaks ski lifts are running now, or one lift's status and today's hours. Use for 'is "
             "the Crystal chair open?', 'which lifts are running?', 'is Sunburst open yet?', 'when does "
             "Sundance close?'. Not for weather.",
             params={"type": "object", "properties": {
                 "lift": {"type": "string", "maxLength": 40,
                          "description": "One lift in the guest's words. Sun Peaks has Sunburst Express, "
                                         "Sundance Express, Morrisey Express, West Bowl Express, Crystal, "
                                         "Burfield, Elevation, Orient, Morrisey Platter, Village Platter and "
                                         "magic carpets (no gondola). Leave out for every lift."},
             }},
             modes=ALL_MODES, readonly=True),
        Tool(RUN_STATUS, "Run status",
             "Sun Peaks ski runs: how many are open, which are groomed, or one run's status, difficulty and "
             "grooming, optionally for one area. Use for 'what runs are groomed?', 'is 5 Mile open?', 'what's "
             "open on Sundance?'.",
             params={"type": "object", "properties": {
                 "run": {"type": "string", "maxLength": 40,
                         "description": "One run (trail) in the guest's words, e.g. '5 Mile', 'Cahilty'. "
                                        "Leave out for a summary."},
                 "area": {"type": "string", "enum": AREAS,
                          "description": "Only runs in this area of the mountain."},
             }},
             modes=ALL_MODES, readonly=True),
    ]


# ── data ──

def _data():
    try:
        data = get_lift_status()
    except Exception:
        log.exception("lift status page unavailable")
        raise ToolError(UNAVAILABLE) from None
    if not data or not data.get("lifts"):
        raise ToolError(OFF_SEASON)
    return data


# ── names ──

def _words(text, filler):
    text = (text or "").casefold().replace("'", "").replace("’", "")
    words = (NUMBERS.get(w, w) for w in re.split(r"[^0-9a-z]+", text) if w)
    return tuple(w for w in words if w not in filler)


def _fix_words(words, vocab, cutoff):
    """Each word, or the known word it was probably misheard as ("kristal" → "crystal")."""
    out = []
    for w in words:
        if w in vocab or w.isdigit():
            out.append(w)
            continue
        close = difflib.get_close_matches(w, vocab, n=1, cutoff=cutoff)
        out.append(close[0] if close else w)
    return tuple(out)


def match(text, names, filler, cutoff=RUN_FUZZY_WORD, exact_wins=True):
    """The names (in order) that ``text`` means, tolerant of misheard words.

    An exact name wins (with ``exact_wins`` false, names holding more words
    come too: "Morrisey" is both the Morrisey Express and the Morrisey
    Platter); otherwise every name holding all the request's words, then the
    closest whole names. Empty when nothing is close.
    """
    keys = {name: frozenset(_words(name, filler)) for name in names}
    vocab = sorted({w for k in keys.values() for w in k})
    raw = _words(text, filler)
    fixed = _fix_words(raw, vocab, cutoff)
    for attempt in (raw, fixed):
        key = frozenset(attempt)
        if not key:
            return []
        exact = [n for n in names if keys[n] == key]
        holding = [n for n in names if key <= keys[n]]
        if exact and (exact_wins or len(holding) == 1 or len(exact) > 1):
            return exact
        if holding:
            return holding
    tries = {"".join(raw), "".join(fixed)}
    scored = sorted(((max(difflib.SequenceMatcher(None, t, "".join(_words(n, filler))).ratio() for t in tries), n)
                     for n in names), reverse=True)
    best = [n for score, n in scored if score >= FUZZY_NAME and score >= scored[0][0] - 0.05]
    return [n for n in names if n in best]


def _join(parts):
    parts = list(parts)
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


# ── hours ──

def _clock(hour, minute, ap):
    h = int(hour) % 12 + (12 if ap.lower() == "p" else 0)
    return time(h, int(minute or 0))


def _speak(t):
    if t.hour == 12 and t.minute == 0:
        return "noon"
    minutes = f":{t:%M}" if t.minute else ""
    return f"{t.hour % 12 or 12}{minutes} {'am' if t.hour < 12 else 'pm'}"


def _season_date(month_name, day, today):
    """A "starting February 1" date in the ski season ``today`` is in (seasons start in the fall)."""
    try:
        month = datetime.strptime(month_name[:3].title(), "%b").month
    except ValueError:
        return None
    start_year = today.year if today.month >= 7 else today.year - 1
    try:
        return date(start_year if month >= 7 else start_year + 1, month, int(day))
    except ValueError:
        return None


def todays_hours(lines, today):
    """``(opens, closes, "9:30 am to 4 pm")`` for the schedule in effect ``today``, or None.

    Lines are the lift's posted schedules; "..., starting February 1" ones
    take over from that date.
    """
    best = None
    for line in lines or ():
        m = _HOURS.search(line)
        if not m:
            continue
        starting = _STARTING.search(line)
        since = _season_date(*starting.groups(), today) if starting else date.min
        if since is None or since > today or (best and since < best[0]):
            continue
        opens, closes = _clock(*m.group(1, 2, 3)), _clock(*m.group(4, 5, 6))
        text = _STARTING.sub("", line)
        text = (text[:m.start()] + f"{_speak(opens)} to {_speak(closes)}" + text[m.end():]).strip(" ,")
        best = (since, opens, closes, text[0].lower() + text[1:])
    return best[1:] if best else None


def _lift_state(lift, local):
    hours = todays_hours(lift.get("hours"), local.date())
    status = lift.get("status")
    if status == "open":
        if hours and local.time() < hours[0]:
            state = f"opens at {_speak(hours[0])}"
        elif hours and local.time() >= hours[1]:
            state = f"closed for the day at {_speak(hours[1])}"
        elif hours:
            state = f"open until {_speak(hours[1])}"
        else:
            state = "open"
    elif status == "closed":
        state = "closed"
    else:
        state = "no status posted"
    return state, hours


# ── running ──

def _lift_tool(args, now):
    data = _data()
    local = now.astimezone(LODGE_TZ).replace(tzinfo=None)
    lifts = data["lifts"]
    update = data.get("update") or {}
    headline = update.get("headline")
    if args.get("lift"):
        names = match(args["lift"], [l["name"] for l in lifts], LIFT_FILLER, LIFT_FUZZY_WORD,
                      exact_wins=False)
        if len(names) > 1 and CHAIR_WORDS & set(args["lift"].casefold().split()):
            names = [n for n in names if "chair" in n.lower()] or names
        if not names:
            raise ToolError(f"Sun Peaks has no lift called {args['lift'].strip()!r}. The lifts are "
                            f"{_join(l['short_name'] for l in lifts)}.")
        entries = []
        for lift in (l for l in lifts if l["name"] in names[:MAX_MATCHES]):
            state, hours = _lift_state(lift, local)
            entries.append({"lift": lift["name"], "status": state, **({"hours": hours[2]} if hours else {})})
        out = entries[0] if len(entries) == 1 else {"matches": entries}
        if headline:
            out["resort_update"] = headline
        return out
    running, closed = [], []
    for lift in lifts:
        state, _ = _lift_state(lift, local)
        if state.startswith(("open", "opens")):
            running.append(f"{lift['short_name']} {state.removeprefix('open ')}".strip())
        else:
            closed.append(lift["short_name"])
    summary = data.get("summary") or {}
    out = {
        "lifts_open": f"{len(running)} of {len(lifts)}",
        "open": running,
        "closed": closed,
        "runs_open": (f"{summary.get('trails_open', 0)} of {summary['trails_total']}"
                      if summary.get("trails_total") else None),
        "resort_update": headline,
    }
    if not running:
        out["note"] = NO_LIFTS
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def _areas(data):
    """``[(area label, trails)]``, with West Bowl apart from Tod Mountain."""
    out = []
    for zone in data.get("zones") or ():
        out.append((zone["label"], [t for g in zone["trails_by_difficulty"] for t in g["trails"]]))
        for section in zone.get("sections") or ():
            out.append((section["label"], [t for g in section["trails_by_difficulty"] for t in g["trails"]]))
    return out


def _groomed(trail):
    return trail["status"] == "open" and trail.get("grooming", "none") != "none"


def _names(trails):
    names = [t["name"] for t in trails]
    return names if len(names) <= MAX_RUNS else names[:MAX_RUNS] + [f"and {len(names) - MAX_RUNS} more"]


def _run_tool(args, now):
    data = _data()
    areas = _areas(data)
    if args.get("area"):
        areas = [(label, trails) for label, trails in areas if label == args["area"]]
    if args.get("run"):
        everything = [(label, t) for label, trails in areas for t in trails]
        names = match(args["run"], list(dict.fromkeys(t["name"] for _, t in everything)), RUN_FILLER)
        if not names:
            where = f" in {args['area']}" if args.get("area") else ""
            raise ToolError(f"There's no run called {args['run'].strip()!r}{where} on the Sun Peaks trail list.")
        entries = []
        for label, t in everything:
            if t["name"] in names[:MAX_MATCHES]:
                status = "open" if t["status"] == "open" else "closed"
                if _groomed(t):
                    status += ", groomed"
                entries.append({"run": t["name"], "area": label, "status": status,
                                "difficulty": DIFFICULTY.get(t.get("difficulty"), "")})
        entries = [{k: v for k, v in e.items() if v} for e in entries]
        return entries[0] if len(entries) == 1 else {"matches": entries}
    trails = [t for _, ts in areas for t in ts]
    if not trails:
        raise ToolError(OFF_SEASON)
    open_runs = [t for t in trails if t["status"] == "open"]
    groomed = [t for t in open_runs if _groomed(t)]
    out = {"area": args.get("area"), "runs_open": f"{len(open_runs)} of {len(trails)}",
           "groomed": _names(groomed) if groomed else "none"}
    if args.get("area"):
        ungroomed = [t for t in open_runs if not _groomed(t)]
        out["open_not_groomed"] = _names(ungroomed)
    elif open_runs:
        out["by_area"] = {label: f"{sum(t['status'] == 'open' for t in ts)} of {len(ts)} open"
                          for label, ts in areas if any(t["status"] == "open" for t in ts)}
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}


_RUNNERS = {LIFT_STATUS: _lift_tool, RUN_STATUS: _run_tool}


def run_tool(tool_id, args, mode=None):
    runner = _RUNNERS.get(tool_id)
    if runner is None:
        raise ToolError(f"Unknown tool {tool_id!r}")
    return runner(args or {}, utc_now())
