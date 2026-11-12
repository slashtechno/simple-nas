#!/usr/bin/env python3
"""A web page that shows, unlocks and locks the encrypted folders of this host (docs/encryption.md#unlock-page).

The Ansible role puts Tinyauth in front of it, so whoever reaches the page is logged in. A button sends one word, unlock, lock or
status, to a socket that only root on the host can use. A script there compares the word with those three and runs unlock.sh. For
unlock the owner types the passphrase on the page and the page passes it on the socket. Nothing stores it: not this page, not the
host, and it is in no log, URL or reply.

  python3 app.py           serve the page
  python3 app.py check     print the host's status; exit 1 if the socket cannot be reached

The socket path is the environment variable UNLOCK_SOCKET; the default is where the role's compose file mounts it.
"""

import html
import http.server
import os
import socket
import sys
import urllib.parse

SOCKET = os.environ.get("UNLOCK_SOCKET", "/run/unlock/unlock.sock")
PORT = int(os.environ.get("PORT", "8080"))

PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Unlock</title><body style="font:16px system-ui;max-width:32rem;margin:2rem auto;padding:0 1rem">
<h1>Unlock</h1>{result}
<form method=post><input type=password name=passphrase autocomplete=current-password placeholder=Passphrase>
<button name=action value=unlock>Unlock</button>
<button name=action value=lock onclick="return confirm('Stop the services that use the folders and lock them?')">Lock</button></form>
<h2>Status</h2>{status}"""


def ask(word, passphrase=""):
    """Send one word to the host's script. Returns (exit code, output). The script accepts unlock, lock and status only.
    The passphrase follows the word on its own line, for unlock."""
    try:
        with socket.socket(socket.AF_UNIX) as conn:
            conn.settimeout(900)
            conn.connect(SOCKET)
            conn.sendall(word.encode() + b"\n" + (passphrase.encode() + b"\n" if passphrase else b""))
            conn.shutdown(socket.SHUT_WR)
            reply = b""
            while chunk := conn.recv(4096):
                reply += chunk
    except OSError as error:
        return 255, f"Cannot reach {SOCKET}: {error}"
    text = reply.decode(errors="replace").rstrip("\n")
    output, _, last = text.rpartition("\n")
    if not last.startswith("exit "):  # the script did not finish: show everything it said
        return 255, text
    return int(last.removeprefix("exit ") or 255), output


def same_origin(headers):
    """A browser sends Origin on a POST. A form on another site would carry the Tinyauth cookie, so refuse a different one."""
    origin = headers.get("Origin")
    return origin is None or urllib.parse.urlparse(origin).netloc == headers.get("Host")


def good_passphrase(text):
    """One line of 1 to 1024 characters. The script reads one line, and bash cannot hold a NUL."""
    return 0 < len(text.encode()) <= 1024 and not any(c in text for c in "\n\r\0")


def render(code, output):
    return f"<h2>{'ok' if code == 0 else 'failed'}</h2><pre>{html.escape(output)}</pre>"


class Handler(http.server.BaseHTTPRequestHandler):
    def send_page(self, result, status=200):
        data = PAGE.format(result=result, status=render(*ask("status"))).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.send_page("")

    def do_POST(self):
        # Read the body first: closing a connection with unread data can reset it and lose the reply.
        fields = urllib.parse.parse_qs(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 16384)).decode())
        if not same_origin(self.headers):
            return self.send_page("<p>Refused: the request came from another site.</p>", 403)
        action = fields.get("action", [""])[0]
        if action not in ("unlock", "lock"):
            return self.send_page("<p>Unknown action.</p>", 400)
        if action == "lock":
            return self.send_page(render(*ask("lock")))
        passphrase = fields.get("passphrase", [""])[0]
        if not good_passphrase(passphrase):  # never shown back
            return self.send_page("<p>Type the passphrase: one line, up to 1024 characters.</p>", 400)
        self.send_page(render(*ask("unlock", passphrase)))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        code, output = ask("status")
        print(output)
        sys.exit(0 if code == 0 else 1)
    # HTTPServer, not ThreadingHTTPServer: one request at a time, so an unlock and a lock never overlap.
    http.server.HTTPServer(("", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
