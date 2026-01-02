#!/usr/bin/env python3
"""
GCLI2API CLI - Command line interface for managing the gcli2api service.

Usage:
    gcli2api start       Start the service (in foreground)
    gcli2api start -d    Start the service (in background/daemon mode)
    gcli2api stop        Stop the service
    gcli2api restart     Restart the service
    gcli2api status      Show service status
    gcli2api logs        Show recent logs
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

# Configuration
DEFAULT_PORT = 7861
DEFAULT_HOST = "127.0.0.1"
PID_FILE = Path.home() / ".gcli2api" / "gcli2api.pid"
LOG_FILE = Path.home() / ".gcli2api" / "gcli2api.log"


def ensure_pid_dir():
    """Ensure the PID file directory exists."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)


def read_pid() -> int | None:
    """Read the PID from the PID file."""
    try:
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            return pid
    except (ValueError, OSError):
        pass
    return None


def write_pid(pid: int):
    """Write the PID to the PID file."""
    ensure_pid_dir()
    PID_FILE.write_text(str(pid))


def remove_pid():
    """Remove the PID file."""
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except OSError:
        pass


def is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def is_service_running() -> tuple[bool, int | None]:
    """Check if the gcli2api service is running."""
    pid = read_pid()
    if pid and is_process_running(pid):
        return True, pid

    # Also check by port using HEAD request (the endpoint only responds to HEAD)
    try:
        response = httpx.head(
            f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/keepalive",
            timeout=2.0,
        )
        if response.status_code == 200:
            # Service is running but we don't have the PID
            return True, None
    except Exception:
        pass

    # Clean up stale PID file
    if pid:
        remove_pid()

    return False, None


def find_process_by_port(port: int) -> int | None:
    """Find the PID of the process listening on the given port."""
    try:
        # Use lsof to find the process
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            # May return multiple PIDs, get the first one
            pids = result.stdout.strip().split("\n")
            return int(pids[0])
    except Exception:
        pass

    try:
        # Fallback: use ss/netstat
        result = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            # Parse the output to find the PID
            for line in result.stdout.split("\n"):
                if f":{port}" in line and "pid=" in line:
                    # Extract PID from something like "pid=12345"
                    import re

                    match = re.search(r"pid=(\d+)", line)
                    if match:
                        return int(match.group(1))
    except Exception:
        pass

    return None


def stop_service(force: bool = False) -> bool:
    """Stop the gcli2api service.

    Only stops services that were started by this CLI (tracked via PID file).
    Will NOT kill services started in other terminals to avoid disrupting
    active connections (like Claude Code sessions).
    """
    pid = read_pid()

    if not pid:
        print("No PID file found. Service may be running in another terminal.")
        print("If you want to stop it, use Ctrl+C in that terminal or:")
        port_pid = find_process_by_port(DEFAULT_PORT)
        if port_pid:
            print(f"  kill {port_pid}")
        return False

    if not is_process_running(pid):
        print("Service from PID file is not running. Cleaning up.")
        remove_pid()
        return True

    try:
        print(f"Stopping gcli2api service (PID: {pid})...")
        sig = signal.SIGKILL if force else signal.SIGTERM
        os.kill(pid, sig)

        # Wait for process to stop
        for _ in range(30):  # Wait up to 3 seconds
            if not is_process_running(pid):
                print("Service stopped successfully.")
                remove_pid()
                return True
            time.sleep(0.1)

        # Force kill if still running
        if is_process_running(pid):
            print("Service did not stop gracefully, force killing...")
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)

        remove_pid()
        print("Service stopped.")
        return True

    except ProcessLookupError:
        print("Service already stopped.")
        remove_pid()
        return True
    except PermissionError:
        print(f"Permission denied. Try: sudo kill {pid}")
        return False
    except Exception as e:
        print(f"Error stopping service: {e}")
        return False


def start_service(daemon: bool = False) -> bool:
    """Start the gcli2api service."""
    running, pid = is_service_running()
    if running:
        print(f"Service is already running (PID: {pid or 'unknown'}).")
        return True

    # Clean up any stale processes on the port before starting
    port_pid = find_process_by_port(DEFAULT_PORT)
    if port_pid:
        print(f"Found stale process on port {DEFAULT_PORT} (PID: {port_pid}), cleaning up...")
        try:
            os.kill(port_pid, signal.SIGTERM)
            time.sleep(1)
            # Check if still running and force kill if needed
            if is_process_running(port_pid):
                os.kill(port_pid, signal.SIGKILL)
                time.sleep(0.5)
            print("Stale process cleaned up.")
        except (ProcessLookupError, PermissionError) as e:
            print(f"Warning: Could not clean up stale process: {e}")

    # Get the directory where this script is located
    script_dir = Path(__file__).parent.resolve()
    web_py = script_dir / "web.py"
    venv_python = script_dir / ".venv" / "bin" / "python"

    if not web_py.exists():
        print(f"Error: web.py not found at {web_py}")
        return False

    # Use venv python if available, otherwise system python
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable

    if daemon:
        # Start in background
        ensure_pid_dir()
        log_file = open(LOG_FILE, "a")

        process = subprocess.Popen(
            [python_cmd, str(web_py)],
            cwd=str(script_dir),
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )

        write_pid(process.pid)
        print(f"Service started in background (PID: {process.pid}).")
        print(f"Logs: {LOG_FILE}")

        # Wait a moment and check if it's actually running
        time.sleep(1)
        if not is_process_running(process.pid):
            print("Warning: Service may have failed to start. Check logs.")
            return False

        return True
    else:
        # Start in foreground
        print("Starting gcli2api service...")
        try:
            process = subprocess.Popen(
                [python_cmd, str(web_py)],
                cwd=str(script_dir),
            )
            write_pid(process.pid)
            process.wait()
        except KeyboardInterrupt:
            print("\nStopping service...")
        finally:
            remove_pid()
        return True


def kill_all_on_port(port: int) -> bool:
    """Kill all processes listening on the given port."""
    max_attempts = 10
    for attempt in range(max_attempts):
        pids = []
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = [int(p) for p in result.stdout.strip().split("\n") if p.strip()]
        except Exception:
            pass

        if not pids:
            return True  # Port is free

        for pid in pids:
            try:
                sig = signal.SIGKILL if attempt >= 3 else signal.SIGTERM
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                pass

        time.sleep(0.5)

    return False  # Failed to free port


def restart_service() -> bool:
    """Restart the gcli2api service.

    Will restart the service regardless of how it was started.
    """
    print("Stopping any existing gcli2api processes...")

    # Kill everything on the port
    if not kill_all_on_port(DEFAULT_PORT):
        print(f"Error: Could not free port {DEFAULT_PORT}")
        return False

    # Clean up PID file
    remove_pid()

    print("Port is free, starting service...")
    return start_service(daemon=True)


def show_status():
    """Show the status of the gcli2api service."""
    running, pid = is_service_running()

    if running:
        print("gcli2api service is RUNNING")
        if pid:
            print(f"  PID: {pid}")
        print(f"  URL: http://{DEFAULT_HOST}:{DEFAULT_PORT}")
        print(f"  Control Panel: http://{DEFAULT_HOST}:{DEFAULT_PORT}")

        # Try to get more info
        try:
            response = httpx.head(
                f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/keepalive",
                timeout=2.0,
            )
            print(f"  Health: OK (status {response.status_code})")
        except Exception as e:
            print(f"  Health: Unknown ({e})")
    else:
        print("gcli2api service is NOT RUNNING")
        print("  Start with: gcli2api start -d")


def show_logs(
    lines: int = 50,
    live: bool = False,
    level: str | None = None,
    reqid: str | None = None,
    component: str | None = None,
    since: str | None = None,
    color: bool = False,
    no_color: bool = False,
):
    """Show recent logs using cli_logs.py for full functionality."""
    # Get the directory where this script is located
    script_dir = Path(__file__).parent.resolve()
    cli_logs_py = script_dir / "cli_logs.py"
    venv_python = script_dir / ".venv" / "bin" / "python"

    # Use venv python if available, otherwise system python
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable

    if not cli_logs_py.exists():
        # Fallback to simple tail if cli_logs.py doesn't exist
        if not LOG_FILE.exists():
            print(f"No log file found at {LOG_FILE}")
            return

        try:
            result = subprocess.run(
                ["tail", "-n", str(lines), str(LOG_FILE)],
                capture_output=True,
                text=True,
            )
            if result.stdout:
                print(result.stdout)
            else:
                print("Log file is empty.")
        except Exception as e:
            print(f"Error reading logs: {e}")
        return

    # Build command for cli_logs.py
    cmd = [python_cmd, str(cli_logs_py), "--log-file", str(LOG_FILE)]

    # Always pass --tail for the number of initial lines to show
    cmd.extend(["--tail", str(lines)])

    if live:
        cmd.append("--live")

    if level:
        cmd.extend(["--level", level])
    if reqid:
        cmd.extend(["--reqid", reqid])
    if component:
        cmd.extend(["--component", component])
    if since:
        cmd.extend(["--since", since])
    if color:
        cmd.append("--color")
    if no_color:
        cmd.append("--no-color")

    try:
        # Run cli_logs.py, allowing it to handle signals for live mode
        subprocess.run(cmd)
    except KeyboardInterrupt:
        # Graceful exit on Ctrl+C
        print("\nStopped.", file=sys.stderr)
    except Exception as e:
        print(f"Error reading logs: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="GCLI2API CLI - Manage the gcli2api service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  gcli2api start -d     Start service in background
  gcli2api restart      Restart the service
  gcli2api status       Check if service is running
  gcli2api stop         Stop the service
  gcli2api logs         Show recent logs
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # start command
    start_parser = subparsers.add_parser("start", help="Start the service")
    start_parser.add_argument(
        "-d",
        "--daemon",
        action="store_true",
        help="Run in background (daemon mode)",
    )

    # stop command
    stop_parser = subparsers.add_parser("stop", help="Stop the service")
    stop_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force stop (SIGKILL)",
    )

    # restart command
    subparsers.add_parser("restart", help="Restart the service")

    # status command
    subparsers.add_parser("status", help="Show service status")

    # logs command
    logs_parser = subparsers.add_parser("logs", help="Show recent logs")
    logs_parser.add_argument(
        "-n",
        "--lines",
        type=int,
        default=50,
        help="Number of lines to show (default: 50)",
    )
    logs_parser.add_argument(
        "--live",
        action="store_true",
        help="Stream logs in real-time (exit with Ctrl+C)",
    )
    logs_parser.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Same as --live",
    )
    logs_parser.add_argument(
        "-l",
        "--level",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Filter by log level",
    )
    logs_parser.add_argument(
        "-r",
        "--reqid",
        help="Filter by request ID",
    )
    logs_parser.add_argument(
        "-c",
        "--component",
        help="Filter by component (e.g., ANTHROPIC, STREAMING)",
    )
    logs_parser.add_argument(
        "-s",
        "--since",
        help="Show logs since time (e.g., 5m, 1h, 30s)",
    )
    logs_parser.add_argument(
        "--color",
        action="store_true",
        help="Colorize output (auto-enabled for --live)",
    )
    logs_parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colorized output",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "start":
        success = start_service(daemon=args.daemon)
        sys.exit(0 if success else 1)

    elif args.command == "stop":
        success = stop_service(force=args.force)
        sys.exit(0 if success else 1)

    elif args.command == "restart":
        success = restart_service()
        sys.exit(0 if success else 1)

    elif args.command == "status":
        show_status()

    elif args.command == "logs":
        show_logs(
            lines=args.lines,
            live=args.live or args.follow,
            level=args.level,
            reqid=args.reqid,
            component=args.component,
            since=args.since,
            color=args.color,
            no_color=args.no_color,
        )


if __name__ == "__main__":
    main()
