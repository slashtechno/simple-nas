#!/usr/bin/env python3
"""Read-only backup status dashboard (the "Snapshot Deck").

Serves index.html plus two JSON endpoints, /api/status and /api/snapshots,
built from `restic --no-lock` and the status files the backup scripts write. The repo and
password file are mounted read-only, so nothing here can change a backup;
destructive actions are only shown in the UI as SSH commands to run by hand.

Contract with roles/backup: snapshot tags `daily`/`weekly` and the status files named
in JOB_STATUS_FILES (written by roles/backup/templates/status-report.j2). The logs are for
people to read; this page never parses them.
"""

import datetime
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

# Host-side values from the compose file (HOST_CONFIG, JSON): used to build the SSH commands shown in
# the UI, which run on the host, not in this container.
HOST_CONFIG = json.loads(os.environ["HOST_CONFIG"])

PORT = int(os.environ.get("PORT", "8080"))
CACHE_TTL_SECONDS = 30

LOCAL_STALE_AFTER_SECONDS = 36 * 3600       # daily job — allow a missed run
WEEKLY_STALE_AFTER_SECONDS = 9 * 24 * 3600  # weekly jobs — allow a missed week

# One file per job in BACKUP_LOGS_DIR, written by the backup scripts when a run starts and when it ends.
JOB_STATUS_FILES = {
    "local_daily": "restic-local.status.json",
    "cloud_weekly": "restic-cloud.status.json",
    "integrity_check": "restic-check.status.json",
}

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


def repo_mounted():
    """The repository's config file exists only while the backup drive is mounted."""
    return os.path.isfile(os.path.join(RESTIC_REPO_PATH, "config"))


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


def parse_restic_time(ts):
    """Parse restic's timestamp into an aware datetime.

    Go emits up to 9 fractional digits; fromisoformat accepts at most 6.
    """
    ts = re.sub(r"(\.\d{6})\d*", r"\1", ts)
    return datetime.datetime.fromisoformat(ts)


def job_view(ok, stale, last_run_human, detail_human, running=False):
    return {
        "ok": ok,
        "stale": stale,
        "running": running,
        "last_run_human": last_run_human,
        "detail_human": detail_human,
    }


def read_job_status(job, stale_after):
    """A job's status, from the file its script writes.

    Only `result: ok` in a file younger than `stale_after` counts as ok. A missing, malformed or
    too old file is an error, never ok. `finished: null` is what the script writes when a run
    starts: the run is still going if the file is fresh, and was killed if it is old.
    """
    path = os.path.join(BACKUP_LOGS_DIR, JOB_STATUS_FILES[job])
    try:
        mtime = os.path.getmtime(path)
        with open(path, "r") as f:
            status = json.load(f)
        started = parse_restic_time(status["started"])
        finished = status["finished"]
        result = status["result"]
        exit_code = status["exit_code"]
    except FileNotFoundError:
        return job_view(False, True, None, "no status file: this job has not run since it was deployed")
    except (OSError, ValueError, KeyError, TypeError):
        return job_view(False, True, None, "status file unreadable; read the job's log")
    if result not in ("ok", "failed"):
        return job_view(False, True, None, "status file unreadable; read the job's log")

    age = time.time() - mtime
    stale = age > stale_after
    when = time.strftime("%a %H:%M", time.localtime(mtime))
    if finished is None:
        if stale:
            return job_view(False, True, human_ago(age), f"a run started {started:%a %H:%M} and never finished; read its log")
        return job_view(False, False, human_ago(age), f"running since {started:%H:%M}", running=True)
    if result != "ok":
        return job_view(False, stale, human_ago(age), f"exit {exit_code} at {when}; read the job's log")
    if stale:
        return job_view(False, True, human_ago(age), f"last run finished {when}, too old for this schedule")
    return job_view(True, False, human_ago(age), when)


def build_local_status(stale_after):
    """A status file read through an unmounted mount point is not the drive's, so it is no evidence."""
    if not repo_mounted():
        return job_view(False, True, None, "backup drive not mounted")
    return read_job_status("local_daily", stale_after)


def build_status():
    jobs = {
        "local_daily": build_local_status(LOCAL_STALE_AFTER_SECONDS),
        "integrity_check": read_job_status("integrity_check", WEEKLY_STALE_AFTER_SECONDS),
    }
    # A host without a cloud backup has no cloud job to show.
    if HOST_CONFIG["cloudEnabled"]:
        jobs["cloud_weekly"] = read_job_status("cloud_weekly", WEEKLY_STALE_AFTER_SECONDS)

    mounted = repo_mounted()
    drive = {"mounted": mounted, "label": HOST_CONFIG["backupDrive"]}
    if mounted:
        usage = shutil.disk_usage(RESTIC_REPO_PATH)
        drive["free_human"] = f"{human_bytes(usage.free)} free"
        percent_used = round(usage.used / usage.total * 100)
        drive["detail_human"] = f"of {human_bytes(usage.total)} · {percent_used}% used"
    else:
        drive["free_human"] = None
        drive["detail_human"] = "check the USB connection; the drive mounts itself when it is back"

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
    mounted = repo_mounted()
    local_snapshots = cached("restic_snapshots", lambda: run_restic(["snapshots"])) if mounted else []
    cloud_snapshots = read_cloud_snapshots_cache() if HOST_CONFIG["cloudEnabled"] else []

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
        # "<" is escaped so no value can end the script tag early.
        config_json = json.dumps(HOST_CONFIG).replace("<", "\\u003c")
        html = html.replace("__HOST_CONFIG__", config_json)
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
