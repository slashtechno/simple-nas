#!/usr/bin/env python3
"""Two checks that keep the example files honest. Standard library only.

  - every `vault_*` name used in roles/ or group_vars/ appears in a vault.yml.example,
  - every setting with no default (`undef(hint=...)`) appears in group_vars/all/vars.yml.example.
"""
import re
import sys
from pathlib import Path

ANSIBLE = Path(__file__).resolve().parent.parent
VAULT_EXAMPLES = [ANSIBLE / "group_vars/all/vault.yml.example", ANSIBLE / "host_vars/vault.yml.example"]
VARS_EXAMPLE = ANSIBLE / "group_vars/all/vars.yml.example"
DEFAULTS = [ANSIBLE / "group_vars/all/defaults.yml"] + sorted(ANSIBLE.glob("roles/*/defaults/main.yml"))

problems = []

documented = set()
for path in VAULT_EXAMPLES:
    documented |= set(re.findall(r"^(vault_[a-z0-9_]+):", path.read_text(), re.M))
sources = [p for p in ANSIBLE.glob("roles/**/*") if p.is_file()] + list(ANSIBLE.glob("group_vars/**/*.yml"))
sources += [ANSIBLE / "site.yml", ANSIBLE / "teardown.yml"]
for path in sources:
    if path.name == "vault.yml":
        continue
    try:
        text = path.read_text()
    except UnicodeDecodeError:
        continue
    for name in sorted(set(re.findall(r"\bvault_[a-z0-9_]+\b", text)) - documented):
        problems.append(f"{name} is used in {path.relative_to(ANSIBLE)} but is in no vault.yml.example")

example_keys = set(re.findall(r"^#?\s*([a-z][a-z0-9_]*):", VARS_EXAMPLE.read_text(), re.M))
for path in DEFAULTS:
    for name in re.findall(r"^([a-z][a-z0-9_]*):.*undef\(hint=", path.read_text(), re.M):
        if name not in example_keys:
            problems.append(f"{name} has no default but is not in {VARS_EXAMPLE.relative_to(ANSIBLE)}")

for problem in problems:
    print(f"ERROR: {problem}", file=sys.stderr)
sys.exit(1 if problems else 0)
