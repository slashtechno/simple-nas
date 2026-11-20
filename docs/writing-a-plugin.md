# Writing and using a plugin

A plugin is a service this repo does not ship: a folder shaped like a role, picked up without editing any core file. Crafty and pics are plugins (`ansible/plugins/`); copy the one closest to yours, or `ansible/plugin-template/`. Plugins run as root on your hosts, so read a third party's before you list it. The fields of `service.yml` and the variables a plugin can use are in [plugin-reference.md](./plugin-reference.md).

## Where things are

- **Your computer (where you run `just`):** the plugin folders, in `ansible/plugins/<key>/`. `just plugins` also clones plugins from git here (into `ansible/plugins/.fetched/`, ignored by git) and writes `group_vars/all/plugins.yml`. Templates and settings are read and rendered here. It needs `git` and, for git plugins, the network.
- **The host:** only what the plugin's tasks put there over SSH: the rendered `/opt/services/<compose>/docker-compose.yml`, folders, copied files. Nothing fetches plugin code on the host. A plugin that builds an app from its source clones the app's repository onto the host itself (see "Build from a git repository").

## Write one

1. Copy `ansible/plugin-template/` to `ansible/plugins/<key>/`. The key is lower-case letters, digits and `_`; it is also the role name, the `<key>_enabled` switch and the prefix of every setting.
2. Rename `example` to your key in every file and edit them (the table below).
3. `just plugins` (it needs the vault password file `ansible/.vault-pass`, which `just setup` makes) checks the plugin and its messages say what is wrong; fix and repeat. It refuses a key that is not lower-case letters, digits and `_`, a folder without `service.yml`, `defaults.yml` and `tasks/main.yml`, a setting that is declared twice, a missing `<key>_enabled` or `<key>_sso_enabled`, and an entry whose fields do not fit (the message names the file and the problem).
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
| `vault.yml.example` | Every `vault_` name the plugin uses, with a comment and a placeholder; `just setup <host>` fills the random ones into the host's vault. `just check` fails if a name is missing. |
| `README.md` | What an operator must do by hand (below), and every moved data folder or renamed setting. |

## Do what the service needs

- **A plain container:** `tasks/main.yml` creates the data folder and runs `compose_service` (the template's tasks). The compose file joins the `services` network and sets `container_name`, which is `container` in `service.yml`.
- **Data folders:** each is `<parent>/<key>` or, for several, `<parent>/<key>/<part>`, where the parent is `fast_appdata_dir` (databases, configs) or `primary_appdata_dir` (bulk data); one folder never sits inside another. Name each in `defaults.yml` (`<key>_data_dir`) and list the setting name under `data` in `service.yml`. `keep`, `no_backup` and `no_backup_in` are separate lists of such names: a folder in `keep` is not also in `data`.
- **Secrets in a settings file:** a file the tasks render from vault values (an env file) is mode `0600` with `diff: false` on the task so the values never print. It is in the backup like any file of the service.
- **A container that runs as another user:** the folder must belong to that uid, so the task sets `owner: "<uid>"` instead of `{{ ansible_user }}`. The backup reads files of any owner by default (`backup_read_all_files`, [backups.md](./backups.md#root-only-files)).
- **Build from a git repository:** `compose_service` only renders a compose file, so write the tasks yourself.
  1. Run `include_role: git_clone` with `git_clone_url`, `git_clone_dest` (under `{{ services_dir }}/<compose>/`), `git_clone_version` (a commit hash) and, for a private repository, `git_clone_token` (a vault variable holding an access token, sent as a header and never stored on the host). Afterwards `git_clone_result.before` and `.after` are the commit hashes before and after. It is `include_role` on purpose: `import_role` would tag every inner task.
  2. Give the compose service `build: {context: ./src/<folder in the repository>}`; for a repository holding several projects that is the project's folder.
  3. Write the compose and settings templates and their `template` tasks yourself (the container is not started by `compose_service`), then run `community.docker.docker_compose_v2` (`project_src: "{{ services_dir }}/<compose>"`, `state: present`) with `build: "{{ 'always' if git_clone_result.before != git_clone_result.after else 'policy' }}"`, which rebuilds only when the source moved.
- **A live database:** its file copy is not a restorable backup (it is copied while the app writes, so it can be torn). If the app writes its own consistent snapshot into a data folder, that snapshot is the backup and no script is needed; say so in the README. Set `dump_required: true` in `service.yml`, put the script in `files/dump.sh` and install it in the tasks as `{{ service_dump_scripts_dir }}/<compose>.sh` (mode `0755`, owned by `ansible_user`); the deploy stops if it is missing. The backup runs the script with the dump directory as `$1` and keeps the last 3 files whose names start with `<compose>-`. Write to `<name>.tmp` and rename on success, so a half-written dump is never kept. The restore is by hand, from the dump file ([backups.md](./backups.md#what-is-backed-up-where)).
- **A login of its own:** set `login` in `service.yml`:
  - Absent: Tinyauth's login page sits in front of the Caddy name.
  - `own`: the app has its own login and the page stays off.
  - `tinyauth`: the app also signs in through Tinyauth (OIDC).
  - `tinyauth_users`: the same, and the app lets in only the users in `service_users.<key>`, which your tasks must hand to the app. The deploy stops if `<key>_sso_enabled` is on and `service_users.<key>` is empty.

  Both OIDC values need `oidc` (every address the app is opened at, as a redirect URI; an app that sends the address it was opened on needs one per Caddy name and per extra address, built in `service.yml`) and `oidc_secret` (the name of a `vault_` variable, listed in `vault.yml.example`), and the plugin declares `<key>_sso_enabled` (default false) in `defaults.yml`. Tinyauth's client id is the key: renaming it orphans linked accounts. The sign-in is explained in [auth-reference.md](./auth-reference.md#sign-in-with-tinyauth-oidc). An operator cannot override `login` per host. `just plugins` prints each plugin's `login`.
- **Alerts:** `alert_to: true` in `service.yml` and `<key>_alert_to: ""` in `defaults.yml`. The operator names a destination from `ntfy_destinations` ([services.md](./services.md#ntfy-failure-alerts)); the deploy resolves it into `alert_targets.<key>.url` and `.token` (the ntfy address and its token, empty when off). `.url` is the address of an ntfy topic and `.token` its access token; if the app wants another format (Apprise, for example), your template builds it from these two.
- **Backups:** `data` and `keep` in `service.yml` are covered automatically. `no_backup` is data in no backup and `no_backup_in` leaves one folder of a data directory out. A data folder outside the drives stops the deploy while `backup_local_enabled` is on ([storage.md](./storage.md)).
- **Teardown:** `just teardown <host> -e only=<key>` removes the compose project, the dump script and, with `remove_data=true`, the `data` folders (never `keep`). Anything else the plugin puts on the host is yours to remove; say so in the README.

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

`just teardown <host> -e only=<key>` first, then delete the folder (or the `plugins` entry), delete the plugin's settings from `vars.yml` and `host_vars` (`just plugins` fails and names a setting no plugin declares), and run `just plugins`. Once the entry is gone, teardown no longer knows the service. Teardown never touches a Cloudflare entry or anything else a plugin put on the host.
