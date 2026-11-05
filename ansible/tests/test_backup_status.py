#!/usr/bin/env python3
"""The dashboard's job status comes only from the status files the backup scripts write.

Runs app.py against a temporary repository and logs directory with a fake `restic` on PATH. A missing, stale,
malformed or failed status file must never be reported as ok, and the cloud job exists only when the cloud
backup is on. Standard library only.
"""
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "roles/backup_status/files/app.py"

# A run that succeeded, as roles/backup/templates/status-report.j2 writes it.
OK = {"job": "local", "started": "2025-01-01T02:00:00+00:00", "finished": "2025-01-01T02:20:00+00:00",
      "result": "ok", "exit_code": 0}


def load_app(work, cloud_enabled):
    config = {
        "sshUser": "u", "backupDrive": "/mnt/backup", "cloudEnabled": cloud_enabled, "resticRepoPath": "/r",
        "resticPasswordFile": "/p", "resticCloudRepository": "x", "resticLocalRetention": "a",
        "resticCloudRetention": "b", "resticCloudRcloneArgs": "--x", "scriptsDir": "/s",
    }
    os.environ.update(
        RESTIC_REPO_PATH=str(work / "repo"), RESTIC_PASSWORD_FILE=str(work / "pw"),
        BACKUP_LOGS_DIR=str(work / "logs"), HOST_CONFIG=json.dumps(config),
    )
    spec = importlib.util.spec_from_file_location("app", APP)
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    return app


def status_of(work, cloud_enabled, job):
    return load_app(work, cloud_enabled).build_status()["jobs"][job]


def put(work, name, text):
    path = work / "logs" / name
    path.write_text(text)
    return path


with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp)
    (work / "repo").mkdir()
    (work / "repo/config").touch()
    (work / "logs").mkdir()
    (work / "bin").mkdir()
    fake_restic = work / "bin/restic"
    fake_restic.write_text("#!/bin/sh\necho '[]'\n")
    fake_restic.chmod(0o755)
    os.environ["PATH"] = f"{work / 'bin'}{os.pathsep}{os.environ['PATH']}"

    assert "cloud_weekly" in load_app(work, True).build_status()["jobs"]
    assert "cloud_weekly" not in load_app(work, False).build_status()["jobs"]

    # No status file: an error, never ok.
    for job in ("local_daily", "integrity_check"):
        s = status_of(work, False, job)
        assert s["ok"] is False and s["stale"] is True and s["running"] is False, (job, s)

    # A fresh successful run is ok.
    path = put(work, "restic-local.status.json", json.dumps(OK))
    s = status_of(work, False, "local_daily")
    assert s["ok"] is True and s["stale"] is False, s

    # The same file once it is older than the job's window: stale, not ok.
    old = time.time() - 40 * 3600
    os.utime(path, (old, old))
    s = status_of(work, False, "local_daily")
    assert s["ok"] is False and s["stale"] is True, s

    # A failed run.
    put(work, "restic-local.status.json", json.dumps({**OK, "result": "failed", "exit_code": 3}))
    s = status_of(work, False, "local_daily")
    assert s["ok"] is False and s["stale"] is False and "exit 3" in s["detail_human"], s

    # The file as written when a run starts: running while fresh, dead once old, never ok.
    path = put(work, "restic-local.status.json", json.dumps({**OK, "result": "failed", "finished": None, "exit_code": None}))
    s = status_of(work, False, "local_daily")
    assert s["ok"] is False and s["running"] is True and s["stale"] is False, s
    # Still running after the daily window: a first backup can take days.
    os.utime(path, (old, old))
    s = status_of(work, False, "local_daily")
    assert s["ok"] is False and s["running"] is True and s["stale"] is False, s
    very_old = time.time() - 80 * 3600
    os.utime(path, (very_old, very_old))
    s = status_of(work, False, "local_daily")
    assert s["ok"] is False and s["running"] is False and s["stale"] is True, s

    # Malformed, truncated and unknown values are errors, not ok.
    for bad in ("{not json", "[]", '{"job":"local"}', json.dumps({**OK, "result": "green"})):
        put(work, "restic-local.status.json", bad)
        s = status_of(work, False, "local_daily")
        assert s["ok"] is False and s["stale"] is True, (bad, s)

    # The cloud job reads its own file.
    put(work, "restic-cloud.status.json", json.dumps(OK))
    assert status_of(work, True, "cloud_weekly")["ok"] is True

    # A drive that is not mounted beats a status file that says ok.
    put(work, "restic-local.status.json", json.dumps(OK))
    (work / "repo/config").unlink()
    s = status_of(work, False, "local_daily")
    assert s["ok"] is False and "not mounted" in s["detail_human"], s

print("backup_status: job status comes from the status files; missing, stale and malformed are errors")
sys.exit(0)
