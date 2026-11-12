#!/usr/bin/env python3
"""The unlock page's request script runs only unlock, lock and status, whatever it is sent.

Runs the rendered script (the path is the argument) with a fake unlock.sh that records what it was given. Each of the three words
runs the one fixed command, and every other input, including shell syntax, long input and extra lines, runs nothing. Standard
library only.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

script = Path(sys.argv[1]).read_text()
work = Path(tempfile.mkdtemp())
log = work / "log"
marker = work / "INJECTED"

# The fake records its arguments and what it read from standard input. The real paths in the script point at the fake.
(work / "unlock.sh").write_text(f'#!/bin/bash\necho "args:[$*] stdin:[$(cat)]" >> {log}\n')
(work / "unlock.sh").chmod(0o755)
(work / "passphrase").write_text("the-passphrase")
script = re.sub(r"[^\s<]*/unlock\.sh", str(work / "unlock.sh"), script)
script = re.sub(r"[^\s<]*/unlock-passphrase", str(work / "passphrase"), script)
(work / "request.sh").write_text(script)


def send(payload: bytes):
    log.unlink(missing_ok=True)
    done = subprocess.run(["bash", str(work / "request.sh")], input=payload, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, cwd=work)
    return done.stdout.decode(), (log.read_text() if log.exists() else "")


for word, expected in [("unlock", "args:[] stdin:[the-passphrase]"), ("lock", "args:[--lock] stdin:[]"), ("status", "args:[--status] stdin:[]")]:
    for ending in (b"\n", b""):
        output, ran = send(word.encode() + ending)
        assert expected in ran and ran.count("args:") == 1, (word, ending, ran)
        assert output.rstrip().endswith("exit 0"), (word, output)

# Nothing else may run anything, and none of it may reach a shell.
touch = f"touch {marker}"
for payload in [
    b"", b"\n", b"LOCK\n", b" lock\n", b"lock \n", b"--lock\n", b"unlock lock\n", b"lock extra\n",
    f"lock; {touch}\n".encode(), f"$({touch})\n".encode(), f"`{touch}`\n".encode(), f"lock && {touch}\n".encode(),
    f"lock|{touch}\n".encode(), b"../lock\n", b"a" * 100000, b"lock" + b" " * 12 + b"x\n", b"\r\n", b"lock\r\n",
]:
    output, ran = send(payload)
    assert ran == "" and not marker.exists(), (payload[:40], ran)
    assert "unknown request" in output and output.rstrip().endswith("exit 1"), (payload[:40], output)

# bash's read drops NUL bytes, so a word with one in it can still be a good word. What runs is still only the fixed command.
output, ran = send(f"lock\x00; {touch}\n".encode())
assert ran in ("", "args:[--lock] stdin:[]\n") and not marker.exists(), ran

# Extra lines after a good word are never read: one command runs, once.
output, ran = send(b"lock\nunlock\nlock\n")
assert ran.count("args:") == 1 and "--lock" in ran, ran

print("unlock page: the request script runs unlock, lock and status only")
