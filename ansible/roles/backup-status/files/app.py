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

import datetime
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


def parse_restic_time(ts):
    """Parse restic's RFC3339Nano snapshot timestamp into an aware datetime.

    Go emits up to 9 fractional digits; Python's fromisoformat wants at most
    6, so trim rather than risk a version-dependent parse failure. Returns
    a timezone-aware datetime — comparing/subtracting these is safe
    regardless of what timezone this container itself happens to be in,
    unlike naively using time.mktime on a naive struct_time.
    """
    ts = re.sub(r"(\.\d{6})\d*", r"\1", ts)
    return datetime.datetime.fromisoformat(ts)


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


def build_local_daily_status(stale_after):
    """Derived from the actual local repo, not a log file — this container
    has direct read access to it, so "when did the last daily snapshot
    really land" is directly knowable rather than inferred from whatever
    the last script invocation happened to log. A manual `restic forget`
    or `backup` run outside the script shows up here immediately, where a
    log-based check would miss it entirely.

    Log parsing is still the only option for the cloud and integrity-check
    jobs — see parse_dated_job_log and parse_integrity_log — since this
    container has no cloud credentials and restic check leaves no queryable
    trace of having run.
    """
    snapshots = cached("restic_snapshots", lambda: run_restic(["snapshots"]))
    daily_times = [
        parse_restic_time(s["time"]) for s in snapshots if "daily" in (s.get("tags") or [])
    ]
    if not daily_times:
        return {"ok": None, "stale": True, "last_run_human": None, "detail_human": "no snapshots yet"}

    latest = max(daily_times)
    now = datetime.datetime.now(latest.tzinfo)
    age = (now - latest).total_seconds()
    stale = age > stale_after
    detail = latest.strftime("%a %H:%M")

    # If a script attempt happened more recently than the latest snapshot
    # and didn't complete, that's worth surfacing even though older data
    # still exists — otherwise a currently-broken job could look fine.
    log_path = newest_matching(os.path.join(BACKUP_LOGS_DIR, "restic-local-*.log"))
    if log_path and os.path.getmtime(log_path) > latest.timestamp():
        with open(log_path, "r", errors="replace") as f:
            if "=== Complete:" not in f.read():
                detail += " · a more recent attempt failed"

    return {
        "ok": not stale,
        "stale": stale,
        "last_run_human": human_ago(age),
        "detail_human": detail,
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
        "local_daily": build_local_daily_status(LOCAL_STALE_AFTER_SECONDS),
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


def read_cloud_snapshots_cache():
    """The dashboard has no cloud (rclone/Google Drive) credentials of its
    own — by design, matching the local repo's read-only-mount model. The
    cloud backup script writes this file after each successful weekly run,
    since it already legitimately holds those credentials at that point;
    the dashboard just reads what it left behind. Freshness is therefore
    bounded by the weekly cloud-backup cadence, not live — which matches
    how often that data actually changes anyway.
    """
    path = os.path.join(BACKUP_LOGS_DIR, "cloud-snapshots.json")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []  # a half-written or corrupt cache shouldn't break the page


def _snapshot_row(snap, repo):
    return {
        "id": snap["short_id"],
        "time_human": parse_restic_time(snap["time"]).strftime("%b %d, %H:%M"),
        "tag": (snap.get("tags") or ["untagged"])[0],
        "repo": repo,
        "_sort_time": parse_restic_time(snap["time"]).timestamp(),
    }


def build_snapshots():
    # Deliberately metadata-only (no per-snapshot `restic stats`): stats in
    # restore-size mode walks the whole snapshot tree, which over a slow disk
    # with a large repo can take much longer than a page load should wait —
    # this was measured taking 30s+ per snapshot in practice, hanging the page.
    local_snapshots = cached("restic_snapshots", lambda: run_restic(["snapshots"]))
    cloud_snapshots = read_cloud_snapshots_cache()

    result = [_snapshot_row(s, "local") for s in local_snapshots]
    result += [_snapshot_row(s, "cloud") for s in cloud_snapshots]
    result.sort(key=lambda s: s["_sort_time"], reverse=True)
    for row in result:
        del row["_sort_time"]
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
