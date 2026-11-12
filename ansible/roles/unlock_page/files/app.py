#!/usr/bin/env python3
"""A web page that shows, unlocks and locks the encrypted folders of your hosts (docs/encryption.md#unlock-page).

The Ansible role puts Tinyauth in front of it, so whoever reaches the page is logged in. A button runs `unlock.sh` on each
host over SSH, and Unlock also sends it the gocryptfs passphrase, which only this program can read. The SSH key is limited
on the host to that one script, and the script accepts only no argument, --status and --lock (roles/encryption).

  python3 app.py           serve the page
  python3 app.py check     ask each host for its status; exit 1 if one cannot be reached

Settings are environment variables, set by the role's compose file (roles/unlock_page/templates).
"""

import html
import http.server
import os
import subprocess
import sys
import urllib.parse

# user@address for each host, as name=user@address, comma separated: pi4=user@host.docker.internal,pinas=user@pinas.example.ts.net
HOSTS = [h.split("=", 1) for h in os.environ.get("UNLOCK_HOSTS", "").split(",") if h]
if any(len(h) != 2 for h in HOSTS):
    sys.exit("UNLOCK_HOSTS must look like name=user@address,name=user@address")
SSH_KEY = os.environ.get("UNLOCK_SSH_KEY", "/run/unlock/ssh_key")
KNOWN_HOSTS = os.environ.get("UNLOCK_KNOWN_HOSTS", "/run/unlock/known_hosts")
PASSPHRASE_FILE = os.environ.get("UNLOCK_PASSPHRASE_FILE", "/run/unlock/passphrase")
PORT = int(os.environ.get("PORT", "8080"))

PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Unlock</title><body style="font:16px system-ui;max-width:32rem;margin:2rem auto;padding:0 1rem">
<h1>Unlock</h1>{result}
<form method=post><button name=action value=unlock>Unlock</button>
<button name=action value=lock onclick="return confirm('Stop the services that use the folders and lock them?')">Lock</button></form>
<h2>Status</h2>{status}"""


def ssh(target, command, stdin_text=""):
    """Run unlock.sh on a host with one argument: "" (unlock), --status or --lock. The host accepts nothing else."""
    argv = ["ssh", "-i", SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", target]
    if command:
        argv.append(command)
    try:
        done = subprocess.run(argv, input=stdin_text, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return 255, "timed out"
    return done.returncode, (done.stdout + done.stderr).strip()


def run_all(command):
    """Unlock sends the passphrase on stdin; the other commands need none."""
    passphrase = ""
    if not command:
        try:
            with open(PASSPHRASE_FILE) as f:
                passphrase = f.read().rstrip("\r\n")  # a file made with echo ends with a newline the passphrase does not have
        except OSError as error:
            return [("passphrase", 1, f"Cannot read {PASSPHRASE_FILE}: {error}")]
    return [(name, *ssh(target, command, passphrase)) for name, target in HOSTS]


def summarize(code, output):
    """One word for a host's --status answer: LOCKED if any folder is, otherwise unlocked; an unreachable host says why."""
    if code != 0:
        return False, f"CANNOT REACH: exit {code}: {output}"
    return True, "LOCKED (the page can unlock it)" if "LOCKED" in output else "unlocked"


def same_origin(headers):
    """A browser sends Origin on a POST. A form on another site would carry the Tinyauth cookie, so refuse a different one."""
    origin = headers.get("Origin")
    return origin is None or urllib.parse.urlparse(origin).netloc == headers.get("Host")


def render(results):
    return "".join(
        f"<h2>{html.escape(name)}: {'ok' if code == 0 else 'failed'}</h2><pre>{html.escape(output)}</pre>"
        for name, code, output in results)


class Handler(http.server.BaseHTTPRequestHandler):
    def send_page(self, result, status=200):
        data = PAGE.format(result=result, status=render(run_all("--status"))).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.send_page("")

    def do_POST(self):
        if not same_origin(self.headers):
            return self.send_page("<p>Refused: the request came from another site.</p>", 403)
        fields = urllib.parse.parse_qs(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4096)).decode())
        action = fields.get("action", [""])[0]
        if action not in ("unlock", "lock"):
            return self.send_page("<p>Unknown action.</p>", 400)
        self.send_page(render(run_all("" if action == "unlock" else "--lock")))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        reports = [(name, *summarize(code, output)) for name, code, output in run_all("--status")]
        for name, _, state in reports:
            print(f"{name}: {state}")
        sys.exit(0 if all(ok for _, ok, _ in reports) else 1)
    if not HOSTS:
        sys.exit("Set UNLOCK_HOSTS, for example pi4=user@host.docker.internal")
    # HTTPServer, not ThreadingHTTPServer: one request at a time, so an unlock and a lock never overlap.
    http.server.HTTPServer(("", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
