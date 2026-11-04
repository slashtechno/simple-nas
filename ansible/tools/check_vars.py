#!/usr/bin/env python3
"""Checks that keep the example files honest. Standard library only.

  - every `vault_*` name used in roles/ or group_vars/ appears in a vault.yml.example,
  - no setting is written in two of the files that hold defaults (the later file would silently win),
  - no file in group_vars/all/ that loads after vars.yml sets a key the owner sets in vars.yml,
  - every setting with no default (`undef(hint=...)`) appears in group_vars/all/vars.yml.example.
"""
import re
import sys
from pathlib import Path

ANSIBLE = Path(__file__).resolve().parent.parent
VAULT_EXAMPLES = [ANSIBLE / "group_vars/all/vault.yml.example", ANSIBLE / "host_vars/vault.yml.example"]
VARS_EXAMPLE = ANSIBLE / "group_vars/all/vars.yml.example"
NOT_DEFAULTS = {"vars.yml", "vault.yml", "versions.yml", "derived.yml", "services.yml"}
SHARED = sorted(p for p in (ANSIBLE / "group_vars/all").glob("*.yml") if p.name not in NOT_DEFAULTS)
DEFAULTS = SHARED + sorted(ANSIBLE.glob("roles/*/defaults/main.yml"))

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
# Ansible loads group_vars/all/*.yml in name order and the later file wins, so a file sorting after vars.yml
# would override the owner's values, and a key written in two files has no single answer.
GROUP_ALL = ANSIBLE / "group_vars/all"
owner_keys = set(re.findall(r"^#?\s*([a-z][a-z0-9_]*):", VARS_EXAMPLE.read_text(), re.M))
if (GROUP_ALL / "vars.yml").exists():
    owner_keys |= set(re.findall(r"^([a-z][a-z0-9_]*):", (GROUP_ALL / "vars.yml").read_text(), re.M))
for path in sorted(GROUP_ALL.glob("*.yml")):
    if path.name > "vars.yml" and path.name != "vault.yml":
        for name in sorted(owner_keys & set(re.findall(r"^([a-z][a-z0-9_]*):", path.read_text(), re.M))):
            problems.append(f"{name} is in {path.relative_to(ANSIBLE)}, which loads after vars.yml and would override it; rename the file to sort before vars.yml")

defined_in = {}
for path in DEFAULTS + [GROUP_ALL / "derived.yml", GROUP_ALL / "versions.yml"]:
    for name in re.findall(r"^([a-z][a-z0-9_]*):", path.read_text(), re.M):
        defined_in.setdefault(name, []).append(path.relative_to(ANSIBLE))
for name, paths in defined_in.items():
    if len(paths) > 1:
        problems.append(f"{name} has a default in {len(paths)} files: {', '.join(map(str, paths))}")

for path in DEFAULTS:
    for name in re.findall(r"^([a-z][a-z0-9_]*):.*undef\(hint=", path.read_text(), re.M):
        if name not in example_keys:
            problems.append(f"{name} has no default but is not in {VARS_EXAMPLE.relative_to(ANSIBLE)}")

for problem in problems:
    print(f"ERROR: {problem}", file=sys.stderr)
sys.exit(1 if problems else 0)
