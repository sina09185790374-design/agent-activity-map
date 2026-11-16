"""Agent activity map: a live map of what an agent session did, not a log.

Pattern (original code; learned from alexeyw/lot-map, 2026-11-15): observability
is a map, not a list of commands. Every call lights up its station on a ring
around the centre; spokes wear thicker the more a station is used; the route
shows the last stations in order; errors leave a mark until the next message;
the context window is a ring that fills as the session goes. This tool is that
idea as a small local CLI over a JSONL session log: any agent harness that can
dump its calls as events feeds this CLI, and it answers where the work went.

An event is one JSON object per line:

    {"ts": "2026-11-15T10:00:01Z", "station": "files", "call": "Read",
     "duration_ms": 120, "status": "ok"}

Optional keys: "subagent" (name of the subagent that made the call),
"context_pct" (context-window fill, 0-100), "model" (model name in use).

Stations, in ring order: you, model, memory, files, shell, network,
browser, agents, skills, hooks. ``status`` is ok, error or refused.
Only station names are read -- never call arguments or file contents.
"""

import json
import math
import random

__all__ = [
    "STATIONS",
    "EventError",
    "parse_events",
    "summarize",
    "render_map",
    "check",
    "demo_events",
]

STATIONS = (
    "you",
    "model",
    "memory",
    "files",
    "shell",
    "network",
    "browser",
    "agents",
    "skills",
    "hooks",
)

# Three-letter codes printed on the ring, in station order.
_CODES = ("YOU", "MDL", "MEM", "FIL", "SHL", "NET", "BRW", "AGT", "SKL", "HOK")

_STATUSES = ("ok", "error", "refused")

# Context thresholds, same bands as the pattern: amber at 70, red at 90.
AMBER_AT = 70
RED_AT = 90


class EventError(ValueError):
    """A session-log line that cannot be read as an event."""


def parse_events(text):
    """Parse JSONL session events, validating every line.

    Returns a list of event dicts in log order. Raises EventError naming the
    line number on the first bad line: bad JSON, missing keys, unknown
    station, unknown status, negative duration, or a context_pct outside
    0-100. Blank lines are skipped.
    """
    events = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EventError(f"line {lineno}: not JSON ({exc.msg})") from exc
        if not isinstance(event, dict):
            raise EventError(f"line {lineno}: event is not an object")
        for key in ("ts", "station", "call", "duration_ms", "status"):
            if key not in event:
                raise EventError(f"line {lineno}: missing key {key!r}")
        if event["station"] not in STATIONS:
            raise EventError(
                f"line {lineno}: unknown station {event['station']!r} "
                f"(expected one of {', '.join(STATIONS)})"
            )
        if event["status"] not in _STATUSES:
            raise EventError(
                f"line {lineno}: unknown status {event['status']!r} "
                f"(expected one of {', '.join(_STATUSES)})"
            )
        if not isinstance(event["duration_ms"], (int, float)) or isinstance(
            event["duration_ms"], bool
        ):
            raise EventError(f"line {lineno}: duration_ms is not a number")
        if event["duration_ms"] < 0:
            raise EventError(f"line {lineno}: duration_ms is negative")
        if "context_pct" in event:
            pct = event["context_pct"]
            if not isinstance(pct, (int, float)) or isinstance(pct, bool):
                raise EventError(f"line {lineno}: context_pct is not a number")
            if not 0 <= pct <= 100:
                raise EventError(f"line {lineno}: context_pct outside 0-100")
        events.append(event)
    return events


def _compress_route(events):
    """Station sequence with consecutive repeats collapsed."""
    route = []
    for event in events:
        if not route or route[-1] != event["station"]:
            route.append(event["station"])
    return route


def summarize(events):
    """Summarize a session: per-station use, route, errors, context, models.

    Returns a JSON-serializable dict. An empty session summarizes to zeros
    with an empty route -- a map with nothing on it is still a map.
    """
    per_station = {
        station: {"calls": 0, "errors": 0, "refusals": 0, "ms": 0}
        for station in STATIONS
    }
    total_ms = 0
    errors = 0
    context_peak = None
    models = []
    subagents = []
    for event in events:
        row = per_station[event["station"]]
        row["calls"] += 1
        row["ms"] += event["duration_ms"]
        total_ms += event["duration_ms"]
        if event["status"] == "error":
            row["errors"] += 1
            errors += 1
        elif event["status"] == "refused":
            row["refusals"] += 1
        if "context_pct" in event:
            pct = event["context_pct"]
            context_peak = pct if context_peak is None else max(context_peak, pct)
        if "model" in event and event["model"] not in models:
            models.append(event["model"])
        if "subagent" in event and event["subagent"] not in subagents:
            subagents.append(event["subagent"])
    calls = len(events)
    busiest = None
    if calls:
        busiest = max(STATIONS, key=lambda s: per_station[s]["calls"])
    return {
        "calls": calls,
        "errors": errors,
        "error_rate": (errors / calls) if calls else 0.0,
        "total_ms": total_ms,
        "per_station": per_station,
        "busiest_station": busiest,
        "route": _compress_route(events),
        "context_peak": context_peak,
        "models": models,
        "subagents": subagents,
    }


def context_status(pct):
    """Band name for a context fill: ok, amber (>=70) or red (>=90)."""
    if pct is None:
        return "n/a"
    if pct >= RED_AT:
        return "red"
    if pct >= AMBER_AT:
        return "amber"
    return "ok"


def _context_bar(pct, width=20):
    """A 20-cell fill bar for the context ring, e.g. [####------] 62% ok."""
    if pct is None:
        return "[--------------------] n/a"
    filled = round(pct / 100 * width)
    return f"[{'#' * filled}{'-' * (width - filled)}] {pct:g}% {context_status(pct)}"


def _spoke_char(calls):
    """How worn a spoke looks: unused, light, used, heavily worn."""
    if calls == 0:
        return " "
    if calls == 1:
        return "."
    if calls <= 4:
        return ":"
    return "="


def _station_pos(index, width, height):
    """Ring position of a station: ellipse around the centre, top first."""
    cx, cy = width // 2, height // 2
    angle = math.radians(-90 + index * 36)
    x = cx + round((width // 2 - 4) * math.cos(angle))
    y = cy + round((height // 2 - 2) * math.sin(angle))
    return x, y


def _line(canvas, x0, y0, x1, y1, char):
    """Bresenham line on the char canvas, never overwriting a station cell."""
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        if (x, y) != (x0, y0) and (x, y) != (x1, y1):
            if 0 <= y < len(canvas) and 0 <= x < len(canvas[0]):
                if canvas[y][x] == " ":
                    canvas[y][x] = char
        if x == x1 and y == y1:
            break
        err2 = 2 * err
        if err2 >= dy:
            err += dy
            x += sx
        if err2 <= dx:
            err += dx
            y += sy


def render_map(events):
    """Render the session as a text map: ring, worn spokes, route, context.

    Returns one string. An empty session renders an empty ring -- every
    station unused, no route, no context -- rather than failing.
    """
    summary = summarize(events)
    width, height = 61, 25
    cx, cy = width // 2, height // 2
    canvas = [[" "] * width for _ in range(height)]

    # Spokes first: the centre is the session, the ring is the stations.
    for index, station in enumerate(STATIONS):
        calls = summary["per_station"][station]["calls"]
        if calls == 0:
            continue
        x, y = _station_pos(index, width, height)
        _line(canvas, cx, cy, x, y, _spoke_char(calls))

    # Stations on the ring: o unused, O used, @ used with errors.
    for index, station in enumerate(STATIONS):
        x, y = _station_pos(index, width, height)
        row = summary["per_station"][station]
        if row["errors"]:
            mark = "@"
        elif row["calls"]:
            mark = "O"
        else:
            mark = "o"
        canvas[y][x] = mark
        label = _CODES[index]
        if row["calls"]:
            label += f"x{row['calls']}"
        if row["errors"]:
            label += f"!{row['errors']}"
        # Label sits outside the ring, away from the centre, and never on
        # top of its own marker: if it does not fit on the far side, it
        # goes on the near side instead.
        if x >= cx:
            lx = x + 2
            if lx + len(label) > width:
                lx = x - 2 - len(label)
        else:
            lx = x - 2 - len(label)
            if lx < 0:
                lx = x + 2
        for i, ch in enumerate(label):
            canvas[y][lx + i] = ch

    # Centre: the context ring, as a percentage.
    centre = "CTX" if summary["context_peak"] is None else f"{summary['context_peak']:g}%"
    start = cx - len(centre) // 2
    for i, ch in enumerate(centre):
        canvas[cy][start + i] = ch

    lines = ["".join(row).rstrip() for row in canvas]
    # Trim the empty margin rows above the top station and below the bottom.
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()

    # Below the map: the route, the errors, the subagents, the context bar.
    route = summary["route"]
    if route:
        shown = route[-12:]
        trail = " -> ".join(shown)
        if len(route) > 12:
            trail = "... -> " + trail
        lines.append(f"route: {trail}")
    else:
        lines.append("route: (empty session)")
    bad = [
        f"{s}!{summary['per_station'][s]['errors']}"
        for s in STATIONS
        if summary["per_station"][s]["errors"]
    ]
    lines.append(f"errors: {', '.join(bad) if bad else 'none'}")
    if summary["subagents"]:
        lines.append(f"subagents: {', '.join(summary['subagents'])}")
    if summary["models"]:
        lines.append(f"models: {' -> '.join(summary['models'])}")
    lines.append(f"context: {_context_bar(summary['context_peak'])}")
    lines.append(
        "legend: o unused · O used · @ errors · . : = worn spokes · "
        "context amber >=70, red >=90"
    )
    return "\n".join(lines) + "\n"


def check(events, max_error_rate=0.05, max_context=90):
    """The quality gate: findings that fail a session, or [] when clean.

    Fails on an error rate above ``max_error_rate``, a context peak above
    ``max_context``, or any refused call left standing (a refusal is a human
    decision the session never resolved).
    """
    summary = summarize(events)
    findings = []
    if summary["calls"] and summary["error_rate"] > max_error_rate:
        findings.append(
            f"error-rate {summary['error_rate']:.1%} above "
            f"{max_error_rate:.0%} ({summary['errors']}/{summary['calls']} calls)"
        )
    if summary["context_peak"] is not None and summary["context_peak"] > max_context:
        findings.append(
            f"context peak {summary['context_peak']:g}% above {max_context}%"
        )
    for station in STATIONS:
        row = summary["per_station"][station]
        if row["refusals"]:
            findings.append(
                f"{station}: {row['refusals']} refused call(s) left standing"
            )
    return findings


def demo_events(n=40, seed=7):
    """A deterministic sample session, so the tool works out of the box.

    Same seed -> same events. A realistic loop: you ask, the model plans,
    files and shell do the work, the network checks something, a subagent
    helps, the context fills as the session goes, and one call in twenty
    fails. Never any real data -- this is a fixture, not a recording.
    """
    rng = random.Random(seed)
    flow = [
        ("you", "Message", 40),
        ("model", "Request", 900),
        ("memory", "Recall", 60),
        ("files", "Read", 120),
        ("files", "Edit", 200),
        ("shell", "Run", 450),
        ("model", "Request", 1100),
        ("network", "Fetch", 800),
        ("agents", "Spawn", 300),
        ("skills", "Lookup", 90),
        ("files", "Read", 110),
        ("shell", "Run", 380),
        ("hooks", "Check", 25),
        ("model", "Request", 950),
        ("browser", "Open", 600),
    ]
    events = []
    context = 12.0
    for i in range(n):
        station, call, base_ms = flow[i % len(flow)]
        context = min(96.0, context + rng.uniform(0.5, 2.8))
        roll = rng.random()
        if roll < 0.05:
            status = "error"
        elif roll < 0.13:
            status = "refused"
        else:
            status = "ok"
        event = {
            "ts": f"2026-11-15T10:{i // 60:02d}:{i % 60:02d}Z",
            "station": station,
            "call": call,
            "duration_ms": max(1, int(base_ms * rng.uniform(0.6, 1.6))),
            "status": status,
            "context_pct": round(context, 1),
            "model": "opus" if i < n // 2 else "sonnet",
        }
        if station == "agents":
            event["subagent"] = rng.choice(["scout", "builder", "reviewer"])
        events.append(event)
    return events
