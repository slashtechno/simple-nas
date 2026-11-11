#!/usr/bin/env python3
"""A web page that unlocks the encrypted folders of your hosts (unlock-page/README.md).

You type a password. The page then runs `unlock.sh` on each host over SSH and feeds it the gocryptfs passphrase,
which only this program knows. The SSH key is limited on the host to that one command (docs/encryption.md).

  python3 app.py           serve the page
  python3 app.py hash      print the value for UNLOCK_PASSWORD_HASH (asks for the password)
  python3 app.py check     ask each host if it is unlocked, without sending the passphrase; exit 1 if one cannot be reached

Settings are environment variables, listed in README.md.
"""

import getpass
import hashlib
import hmac
import html
import http.server
import os
import secrets
import subprocess
import sys
import time
import urllib.parse

# user@address for each host, as name=user@address, comma separated: pi4=user@pi4.example.ts.net,pinas=user@pinas.example.ts.net
HOSTS = [h.split("=", 1) for h in os.environ.get("UNLOCK_HOSTS", "").split(",") if h]
if any(len(h) != 2 for h in HOSTS):
    sys.exit("UNLOCK_HOSTS must look like name=user@address,name=user@address")
SSH_KEY = os.environ.get("UNLOCK_SSH_KEY", "/run/unlock/ssh_key")
KNOWN_HOSTS = os.environ.get("UNLOCK_KNOWN_HOSTS", "/run/unlock/known_hosts")
PASSPHRASE_FILE = os.environ.get("UNLOCK_PASSPHRASE_FILE", "/run/unlock/passphrase")
# "password": the page asks for UNLOCK_PASSWORD_HASH's password. "none": something in front of the page (Tinyauth, a VPN)
# already did the login. Never an empty hash: a missing setting must not open the page.
LOGIN = os.environ.get("UNLOCK_LOGIN", "password")
PASSWORD_HASH = os.environ.get("UNLOCK_PASSWORD_HASH", "")
PORT = int(os.environ.get("PORT", "8080"))

PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Unlock</title><body style="font:16px system-ui;max-width:32rem;margin:2rem auto;padding:0 1rem">
<h1>Unlock</h1>{form}{result}"""
FORM = """<form method=post>{field}<button>Unlock {names}</button></form>"""
FIELD = """<p><input type=password name=password placeholder=Password autofocus required style="font:inherit;width:100%"></p>"""


def hash_password(password, salt=None):
    """scrypt$<salt>$<hash>, all hex. scrypt is slow on purpose, so each guess costs time."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def password_ok(password):
    try:
        _, salt, _ = PASSWORD_HASH.split("$")
        return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), PASSWORD_HASH)
    except ValueError:  # no or malformed hash: nothing is accepted
        return False


def ssh(target, stdin_text):
    """Run the forced command on a host. Returns (exit code, output). The command is fixed on the host, not chosen here."""
    command = ["ssh", "-i", SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
               "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", target]
    try:
        done = subprocess.run(command, input=stdin_text, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return 255, "timed out"
    return done.returncode, (done.stdout + done.stderr).strip()


def unlock_all():
    try:
        with open(PASSPHRASE_FILE) as f:
            passphrase = f.read().rstrip("\r\n")  # a file made with echo ends with a newline the passphrase does not have
    except OSError as error:
        return [("passphrase", 1, f"Cannot read {PASSPHRASE_FILE}: {error}")]
    return [(name, *ssh(target, passphrase)) for name, target in HOSTS]


def check_all():
    """Empty input: an unlocked host says so (exit 0), a locked one says no passphrase was given (exit 1)."""
    report = []
    for name, target in HOSTS:
        code, output = ssh(target, "")
        if code == 0:
            report.append((name, "unlocked", True))
        elif "no passphrase given" in output:
            report.append((name, "LOCKED (the page can unlock it)", True))
        else:
            report.append((name, f"CANNOT UNLOCK: exit {code}: {output}", False))
    return report


class Handler(http.server.BaseHTTPRequestHandler):
    def send_page(self, body, status=200):
        data = PAGE.format(form=FORM.format(field=FIELD if LOGIN == "password" else "",
                                           names=html.escape(", ".join(n for n, _ in HOSTS))), result=body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.send_page("")

    def do_POST(self):
        fields = urllib.parse.parse_qs(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4096)).decode())
        if LOGIN == "password" and not password_ok(fields.get("password", [""])[0]):
            time.sleep(2)  # one request at a time (see below) plus this: about 30 guesses a minute
            return self.send_page("<p>Wrong password.</p>", 403)
        body = "".join(
            f"<h2>{html.escape(name)}: {'ok' if code == 0 else 'failed'}</h2><pre>{html.escape(output)}</pre>"
            for name, code, output in unlock_all())
        self.send_page(body)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "hash":
        print(hash_password(getpass.getpass("Password for the page: ")))
    elif len(sys.argv) > 1 and sys.argv[1] == "check":
        report = check_all()
        for name, state, _ in report:
            print(f"{name}: {state}")
        sys.exit(0 if all(ok for _, _, ok in report) else 1)
    else:
        if LOGIN not in ("password", "none"):
            sys.exit("UNLOCK_LOGIN must be password or none")
        if LOGIN == "password" and not PASSWORD_HASH:
            sys.exit("Set UNLOCK_PASSWORD_HASH (python3 app.py hash), or UNLOCK_LOGIN=none if a login sits in front of the page.")
        if not HOSTS:
            sys.exit("Set UNLOCK_HOSTS, for example pi4=user@pi4.example.ts.net")
        # HTTPServer, not ThreadingHTTPServer: one request at a time, so guesses and unlocks never overlap.
        http.server.HTTPServer(("", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
