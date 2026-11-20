# pics (photo culling and sharing)

A bundled plugin ([how plugins work](../../../docs/writing-a-plugin.md)). Needs the `fast` and `primary` drive roles and Copyparty; switch it on with `pics_enabled: true` in a host's `vars.yml`.

The `pics` role clones the private repo in `pics_repo` and builds the image on the host (about 10 minutes on a Pi 5). Later runs rebuild only when the repo's commit changed. The role runs the app on `services`. It uses the Copyparty login `pics` and two folders: `/pics/photos` (no delete) and `/pics/trash` (delete allowed). The build needs memory on top of the running services. On a 4 GB host deploy a changed `pics` while Immich and Crafty are idle, then check `free -m` and `journalctl -k | grep -i oom`.

1. Set `pics_repo` (`owner/name`) and `pics_public_url` (e.g. `https://photos.example.com`) in `group_vars/all/vars.yml`. Add `pics` to `service_users` if you use `pics_sso_enabled`.
2. Add a `cloudflared_ingress` entry for the public hostname, pointing at `http://pics:<pics_public_port>` (8001, inside Docker only). It serves the guest pages (shares, portfolio) and no owner routes, so it needs no `path` rule. The owner app (cull UI, password-gated) is on the host port `pics_port` (8100): `http://<host>:<pics_port>`.
3. Add `vault_pics_password` (12+ characters), `vault_pics_secret_key` (`openssl rand -base64 48`) and `vault_pics_copyparty_password` to the host's vault, without single quotes. Then add the login `pics` to `vault_copyparty_accounts` with `pass: "{{ vault_pics_copyparty_password }}"`.
4. Add two folders to `copyparty_folders` in the host's `vars.yml`, as in the [example](../../../docs/services.md#add-a-folder-or-a-login). Add `services/pics/photos` with `dir: "{{ pics_photos_dir }}"` and `access: {pics: rwm}`. Add `services/pics/trash` with `dir: "{{ pics_trash_dir }}"` and `access: {pics: rwmd}`. The deploy stops when a folder or a `dir` is not valid.
5. Run `just deploy copyparty,pics,cloudflared --limit <host>` (`copyparty` creates the login and folders first).
6. Optional: sign in with Tinyauth (`pics_sso_enabled`, [auth-reference.md](../../../docs/auth-reference.md#sign-in-with-tinyauth-oidc)). The password login and the importer's token stay, and pics' Caddy name is not behind Tinyauth: pics has its own login.

The database is in `pics_data_dir`, covered by the daily backup (the app also writes its own daily snapshots there). `teardown.yml -e only=pics` keeps all of pics' data unless `-e remove_data=true`, which also deletes the photos and trash.

## Private repository token

Token: `vault_pics_repo_token`, a read-only fine-grained token scoped to the one repo (`vault.yml.example` says how). A role calls `roles/git_clone` with a URL and `dest`. The token reaches git through its environment, so it is not stored in `.git/config`. If it expires the clone step fails: make a new one and update the vault.
