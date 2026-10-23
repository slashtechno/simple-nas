# AGENTS.md

For AI agents, not humans. Keep it short; detail lives in the linked docs.

- Two top priorities, equal: reliability (especially backups), and the owner understanding, changing and extending this without an AI agent. Neither is traded away for the other. Choose the plain, readable option over the clever one. Prefer a well-known, documented tool over hand-rolled code; add no abstraction of our own without a current use.
- Follow the `maintaining-codebases` skill for refactors and docs if you have it; if not, the rules in this file apply.
- Everything is deployed by Ansible from `ansible/`; one role per service under `ansible/roles/`. See [ansible/README.md](./ansible/README.md); service notes are in [docs/services.md](./docs/services.md) and drives in [docs/storage.md](./docs/storage.md).
- Services are opt-in via `<name>_enabled` in `site.yml`. Compose-only services reuse `roles/compose_service`; teardown reuses `teardown_service.yml`.
- Every deployed image version lives in `ansible/group_vars/all/versions.yml`; templates and Dockerfiles take it from there.
- Settings used by one role go in that role's `defaults/main.yml`. Settings shared across roles or `teardown.yml` go in `group_vars/<all|nas>/vars.yml` (per-host ones in `host_vars/<host>/vars.yml`) and the matching `vars.yml.example`, kept in sync.
- Use `import_role`/`import_tasks`, not `include_*`, so `--tags` work. Two `include_role` calls (pics, tailscale) are kept on purpose and marked in the code.
- `just check` (in `ansible/`) must pass: lint, syntax-check and the template render test. Add lint skips only with a written reason.
- Never run playbooks against the Pi. Check changes with `--syntax-check` and `--list-tasks`; the owner runs `--check --diff`.
- Commit small and labeled; refactors go on a branch.
- Backups: [docs/backups.md](./docs/backups.md).
