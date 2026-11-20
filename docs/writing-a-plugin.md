# Writing and using a plugin

A plugin is a service this repo does not ship: a folder shaped like a role, picked up without editing any core file. Crafty is one (`ansible/plugins/crafty/`). Plugins run as root on your hosts, so read a third party's before you list it.

## Write one

1. Copy `ansible/plugin-template/` to `ansible/plugins/<key>/`. The key is lower-case letters, digits and `_`; it is also the role name, the `<key>_enabled` switch and the prefix of every setting.
2. Rename `example` to your key in every file, and edit them (the table below).
3. `just plugins` checks it and says what is wrong; fix and repeat.
4. `just preview <key> --limit <host>`, then `just deploy <key> --limit <host>`, with `<key>_enabled: true` in that host's `vars.yml`.

| File | What it holds |
|---|---|
| `service.yml` | The plugin's entry in the services list: what teardown removes, what the backup covers, the Caddy name and Homepage tile, how people sign in. Every field is explained at the top of `ansible/group_vars/all/services.yml`. |
| `defaults.yml` | The settings the rest of the repo reads: `<key>_enabled: false`, `<key>_port`, `<key>_subdomain`, data folders, the image version, `<key>_alert_to`. Each has a comment above it. |
| `defaults/main.yml` | Settings only the plugin's own tasks read. |
| `tasks/main.yml` | Ordinary Ansible. Most services create their folders and run `compose_service` (`ansible/README.md#add-a-new-service`). |
| `templates/` | The compose file and any other file the tasks render. |
| `README.md` | What an operator must create (vault names, a Copyparty login), and every moved data folder or renamed setting. |

A setting goes in `defaults.yml` when another host or role reads it, because role defaults are invisible to them; a setting declared in two places is refused.

<details>
<summary>How the plugin, you and the core divide the work</summary>

The author knows how the software behaves; the operator knows their own people and hosts. No user name lives in a plugin.

- **Plugin:** `login`, `oidc` paths, `oidc_secret` (the vault variable's name), `container_port`, `data`, `dump_required`, `alert_to`, and the default settings.
- **Operator:** `<key>_enabled`, `<key>_sso_enabled`, `service_users.<key>`, ports, subdomains, drives, `<key>_alert_to` (which destination), vault values, Cloudflare ingress, Copyparty logins and folders.
- **`login`** decides the Tinyauth login page. Absent: it sits in front of the Caddy name. `own`: the app has its own login and the page stays off. `tinyauth`: the app also signs in through Tinyauth (needs `oidc`, `oidc_secret`, `<key>_sso_enabled`). `tinyauth_users`: the same, and the app lets in only the users in `service_users.<key>`, which its role must hand to the app (Tinyauth cannot limit an OIDC client). `login` is security-relevant and an operator cannot override it per host; to disagree, keep a copy in `plugins/<key>/` and drop the `plugins` entry. `just plugins` prints each plugin's `login`.
- Copyparty folders, Cloudflare tunnel entries and their DNS are by hand, as for a built-in service; the plugin's README names the port or folders.
- A `dump_required` plugin must install `<service_dump_scripts_dir>/<compose>.sh`; without it the backup stops the deploy.
- The key is the Tinyauth client id: renaming it orphans every linked account.
- Backups cover `data` and `keep` automatically. `no_backup` means the data is in no backup. A data folder outside the drives stops the deploy while `backup_local_enabled` is on.
- `just check` renders the plugins kept in this repo, not fetched ones; `just preview` is the check for those.
- Do not register a fact named `services` (`service_facts` does): it hides the services list.

</details>

## From a git repository

A plugin in a git repository is listed in `ansible/group_vars/all/vars.yml` (every host; a `plugins` key in `host_vars` is ignored). Only hosts with `<key>_enabled` deploy it.

```yaml
plugins:
  - {key: myservice, location: "https://git.example.com/you/myservice", commit: "0123456789abcdef0123456789abcdef01234567", auth: vault_myservice_repo_token}
  - {key: other, location: "https://github.com/someone/plugins", commit: "89abcdef0123456789abcdef0123456789abcdef", path: other}
```

- `location` is an https git address, `commit` the full 40-character hash of the exact code to run. A tag or branch is refused because its owner can move it, and plugin code runs as root on your hosts. Get the hash with `git ls-remote <location> <tag or branch>`, read the code at that commit, and update the hash only after reading the changes.
- `path` is the folder inside the repository that holds the plugin, for a repository with several. Without it the repository root is the plugin. The `key` here is the role name, whatever the folder is called there.
- `auth` names a vault variable (in `group_vars/all/vault.yml`) holding an access token for a private repository. It is sent as a header, never stored in `.git/config`. For a forge that wants a particular user name, put it in the address: `https://alice@host/...`.
- `just plugins` fetches every entry again (and `just deploy`, `preview` and `teardown` run it first), so the network is needed and a moved branch is picked up. It prints each plugin's source and commit.
- A plugin kept in `ansible/plugins/` needs no entry. A key in both places is refused, so to use your own copy of a fetched plugin, remove the entry.

## Remove one

`just teardown <host> -e only=<key>` first, then delete the folder (or the `plugins` entry) and run `just plugins`. Once the entry is gone, teardown no longer knows the service. Teardown removes the compose project, the dump script and, with `remove_data=true`, the data; it never touches a Cloudflare entry or anything else a plugin put on the host.
