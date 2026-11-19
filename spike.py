#!/usr/bin/env python3
"""Command line for the build-spike kit.

Commands: count, gate, screen, new, close, fates. Exit 0 means the answer is
yes, exit 1 means the answer is no, and exit 2 means the arguments or the input
were bad. Each command is one function in the COMMANDS table.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import count
import gate
import index
import receipt
import screen


class CliError(Exception):
    """Bad arguments or unreadable input: reported on one line, exit 2."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError(message)


COMMANDS = {}


def command(name, configure):
    """Register a function under `name`, with `configure(parser)` adding its arguments."""
    def register(function):
        function.configure = configure
        COMMANDS[name] = function
        return function
    return register


def default_root() -> str:
    return os.environ.get("SPIKE_ROOT") or "spikes"


def add_root(parser):
    parser.add_argument("--root", default=None,
                        help="folder holding the spike folders (default: $SPIKE_ROOT, else ./spikes)")


def index_path(args) -> Path:
    return Path(args.root or default_root()) / "index.json"


def read_text(source: str, replace_errors: bool = False) -> str:
    """Read a file, or standard input when `source` is a hyphen."""
    errors = "replace" if replace_errors else "strict"
    try:
        if source == "-":
            return sys.stdin.buffer.read().decode("utf-8", errors)
        return Path(source).read_bytes().decode("utf-8", errors)
    except OSError as error:
        raise CliError("cannot read %s: %s" % (source, error.strerror or error))
    except UnicodeDecodeError:
        raise CliError("cannot read %s: not valid UTF-8 text" % source)


def percent(share: float) -> str:
    return "%.1f" % (100.0 * share)


# count

def configure_count(parser):
    parser.add_argument("file", help="JSON list or JSON Lines file of rows")
    parser.add_argument("--key", required=True, help="field to count by; a dotted key reaches into nested objects")
    parser.add_argument("--todo", default=None, help="comma-separated kinds that are to-dos for a person")
    parser.add_argument("--max-share", type=float, default=0.5,
                        help="largest acceptable share of to-do rows, 0 to 1 (default 0.5)")


@command("count", configure_count)
def cmd_count(args) -> int:
    """count rows by kind and report the share of to-dos"""
    if not args.key.strip():
        raise CliError("--key must not be empty")
    if not 0.0 <= args.max_share <= 1.0:
        raise CliError("--max-share must be a number from 0 to 1")
    todo = None
    if args.todo is not None:
        todo = [kind.strip() for kind in args.todo.split(",") if kind.strip()]
        if not todo:
            raise CliError("--todo needs at least one kind")
    try:
        rows = count.load_rows(args.file)
    except OSError as error:
        raise CliError("cannot read %s: %s" % (args.file, error.strerror or error))
    except ValueError as error:
        raise CliError("%s: %s" % (args.file, error))
    counts = count.count_kinds(rows, args.key)
    total = len(rows)
    if not counts:
        print("no rows")
    else:
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        kind_width = max(len(kind) for kind, _ in ordered)
        count_width = max(len(str(n)) for _, n in ordered)
        for kind, n in ordered:
            line = "%-*s  %*d  %5s%%" % (kind_width, kind, count_width, n, percent(n / total))
            if todo is not None and kind in todo:
                line += "  to-do"
            print(line)
    if todo is None:
        return 0
    share = count.todo_share(counts, todo)
    todo_rows = sum(counts.get(kind, 0) for kind in set(todo))
    print("to-do share: %d of %d (%s%%)" % (todo_rows, total, percent(share)))
    return 1 if share > args.max_share else 0


# gate

def configure_gate(parser):
    parser.add_argument("plan", help="JSON file holding one plan object, or - for standard input")
    parser.add_argument("--threshold", type=int, default=gate.DEFAULT_THRESHOLD,
                        help="lowest cheapness that may build, 0 to 100 (default %d)" % gate.DEFAULT_THRESHOLD)


@command("gate", configure_gate)
def cmd_gate(args) -> int:
    """decide whether a plan may be built or must be asked about"""
    if not 0 <= args.threshold <= 100:
        raise CliError("--threshold must be a whole number from 0 to 100")
    try:
        plan = json.loads(read_text(args.plan))
    except ValueError as error:
        raise CliError("%s is not valid JSON: %s" % (args.plan, error))
    if not isinstance(plan, dict):
        raise CliError("%s must hold one JSON object" % args.plan)
    ok, reason = gate.decide(plan, args.threshold)
    print("%s: %s" % ("BUILD" if ok else "ASK", reason))
    return 0 if ok else 1


# screen

def configure_screen(parser):
    parser.add_argument("file", help="check script to read, or - for standard input")


@command("screen", configure_screen)
def cmd_screen(args) -> int:
    """screen a check script for commands that must not run unattended"""
    reason = screen.unsafe_shell(read_text(args.file, replace_errors=True))
    if reason is None:
        print("OK")
        return 0
    print("UNSAFE: %s" % reason)
    return 1


# new

def configure_new(parser):
    parser.add_argument("title", help="the idea, in a few words")
    add_root(parser)
    parser.add_argument("--max-per-day", type=int, default=2,
                        help="spikes that may be started per day; 0 turns the cap off (default 2)")


@command("new", configure_new)
def cmd_new(args) -> int:
    """start a spike folder with a receipt template and a check stub"""
    if not args.title.strip():
        raise CliError("title must not be empty")
    if args.max_per_day < 0:
        raise CliError("--max-per-day must be 0 or more")
    root = Path(args.root or default_root())
    try:
        folder = receipt.new_spike(root, args.title, max_per_day=args.max_per_day)
    except receipt.CapReached as error:
        print("CAP: %s" % error, file=sys.stderr)
        return 1
    except OSError as error:
        raise CliError("cannot create the spike folder: %s" % (error.strerror or error))
    print(folder)
    return 0


# close

def configure_close(parser):
    parser.add_argument("spike_dir", help="the spike folder")
    parser.add_argument("--verify-exit", type=int, required=True,
                        help="exit code the check script returned when you ran it")
    add_root(parser)


@command("close", configure_close)
def cmd_close(args) -> int:
    """close a spike under the receipt-and-check rule and record it"""
    folder = Path(args.spike_dir)
    if not folder.is_dir():
        raise CliError("%s is not a folder" % args.spike_dir)
    try:
        ok, reason = receipt.close_spike(folder, args.verify_exit, index_path(args))
    except FileNotFoundError as error:
        raise CliError(str(error))
    except OSError as error:
        raise CliError("cannot record the result: %s" % (error.strerror or error))
    if ok:
        print("BUILT: %s" % args.spike_dir)
        return 0
    print("FAILED: %s" % reason)
    return 1


# fates

def configure_fates(parser):
    add_root(parser)
    parser.add_argument("--grace-seconds", type=int, default=300,
                        help="changes within this many seconds of the build do not count (default 300)")
    parser.add_argument("--json", action="store_true", help="print the rows as a JSON list")


def _sort_key(row):
    built_at = row.get("built_at")
    built_at = built_at if isinstance(built_at, (int, float)) and not isinstance(built_at, bool) else 0
    return (str(row.get("date", "")), built_at)


@command("fates", configure_fates)
def cmd_fates(args) -> int:
    """show what became of every recorded spike"""
    if args.grace_seconds < 0:
        raise CliError("--grace-seconds must be 0 or more")
    rows = index.fates(index_path(args), args.grace_seconds)
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("No spikes recorded yet.")
        return 0
    print(index.summary(rows))
    for row in sorted(rows, key=_sort_key, reverse=True):
        mark = "verified" if row.get("verified") is True else "failed"
        print("%s %s [%s] %s" % (row.get("date") or "?", mark, row["fate"], row.get("idea", "")))
        print("    %s" % (row.get("dir") or ""))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(prog="spike.py", description="Build small runnable things instead of handing out to-dos.")
    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.required = True
    for name, function in COMMANDS.items():
        function.configure(sub.add_parser(name, help=(function.__doc__ or "").strip() or None))
    return parser


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return COMMANDS[args.command](args)
    except CliError as error:
        print("spike: %s" % error, file=sys.stderr)
        return 2
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 0


if __name__ == "__main__":
    sys.exit(main())
