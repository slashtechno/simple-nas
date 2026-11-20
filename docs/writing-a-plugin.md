# Writing and using a plugin

A plugin is a service this repo does not ship: a folder shaped like a role, picked up without editing any core file. Crafty and pics are plugins (`ansible/plugins/`); copy the one closest to yours, or `ansible/plugin-template/`. A plugin runs as root on your hosts, and its `service.yml` and `defaults.yml` are also templated on your computer, where Jinja can run commands and your vault is open: read a third party's plugin before you list it, and again before you change its commit. The fields of `service.yml` and the variables a plugin can use are in [plugin-reference.md](./plugin-reference.md).

## Where things are

- **Your computer (where you run `just`):** the plugin folders, in `ansible/plugins/<key>/`. `just plugins` also clones plugins from git here (into `ansible/plugins/.fetched/`, ignored by git) and writes `group_vars/all/plugins.yml`. Templates and settings are read and rendered here. It needs `git` and, for git plugins, the network.
- **The host:** only what the plugin's tasks put there over SSH: the rendered `/opt/services/<compose>/docker-compose.yml`, folders, copied files. Nothing fetches plugin code on the host. A plugin that builds an app from its source clones the app's repository onto the host itself (see "Build from a git repository").

## Write one

1. Copy `ansible/plugin-template/` to `ansible/plugins/<key>/`. The key is lower-case letters, digits and `_`; it is also the role name, the `<key>_enabled` switch and the prefix of every setting.
2. Rename `example` to your key in every file and edit them (the table below).
3. `just plugins` (it needs the vault password file `ansible/.vault-pass`, which `just setup` makes) checks the plugin; its messages name the file and the problem, so fix and repeat. It refuses, among others: a key that is not lower-case letters, digits and `_` or is a role's name, a folder without `service.yml`, `defaults.yml` and `tasks/main.yml`, a setting declared twice, a field `service.yml` does not have, and a missing `<key>_enabled` (and `<key>_sso_enabled` with `oidc`, `<key>_alert_to` with `alert_to`).
4. `just preview <key> --limit <host>`, then `just deploy <key> --limit <host>`, with `<key>_enabled: true` in that host's `vars.yml`.

| File | What it holds |
|---|---|
| `service.yml` | The plugin's entry in the services list: what teardown removes, what the backup covers, the Caddy name and Homepage tile, how people sign in, whether it alerts. Every field is in [plugin-reference.md](./plugin-reference.md#the-service-entry). |
| `defaults.yml` | Settings the rest of the repo reads (other hosts, `service.yml`, the backup): `<key>_enabled: false`, `<key>_port`, `<key>_subdomain`, data folders, the image version, `<key>_sso_enabled`, `<key>_alert_to`. A comment above each. A setting declared here and in the core, or in another plugin, is refused. |
| `defaults/main.yml` | Settings only the plugin's own tasks read, such as the repository to build from or a public address. These belong here, not in `defaults.yml`, and in `vars.yml.example` when they have no default. A setting with no default uses `"{{ undef(hint='...') }}"`, which fails the deploy with the hint until the owner sets it. |
| `tasks/main.yml` | Ordinary Ansible, run on the host. Most services create their folders and run `compose_service`. |
| `templates/` | The compose file and any other file the tasks render (`ansible.builtin.template`). |
| `files/` | Files the tasks copy as they are (`ansible.builtin.copy` finds them here), such as a dump script. |
| `handlers/` | Optional handlers, as in any role. |
| `vars.yml.example` | The values the owner must set in `vars.yml` (every setting with `undef`). `just check` fails if one is missing. |
| `vault.yml.example` | Every `vault_` name the plugin uses, with a comment and a placeholder; `just setup <host>` fills the random ones into the host's vault (for a plugin from git, run `just plugins` first). `just check` fails if a name is missing. |
| `README.md` | What an operator must do by hand (below), and every moved data folder or renamed setting. |

## Recipes

Each bullet is what a plugin of that kind adds to the template's tasks. The fields it sets are in [plugin-reference.md](./plugin-reference.md#the-service-entry).

- **A plain container:** create the data folder, then run `compose_service`, which renders `templates/docker-compose.yml.j2` into `{{ services_dir }}/<name>/` and starts it (it recreates the container when the file changed). A compose file that holds a secret sets `compose_service_has_secrets: true`, which keeps it out of the `just preview` diff. `container_name` is the entry's `container`:

  ```yaml
  - ansible.builtin.import_role:
      name: compose_service
    vars:
      compose_service_name: example
  ```
- **Data folders:** each is `<parent>/<key>` or, for several, `<parent>/<key>/<part>`, where the parent is `fast_appdata_dir` (databases, configs) or `primary_appdata_dir` (bulk data); one folder never sits inside another. Name each in `defaults.yml` (`<key>_data_dir`) and list the names under `data`, `keep`, `no_backup` or `no_backup_in` (a folder is in one list). The backup covers `data` and `keep` ([storage.md](./storage.md)).
- **A container that runs as another user:** the folder belongs to that uid (`owner: "<uid>"` on the folder task). The backup reads files of any owner ([backups.md](./backups.md#root-only-files)).
- **A settings file with secrets** (an env file): mode `0600` and `diff: false`, so the values never print. It is in the backup like any file of the service.
- **A login:** set `login` ([values](./plugin-reference.md#the-service-entry)). Both Tinyauth values need `oidc`, `oidc_secret` (also in `vault.yml.example`) and `<key>_sso_enabled` (default false) in `defaults.yml`; `tinyauth_users` also needs your template to hand `service_users.<key>` to the app. Sign-in: [auth-reference.md](./auth-reference.md#sign-in-with-tinyauth-oidc).

**Build from a git repository.** `compose_service` only renders a compose file, so write the tasks (the compose file has `build: {context: ./src}` or the repository's subfolder):

```yaml
# include_role, not import_role: import would tag every inner task
- ansible.builtin.include_role:
    name: git_clone
  vars:
    git_clone_url: "https://github.com/{{ example_repo }}.git"
    git_clone_dest: "{{ services_dir }}/example/src"
    git_clone_version: "{{ example_commit }}"       # a full commit hash
    git_clone_token: "{{ vault_example_repo_token }}"   # optional: a private repository; sent as a header, never stored

- ansible.builtin.template:
    src: docker-compose.yml.j2
    dest: "{{ services_dir }}/example/docker-compose.yml"
    mode: "0640"

- community.docker.docker_compose_v2:
    project_src: "{{ services_dir }}/example"
    state: present
    # before and after are the commit hashes: rebuild only when the source moved
    build: "{{ 'always' if git_clone_result.before != git_clone_result.after else 'policy' }}"
```

**A live database.** Its file copy can be torn, so it is not a backup. Set `dump_required: true` and install a script the backup runs with the dump directory as `$1`; it keeps the last 3 files named `<compose>-*`, and the deploy stops if the script is missing:

```yaml
- ansible.builtin.copy:
    src: dump.sh                                   # plugins/<key>/files/dump.sh
    dest: "{{ service_dump_scripts_dir }}/example.sh"
    mode: "0755"
```

```bash
#!/bin/bash
set -euo pipefail
OUT="$1/example-$(date +%Y%m%dT%H%M%S).sql"
docker exec example pg_dump -U example example > "$OUT.tmp"   # .tmp first: a half-written dump is never kept
mv "$OUT.tmp" "$OUT"
```

Restoring is by hand ([backups.md](./backups.md#what-is-backed-up-where)). If the app writes its own consistent snapshot into a data folder, that snapshot is the backup and no script is needed: say so in the README.

**Alerts.** `alert_to: true` in the entry and `<key>_alert_to: ""` in `defaults.yml`. The deploy resolves the operator's destination into `alert_targets.<key>`, empty when off ([services.md](./services.md#ntfy-failure-alerts)):

```jinja
{% if alert_targets.example.url | length > 0 %}
ALERT_URL={{ alert_targets.example.url }}      {# an ntfy topic address #}
ALERT_TOKEN={{ alert_targets.example.token }}
{% endif %}
```

## What stays by hand

These are the same for a built-in service. List the ones that apply in the plugin's README, with the exact names:

- A Cloudflare tunnel entry (`cloudflared_ingress`) for a public hostname, and its DNS.
- Copyparty, for an app that reads or writes files there: give it a login and a folder. The login's password is a vault variable, and the operator adds an entry to `vault_copyparty_accounts` with that name. The folder is an entry in `copyparty_folders`, whose `dir` is the plugin's data folder or a part of it, and whose `access` names the login ([services.md](./services.md#copyparty-folders-and-logins)); name the folders and the access in the README.
- `service_users.<key>` for a plugin with `login: tinyauth_users`, and the vault values.

A plugin fetched from git is not rendered by `just check`: `just preview` is its check. A plugin kept in `ansible/plugins/` is rendered with example values, with `<key>_sso_enabled` and `<key>_alert_to` off, so `just check` says nothing about those branches: turn them on in `just preview` on a host before you trust them.

<details>
<summary>Details that surprise people</summary>

- A plugin's `defaults.yml` loads before `vars.yml` and `host_vars`, so an owner can override any setting in it, including an image version. Core versions are different: `versions.yml` wins. `just platforms` does not see a plugin's image.
- Do not register a fact named `services` (`service_facts` does): it hides the services list.
- Plugins are deployed after Garage and before the backup role, so a plugin can rely on everything before it.
- The render test also loads `ansible/tests/fixture-plugin/`, a made-up service that covers the core's branches, so deleting a bundled plugin does not break `just check`.
- `ansible/group_vars/all/plugins.yml` is generated and never edited. `just deploy`, `preview` and `teardown` write it first.

</details>

## From a git repository

A plugin in a git repository is listed in `ansible/group_vars/all/vars.yml` (every host; a `plugins` key in `host_vars` is ignored). Only hosts with `<key>_enabled` deploy it.

```yaml
plugins:
  - {key: myservice, location: "https://git.example.com/you/myservice", commit: "0123456789abcdef0123456789abcdef01234567", auth: vault_myservice_repo_token}
  - {key: other, location: "https://github.com/someone/plugins", commit: "89abcdef0123456789abcdef0123456789abcdef", path: other}
```

| Field | Meaning |
|---|---|
| `key` | The plugin's role name; must match the key in its `service.yml`. |
| `location` | An https git address. |
| `commit` | The full 40-character hash of the exact code to run. A tag or branch is refused, because its owner can move it and the code runs as root on your hosts. Get the hash with `git ls-remote <location> <tag or branch>`, read the code at that commit, and change it only after reading the changes. |
| `path` | Optional. The folder inside the repository that holds the plugin, for a repository with several. Without it the repository root is the plugin. |
| `auth` | Optional. The name of a vault variable (in `group_vars/all/vault.yml`) holding an access token for a private repository. It is sent as a header, never stored in `.git/config`. For a forge that wants a particular user name, put it in the address: `https://alice@host/...`. |

- `just plugins` fetches every entry again (and `just deploy`, `preview` and `teardown` run it first), so the network is needed. It prints each plugin's source and commit.
- A plugin kept in `ansible/plugins/` needs no entry and no commit: its files are in your repo, and git history is its pin. A key in both places is refused, so to use your own copy of a fetched plugin, remove the entry.
- A copy of this repo keeps your `vars.yml`, including this list: [ansible/README.md](../ansible/README.md#using-this-repo-for-your-own-hosts).

## Remove one

Run [teardown](../ansible/README.md#turn-off-or-remove-a-service) for the key first (`-e only=<key>`; it never touches a Cloudflare entry or anything else a plugin put on the host). Then delete the folder (or the `plugins` entry) and the plugin's settings in `vars.yml` and `host_vars`, and run `just plugins`: it fails and names any setting no plugin declares.
