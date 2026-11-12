#!/usr/bin/env python3
"""The unlock page's request script runs only unlock, lock and status, whatever it is sent, and the page works with it.

Runs the rendered script (the path is the argument) with a fake unlock.sh that records what it was given. Each of the three words
runs the one fixed command, and every other input, including shell syntax, long input and extra lines, runs nothing. The
passphrase typed for unlock reaches unlock.sh as exactly its bytes on standard input, and is in no argument, reply or page. Then it
starts the page (app.py) against a socket served the way systemd serves it (one copy of the script per connection, the connection as
its input and output) and uses the page over HTTP. Standard library only.
"""
import http.server
import importlib.util
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

script = Path(sys.argv[1]).read_text()
work = Path(tempfile.mkdtemp(dir="/tmp"))  # short: a socket path is limited to about 100 characters
log = work / "log"
marker = work / "INJECTED"

# The fake records its arguments. Called with none (an unlock), it keeps what it read from standard input byte for byte: the page
# asks for the status after every action, and that call must not overwrite it. The path in the script points at the fake.
stdin_file = work / "stdin.bin"
(work / "unlock.sh").write_text(f'#!/bin/bash\n[ $# -eq 0 ] && cat > {stdin_file}\necho "args:[$*]" >> {log}\necho "ran [$*]"\n')
(work / "unlock.sh").chmod(0o755)
script = re.sub(r"[^\s<]*/unlock\.sh", str(work / "unlock.sh"), script)
(work / "request.sh").write_text(script)


def send(payload: bytes):
    log.unlink(missing_ok=True)
    stdin_file.unlink(missing_ok=True)
    done = subprocess.run(["bash", str(work / "request.sh")], input=payload, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, cwd=work)
    return done.stdout.decode(), (log.read_text() if log.exists() else "")


for word, expected in [("lock", "args:[--lock]"), ("status", "args:[--status]")]:
    for ending in (b"\n", b""):
        output, ran = send(word.encode() + ending)
        assert ran == expected + "\n", (word, ending, ran)
        assert output.rstrip().endswith("exit 0"), (word, output)

# unlock: the line after the word reaches unlock.sh as exactly those bytes on standard input, never as an argument.
passphrases = [
    "the-passphrase", "with spaces  and\ttabs", "quote'single\"double", "$(touch INJECTED)", "`touch INJECTED`", "a;b|c&d#e>f<g",
    "back\\slash\\n", "ünïcödé-密码", "-n", "--lock", "x" * 1024,
]
for passphrase in passphrases:
    for ending in (b"\n", b""):
        output, ran = send(b"unlock\n" + passphrase.encode() + ending)
        assert ran == "args:[]\n" and stdin_file.read_bytes() == passphrase.encode(), (passphrase[:30], ran)
        assert output.rstrip().endswith("exit 0") and passphrase not in output, (passphrase[:30], output)
# No passphrase, or an empty line: nothing runs. A longer one is cut at 1024 characters, so it fails to unlock, and runs no shell.
for payload in [b"unlock\n", b"unlock", b"unlock\n\n", b"unlock\n\nlock\n"]:
    output, ran = send(payload)
    assert ran == "" and "no passphrase sent" in output and output.rstrip().endswith("exit 1"), (payload, ran, output)
output, ran = send(b"unlock\n" + b"y" * 5000 + b"\n")
assert stdin_file.read_bytes() == b"y" * 1024 and ran == "args:[]\n"
# lock and status never read the passphrase line.
output, ran = send(b"lock\nsecret-passphrase\n")
assert ran == "args:[--lock]\n" and not stdin_file.exists(), ran

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
assert ran in ("", "args:[--lock]\n") and not marker.exists(), ran

# Extra lines after a good word are never run: one command runs, once.
output, ran = send(b"lock\nunlock\nlock\n")
assert ran.count("args:") == 1 and "--lock" in ran, ran

print("unlock page: the request script runs unlock, lock and status only")


# The page against a socket served like systemd does: each connection runs one copy of the script.
sock_path = str(work / "unlock.sock")
server = socket.socket(socket.AF_UNIX)
server.bind(sock_path)
server.listen(8)


def serve():
    while True:
        conn, _ = server.accept()
        subprocess.Popen(["bash", str(work / "request.sh")], stdin=conn, stdout=conn, stderr=conn).wait()
        conn.close()


threading.Thread(target=serve, daemon=True).start()

os.environ["UNLOCK_SOCKET"] = sock_path
spec = importlib.util.spec_from_file_location("unlock_app", Path(__file__).resolve().parent.parent / "roles/unlock_page/files/app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

assert app.ask("status") == (0, "ran [--status]"), app.ask("status")
assert app.ask("lock") == (0, "ran [--lock]")
assert app.ask("unlock", "the-passphrase") == (0, "ran []") and stdin_file.read_bytes() == b"the-passphrase"
code, output = app.ask("lock; " + touch)
assert code == 1 and "unknown request" in output and not marker.exists(), (code, output)
app.SOCKET = str(work / "missing.sock")
code, output = app.ask("status")
assert code == 255 and "Cannot reach" in output, (code, output)
app.SOCKET = sock_path

web = http.server.HTTPServer(("127.0.0.1", 0), app.Handler)
threading.Thread(target=web.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{web.server_port}/"


def fetch(data=None, origin=None):
    request = urllib.request.Request(base, data=data and data.encode())
    if origin:
        request.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


form = urllib.parse.urlencode


status, page = fetch()
assert status == 200 and "ran [--status]" in page and "the-passphrase" not in page and "type=password" in page
assert "prefers-color-scheme" in page and "/*css*/" not in page  # the stylesheet is in the page
status, page = fetch("action=lock", origin=base.rstrip("/"))
assert status == 200 and "ran [--lock]" in page, page
hard = "p@ss word&=%+;$(x)\"'"  # characters that the form encoding and a shell would each treat specially
status, page = fetch(form({"action": "unlock", "passphrase": hard}))  # no Origin header: a command-line client, not a browser
assert status == 200 and "ran []" in page and hard not in page and stdin_file.read_bytes() == hard.encode(), page
assert "type=password" in page and hard not in page
for bad in ["", "two\nlines", "cr\rhere", "nul\0here", "z" * 1025]:  # refused by the page, never sent, never shown back
    stdin_file.unlink(missing_ok=True)  # only an unlock writes it
    status, page = fetch(form({"action": "unlock", "passphrase": bad}), origin=base.rstrip("/"))
    assert status == 400 and "Type the passphrase" in page and not stdin_file.exists() and (not bad or bad not in page), (bad[:10], status)
status, page = fetch(form({"action": "unlock", "passphrase": hard}), origin="https://evil.example")
assert status == 403 and "another site" in page and hard not in page
status, page = fetch("action=lock", origin="https://evil.example")
assert status == 403 and "another site" in page
status, page = fetch(f"action=lock; {touch}")
assert status == 400 and not marker.exists()
status, page = fetch("action=status")  # only the two buttons are actions
assert status == 400

print("unlock page: the page works over the socket, and refuses another site and any other action")
