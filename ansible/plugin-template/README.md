# Example plugin

Copy this folder to `ansible/plugins/<key>/` and rename `example` to your key in every file (docs/writing-a-plugin.md). Replace this file with
what an operator needs to know:

- the vault variables to create, a Copyparty login, a Cloudflare tunnel entry, `service_users` (nothing in a plugin names a person);
- every data folder that moved and every setting that was renamed, so an upgrade does not lose data silently.
