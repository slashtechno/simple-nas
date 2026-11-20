# Example plugin

Copy this folder to `ansible/plugins/<key>/` and rename `example` to your key in every file ([docs/writing-a-plugin.md](../../docs/writing-a-plugin.md)). Replace this file with what an operator must do by hand:

- the vault variables to create (also in a `vault.yml.example` in this folder, if the plugin has secrets) and the values to set in `vars.yml` (a `vars.yml.example`, if any setting has no default);
- a Copyparty login and its folders, a Cloudflare tunnel entry, `service_users` (nothing in a plugin names a person);
- every data folder that moved and every setting that was renamed, so an upgrade does not lose data silently.

Optional files a plugin adds when it needs them: `files/` (copied as they are, such as `dump.sh`), `handlers/`, `vars.yml.example`, `vault.yml.example`.
