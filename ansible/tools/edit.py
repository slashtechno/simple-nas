#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["questionary==2.1.1"]
# ///
"""Open a vars or vault file in an editor: `just edit [vars|vault] [--host NAME | --all] [--editor CMD]`.

  just edit                          asks for the file and the host (or all hosts) with the arrow keys, opens $EDITOR
  just edit vault --host pinas       host_vars/pinas/vault.yml in $EDITOR, no questions
  just edit -c                       also asks which editor
  just edit vars --all --editor nvim group_vars/all/vars.yml in Neovim

`--all` is the files shared by every host (group_vars/all). The editor is your $VISUAL or $EDITOR; without one, or with
`-c`, a menu of the editors found on the PATH (VS Code, Cursor, Zed, Sublime Text, Neovim, Vim, Helix, Micro, Nano).
`--editor` takes one of those commands or any other command line.

A vault opens through `ansible-vault edit`, which decrypts to a temporary file and encrypts it again when the editor
exits, so the editor must wait for the file to be closed. The listed GUI editors are started with the flag that does
that, also when they come from $EDITOR; a command that is not listed needs its own wait flag.

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
]
SHARED = "Every host (group_vars/all)"


def fail(message):
    sys.exit(f"edit: {message}")


def ask(question):
    try:
        answer = question.ask()
    except EOFError:
        answer = None
    if answer is None:
        sys.exit(1)
    return answer


def with_wait(command):
    """The command line, plus the wait flag if it is a listed editor that needs one (a vault is encrypted again when the editor exits)."""
    for _, name, wait in EDITORS:
        if command == [name] and wait:
            return [name, wait]
    return command


def own_editor():
    return os.environ.get("VISUAL") or os.environ.get("EDITOR")


def installed_editors():
    """(label, command line) for each editor on the PATH, your own $VISUAL or $EDITOR first, each command once."""
    found = {}
    if own_editor():
        found[tuple(with_wait(shlex.split(own_editor())))] = f"Your editor ({own_editor()})"
    for name, command, wait in EDITORS:
        line = tuple([command, wait] if wait else [command])
        if shutil.which(command) and line not in found:
            found[line] = name
    return [(label, list(line)) for line, label in found.items()]


def choose_editor(given, choose):
    """--editor, else your $VISUAL or $EDITOR, else (or with -c) a menu of the editors on the PATH."""
    if given:
        return with_wait(shlex.split(given))
    if own_editor() and not choose:
        return with_wait(shlex.split(own_editor()))
    found = installed_editors()
    if not found:
        fail("no editor found on the PATH; set $EDITOR or pass --editor <command>")
    if len(found) == 1:
        print(f"Editor: {found[0][0]}")
        return found[0][1]
    label = ask(questionary.select("Editor", choices=[label for label, _ in found]))
    return dict(found)[label]


def hosts():
    return sorted(p.name for p in (ANSIBLE / "host_vars").iterdir() if p.is_dir())


def main():
    names = hosts()
    parser = argparse.ArgumentParser(description="Open a vars or vault file in an editor.")
    parser.add_argument("kind", nargs="?", choices=["vars", "vault"])
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--host", choices=names, metavar="HOST", help="one of: " + ", ".join(names))
    where.add_argument("--all", action="store_true", help="the files shared by every host (group_vars/all)")
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--editor", help="a command such as code, nvim or 'subl --wait', instead of $EDITOR")
    which.add_argument("-c", "--choose", action="store_true", help="pick the editor from a menu instead of using $EDITOR")
    args = parser.parse_args()

    if not sys.stdin.isatty() and not (args.kind and (args.host or args.all) and (args.editor or own_editor())):
        fail("no terminal to ask in; pass vars|vault, --host or --all, and --editor (or set $EDITOR)")

    kind = args.kind or ask(questionary.select("Which file?", choices=["vars", "vault"]))
    if args.all:
        host = None
    elif args.host:
        host = args.host
    else:
        choice = ask(questionary.select("Which host?", choices=names + [SHARED]))
        host = None if choice == SHARED else choice
    editor = choose_editor(args.editor, args.choose)

    folder = ANSIBLE / ("host_vars/" + host if host else "group_vars/all")
    path = folder / f"{kind}.yml"
    if not path.exists():
        fail(f"{path.relative_to(ANSIBLE)} does not exist; `just setup {host or '<host>'}` creates it"
             if host else f"{path.relative_to(ANSIBLE)} does not exist; copy {kind}.yml.example next to it")

    if not shutil.which(editor[0]):
        fail(f"{editor[0]} is not on the PATH")
    if kind == "vars":
        sys.exit(subprocess.call([*editor, str(path)]))
    if not shutil.which("ansible-vault"):
        fail("ansible-vault is not on the PATH; install the tools first (ansible/README.md)")
    password_file = ANSIBLE / ".vault-pass"
    if not password_file.exists():
        fail(".vault-pass does not exist; `just setup <host>` creates it")
    env = {**os.environ, "EDITOR": shlex.join(editor)}
    sys.exit(subprocess.call(["ansible-vault", "edit", "--vault-password-file", str(password_file), str(path)], env=env))


if __name__ == "__main__":
    main()
