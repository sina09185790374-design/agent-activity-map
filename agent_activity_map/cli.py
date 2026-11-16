"""CLI: map, summarize, check, demo over a JSONL agent session log.

Exit codes: 0 ok / clean · 1 bad input or check findings.
"""

import argparse
import json
import sys

from .map import EventError, check, demo_events, parse_events, render_map, summarize


def _read_log(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return None


def _load(path):
    text = _read_log(path)
    if text is None:
        return None
    try:
        return parse_events(text)
    except EventError as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return None


def cmd_map(args):
    events = _load(args.log)
    if events is None:
        return 1
    sys.stdout.write(render_map(events))
    return 0


def cmd_summarize(args):
    events = _load(args.log)
    if events is None:
        return 1
    print(json.dumps(summarize(events), indent=2, ensure_ascii=False))
    return 0


def cmd_check(args):
    events = _load(args.log)
    if events is None:
        return 1
    findings = check(
        events,
        max_error_rate=args.max_error_rate,
        max_context=args.max_context,
    )
    if findings:
        for finding in findings:
            print(f"FAIL: {finding}")
        return 1
    print("clean: error rate and context within limits, no refusals standing")
    return 0


def cmd_demo(args):
    events = demo_events(n=args.events, seed=args.seed)
    text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as exc:
            print(f"cannot write {args.out}: {exc}", file=sys.stderr)
            return 1
        print(f"wrote {len(events)} events to {args.out}")
    else:
        sys.stdout.write(text)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="agent-activity-map",
        description="A live map of what an agent session did, not a log.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_map = sub.add_parser("map", help="render the session as a text map")
    p_map.add_argument("log", help="JSONL session log")
    p_map.set_defaults(func=cmd_map)

    p_sum = sub.add_parser("summarize", help="print a JSON summary of the session")
    p_sum.add_argument("log", help="JSONL session log")
    p_sum.set_defaults(func=cmd_summarize)

    p_check = sub.add_parser("check", help="CI gate: error rate, context, refusals")
    p_check.add_argument("log", help="JSONL session log")
    p_check.add_argument("--max-error-rate", type=float, default=0.05)
    p_check.add_argument("--max-context", type=float, default=90)
    p_check.set_defaults(func=cmd_check)

    p_demo = sub.add_parser("demo", help="write a deterministic sample session")
    p_demo.add_argument("--events", type=int, default=40)
    p_demo.add_argument("--seed", type=int, default=7)
    p_demo.add_argument("--out", help="write JSONL to this file instead of stdout")
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)
