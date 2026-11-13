# Move pinas's /collab into the shared folders layout

> **Status: active plan. Delete this file when pinas serves `/collab` from `/mnt/t7/shared/collab`; git history keeps it.** It records one owner's steps, not conventions: the rules are in AGENTS.md and the code.

The code, `host_vars/pinas/vars.yml` and pinas's vault are changed: `copyparty_shared_folders: [collab]` replaces the collab switch, and `vault_copyparty_accounts` (each entry has `folders: [collab]`) replaces `vault_copyparty_collab_users`. The address `/collab` and every login stay the same. What is left is moving the files to where the deploy now looks.

- [ ] `just preview copyparty --limit pinas` shows the compose mount going from `/mnt/t7/collab:/collab` to `/mnt/t7/shared:/shared`.
- [ ] On pinas, stop Copyparty and move the folder (same drive, so it is instant): `docker stop copyparty && mkdir /mnt/t7/shared && mv /mnt/t7/collab /mnt/t7/shared/collab`.
- [ ] `just deploy copyparty --limit pinas`. The container is recreated with the new mount.
- [ ] Sign in as a friend and open `/collab`: the files are there. Sign in as the admin: `/collab` is there too.
- [ ] Delete this file.
