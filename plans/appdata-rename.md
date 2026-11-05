# Rename `<fast>/docker` to `<fast>/appdata`

Status: pi4 done when this line says so; pinas and dietvostro wait for their next deploy. Delete this file when all hosts are done.

The per-service data directory on the fast drive was `<fast>/docker`, which reads like Docker's engine storage. It is now `<fast>/appdata` (`group_vars/all/data-dirs.yml`). The code has no fallback to the old name, so each host moves its directory once, before its next deploy.

On each host, as the Ansible user, with `FAST` the fast drive's mount (`/mnt/apps` on pi4, `/mnt/t7` on pinas):

1. Stop every service whose data is in `$FAST/docker`: `for f in /opt/services/*/docker-compose.yml; do docker compose -f $f down; done`. Dockge stacks that do not use `$FAST/docker` can keep running.
2. No host encrypts `$FAST/docker` yet. Encrypt `appdata` only after this move ([encryption.md](../docs/encryption.md)).
3. `sudo mv $FAST/docker $FAST/appdata`.
4. In `host_vars/<host>/vars.yml`, change any path setting that names `/docker`.
5. `just deploy '' --limit <host>`: the compose files are regenerated with the new paths and the services start.
6. Check each service answers, then run one backup by hand as the Ansible user. The snapshot lists the folder under the new path; restic stores the unchanged data once.
7. Delete the old `$FAST/docker` if it is left over (it is only an empty folder after the move).
