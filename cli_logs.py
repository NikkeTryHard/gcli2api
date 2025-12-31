#!/usr/bin/env python3
"""
CLI Log Lookup Tool for gcli2api

Usage:
    python cli_logs.py --reqid <id>          # Filter by request ID
    python cli_logs.py --tail 50             # Show last 50 entries
    python cli_logs.py --level error         # Filter by level
    python cli_logs.py --since 5m            # Show logs from last 5 minutes
    python cli_logs.py --component ANTHROPIC # Filter by component
    python cli_logs.py --follow              # Stream new logs (like tail -f)
"""

import argparse
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Optional, List, Generator


def parse_log_line(line: str) -> Optional[dict]:
    """Parse a log line in format: [YYYY-MM-DD HH:MM:SS] [LEVEL] message"""
    pattern = r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(\w+)\] (.+)$"
    match = re.match(pattern, line.strip())
    if not match:
        return None

    timestamp_str, level, message = match.groups()
    try:
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        timestamp = None

    # Extract request ID if present (format: reqId=xxx or X-Request-ID: xxx)
    req_id = None
    req_id_match = re.search(r"(?:reqId=|X-Request-ID[=:]\s*)([a-zA-Z0-9_-]+)", message)
    if req_id_match:
        req_id = req_id_match.group(1)

    # Extract component if present (format: [COMPONENT])
    component = None
    component_match = re.search(r"\[([A-Z][A-Z0-9_]+)\]", message)
    if component_match:
        component = component_match.group(1)

    return {
        "timestamp": timestamp,
        "timestamp_str": timestamp_str,
        "level": level.lower(),
        "message": message,
        "req_id": req_id,
        "component": component,
        "raw": line.strip(),
    }


def parse_time_delta(time_str: str) -> Optional[timedelta]:
    """Parse time string like '5m', '1h', '30s' into timedelta"""
    pattern = r"^(\d+)([smhd])$"
    match = re.match(pattern, time_str.lower())
    if not match:
        return None

    value, unit = int(match.group(1)), match.group(2)
    units = {
        "s": timedelta(seconds=value),
        "m": timedelta(minutes=value),
        "h": timedelta(hours=value),
        "d": timedelta(days=value),
    }
    return units.get(unit)


def read_log_file(log_path: str) -> Generator[str, None, None]:
    """Read log file line by line"""
    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}", file=sys.stderr)
        return

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            yield line


def tail_log_file(log_path: str, n: int) -> List[str]:
    """Get last n lines from log file"""
    if not os.path.exists(log_path):
        return []

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
        return lines[-n:] if len(lines) >= n else lines


def follow_log_file(log_path: str) -> Generator[str, None, None]:
    """Follow log file like tail -f"""
    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}", file=sys.stderr)
        return

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        # Go to end of file
        f.seek(0, 2)
        while True:
            line = f.readline()
            if line:
                yield line
            else:
                time.sleep(0.1)


def filter_logs(
    lines: Generator[str, None, None],
    req_id: Optional[str] = None,
    level: Optional[str] = None,
    since: Optional[timedelta] = None,
    component: Optional[str] = None,
) -> Generator[dict, None, None]:
    """Filter log lines based on criteria"""
    now = datetime.now()
    since_time = now - since if since else None

    for line in lines:
        parsed = parse_log_line(line)
        if not parsed:
            continue

        # Filter by request ID
        if req_id and (
            not parsed["req_id"] or req_id.lower() not in parsed["req_id"].lower()
        ):
            continue

        # Filter by level
        if level:
            level_order = {
                "debug": 0,
                "info": 1,
                "warning": 2,
                "error": 3,
                "critical": 4,
            }
            if level_order.get(parsed["level"], 1) < level_order.get(level.lower(), 1):
                continue

        # Filter by time
        if since_time and parsed["timestamp"] and parsed["timestamp"] < since_time:
            continue

        # Filter by component
        if component and (
            not parsed["component"]
            or component.upper() not in parsed["component"].upper()
        ):
            continue

        yield parsed


def format_output(entry: dict, json_mode: bool = False) -> str:
    """Format log entry for output"""
    if json_mode:
        import json

        return json.dumps(
            {
                "ts": entry["timestamp_str"],
                "level": entry["level"],
                "component": entry["component"],
                "reqId": entry["req_id"],
                "msg": entry["message"],
            },
            ensure_ascii=False,
        )
    else:
        return entry["raw"]


def main():
    parser = argparse.ArgumentParser(
        description="gcli2api log viewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python cli_logs.py --reqid abc123
    python cli_logs.py --tail 100 --level error
    python cli_logs.py --since 30m --component ANTHROPIC
    python cli_logs.py --follow
        """,
    )
    parser.add_argument("--reqid", "-r", help="Filter by request ID (partial match)")
    parser.add_argument(
        "--tail", "-n", type=int, default=50, help="Show last N entries (default: 50)"
    )
    parser.add_argument(
        "--level",
        "-l",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Show logs at or above this level",
    )
    parser.add_argument(
        "--since", "-s", help="Show logs since time (e.g., 5m, 1h, 30s)"
    )
    parser.add_argument(
        "--component", "-c", help="Filter by component (e.g., ANTHROPIC, STREAMING)"
    )
    parser.add_argument(
        "--follow", "-f", action="store_true", help="Follow log file (like tail -f)"
    )
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--log-file",
        default=None,
        help="Log file path (default: from LOG_FILE env or log.txt)",
    )

    args = parser.parse_args()

    # Determine log file path
    log_file = args.log_file or os.getenv("LOG_FILE", "log.txt")

    # Parse since time if provided
    since_delta = None
    if args.since:
        since_delta = parse_time_delta(args.since)
        if since_delta is None:
            print(
                f"Invalid time format: {args.since}. Use formats like: 5m, 1h, 30s",
                file=sys.stderr,
            )
            sys.exit(1)

    try:
        if args.follow:
            # Follow mode
            print(f"Following {log_file}... (Ctrl+C to stop)", file=sys.stderr)
            lines = follow_log_file(log_file)
        else:
            # Tail mode
            lines = (
                line for line in tail_log_file(log_file, args.tail * 10)
            )  # Read extra for filtering

        filtered = filter_logs(
            lines,
            req_id=args.reqid,
            level=args.level,
            since=since_delta,
            component=args.component,
        )

        count = 0
        for entry in filtered:
            print(format_output(entry, args.json))
            count += 1
            if not args.follow and count >= args.tail:
                break

        if not args.follow and count == 0:
            print("No matching log entries found.", file=sys.stderr)

    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
