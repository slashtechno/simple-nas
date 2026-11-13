#!/usr/bin/env python3
"""alert.sh logs every alert and sends it only to the destination its sender names.

Runs the rendered scripts (two paths as arguments: one with destinations, one with none) with a fake curl and a fake logger.
The token files are pointed at temporary files. Standard library only.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

work = Path(tempfile.mkdtemp(dir="/tmp"))
bin_dir = work / "bin"
bin_dir.mkdir()
curl_log = work / "curl"
logger_log = work / "logger"

# curl records its arguments on one line; FAKE_CURL_FAIL=1 makes it fail as a refused alert does.
(bin_dir / "curl").write_text(f'#!/bin/bash\necho "$*" >> {curl_log}\n[ -z "$FAKE_CURL_FAIL" ]\n')
(bin_dir / "curl").chmod(0o755)
(bin_dir / "logger").write_text(f'#!/bin/bash\nprintf "%s|%s\\n" "$2" "$3" >> {logger_log}\n')
(bin_dir / "logger").chmod(0o755)

token = work / "unlock-token"
token.write_text("tk_unlock")


def script(path, name):
    text = Path(path).read_text()
    text = re.sub(r"(?<=token_file=)\S*/alert-tokens/unlock", str(token), text)
    out = work / name
    out.write_text(text)
    return out


def run(path, *args, fail=False):
    curl_log.unlink(missing_ok=True)
    logger_log.unlink(missing_ok=True)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin"}
    if fail:
        env["FAKE_CURL_FAIL"] = "1"
    done = subprocess.run(["bash", str(path), *args], env=env, capture_output=True, text=True, timeout=30)
    return done, (curl_log.read_text() if curl_log.exists() else ""), (logger_log.read_text() if logger_log.exists() else "")


on = script(sys.argv[1], "on.sh")
off = script(sys.argv[2], "off.sh")

# A sender with a destination and no token: logged, then sent with the timeout, --fail, the host's title and no login.
done, curl, logged = run(on, "system", "backup", "backup failed", "disk full")
assert done.returncode == 0, done
assert logged == "backup|disk full\n", logged
assert "https://ntfy.sh/host-topic" in curl and "--max-time 15" in curl and "--fail" in curl, curl
assert "Title: " in curl and ": backup failed" in curl and "Priority: high" in curl and "-d disk full" in curl, curl
assert "Authorization" not in curl, curl

# A sender with a token sends it as a Bearer login, read from its own file.
done, curl, logged = run(on, "unlock", "unlock", "encrypted folders need attention", "Locked: /mnt/a")
assert done.returncode == 0 and logged == "unlock|Locked: /mnt/a\n", (done, logged)
assert "https://ntfy.sh/unlock-topic" in curl and "Authorization: Bearer tk_unlock" in curl, curl
assert "host-topic" not in curl, curl

# A refused alert is written to the system log beside it, and does not fail the caller.
done, curl, logged = run(on, "system", "backup", "backup failed", "disk full", fail=True)
assert done.returncode == 0 and "the alert could not be sent to ntfy" in logged, (done, logged)

# A sender that names no destination only writes to the log.
for sender in ("system", "unlock"):
    done, curl, logged = run(off, sender, "backup", "backup failed", "disk full")
    assert done.returncode == 0 and curl == "" and logged == "backup|disk full\n", (sender, done, curl, logged)

# An unknown sender is an error, and the message is still logged.
done, curl, logged = run(on, "nobody", "backup", "backup failed", "disk full")
assert done.returncode == 1 and curl == "" and "unknown sender nobody" in logged and logged.startswith("backup|disk full"), (done, curl, logged)

print("alert.sh: each sender sends to its own destination with its own token; none sends only to the log")
