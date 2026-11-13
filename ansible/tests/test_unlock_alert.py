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
(work / "alert.sh").write_text(f'#!/bin/bash\nprintf "%s|%s|%s\\n" "$1" "$2" "$3" >> {sent}\n')
(work / "alert.sh").chmod(0o755)

script = Path(sys.argv[1]).read_text()
folder_line = re.compile(r"^(\s*show_state )(\S+) (\S+)( >/dev/null)$", re.M)
mounts = [m.group(2).strip("'") for m in folder_line.finditer(script)]
assert mounts, "the --alert branch lists the folders"


def cipher_dir(cipher):
    path = work / "cipher" / cipher.strip("'").strip("/").replace("/", "_")
    path.mkdir(parents=True, exist_ok=True)
    return path


script = folder_line.sub(lambda m: f"{m.group(1)}{m.group(2)} {cipher_dir(m.group(3))}{m.group(4)}", script)
script = re.sub(r"exec \S*alert\.sh", f"exec {work / 'alert.sh'}", script)
(work / "unlock.sh").write_text(script)


def run(unlocked):
    sent.unlink(missing_ok=True)
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
    assert tag == "unlock" and "passphrase" in title, (tag, title)

done, text = run([])
assert all(m in text for m in mounts), text

print("unlock.sh --alert: one alert naming the locked folders, none when everything is unlocked")
