# AGENTS.md

For AI agents, not humans. Keep it short; detail lives in the linked docs.

- Priorities, in order: reliability (especially backups), then the owner understanding, changing and extending this without an AI agent. Choose the plain, readable option over the clever one; no abstraction without a current use.
- Follow the `maintaining-codebases` skill for refactors and docs.
- Everything is deployed by Ansible from `ansible/`; one role per service under `ansible/roles/`. See [ansible/README.md](./ansible/README.md).
- Services are opt-in via `<name>_enabled` in `site.yml`. Compose-only services reuse `roles/compose_service`; teardown reuses `teardown_service.yml`.
- Settings used by one role go in that role's `defaults/main.yml`. Settings shared across roles or `teardown.yml` go in `group_vars/nas/vars.yml` and `vars.yml.example`, kept in sync.
- Use `import_role`/`import_tasks`, not `include_*`, so `--tags` work.
- `uvx ansible-lint` (in `ansible/`) must pass. Add skips only with a written reason.
- Never run playbooks against the Pi. Check changes with `--syntax-check` and `--list-tasks`; the owner runs `--check --diff`.
- Commit small and labeled; refactors go on a branch.
- Backups: [BACKUPS.md](./BACKUPS.md).
