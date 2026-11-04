#!/usr/bin/env python3
"""List every setting: its default, the file that defines it, and where the owner overrides it. Standard library only.

  python3 tools/settings.py          every setting
  python3 tools/settings.py gitea    only names containing "gitea"

Reads text only (no YAML parser), so a multi-line default shows just its first line. Writes nothing.
"""
import re
import sys
from pathlib import Path

ANSIBLE = Path(__file__).resolve().parent.parent
NOT_DEFAULTS = {"vars.yml", "vault.yml", "services.yml"}
DEFAULT_FILES = sorted(str(p.relative_to(ANSIBLE)) for p in (ANSIBLE / "group_vars/all").glob("*.yml") if p.name not in NOT_DEFAULTS)
DEFAULT_FILES += sorted(str(p.relative_to(ANSIBLE)) for p in ANSIBLE.glob("roles/*/defaults/main.yml"))
OWNER_FILES = ["group_vars/all/vars.yml"] + sorted(str(p.relative_to(ANSIBLE)) for p in ANSIBLE.glob("host_vars/*/vars.yml"))


def top_level(path):
    """Yield (name, first line of value, first comment line above it) for each top-level key in a YAML file."""
    comment = ""
    for line in (ANSIBLE / path).read_text().splitlines():
        if line.startswith("#"):
            comment = comment or line.lstrip("# ").strip()
            continue
        match = re.match(r"^([a-z][a-z0-9_]*):\s*(.*)$", line)
        if match:
            yield match.group(1), match.group(2), comment
        comment = ""


overrides = {}
for path in OWNER_FILES:
    if (ANSIBLE / path).exists():
        for name, _, _ in top_level(path):
            overrides.setdefault(name, []).append(path.replace("/vars.yml", "").replace("host_vars/", ""))

word = sys.argv[1] if len(sys.argv) > 1 else ""
for path in DEFAULT_FILES:
    rows = [row for row in top_level(path) if word in row[0]]
    if not rows:
        continue
    print(f"\n# {path}")
    for name, value, comment in rows:
        value = value if len(value) <= 60 else value[:57] + "..."
        print(f"{name}: {value}")
        if comment:
            print(f"    {comment}")
        if name in overrides:
            print(f"    overridden in: {', '.join(overrides[name])}")
