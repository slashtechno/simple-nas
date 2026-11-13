#!/usr/bin/env python3
"""Checks that keep the example files honest. Standard library only.

  - every `vault_*` name used in roles/ or group_vars/ appears in a vault.yml.example,
  - no setting is written in two of the files that hold defaults (the later file would silently win),
  - every file in group_vars/all/ is a known one (defaults.yml, defaults-<topic>.yml, vars, vault, derived, services, versions),
  - every shared defaults file in group_vars/all/ sorts before vars.yml (the later file wins), and no version is set in vars.yml,
  - every setting with no default (`undef(hint=...)`) appears in group_vars/all/vars.yml.example.
"""
import re
import sys
from pathlib import Path

ANSIBLE = Path(__file__).resolve().parent.parent
VAULT_EXAMPLES = [ANSIBLE / "group_vars/all/vault.yml.example", ANSIBLE / "host_vars/vault.yml.example"]
VARS_EXAMPLE = ANSIBLE / "group_vars/all/vars.yml.example"
NOT_DEFAULTS = {"vars.yml", "vault.yml", "versions.yml", "derived.yml", "services.yml"}
SHARED = sorted((ANSIBLE / "group_vars/all").glob("defaults*.yml"))
DEFAULTS = SHARED + sorted(ANSIBLE.glob("roles/*/defaults/main.yml"))

problems = []

for path in sorted((ANSIBLE / "group_vars/all").glob("*.yml")):
    if path not in SHARED and path.name not in NOT_DEFAULTS:
        problems.append(f"{path.relative_to(ANSIBLE)} is not a known file; shared defaults are in defaults.yml or defaults-<topic>.yml")

documented = set()
for path in VAULT_EXAMPLES:
    documented |= set(re.findall(r"^(vault_[a-z0-9_]+):", path.read_text(), re.M))
sources = [p for p in ANSIBLE.glob("roles/**/*") if p.is_file()] + list(ANSIBLE.glob("group_vars/**/*.yml"))
sources += [ANSIBLE / "site.yml", ANSIBLE / "teardown.yml"]
for path in sources:
    # vars.yml is the owner's own values: a vault name they invent there (a sender's token) needs no example entry.
    if path.name in ("vault.yml", "vars.yml"):
        continue
    try:
        text = path.read_text()
    except UnicodeDecodeError:
        continue
    for name in sorted(set(re.findall(r"\bvault_[a-z0-9_]+\b", text)) - documented):
        problems.append(f"{name} is used in {path.relative_to(ANSIBLE)} but is in no vault.yml.example")

example_keys = set(re.findall(r"^#?\s*([a-z][a-z0-9_]*):", VARS_EXAMPLE.read_text(), re.M))
# Ansible loads group_vars/all/*.yml in name order and the later file wins. A shared defaults file sorting after
# vars.yml would override the owner's values, so each must sort before it.
GROUP_ALL = ANSIBLE / "group_vars/all"
for path in SHARED:
    if path.name > "vars.yml":
        problems.append(f"{path.relative_to(ANSIBLE)} sorts after vars.yml, so its values would override yours; rename it to sort before vars.yml")
# versions.yml sorts after vars.yml too, so a version set in vars.yml would be ignored.
owner_keys = set(example_keys)
if (GROUP_ALL / "vars.yml").exists():
    owner_keys |= set(re.findall(r"^([a-z][a-z0-9_]*):", (GROUP_ALL / "vars.yml").read_text(), re.M))
for name in sorted(owner_keys & set(re.findall(r"^([a-z][a-z0-9_]*):", (GROUP_ALL / "versions.yml").read_text(), re.M))):
    problems.append(f"{name} is set in vars.yml but versions.yml loads after it and wins; change it in versions.yml")

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
