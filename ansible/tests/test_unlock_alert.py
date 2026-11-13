#!/usr/bin/env python3
"""unlock.sh --alert sends one alert naming the locked folders, and nothing when none is locked.

Runs the rendered script (the path is the argument) with a fake mountpoint and a fake alert.sh. The folders' ciphertext paths in
the script are pointed at temporary folders so the "files exist" check passes. Standard library only.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

work = Path(tempfile.mkdtemp(dir="/tmp"))
bin_dir = work / "bin"
bin_dir.mkdir()
sent = work / "sent"

# mountpoint -q <path>/. succeeds for every path listed in "unlocked" (one path per line).
(bin_dir / "mountpoint").write_text('#!/bin/bash\npath="${2%/.}"\ngrep -qxF "$path" "$FAKE/unlocked"\n')
(bin_dir / "mountpoint").chmod(0o755)
# curl records "message|unlock|title" for the ntfy post; logger records "tag|message" for the system log.
(bin_dir / "curl").write_text(
    '#!/bin/bash\nmsg=""; title=""\n'
    'while [ $# -gt 0 ]; do case "$1" in -d) msg="$2"; shift;; -H) case "$2" in Title:*) title="${2#Title: }";; esac; shift;; esac; shift; done\n'
    f'printf "%s|unlock|%s\\n" "$msg" "$title" >> {sent}\n')
(bin_dir / "curl").chmod(0o755)
(bin_dir / "logger").write_text(f'#!/bin/bash\nprintf "%s|%s\\n" "$2" "$3" >> {work / "logged"}\n')
(bin_dir / "logger").chmod(0o755)

script = Path(sys.argv[1]).read_text()
folder_line = re.compile(r"^(\s*show_state )(\S+) (\S+)( >/dev/null)$", re.M)
mounts = [m.group(2).strip("'") for m in folder_line.finditer(script)]
assert mounts, "the --alert branch lists the folders"


ciphers = {}


def cipher_dir(mount, cipher):
    path = work / "cipher" / cipher.strip("'").strip("/").replace("/", "_")
    path.mkdir(parents=True, exist_ok=True)
    ciphers[mount.strip("'")] = path
    return path


script = folder_line.sub(lambda m: f"{m.group(1)}{m.group(2)} {cipher_dir(m.group(2), m.group(3))}{m.group(4)}", script)
script = re.sub(r"cat \S*unlock-ntfy-token", f"echo token", script)
(work / "unlock.sh").write_text(script)


def run(unlocked, missing=()):
    sent.unlink(missing_ok=True)
    (work / "logged").unlink(missing_ok=True)
    for mount, path in ciphers.items():   # a folder whose drive is not mounted has no ciphertext folder
        path.mkdir(exist_ok=True)
        if mount in missing:
            path.rmdir()
    (work / "unlocked").write_text("".join(f"{m}\n" for m in unlocked))
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "FAKE": str(work)}
    done = subprocess.run(["bash", str(work / "unlock.sh"), "--alert"], env=env, capture_output=True, text=True, timeout=30)
    return done, (sent.read_text() if sent.exists() else "")


done, text = run(mounts)
assert done.returncode == 0 and text == "", ("everything unlocked sends nothing", done, text)
assert done.stdout == "", "--alert prints nothing of its own"

# Each folder locked in turn, the others unlocked: only that one is named.
for locked in mounts:
    done, text = run([m for m in mounts if m != locked])
    assert done.returncode == 0 and text.count("\n") == 1, (done, text)
    message, tag, title = text.rstrip("\n").split("|")
    assert locked in message and all(m not in message for m in mounts if m != locked), message
    assert "Locked, waiting for the passphrase" in message and "nlock" in message, message
    assert tag == "unlock" and "attention" in title, (tag, title)
    logged = (work / "logged").read_text()
    assert logged.startswith("unlock|") and locked in logged, logged   # the system log gets it too

done, text = run([])
assert all(m in text for m in mounts), text

# A folder with no ciphertext (its drive did not mount) alerts too, apart from the locked ones, and the others stay out of it.
for gone in mounts:
    done, text = run([m for m in mounts if m != gone], missing=[gone])
    assert done.returncode == 0 and text.count("\n") == 1, (done, text)
    message = text.split("|")[0]
    assert "No encrypted files found" in message and gone in message and "Locked, waiting" not in message, message
    assert all(m not in message for m in mounts if m != gone), message

print("unlock.sh --alert: one alert naming the locked folders, none when everything is unlocked")
