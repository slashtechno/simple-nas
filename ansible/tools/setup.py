#!/usr/bin/env python3
"""First-run setup for one host: `just setup <host>`. Standard library only.

  - creates .vault-pass (a random password) if it is missing,
  - creates host_vars/<host>/vars.yml from the example if it is missing,
  - fills the secrets that are random strings (letters and digits, or hex where the example says hex) (database passwords, tokens, the restic password) in the two vault
    files, creating them if needed and adding only the names that are missing, never changing one that exists.

It does not touch the host and never prints a secret. Every other secret in the examples (account names, Cloudflare,
GitHub, Google Drive, optional and list-valued ones) is listed at the end; add the ones your services use with
`ansible-vault edit`.
"""
import os
import re
import secrets
import shutil
import string
import subprocess
import sys
from pathlib import Path

ANSIBLE = Path(__file__).resolve().parent.parent
VAULT_PASS = ANSIBLE / ".vault-pass"
GROUP_VAULT = (ANSIBLE / "group_vars/all/vault.yml", ANSIBLE / "group_vars/all/vault.yml.example")
HOST_VAULT_EXAMPLE = ANSIBLE / "host_vars/vault.yml.example"
# A one-line secret in an example file. It is random when the example value is a placeholder.
LINE = re.compile(r'^(vault_[a-z0-9_]+): "(.*)"$')
PLACEHOLDER = re.compile(r"change-?me", re.I)


def random_value(example):
    if example.startswith("tk_"):   # an ntfy token: "tk_" and 29 letters or digits
        return "tk_" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(29))
    hex_bytes = re.search(r"hex-(\d+)", example)   # "...openssl-rand-hex-32": 32 bytes as hex (Garage needs this)
    if hex_bytes:
        return secrets.token_hex(int(hex_bytes.group(1)))
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(40))


def vault(*args, stdin=None):
    return subprocess.run(["ansible-vault", *args, "--vault-password-file", str(VAULT_PASS)],
                          input=stdin, check=True, capture_output=True, text=True).stdout


def fill(vault_file, example):
    """Add the random secrets missing from vault_file. Returns the names added and the names left to the owner."""
    wanted, manual = {}, []
    for line in example.read_text().splitlines():
        match = LINE.match(line)
        if match and PLACEHOLDER.search(match.group(2)):
            wanted[match.group(1)] = random_value(match.group(2))
        else:
            name = re.match(r"^(vault_[a-z0-9_]+):", line)
            if name:
                manual.append(name.group(1))

    if vault_file.exists():
        text = vault("view", str(vault_file))
        had_file = True
    else:
        text = "---\n"
        had_file = False
    present = set(re.findall(r"^(vault_[a-z0-9_]+):", text, re.M))
    added = [name for name in wanted if name not in present]
    manual = [name for name in manual if name not in present]
    if added:
        text = text.rstrip("\n") + "\n" + "".join(f'{name}: "{wanted[name]}"\n' for name in added)
        vault_file.parent.mkdir(parents=True, exist_ok=True)
        vault("encrypt", "--output", str(vault_file), "-", stdin=text)
    return added, manual, had_file


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: just setup <host>   (the host's name in inventory/hosts.yml)")
    host = sys.argv[1]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", host):
        sys.exit(f"{host!r} is not a host name")

    if not VAULT_PASS.exists():
        existing = sorted(ANSIBLE.glob("group_vars/*/vault.yml")) + sorted(ANSIBLE.glob("host_vars/*/vault.yml"))
        if existing:
            sys.exit(f"{existing[0].relative_to(ANSIBLE)} exists but .vault-pass does not: put the existing vault "
                     "password in .vault-pass (a new one could not open it).")
        with open(os.open(VAULT_PASS, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
            f.write(secrets.token_urlsafe(32) + "\n")
        print(f"Created {VAULT_PASS.relative_to(ANSIBLE)}. Copy it into your password manager now: every vault file")
        print("needs it, and the restic backups cannot be read without the vault.")

    host_dir = ANSIBLE / "host_vars" / host
    host_dir.mkdir(parents=True, exist_ok=True)
    host_vars = host_dir / "vars.yml"
    if not host_vars.exists():
        shutil.copy(ANSIBLE / "host_vars/vars.yml.example", host_vars)
        print(f"Created {host_vars.relative_to(ANSIBLE)}: set the drives and switch on the services you want.")

    manual_all = []
    for vault_file, example in (GROUP_VAULT, (host_dir / "vault.yml", HOST_VAULT_EXAMPLE)):
        added, manual, had_file = fill(vault_file, example)
        shown = vault_file.relative_to(ANSIBLE)
        if added:
            print(f"{shown}: {'added' if had_file else 'created with'} {', '.join(added)}")
        else:
            print(f"{shown}: nothing to add")
        manual_all += [(shown, name) for name in manual]

    if manual_all:
        print("\nSecrets only you can supply (see the comments in the vault.yml.example files). Add the ones your")
        print("services use with `ansible-vault edit --vault-password-file .vault-pass <file>`:")
        for shown, name in manual_all:
            print(f"  {shown}: {name}")


main()
