"""Command line entry: python -m minutes extract|overdue|owners|check."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date

from .parser import meeting_date, overdue, parse_minutes, problems


def _table(items) -> str:
    head = ["id", "owner", "due", "status", "task"]
    rows = [[i.id, i.owner, i.due.isoformat() if i.due else "-", "done" if i.done else "open", i.task] for i in items]
    widths = [max(len(r[c]) for r in [head] + rows) for c in range(4)]
    lines = []
    for n, row in enumerate([head] + rows):
        lines.append("  ".join(row[c].ljust(widths[c]) for c in range(4)) + "  " + row[4])
        if n == 0:
            lines.append("  ".join("-" * w for w in widths) + "  ----")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Return 0 on success, 1 when overdue items or problems are found, 2 on bad input."""
    parser = argparse.ArgumentParser(prog="minutes", description="Parse meeting minutes into action items")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("extract", "list the action items"), ("overdue", "open items past their due date"),
                       ("owners", "open items per owner"), ("check", "items with no owner or no due date")):
        p = sub.add_parser(name, help=text)
        p.add_argument("file")
        p.add_argument("--meeting-date", help="YYYY-MM-DD when the minutes have no Date line")
        p.add_argument("--markers-only", action="store_true", help="skip 'Name will ...' sentences")
        if name == "extract":
            p.add_argument("--format", choices=["table", "csv", "json"], default="table")
        if name == "overdue":
            p.add_argument("--today", help="YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)

    try:
        with open(args.file, encoding="utf-8") as handle:
            text = handle.read()
        meeting = meeting_date(text, date.fromisoformat(args.meeting_date) if args.meeting_date else None)
        today = date.fromisoformat(args.today) if getattr(args, "today", None) else date.today()
    except FileNotFoundError:
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    items = parse_minutes(text, meeting, args.markers_only)

    if args.command == "extract":
        if args.format == "json":
            print(json.dumps([i.as_dict() for i in items], indent=2))
        elif args.format == "csv":
            writer = csv.writer(sys.stdout, lineterminator="\n")
            writer.writerow(["id", "owner", "task", "due", "done", "line"])
            for i in items:
                d = i.as_dict()
                writer.writerow([d["id"], d["owner"], d["task"], d["due"], d["done"], d["line"]])
        else:
            print(f"Meeting {meeting.isoformat()}: {len(items)} action item(s)")
            print(_table(items))
        return 0
    if args.command == "overdue":
        late = overdue(items, today)
        for i in late:
            print(f"{i.id}  {i.owner}  due {i.due}  {(today - i.due).days} day(s) late  {i.task}")
        print(f"{len(late)} overdue as of {today}")
        return 1 if late else 0
    if args.command == "owners":
        counts = Counter()
        for i in items:
            if not i.done:
                for name in i.owner.split(", "):
                    counts[name] += 1
        for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"{count:3}  {name}")
        return 0
    found = problems(items)
    for line in found:
        print(line)
    print(f"{len(found)} problem(s)" if found else "every item has an owner and a due date")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
