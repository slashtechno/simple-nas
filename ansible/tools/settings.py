#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["rich==14.0.0"]
# ///
"""List every setting: its default, what it does, and where the owner overrides it.

  just settings           every setting
  just settings gitea     only names containing "gitea" (with the full comment)

Reads the YAML as text, so a multi-line default is shown on one line, cut off after 70 characters. Writes nothing.
"""
import re
import sys
from pathlib import Path

from rich.console import Console
from rich.padding import Padding
from rich.text import Text

ANSIBLE = Path(__file__).resolve().parent.parent
# A longer default (a template) is cut off; read the file for the rest.
MAX_VALUE = 70
NOT_DEFAULTS = {"vars.yml", "vault.yml", "services.yml"}
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
                parts.append(more.strip())
            yield match.group(1), " ".join(parts), comment
        comment = []


def owner_overrides():
    found = {}
    for path in OWNER_FILES:
        if (ANSIBLE / path).exists():
            where = "all hosts" if path.startswith("group_vars") else path.split("/")[1]
            for name, _, _ in top_level(path):
                found.setdefault(name, []).append(where)
    return found


def main():
    word = sys.argv[1] if len(sys.argv) > 1 else ""
    console = Console()
    overrides = owner_overrides()
    shown = 0
    for path in DEFAULT_FILES:
        rows = [row for row in top_level(path) if word in row[0]]
        if not rows:
            continue
        console.print()
        console.rule(Text(path, style="bold"), align="left")
        for name, value, comment in rows:
            if len(value) > MAX_VALUE:
                value = value[:MAX_VALUE - 1] + "…"
            line = Text.assemble((name, "bold cyan"), (" = ", "dim"), value or "(empty)")
            if name in overrides:
                line.append("   <- set for " + ", ".join(overrides[name]), style="green")
            console.print(line)
            if comment:
                text = " ".join(comment) if word else comment[0]
                console.print(Padding(Text(text, style="dim"), (0, 0, 0, 4)))
            shown += 1
    console.print(f"\n{shown} settings" + (f" matching '{word}'" if word else "") + ". Green: the owner sets it.", style="dim")


main()
