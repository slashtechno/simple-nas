# Plugin reference

The fields of a service entry (`service.yml` in a plugin, an item of `core_services` in `ansible/group_vars/all/services.yml` for a built-in service) and the variables a plugin's tasks and templates can use. The guide is [writing-a-plugin.md](./writing-a-plugin.md).

## The service entry

Teardown, the backup, the Caddy name and the Homepage tile all read it. Settings that differ per host (`<key>_port`, data folder paths) are not in it: they are plain settings in `defaults.yml`, and the entry names them.

| Field | Meaning |
|---|---|
| `name` | The display name (the Homepage tile, messages). Required. |
| `key` | The prefix of the service's settings: `<key>_enabled` switches it on, `<key>_port` is its host port and `<key>_subdomain` its name under the private domain. For a plugin it is also the role name. Required. |
| `compose` | The service's directory under `services_dir` (`/opt/services/<compose>`), also its compose project. Teardown removes it. |
| `data` | The **names** of the settings that hold the service's data folders (not paths: a host without drives still reads the entry). The deploy fails unless the local backup covers them; the offsite notice names them; teardown deletes them with `remove_data=true`. A name that evaluates to `""` is skipped, so `"{{ 'x_dir' if x_enabled \| bool else '' }}"` makes a folder conditional. |
| `no_backup` | Setting names of folders teardown deletes but the backup leaves out on purpose (data that is made again, or covered by a dump). |
| `no_backup_in` | `{setting name: folder}`: a folder inside a data folder that the backup leaves out on purpose (it is made again). Say why in a comment by the entry. |
| `keep` | Setting names of folders the backup covers but teardown never deletes (the owner's files). |
| `dump_required` | `true` when the file copy of a live database is not the copy to restore. The plugin must then install `{{ service_dump_scripts_dir }}/<compose>.sh` ([how](./writing-a-plugin.md#recipes)); the deploy fails if it is missing, and teardown removes it. |
| `alert_to` | `true` when the service sends alerts itself. Its sender name is the key and its setting `<key>_alert_to` (in `defaults.yml`, default `""`), the name of a destination in `ntfy_destinations`. The deploy resolves it into `alert_targets.<key>.url` and `.token`. |
| `login` | How people sign in. Absent: Tinyauth's login page sits in front of the Caddy name (an app with no login of its own). Any other value leaves that page off. `own`: the service has its own login, or its clients (apps, git, WebDAV, push) cannot sign in through a web page. `tinyauth`: its own login plus "sign in with Tinyauth" (OIDC); the app's own accounts decide who enters. `tinyauth_users`: the same, but the app lets in only the users in `service_users.<key>`, which the plugin's tasks must hand to the app, because Tinyauth cannot limit an OIDC client. Both Tinyauth values need `oidc` and `oidc_secret`. A fixed `port` has no Caddy name, so no login page either. |
| `oidc_secret` | The name of the vault variable holding the app's Tinyauth client secret. Required with `login: tinyauth` or `tinyauth_users`, and only then. |
| `oidc` | The redirect URIs the app returns to after a Tinyauth login, full addresses, exactly as the app sends them (an app that sends the address it was opened on needs one per address). An entry with `oidc` is a Tinyauth client (id: its key, name: its name) on a host with `<key>_sso_enabled`. The id is part of the account id the app stores, so changing it orphans every linked account. The app's own side repeats the id and the URI: change both together. |
| `port` | A fixed host port, for a service whose port is not ours to set (one on the host network). Such a service has no `<key>_port`, no `<key>_subdomain` and no Caddy name. |
| `container`, `container_port` | What Caddy proxies to on the `services` network. A web service needs both, an `icon`, and `<key>_port` and `<key>_subdomain` in `defaults.yml`. |
| `tile_url` | The name of a setting (not an address) holding the address the Homepage tile links to, when the sign-in has to start there instead of on the Caddy name. |
| `scheme` | `http` unless set; `https` means the container serves a self-signed certificate, which Caddy accepts. |
| `icon` | A name from [dashboard-icons](https://github.com/homarr-labs/dashboard-icons), or `mdi-<name>` from [Material Design Icons](https://pictogrammers.com/library/mdi/). An entry with an `icon` has a Homepage tile and a Caddy name. |
| `description` | The line under the Homepage tile's name. |

`oidc` for an app served at `<key>_subdomain` under every private domain, whose login returns to `/auth/callback`:

```yaml
oidc: "{{ caddy_private_domains | map('regex_replace', '^', 'https://' ~ example_subdomain ~ '.') | map('regex_replace', '$', '/auth/callback') | list }}"
```

## Variables a plugin can use

Settings of this repo, available in tasks, templates and the entry:

| Variable | Is |
|---|---|
| `services_dir` | `/opt/services`: the parent of every compose directory. |
| `docker_network` | The shared network every compose file joins (`services`). |
| `timezone` | The host's timezone, for a container's `TZ`. |
| `fast_appdata_dir`, `primary_appdata_dir` | The app data folders on the `fast` and `primary` drives ([storage.md](./storage.md)). A plugin's data folder defaults to `{{ primary_appdata_dir }}/<key>` or `{{ fast_appdata_dir }}/<key>`. |
| `ansible_user` | The user that owns the files a task creates. |
| `service_dump_scripts_dir` | Where a dump script is installed. |
| `caddy_private_domains` | The private domains; a service is served at `<key>_subdomain.<domain>` under each. |
| `tinyauth_url` | The address of the Tinyauth login page, for an app that signs in through it. |
| `service_users` | `{key: [user names]}`; a plugin with `login: tinyauth_users` hands `service_users.<key>` to the app. |
| `alert_targets.<key>` | `.url` and `.token` of the alert destination (empty when off), for a plugin with `alert_to`. |
| `vault_<name>` | Any value in the host's vault ([ansible/README.md](../ansible/README.md#vault-secrets)). |
| `<other service>_enabled`, `<other service>_port`, … | Any other service's settings, for example to check that Copyparty runs on the host. |

`just settings <word>` lists the core's settings with their default and what sets it, and each plugin's once `just plugins` has run.
