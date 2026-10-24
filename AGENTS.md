# AGENTS.md

For AI agents, not humans. Keep it short; detail lives in the linked docs.

- Two top priorities, equal: reliability (especially backups), and the owner understanding, changing and extending this without an AI agent. Neither is traded away for the other. Choose the plain, readable option over the clever one. Prefer a well-known, documented tool over hand-rolled code; add no abstraction of our own without a current use.
- Follow the `maintaining-codebases` skill for refactors and docs if you have it; if not, the rules in this file apply.
- Everything is deployed by Ansible from `ansible/`; one role per service under `ansible/roles/`. See [ansible/README.md](./ansible/README.md); service notes are in [docs/services.md](./docs/services.md) and drives in [docs/storage.md](./docs/storage.md).
- Services are switched on or off with `<name>_enabled` (every service flag defaults to false in `group_vars/all/defaults.yml`; a host turns its own on in `host_vars/<host>/vars.yml`). Compose-only services reuse `roles/compose_service`; teardown reuses `teardown_service.yml`.
- Every deployed image version lives in `ansible/group_vars/all/versions.yml`; templates and Dockerfiles take it from there.
- A default is written in exactly one place: a role's `defaults/main.yml` for a setting only that role uses, `group_vars/all/defaults.yml` for one shared across roles or read by `teardown.yml`. `group_vars/all/vars.yml` and `host_vars/<host>/vars.yml` hold only the owner's values (`vars.yml.example` files show the shape). Every setting has a comment above it; a setting with no sensible default uses `undef(hint=...)`. To see every setting and its default, read those two files; nothing is generated. No group carries behaviour.
- Use `import_role`/`import_tasks`, not `include_*`, so `--tags` work. Two `include_role` calls (pics, tailscale) are kept on purpose and marked in the code.
- `just check` (in `ansible/`) must pass: lint, syntax-check, the vars check (vault name or `undef` setting missing from its example), the doc link check and the template render test. Add lint skips only with a written reason.
- Never run playbooks against a host. Check changes with `--syntax-check` and `--list-tasks`; the owner runs `--check --diff`.
- Commit small and labeled; refactors go on a branch.
- Backups: [docs/backups.md](./docs/backups.md).
- Docs state how things are, as plain reference: no narratives, test logs, scenario walk-throughs or history. Temporary notes, test checklists and scratch output go in `scratch/` (git ignores it; wipe it freely). Move anything lasting into the docs, written as reference.
- `TODO.md` is the owner's list of work that waits for their time or hardware; each item says what it waits for, and an item is deleted when done. Facts and decisions go in the docs, not there.
- Two more kinds of non-reference documents, each with a status line at the top: research notes for work not built (`docs/research/`, not kept current), and the one active plan for work waiting on something (`plans/`, deleted when done). A finished plan is deleted; git history keeps it (`git log --diff-filter=D --name-only -- 'plans/*' 'docs/plans/*'`). Plans and research notes record decisions, not conventions: take rules from this file and the code, never copy a pattern from them.

## Common mistakes

- Assuming the root drive is a microSD. It can be NVMe, USB or SD; say "root drive".
- Keying behaviour on a group name. Behaviour comes from `<name>_enabled` flags and the `drives` list.
- Writing a default in two places, or a setting without a comment above it.
- "Now", "no longer", "used to be" or other history wording in code, comments and docs.
- Repeating the same YAML example in several docs. Spell it out once and link to it.
- Treating `--list-tasks` as proof that a `when:` works. It ignores `when:`; the render test is the check.
- Adding an option the user should not need, or deriving something the user is better off setting and seeing.
- Adding a mechanism the system or tool already provides (a tmpfiles entry, udev rule, handler, guard, workaround, task or setting). Before adding one, name what breaks without it and show it (read the tool's docs, or test on a host). If nothing breaks, leave it out. A mechanism kept for tidiness, not function, is also out.
- Piling on guards and special cases for rare failures. One plain check that fails loudly beats several layers; delete a layer when another already covers it.
