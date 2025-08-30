#!/usr/bin/env python3
import configparser
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

from config import DEFAULT_CONFIG


STOP = False

def _sig_handler(signum, frame):
    global STOP
    STOP = True
    print(f"[{datetime.now().isoformat()}] Received signal {signum}. Shutting down after current run...", flush=True)

def parse_bool(s: str, default: bool = False) -> bool:
    if s is None:
        return default
    return s.strip().lower() in ("1", "true", "yes", "on")

def main():
    # Resolve CONFIG_PATH and normalize to absolute early
    raw_cfg = os.environ.get("CONFIG_PATH", "/app/data/config.ini")
    config_path = raw_cfg if os.path.isabs(raw_cfg) else os.path.abspath(raw_cfg)

    # If config is missing, create and exit so the user can fill it in
    cfg_dir = os.path.dirname(config_path) or "."
    if not os.path.exists(config_path):
        os.makedirs(cfg_dir, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_CONFIG)
        print(f"[{datetime.now().isoformat()}] Created default config at {config_path}. Please edit api_key and restart.", flush=True)
        sys.exit(1)


    # Load schedule settings
    cp = configparser.ConfigParser()
    if not cp.read(config_path, encoding="utf-8"):
        print(f"ERROR: Could not read config: {config_path}", file=sys.stderr)
        sys.exit(2)

    interval_seconds = cp.getint("schedule", "interval_seconds", fallback=3600)
    run_at_start     = parse_bool(cp.get("schedule", "run_at_start", fallback="true"))
    jitter_seconds   = cp.getint("schedule", "jitter_seconds", fallback=0)  # optional, default 0
    max_runs         = cp.getint("schedule", "max_runs", fallback=50)        # updated default

    if interval_seconds < 1:
        print("ERROR: [schedule].interval_seconds must be >= 1", file=sys.stderr)
        sys.exit(2)

    # Signal handling for graceful exit
    signal.signal(signal.SIGTERM, _sig_handler)
    signal.signal(signal.SIGINT, _sig_handler)

    run_count = 0
    first_loop = True

    while not STOP:
        if first_loop and not run_at_start:
            first_loop = False
            delay = interval_seconds
            print(f"[{datetime.now().isoformat()}] Waiting {delay}s before first run...", flush=True)
            time.sleep(delay)
            if STOP:
                break

        first_loop = False

        # Optional jitter
        delay_before = 0
        if jitter_seconds > 0:
            try:
                delay_before = int.from_bytes(os.urandom(2), "big") % (jitter_seconds + 1)
            except Exception:
                delay_before = 0

        if delay_before > 0:
            print(f"[{datetime.now().isoformat()}] Sleeping jitter {delay_before}s before run...", flush=True)
            time.sleep(delay_before)
            if STOP:
                break

        # Run the main script once
        print(f"[{datetime.now().isoformat()}] Starting lidarr cache warmer...", flush=True)
        extra = []
        
        # Optional: Environment variable overrides for force modes
        if os.environ.get("FORCE_ARTISTS", "false").lower() in ("1", "true", "yes", "on"):
            extra.append("--force-artists")
        if os.environ.get("FORCE_RG", "false").lower() in ("1", "true", "yes", "on"):
            extra.append("--force-rg")
        if os.environ.get("FORCE_TEXT_SEARCH", "false").lower() in ("1", "true", "yes", "on"):
            extra.append("--force-text-search")

        proc = subprocess.run(
            ["python", "/app/main.py", "--config", config_path] + extra,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        print(f"[{datetime.now().isoformat()}] Run complete (exit={proc.returncode}).", flush=True)

        run_count += 1
        if max_runs > 0 and run_count >= max_runs:
            print(f"[{datetime.now().isoformat()}] Reached max_runs={max_runs}. Exiting.", flush=True)
            break
        if STOP:
            break

        # Sleep until next run
        print(f"[{datetime.now().isoformat()}] Sleeping {interval_seconds}s until next run...", flush=True)
        for _ in range(interval_seconds):
            if STOP:
                break
            time.sleep(1)

    print(f"[{datetime.now().isoformat()}] Exited entrypoint loop.", flush=True)


if __name__ == "__main__":
    main()
