#!/usr/bin/env python3
"""The dashboard builds its status from HOST_CONFIG: the cloud job exists only when the cloud backup is on.

Runs app.py against an empty repository folder with a fake `restic` on PATH. Standard library only.
"""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "roles/backup_status/files/app.py"


def job_names(cloud_enabled, workdir):
    config = {
        "sshUser": "u", "backupDrive": "/mnt/backup", "cloudEnabled": cloud_enabled, "resticRepoPath": "/r",
        "resticPasswordFile": "/p", "resticCloudRepository": "x", "resticLocalRetention": "a",
        "resticCloudRetention": "b", "resticCloudRcloneArgs": "--x", "scriptsDir": "/s",
    }
    os.environ.update(
        RESTIC_REPO_PATH=str(workdir / "repo"), RESTIC_PASSWORD_FILE=str(workdir / "pw"),
        BACKUP_LOGS_DIR=str(workdir / "logs"), HOST_CONFIG=json.dumps(config),
    )
    spec = importlib.util.spec_from_file_location("app", APP)
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    return sorted(app.build_status()["jobs"])


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

    with_cloud = job_names(True, work)
    without_cloud = job_names(False, work)

assert "cloud_weekly" in with_cloud, with_cloud
assert "cloud_weekly" not in without_cloud, without_cloud
print("backup_status: cloud job shown only when the cloud backup is on")
sys.exit(0)
