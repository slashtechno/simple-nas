#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["questionary==2.1.1"]
# ///
"""Open a vars or vault file in an editor: `just edit [vars|vault] [--host NAME | --all] [--editor CMD]`.

  just edit                          asks for the file, the host (or all hosts) and the editor, with the arrow keys
  just edit vault --host pinas       host_vars/pinas/vault.yml, asking only for the editor
  just edit vars --all --editor nvim group_vars/all/vars.yml in Neovim, no questions

`--all` is the files shared by every host (group_vars/all). A vault opens through `ansible-vault edit`, which
decrypts to a temporary file, opens the editor and encrypts again when it exits, so the editor must wait for the file to be
closed: the editors this lists are started with the flag that does that. Editors found on the PATH: VS Code, Cursor, Zed,
Sublime Text, Neovim, Vim, Helix, Micro, Nano, Notepad, and your $VISUAL or $EDITOR. `--editor` takes one of those
commands or any other command line (add its own wait flag for a vault).

A missing file is reported, not created: `just setup <host>` creates a host's files. Nothing is printed from a vault.
"""
import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import questionary

ANSIBLE = Path(__file__).resolve().parent.parent

# (name, command, flag that makes the editor wait until the file is closed)
EDITORS = [
    ("VS Code", "code", "--wait"),
    ("Cursor", "cursor", "--wait"),
    ("Zed", "zed", "--wait"),
    ("Sublime Text", "subl", "--wait"),
    ("Neovim", "nvim", ""),
    ("Vim", "vim", ""),
    ("Helix", "hx", ""),
    ("Micro", "micro", ""),
    ("Nano", "nano", ""),
    ("Notepad", "notepad", ""),
]
SHARED = "Every host (group_vars/all)"


def fail(message):
    sys.exit(f"edit: {message}")


def ask(question):
    answer = question.ask()
    if answer is None:
        sys.exit(1)
    return answer


def installed_editors():
    """(label, command line as a list) for each editor on the PATH, your own $VISUAL/$EDITOR first."""
    found = []
    own = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if own:
        found.append((f"Your editor ({own})", shlex.split(own)))
    for name, command, wait in EDITORS:
        if shutil.which(command):
            found.append((name, [command, wait] if wait else [command]))
    return found


def choose_editor(given):
    if given:
        for _, command, wait in EDITORS:
            if given == command:
                return [command, wait] if wait else [command]
        return shlex.split(given)
    found = installed_editors()
    if not found:
        fail("no editor found on the PATH; set $EDITOR or pass --editor <command>")
    if len(found) == 1:
        print(f"Editor: {found[0][0]}")
        return found[0][1]
    if not sys.stdin.isatty():
        fail("no terminal to ask in; pass --editor <command>")
    label = ask(questionary.select("Editor", choices=[name for name, _ in found]))
    return dict(found)[label]


def hosts():
    return sorted(p.name for p in (ANSIBLE / "host_vars").iterdir() if p.is_dir())


def main():
    parser = argparse.ArgumentParser(description="Open a vars or vault file in an editor.")
    parser.add_argument("kind", nargs="?", choices=["vars", "vault"])
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--host", choices=hosts(), metavar="HOST", help="one of: " + ", ".join(hosts()))
    where.add_argument("--all", action="store_true", help="the files shared by every host (group_vars/all)")
    parser.add_argument("--editor", help="a command such as code, nvim or 'subl --wait'")
    args = parser.parse_args()

    interactive = sys.stdin.isatty()
    if not interactive and not (args.kind and (args.host or args.all) and args.editor):
        fail("no terminal to ask in; pass vars|vault, --host or --all, and --editor")

    kind = args.kind or ask(questionary.select("Which file?", choices=["vars", "vault"]))
    if args.all:
        host = None
    elif args.host:
        host = args.host
    else:
        choice = ask(questionary.select("Which host?", choices=hosts() + [SHARED]))
        host = None if choice == SHARED else choice
    editor = choose_editor(args.editor)

    folder = ANSIBLE / ("host_vars/" + host if host else "group_vars/all")
    path = folder / f"{kind}.yml"
    if not path.exists():
        fail(f"{path.relative_to(ANSIBLE)} does not exist; `just setup {host or '<host>'}` creates it"
             if host else f"{path.relative_to(ANSIBLE)} does not exist; copy {kind}.yml.example next to it")

    if kind == "vars":
        sys.exit(subprocess.call([*editor, str(path)]))
    password_file = ANSIBLE / ".vault-pass"
    if not password_file.exists():
        fail(".vault-pass does not exist; `just setup <host>` creates it")
    env = {**os.environ, "EDITOR": shlex.join(editor)}
    sys.exit(subprocess.call(["ansible-vault", "edit", "--vault-password-file", str(password_file), str(path)], env=env))


if __name__ == "__main__":
    main()
