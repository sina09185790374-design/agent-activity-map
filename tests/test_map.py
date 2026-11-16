"""Tests for agent-activity-map."""

import json
import unittest

from agent_activity_map.map import (
    EventError,
    check,
    context_status,
    demo_events,
    parse_events,
    render_map,
    summarize,
)

SAMPLE = """\
{"ts": "2026-11-15T10:00:01Z", "station": "you", "call": "Message", "duration_ms": 40, "status": "ok", "context_pct": 12}
{"ts": "2026-11-15T10:00:02Z", "station": "model", "call": "Request", "duration_ms": 900, "status": "ok", "context_pct": 20, "model": "opus"}
{"ts": "2026-11-15T10:00:03Z", "station": "files", "call": "Read", "duration_ms": 120, "status": "ok", "context_pct": 21}
{"ts": "2026-11-15T10:00:04Z", "station": "files", "call": "Edit", "duration_ms": 200, "status": "error", "context_pct": 22}
{"ts": "2026-11-15T10:00:05Z", "station": "shell", "call": "Run", "duration_ms": 450, "status": "ok", "context_pct": 23}
{"ts": "2026-11-15T10:00:06Z", "station": "files", "call": "Read", "duration_ms": 110, "status": "ok", "context_pct": 24}
{"ts": "2026-11-15T10:00:07Z", "station": "model", "call": "Request", "duration_ms": 950, "status": "ok", "context_pct": 30, "model": "sonnet"}
{"ts": "2026-11-15T10:00:08Z", "station": "network", "call": "Fetch", "duration_ms": 800, "status": "refused", "context_pct": 31}
"""


class TestParse(unittest.TestCase):
    def test_valid_session_parses_in_order(self):
        events = parse_events(SAMPLE)
        self.assertEqual(len(events), 8)
        self.assertEqual([e["station"] for e in events][:3], ["you", "model", "files"])

    def test_blank_lines_skipped(self):
        events = parse_events("\n" + SAMPLE + "\n\n")
        self.assertEqual(len(events), 8)

    def test_empty_text_is_empty_session(self):
        self.assertEqual(parse_events(""), [])
        self.assertEqual(parse_events("\n\n"), [])

    def test_bad_json_names_the_line(self):
        good = '{"ts": "t", "station": "files", "call": "Read", "duration_ms": 1, "status": "ok"}\n'
        with self.assertRaises(EventError) as ctx:
            parse_events(good + "not json\n")
        self.assertIn("line 2", str(ctx.exception))

    def test_missing_key_names_the_line_and_key(self):
        with self.assertRaises(EventError) as ctx:
            parse_events('{"ts": "t", "station": "files", "call": "Read", "duration_ms": 1}\n')
        self.assertIn("line 1", str(ctx.exception))
        self.assertIn("status", str(ctx.exception))

    def test_unknown_station_rejected(self):
        with self.assertRaises(EventError) as ctx:
            parse_events(
                '{"ts": "t", "station": "teleport", "call": "X", "duration_ms": 1, "status": "ok"}\n'
            )
        self.assertIn("teleport", str(ctx.exception))

    def test_unknown_status_rejected(self):
        with self.assertRaises(EventError) as ctx:
            parse_events(
                '{"ts": "t", "station": "files", "call": "X", "duration_ms": 1, "status": "meh"}\n'
            )
        self.assertIn("meh", str(ctx.exception))

    def test_negative_duration_rejected(self):
        with self.assertRaises(EventError):
            parse_events(
                '{"ts": "t", "station": "files", "call": "X", "duration_ms": -5, "status": "ok"}\n'
            )

    def test_context_pct_out_of_range_rejected(self):
        with self.assertRaises(EventError):
            parse_events(
                '{"ts": "t", "station": "files", "call": "X", "duration_ms": 1, "status": "ok", "context_pct": 101}\n'
            )

    def test_non_object_line_rejected(self):
        with self.assertRaises(EventError):
            parse_events('[1, 2]\n')


class TestSummarize(unittest.TestCase):
    def test_counts_per_station(self):
        s = summarize(parse_events(SAMPLE))
        self.assertEqual(s["calls"], 8)
        self.assertEqual(s["per_station"]["files"]["calls"], 3)
        self.assertEqual(s["per_station"]["files"]["errors"], 1)
        self.assertEqual(s["per_station"]["network"]["refusals"], 1)
        self.assertEqual(s["total_ms"], 3570)
        self.assertEqual(s["busiest_station"], "files")

    def test_error_rate(self):
        s = summarize(parse_events(SAMPLE))
        self.assertEqual(s["errors"], 1)
        self.assertAlmostEqual(s["error_rate"], 0.125)

    def test_route_collapses_consecutive_repeats(self):
        events = parse_events(
            "".join(
                json.dumps(
                    {"ts": "t", "station": st, "call": "X", "duration_ms": 1, "status": "ok"}
                )
                + "\n"
                for st in ["files", "files", "shell", "files", "files"]
            )
        )
        self.assertEqual(summarize(events)["route"], ["files", "shell", "files"])

    def test_context_peak_and_models(self):
        s = summarize(parse_events(SAMPLE))
        self.assertEqual(s["context_peak"], 31)
        self.assertEqual(s["models"], ["opus", "sonnet"])

    def test_empty_session(self):
        s = summarize([])
        self.assertEqual(s["calls"], 0)
        self.assertEqual(s["error_rate"], 0.0)
        self.assertIsNone(s["busiest_station"])
        self.assertEqual(s["route"], [])
        self.assertIsNone(s["context_peak"])


class TestRender(unittest.TestCase):
    def test_map_contains_stations_route_and_context(self):
        out = render_map(parse_events(SAMPLE))
        for code in ("YOU", "MDL", "FIL", "SHL", "NET"):
            self.assertIn(code, out)
        self.assertIn("route: you -> model -> files -> shell -> files -> model -> network", out)
        self.assertIn("context: [", out)
        self.assertIn("31% ok", out)

    def test_error_station_marked(self):
        out = render_map(parse_events(SAMPLE))
        self.assertIn("FILx3!1", out)
        self.assertIn("errors: files!1", out)

    def test_worn_spoke_char_grows_with_use(self):
        def one(station, n):
            events = [
                {"ts": "t", "station": station, "call": "X", "duration_ms": 1, "status": "ok"}
                for _ in range(n)
            ]
            return render_map(events)

        self.assertIn(".", one("files", 1))
        self.assertIn(":", one("files", 3))
        self.assertIn("=", one("files", 6))

    def test_empty_session_renders_empty_ring(self):
        out = render_map([])
        self.assertIn("route: (empty session)", out)
        self.assertIn("errors: none", out)
        self.assertIn("context: [--------------------] n/a", out)
        self.assertIn("YOU", out)


class TestCheck(unittest.TestCase):
    def test_clean_session_passes(self):
        events = parse_events(
            '{"ts": "t", "station": "files", "call": "Read", "duration_ms": 1, "status": "ok"}\n'
        )
        self.assertEqual(check(events), [])

    def test_high_error_rate_fails(self):
        self.assertTrue(any("error-rate" in f for f in check(parse_events(SAMPLE))))

    def test_context_peak_fails(self):
        events = parse_events(
            '{"ts": "t", "station": "files", "call": "X", "duration_ms": 1, "status": "ok", "context_pct": 95}\n'
        )
        self.assertTrue(any("context peak" in f for f in check(events)))

    def test_refusal_left_standing_fails(self):
        self.assertTrue(any("refused" in f for f in check(parse_events(SAMPLE))))

    def test_thresholds_are_tunable(self):
        self.assertEqual(check(parse_events(SAMPLE), max_error_rate=0.5, max_context=100), ["network: 1 refused call(s) left standing"])


class TestContextStatus(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(context_status(None), "n/a")
        self.assertEqual(context_status(69.9), "ok")
        self.assertEqual(context_status(70), "amber")
        self.assertEqual(context_status(89.9), "amber")
        self.assertEqual(context_status(90), "red")


class TestDemo(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(demo_events(20, seed=3), demo_events(20, seed=3))
        self.assertNotEqual(demo_events(20, seed=3), demo_events(20, seed=4))

    def test_demo_output_parses_and_summarizes(self):
        text = "".join(json.dumps(e) + "\n" for e in demo_events(40, seed=7))
        events = parse_events(text)
        self.assertEqual(len(events), 40)
        s = summarize(events)
        self.assertGreater(s["calls"], 0)
        self.assertIsNotNone(s["context_peak"])
        self.assertTrue(render_map(events))

    def test_demo_uses_known_stations_only(self):
        for event in demo_events(60, seed=11):
            self.assertIn(event["station"], ("you", "model", "memory", "files", "shell", "network", "browser", "agents", "skills", "hooks"))


if __name__ == "__main__":
    unittest.main()
