#!/usr/bin/env python3
"""Read-only backup status dashboard.

Serves a static page plus two JSON endpoints (/api/status, /api/snapshots)
built by shelling out to `restic --no-lock` (read-only flag: restic never
takes a repo lock) and parsing the existing backup role's log files. This
process holds no write access anywhere — the repo and password file are
bind-mounted read-only by docker-compose — so there is nothing here that
can delete a snapshot or touch a backup; those actions only ever render an
SSH command in the UI for a human to run themselves.

No framework: two GET endpoints and two static files don't need one.
"""

import glob
import http.server
import json
import os
import re
import shutil
import subprocess
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Container-internal paths (our own convention, fixed by the Dockerfile/
# compose mount targets — not host paths, so nothing here is a "hardcoded
# drive name"; the actual host paths only ever live in group_vars/nas).
RESTIC_REPO_PATH = os.environ["RESTIC_REPO_PATH"]
RESTIC_PASSWORD_FILE = os.environ["RESTIC_PASSWORD_FILE"]
BACKUP_LOGS_DIR = os.environ["BACKUP_LOGS_DIR"]

# Real host-side values, templated in by Ansible from group_vars/nas — used
# only for display and for the SSH commands the UI generates, since those
# commands run on the Pi itself, not inside this container.
NAS_SSH_USER = os.environ["NAS_SSH_USER"]
HOST_BACKUP_DRIVE = os.environ["HOST_BACKUP_DRIVE"]
HOST_RESTIC_REPO_PATH = os.environ["HOST_RESTIC_REPO_PATH"]
HOST_RESTIC_PASSWORD_FILE = os.environ["HOST_RESTIC_PASSWORD_FILE"]
HOST_RESTIC_CLOUD_REPOSITORY = os.environ["HOST_RESTIC_CLOUD_REPOSITORY"]
HOST_RESTIC_LOCAL_RETENTION = os.environ["HOST_RESTIC_LOCAL_RETENTION"]
HOST_RESTIC_CLOUD_RETENTION = os.environ["HOST_RESTIC_CLOUD_RETENTION"]
HOST_SCRIPTS_DIR = os.environ["HOST_SCRIPTS_DIR"]

PORT = int(os.environ.get("PORT", "8080"))
CACHE_TTL_SECONDS = 30

LOCAL_STALE_AFTER_SECONDS = 36 * 3600       # daily job — allow a missed run
WEEKLY_STALE_AFTER_SECONDS = 9 * 24 * 3600  # weekly jobs — allow a missed week

_cache_lock = threading.Lock()
_cache = {}  # key -> (expires_at_monotonic, value)


def cached(key, build):
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
    value = build()
    with _cache_lock:
        _cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, value)
    return value


def run_restic_lines(args, timeout=20):
    """For subcommands like `list locks` that print one ID per line, not JSON
    — even with --json, `restic list` emits JSON Lines, not a single
    document, so json.loads() on the whole output would fail."""
    env = dict(os.environ)
    env["RESTIC_REPOSITORY"] = RESTIC_REPO_PATH
    env["RESTIC_PASSWORD_FILE"] = RESTIC_PASSWORD_FILE
    result = subprocess.run(
        ["restic", "--no-lock", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def run_restic(args, timeout=20):
    env = dict(os.environ)
    env["RESTIC_REPOSITORY"] = RESTIC_REPO_PATH
    env["RESTIC_PASSWORD_FILE"] = RESTIC_PASSWORD_FILE
    result = subprocess.run(
        ["restic", "--no-lock", "--json", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return json.loads(result.stdout)


def human_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


def human_ago(seconds):
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def newest_matching(pattern):
    matches = glob.glob(pattern)
    return max(matches, key=os.path.getmtime) if matches else None


def parse_dated_job_log(glob_pattern, stale_after):
    """Parse a backup-restic-{local,cloud}.sh.j2-style dated log file.

    Success is judged by whether the script reached its final "=== Complete"
    line, not by matching specific wording — both the clean-success and the
    partial-success (some source files unreadable, restic exit 3) paths print
    different text but both fall through to "=== Complete"; a real failure
    calls `exit 1` before ever reaching it. This is tied to control flow, not
    prose, so it doesn't need updating if the scripts' log messages change.
    """
    path = newest_matching(glob_pattern)
    if not path:
        return {"ok": None, "stale": True, "last_run_human": None, "detail_human": "no log yet"}

    mtime = os.path.getmtime(path)
    age = time.time() - mtime
    with open(path, "r", errors="replace") as f:
        content = f.read()

    ok = "=== Complete:" in content

    return {
        "ok": ok,
        "stale": age > stale_after,
        "last_run_human": human_ago(age),
        "detail_human": time.strftime("%a %H:%M", time.localtime(mtime)),
    }


def parse_integrity_log(stale_after):
    path = os.path.join(BACKUP_LOGS_DIR, "restic-check.log")
    if not os.path.isfile(path):
        return {"ok": None, "stale": True, "last_run_human": None, "detail_human": "no log yet"}

    mtime = os.path.getmtime(path)
    age = time.time() - mtime
    with open(path, "r", errors="replace") as f:
        content = f.read()

    ok = "error" not in content.lower() and content.strip() != ""
    error_count = len(re.findall(r"error", content, re.IGNORECASE))

    return {
        "ok": ok,
        "stale": age > stale_after,
        "last_run_human": human_ago(age),
        "detail_human": f"read errors: {error_count}",
    }


def build_status():
    jobs = {
        "local_daily": parse_dated_job_log(
            os.path.join(BACKUP_LOGS_DIR, "restic-local-*.log"),
            LOCAL_STALE_AFTER_SECONDS,
        ),
        "cloud_weekly": parse_dated_job_log(
            os.path.join(BACKUP_LOGS_DIR, "restic-cloud-*.log"),
            WEEKLY_STALE_AFTER_SECONDS,
        ),
        "integrity_check": parse_integrity_log(WEEKLY_STALE_AFTER_SECONDS),
    }

    mounted = os.path.isfile(os.path.join(RESTIC_REPO_PATH, "config"))
    drive = {"mounted": mounted, "label": HOST_BACKUP_DRIVE}
    if mounted:
        usage = shutil.disk_usage(RESTIC_REPO_PATH)
        drive["free_human"] = f"{human_bytes(usage.free)} free"
        percent_used = round(usage.used / usage.total * 100)
        drive["detail_human"] = f"of {human_bytes(usage.total)} · {percent_used}% used"
    else:
        drive["free_human"] = None
        drive["detail_human"] = "check the USB connection, then: sudo mount -a"

    # A stale lock (e.g. left behind by a run interrupted when the drive
    # dropped) silently blocks forget/prune while backup itself can still
    # succeed — surfacing this saves a manual `restic list locks` SSH trip.
    lock_count = 0
    if mounted:
        try:
            lock_count = len(cached("restic_locks", lambda: run_restic_lines(["list", "locks"])))
        except Exception:
            lock_count = -1  # couldn't tell — don't claim "0 locks" when unsure

    return {"jobs": jobs, "drive": drive, "lock_count": lock_count}


def build_snapshots():
    # Deliberately metadata-only (no per-snapshot `restic stats`): stats in
    # restore-size mode walks the whole snapshot tree, which over a slow disk
    # with a large repo can take much longer than a page load should wait —
    # this was measured taking 30s+ per snapshot in practice, hanging the page.
    snapshots = cached("restic_snapshots", lambda: run_restic(["snapshots"]))
    result = []
    for snap in snapshots:
        tag = (snap.get("tags") or ["untagged"])[0]
        time_human = time.strftime(
            "%b %d, %H:%M", time.strptime(snap["time"][:19], "%Y-%m-%dT%H:%M:%S")
        )
        result.append({
            "id": snap["short_id"],
            "time_human": time_human,
            "tag": tag,
        })
    result.sort(key=lambda s: s["time_human"], reverse=True)
    return {"snapshots": result}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # quiet by default; container logs stay to stdout via docker anyway

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, content_type):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _index(self):
        with open(os.path.join(BASE_DIR, "index.html"), "r") as f:
            html = f.read()
        html = (
            html.replace("__NAS_SSH_USER__", NAS_SSH_USER)
            .replace("__HOST_RESTIC_REPO_PATH__", HOST_RESTIC_REPO_PATH)
            .replace("__HOST_RESTIC_PASSWORD_FILE__", HOST_RESTIC_PASSWORD_FILE)
            .replace("__HOST_RESTIC_CLOUD_REPOSITORY__", HOST_RESTIC_CLOUD_REPOSITORY)
            .replace("__HOST_RESTIC_LOCAL_RETENTION__", HOST_RESTIC_LOCAL_RETENTION)
            .replace("__HOST_RESTIC_CLOUD_RETENTION__", HOST_RESTIC_CLOUD_RETENTION)
            .replace("__HOST_SCRIPTS_DIR__", HOST_SCRIPTS_DIR)
        )
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path == "/" or self.path == "/index.html":
                self._index()
            elif self.path == "/pico.min.css":
                self._file(os.path.join(BASE_DIR, "pico.min.css"), "text/css")
            elif self.path == "/api/status":
                self._json(cached("status", build_status))
            elif self.path == "/api/snapshots":
                self._json(cached("snapshots", build_snapshots))
            else:
                self.send_error(404)
        except subprocess.CalledProcessError as e:
            self._json({"error": e.stderr or str(e)}, status=502)
        except Exception as e:  # last-resort — never crash the server on a bad read
            self._json({"error": str(e)}, status=500)


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
