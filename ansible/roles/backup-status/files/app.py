#!/usr/bin/env python3
"""Read-only backup status dashboard (the "Snapshot Deck").

Serves index.html plus two JSON endpoints, /api/status and /api/snapshots,
built from `restic --no-lock` and the backup role's log files. The repo and
password file are mounted read-only, so nothing here can change a backup;
destructive actions are only shown in the UI as SSH commands to run by hand.

Contract with roles/backup: snapshot tags `daily`/`weekly`, the log names
below, and the "=== Complete:" line a script prints only when it succeeded.
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

# Container paths, fixed by the compose mounts.
RESTIC_REPO_PATH = os.environ["RESTIC_REPO_PATH"]
RESTIC_PASSWORD_FILE = os.environ["RESTIC_PASSWORD_FILE"]
BACKUP_LOGS_DIR = os.environ["BACKUP_LOGS_DIR"]

# Host-side values from group_vars, used only to build the SSH commands shown
# in the UI (they run on the Pi, not in this container).
NAS_SSH_USER = os.environ["NAS_SSH_USER"]
HOST_BACKUP_DRIVE = os.environ["HOST_BACKUP_DRIVE"]
HOST_RESTIC_REPO_PATH = os.environ["HOST_RESTIC_REPO_PATH"]
HOST_RESTIC_PASSWORD_FILE = os.environ["HOST_RESTIC_PASSWORD_FILE"]
HOST_RESTIC_CLOUD_REPOSITORY = os.environ["HOST_RESTIC_CLOUD_REPOSITORY"]
HOST_RESTIC_LOCAL_RETENTION = os.environ["HOST_RESTIC_LOCAL_RETENTION"]
HOST_RESTIC_CLOUD_RETENTION = os.environ["HOST_RESTIC_CLOUD_RETENTION"]
HOST_RESTIC_CLOUD_RCLONE_ARGS = os.environ["HOST_RESTIC_CLOUD_RCLONE_ARGS"]
HOST_SCRIPTS_DIR = os.environ["HOST_SCRIPTS_DIR"]

PORT = int(os.environ.get("PORT", "8080"))
CACHE_TTL_SECONDS = 30

LOCAL_STALE_AFTER_SECONDS = 36 * 3600       # daily job — allow a missed run
WEEKLY_STALE_AFTER_SECONDS = 9 * 24 * 3600  # weekly jobs — allow a missed week

# Printed by the backup scripts only after every step succeeded.
COMPLETE_MARKER = "=== Complete:"

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


def restic_output(args, timeout=20):
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
    return result.stdout


def run_restic(args):
    return json.loads(restic_output(["--json", *args]))


def run_restic_lines(args):
    """One ID per line. `restic list --json` emits JSON Lines, not one
    document, so json.loads() on the whole output would fail."""
    return [line for line in restic_output(args).splitlines() if line.strip()]


def read_text(path):
    with open(path, "r", errors="replace") as f:
        return f.read()


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
    """Parse restic's timestamp into an aware datetime.

    Go emits up to 9 fractional digits; fromisoformat accepts at most 6.
    """
    ts = re.sub(r"(\.\d{6})\d*", r"\1", ts)
    return datetime.datetime.fromisoformat(ts)


def last_run_completed(log_text):
    """True if the most recent run in the log reached the Complete marker.

    A log file holds every run of one day (the scripts append), so a failure
    after an earlier success must not be hidden. Each run starts with a header
    line "=== <Job>: <date>"; only the text after the last header counts.
    """
    headers = [m.start() for m in re.finditer(r"^=== (?!Complete)", log_text, re.MULTILINE)]
    last_run = log_text[headers[-1]:] if headers else log_text
    return COMPLETE_MARKER in last_run


def parse_dated_job_log(glob_pattern, stale_after):
    """Status of the newest dated log matching the pattern.

    Success means the log contains COMPLETE_MARKER. A partial success (restic
    exit 3) still reaches it; a real failure exits before. Don't grep for
    "error": restic's own success line says "no errors were found".
    """
    path = newest_matching(glob_pattern)
    if not path:
        return {"ok": None, "stale": True, "last_run_human": None, "detail_human": "no log yet"}

    mtime = os.path.getmtime(path)
    age = time.time() - mtime
    return {
        "ok": last_run_completed(read_text(path)),
        "stale": age > stale_after,
        "last_run_human": human_ago(age),
        "detail_human": time.strftime("%a %H:%M", time.localtime(mtime)),
    }


def build_local_daily_status(stale_after):
    """Read from the repo itself, so manual restic runs show up too. The cloud
    and integrity jobs can only be judged from logs: this container has no
    cloud credentials and `restic check` leaves nothing to query.
    """
    if not os.path.isfile(os.path.join(RESTIC_REPO_PATH, "config")):
        return {"ok": False, "stale": True, "last_run_human": None, "detail_human": "backup drive not mounted"}
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
    failed_since = False

    # A failed run newer than the last snapshot would otherwise look fine.
    log_path = newest_matching(os.path.join(BACKUP_LOGS_DIR, "restic-local-*.log"))
    if (
        log_path
        and os.path.getmtime(log_path) > latest.timestamp()
        and not last_run_completed(read_text(log_path))
    ):
        detail += " · a more recent attempt failed"
        failed_since = True

    return {
        "ok": not stale and not failed_since,
        "stale": stale,
        "last_run_human": human_ago(age),
        "detail_human": detail,
    }


def parse_integrity_log(stale_after):
    pattern = os.path.join(BACKUP_LOGS_DIR, "restic-check-*.log")
    result = parse_dated_job_log(pattern, stale_after)
    if result["ok"] is False:
        content = read_text(newest_matching(pattern))
        error_lines = len(re.findall(r"^error:", content, re.IGNORECASE | re.MULTILINE))
        result["detail_human"] = f"failed · {error_lines} error line(s), see log"
    return result


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

    # A stale lock (e.g. from a run cut off by a drive dropout) blocks
    # forget/prune while backups still succeed.
    lock_count = 0
    if mounted:
        try:
            lock_count = len(cached("restic_locks", lambda: run_restic_lines(["list", "locks"])))
        except Exception:
            lock_count = -1  # couldn't tell — don't claim "0 locks" when unsure

    return {"jobs": jobs, "drive": drive, "lock_count": lock_count}


def read_cloud_snapshots_cache():
    """The dashboard has no cloud credentials. backup-restic-cloud.sh writes
    this file after each successful run, so it is only as fresh as that run.
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
    taken = parse_restic_time(snap["time"])
    return {
        "id": snap["short_id"],
        "time_human": taken.strftime("%b %d, %H:%M"),
        "tag": (snap.get("tags") or ["untagged"])[0],
        "repo": repo,
        "_sort_time": taken.timestamp(),
    }


def build_snapshots():
    # No per-snapshot `restic stats`: it walks the whole tree and took 30s+
    # per snapshot on the HDD.
    mounted = os.path.isfile(os.path.join(RESTIC_REPO_PATH, "config"))
    local_snapshots = cached("restic_snapshots", lambda: run_restic(["snapshots"])) if mounted else []
    cloud_snapshots = read_cloud_snapshots_cache()

    result = [_snapshot_row(s, "local") for s in local_snapshots]
    result += [_snapshot_row(s, "cloud") for s in cloud_snapshots]

    # prev_id: the previous snapshot in the same repo, for the UI's `restic diff`.
    for repo in ("local", "cloud"):
        repo_rows = sorted(
            (r for r in result if r["repo"] == repo), key=lambda r: r["_sort_time"]
        )
        for i, row in enumerate(repo_rows):
            row["prev_id"] = repo_rows[i - 1]["id"] if i > 0 else None

    result.sort(key=lambda s: s["_sort_time"], reverse=True)
    for row in result:
        del row["_sort_time"]
    return {"snapshots": result}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # no per-request logging

    def _send(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, status=200):
        self._send(json.dumps(payload).encode(), "application/json", status)

    def _file(self, path, content_type):
        with open(path, "rb") as f:
            self._send(f.read(), content_type)

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
            .replace("__HOST_RESTIC_CLOUD_RCLONE_ARGS__", HOST_RESTIC_CLOUD_RCLONE_ARGS)
            .replace("__HOST_SCRIPTS_DIR__", HOST_SCRIPTS_DIR)
        )
        self._send(html.encode(), "text/html; charset=utf-8")

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
