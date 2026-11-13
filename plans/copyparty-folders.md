# Move Copyparty to one folder list and one login list

> **Status: active plan. Delete this file when pinas and pi4 run the new Copyparty config; git history keeps it.** It records one owner's steps, not conventions: the rules are in AGENTS.md and the code.

The code, `host_vars/pinas/vars.yml` and both hosts' vaults are changed. `copyparty_folders` replaces `copyparty_shared_folders` and pics' `copyparty` field. `vault_copyparty_accounts` replaces `vault_copyparty_user`, `vault_copyparty_password` and `copyparty_sso_admins`: it holds every login, and `admin: true` marks an admin. What is left is the host steps.

What changes for a user:
- `/collab` keeps its address and its logins.
- pics' two folders move from `/apps/pics/photos` and `/apps/pics/trash` to `/pics-photos` and `/pics-trash`. The files stay where they are. pics stores paths relative to its `COPYPARTY_ROOT`, so its database needs no change.
- The `/apps` page is gone. Bookmarks and Copyparty share links that point into `/apps/pics/...` stop working.

## pinas

- [ ] Move the folder to the shared layout (same drive, so it is instant): `docker stop copyparty && mkdir -p /mnt/t7/shared && mv /mnt/t7/collab /mnt/t7/shared/collab`. Skip this step if `/mnt/t7/shared/collab` exists.
- [ ] `just preview copyparty,pics --limit pinas` shows these mounts: `/mnt/t7/shared/collab:/vol/collab`, `/mnt/t7/appdata/pics/photos:/vol/pics-photos` and `/mnt/t7/appdata/pics/trash:/vol/pics-trash`. It shows the pics env roots `/pics-photos` and `/pics-trash`.
- [ ] `just deploy copyparty,pics --limit pinas`.
- [ ] Sign in as an admin: `/collab`, `/pics-photos`, `/pics-trash` and `/drives` are there. Sign in as the friend: only `/collab`.
- [ ] Open pics: the photo list loads and a photo opens.

## pi4

- [ ] `just deploy copyparty --limit pi4`.
- [ ] Sign in with the Tinyauth login and with the admin password: both open `/` and `/drives`.

## Last

- [ ] Delete this file.
