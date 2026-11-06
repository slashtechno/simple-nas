# Settings structure: options considered

Status: research note, not kept current. It records why the settings stay flat and what could make them easier to find. Built: `just settings` (option 8) and the topic split (option 7: the `defaults-<topic>.yml` files beside `defaults.yml`, with a duplicate-key check in `tools/check_vars.py`). The owner decided to keep every setting listed under "Pruning audit" as it is: a default already is the sensible value, and hardcoding it only removes the option to change it.

## The problem

About 190 settings live in four places: `group_vars/all/defaults.yml` (110), the role `defaults/main.yml` files (1 to 9 each), `versions.yml` (28 pins) and `derived.yml` (16 computed values). A name such as `immich_data_dir` is easy to guess, but a person who does not know the name has to read a 300-line file or grep. The owner overrides only about 36 of them, mostly `_enabled` flags, `drives`, the domains and ingress.

## Two constraints that decide most options

1. Ansible replaces a dict that is set in two places (the default `hash_behaviour`). A nested `immich: {port: ..., data_dir: ...}` in `group_vars/all/vars.yml` would erase every other key from the default. The trap is noted at the top of `derived.yml`. `hash_behaviour = merge` is deprecated, and changing it would silently alter every host.
2. Role defaults are invisible through `hostvars`, so any setting read across hosts (flags, ports, subdomains) must stay in `group_vars`.

The services also read each other's settings by name built at run time (`lookup('vars', key ~ '_port')`, `query('vars', ...)` in `site.yml`, `teardown.yml`, `roles/caddy/tasks/web_sites.yml`, Homepage and backup). A grep for a name that finds no reader does not prove the setting is dead.

## Options

| # | Option | Verdict | Why |
|---|---|---|---|
| 1 | Nested dicts per service (`immich.port`) | Rejected | Constraint 1: the owner's single override erases the other keys. |
| 2 | Dotted or double-underscore names (`immich__port`) | Rejected | Same flat namespace, harder to type and grep, and no gain. |
| 3 | Two-layer merge (`defaults` dict plus `overrides` dict merged by a filter in `derived.yml`) | Rejected | Every reader has to use the merged copy; it is a mechanism of our own that Ansible already covers with plain variables. |
| 4 | Defaults as extra columns in the `services.yml` registry | Rejected | Per-host values must never live in that list (AGENTS.md), and a registry row cannot be overridden without replacing the whole list. |
| 5 | Split `host_vars/<host>/` into several files | Rejected | `tests/check_keys.yml` pairs each host's `vars.yml` with its example; splitting breaks that and the owner then edits many files. |
| 6 | Runtime presets (`profile: minimal`) | Rejected | Hides which flags are on. The "Pick what you use" examples in `ansible/README.md` already show the combinations as plain flags. |
| 7 | Keep every name; Split `defaults.yml` into topic files | Possible | `group_vars/all/` loads every file in it, so no variable changes. Cost: `tests/render.yml` and `check_keys.yml` read the literal `defaults.yml` path, and `tools/check_vars.py` globs it. Add a check that no key appears in two files. |
| 8 | (built) A `just settings` index that prints every setting, its default, its file and whether the owner overrides it | Recommended first | Reads the same files the grep recipe does, writes nothing, and fixes the "I do not know the name" problem without moving anything. |
| 9 | Subdomain convention: a service without `<key>_subdomain` uses its key | Possible | Six of the twelve `_subdomain` defaults equal the key. Consumers would use `lookup('vars', key ~ '_subdomain', default=key)` in `site.yml`, `web_sites.yml`, Homepage and the two `oidc` entries. Settings that differ stay explicit. Saves 6 lines for 5 changed readers, so it is a small win only. |
| 10 | Form-shaped `host_vars/<host>/vars.yml.example` grouped by topic, with inert commented presets | Possible | Helps a new owner; costs nothing at run time. |

## Pruning audit

Every setting was checked against all readers, dynamic ones included. Nothing is dead. The suggested removals, checked one by one:

| Setting | Suggested | Decision | Reason |
|---|---|---|---|
| `ntfy_topic`, `ntfy_user` | Hardcode `alerts` | Keep | The token's ACL ties user and topic together; the topic is also named in the `ntfy_alert_url` comment. Two settings next to the ntfy compose file cost nothing. |
| `ntfy_base_url` | Inline in compose | Keep | A named `undef(hint=...)` gives a clear error. |
| `ntfy_token_file` | Hardcode | Keep | Three readers, including `teardown.yml`. |
| `gitea_domain` | Inline | Keep | Documented override; `gitea_ssh_domain` defaults to it. |
| `pics_public_port` | Inline | Keep | The owner's `cloudflared_ingress` uses it. |
| `encryption_hooks_dir` | Inline | Keep | Five readers across the role, the unlock script and the docs. |
| `connectivity_*` tunables | Hardcode | Keep | The owner asked for them to be settings. |
| `scrutiny_collect_schedule` | Hardcode | Open | One reader, never changed. Removing it is a behaviour change, so the owner decides. |
| `backup_work_dir`, `backup_logs_dir`, `restic_repo_path`, `restic_password_file`, `restic_cache_dir` | Move to `derived.yml` | Open | They are compositions, but the owner may want to relocate a repository; `derived.yml` values are not meant to be overridden. |
| 6 `_subdomain` equal to key | Derive | See option 9 | |

## Recommended order

1. `just settings` (option 8). No variable moves.
2. Subdomain convention (option 9), if the owner wants fewer lines.
3. Topic split of `defaults.yml` (option 7), only after 1, with the one-key-one-file check.
4. Form-shaped example file (option 10).

Steps 2 to 4 are each independent; any can be skipped without affecting the others.
