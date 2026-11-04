#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["rich==14.0.0"]
# ///
"""List every setting: its default, what it does, and where the owner overrides it.

  just settings           every setting
  just settings gitea     only names containing "gitea"

`just settings` runs this with uv, which fetches rich for colour. Without uv it is `python3 tools/settings.py [word]`,
the same output without colour.

The value after `=` is the default. A green line under it is an override from vars.yml or a host's vars.yml.

Reads the YAML as text, so a multi-line default is shown on one line and a long template is labelled computed (read the file for it). Writes nothing.
"""
import re
import sys
from pathlib import Path

try:
    from rich.console import Console
    from rich.padding import Padding
    from rich.text import Text
except ImportError:   # plain python3 without rich: the same lines, uncoloured
    Console = None

ANSIBLE = Path(__file__).resolve().parent.parent
# A longer default (a template) is cut off; read the file for the rest.
MAX_VALUE = 70
# vars.yml and vault.yml are the owner's; services.yml is the service list and derived.yml holds computed values, neither a setting.
# vault.yml is never read: only the names of vault entries appear, as in a default of "{{ vault_x }}".
NOT_DEFAULTS = {"vars.yml", "vault.yml", "services.yml", "derived.yml"}
DEFAULT_FILES = sorted(str(p.relative_to(ANSIBLE)) for p in (ANSIBLE / "group_vars/all").glob("*.yml") if p.name not in NOT_DEFAULTS)
DEFAULT_FILES += sorted(str(p.relative_to(ANSIBLE)) for p in ANSIBLE.glob("roles/*/defaults/main.yml"))
OWNER_FILES = ["group_vars/all/vars.yml"] + sorted(str(p.relative_to(ANSIBLE)) for p in ANSIBLE.glob("host_vars/*/vars.yml"))


def top_level(path):
    """Yield (name, value on one line, comment lines above it) for each top-level key in a YAML file."""
    comment, lines = [], (ANSIBLE / path).read_text().splitlines()
    for number, line in enumerate(lines):
        if line.startswith("#"):
            comment.append(line.lstrip("# ").strip())
            continue
        match = re.match(r"^([a-z][a-z0-9_]*):\s*(.*)$", line)
        if match:
            parts = [match.group(2)] if match.group(2) not in (">-", ">", "|", "|-") else []
            for more in lines[number + 1:]:
                if not more.startswith((" ", "\t")):
                    break
                if not more.lstrip().startswith("#"):
                    parts.append(more.strip())
            value = " ".join(parts)
            if not value.startswith(('"', "'")):
                value = re.sub(r"\s+#.*$", "", value)   # a trailing YAML comment
            yield match.group(1), value, comment
        comment = []


def owner_overrides():
    found = {}
    for path in OWNER_FILES:
        if (ANSIBLE / path).exists():
            where = "all hosts" if path.startswith("group_vars") else path.split("/")[1]
            for name, value, _ in top_level(path):
                found.setdefault(name, []).append((where, value))
    return found


def describe(value):
    """A value a person can read: a template that needs the file to understand becomes a label."""
    if re.match(r'"?\{\{\s*undef\(', value):
        return "(required: no default, set it yourself)"
    if value.startswith(("{{", '"{{', "{%", '"{%')) and len(value) > MAX_VALUE:
        return "(computed from other settings; see the file)"
    return value if len(value) <= MAX_VALUE else value[:MAX_VALUE - 1] + "…"


def main():
    word = sys.argv[1] if len(sys.argv) > 1 else ""
    console = Console() if Console else None
    overrides = owner_overrides()
    shown = 0
    for path in DEFAULT_FILES:
        rows = [row for row in top_level(path) if word in row[0]]
        if not rows:
            continue
        if console:
            console.print()
            console.rule(Text(path, style="bold"), align="left")
        else:
            print(f"\n== {path}")
        for name, value, comment in rows:
            vault = re.fullmatch(r'"?\{\{ (vault_\w+) \}\}"?', value)
            if vault:
                value = f"(secret, from the vault entry {vault.group(1)})"
            value = describe(value) or "(empty)"
            if console:
                console.print(Text.assemble((name, "bold cyan"), (" = ", "dim"), value))
            else:
                print(f"{name} = {value}")
            for where, own in overrides.get(name, []):
                own = describe(own) or "(empty)"
                if console:
                    console.print(Text.assemble(("    overridden for " + where + ": ", "green"), (own, "bold green")))
                else:
                    print(f"    overridden for {where}: {own}")
            if comment:
                if console:
                    console.print(Padding(Text(" ".join(comment), style="dim"), (0, 0, 0, 4)))
                else:
                    print("    " + " ".join(comment))
            shown += 1
    footer = f"\n{shown} settings" + (f" matching '{word}'" if word else "") + ". The value after = is the default; an 'overridden' line is a host or all hosts overriding it."
    console.print(footer, style="dim") if console else print(footer)


main()
