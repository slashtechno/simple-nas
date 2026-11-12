# Data layout migration (one appdata folder)

> **Status: active plan. Delete this file when both hosts are migrated and the branch is merged; git history keeps it.** It records one owner's steps, not conventions: the rules are in AGENTS.md and the code.

Branch: `layout-appdata-bulk`. The layout rule is in [storage.md](../docs/storage.md#what-lives-where): a service's data is `appdata/<service>[/<part>]` on its role's drive, and your own files have plain names. `main` is what the hosts deploy from, so merge only after both hosts are done.

**Order: stop, move, deploy. Never deploy first.** A deploy before the move creates empty new folders. Immich would then start a new, empty Postgres cluster, and a later `mv` into an existing folder nests the old one inside it.

## What moves

On pinas (`/mnt/t7`, roles `fast` and `primary` on one drive, so every `mv` below is a rename inside one filesystem):

| Old | New |
|---|---|
| `photos` | `appdata/immich/photos` |
| `appdata/immich_postgres` | `appdata/immich/postgres` |
| `appdata/copyparty_config` | `appdata/copyparty/config` |
| `appdata/copyparty-hist` | `appdata/copyparty/hist` |
| `appdata/gitea` | `appdata/gitea/data` |
| `appdata/gitea_runner` | `appdata/gitea/runner` |
| `appdata/pics` | `appdata/pics/data` |
| `apps/pics/photos`, `apps/pics/trash` | `appdata/pics/photos`, `appdata/pics/trash` |

Garage (`appdata/garage/meta` and `data`) and Crafty (`appdata/crafty`) stay where they are.

On pi4 (`/mnt/apps`): only `appdata/copyparty_config` and `appdata/copyparty-hist` move, to `appdata/copyparty/config` and `appdata/copyparty/hist`.

Unchanged: `caddy`, `dozzle`, `dockge`, `homebridge`, `ntfy`, `scrutiny`, `tinyauth`, `files`, `collab`, `stacks`, `restic-cache`.

Setting names that changed: `immich_upload_location` is `immich_photos_dir`, `immich_db_data_location` is `immich_postgres_dir`, `homebridge_config_dir` is `homebridge_data_dir`, `garage_data_dir` is `garage_meta_dir` plus `garage_blocks_dir`, `appdata_dir` is `fast_appdata_dir` (and `primary_appdata_dir` is new), `copyparty_fast_dir` and `copyparty_fast_enabled` are `copyparty_scratch_dir` and `copyparty_scratch_enabled`. The host vars files set none of them. A host that had the Copyparty `fast` volume on moves `fast` to `scratch` the same way (step 2).

## 0. Before anything

- [ ] On your machine: `git checkout layout-appdata-bulk`, then `just check` in `ansible/`, and `just preview '' --limit <host>` to read the diff (it shows new paths; nothing has moved yet).
- [ ] On each host, run a backup and check it: `/opt/services/scripts/backup-restic-local.sh`, then `restic snapshots` (the restic recipe is in [backups.md](../docs/backups.md)). Check that the newest snapshot is from today.
- [ ] Define a move helper in the host shell. It refuses a missing source or an existing target, and skips a step that is already done, so you can run the list again after a stop:

  ```bash
  mv_new() {
    if [ ! -e "$1" ] && [ -e "$2" ]; then echo "done already: $2"; return 0; fi
    [ -e "$1" ] || { echo "MISSING source: $1" >&2; return 1; }
    [ ! -e "$2" ] || { echo "target exists, stop: $2" >&2; return 1; }
    sudo mv -v "$1" "$2"
  }
  ```

## 1. Stop what uses the old paths

Ask Docker, not memory. This lists every container with a bind mount under the drive and the folder its compose file is in:

```bash
docker ps -q | xargs -r docker inspect -f '{{.Name}} {{index .Config.Labels "com.docker.compose.project.working_dir"}} {{range .Mounts}}{{.Source}} {{end}}' | grep -E '/mnt/(t7|apps)/'
```

Stop the ones whose mounts are in the table above, in each folder: `docker compose down`. On pinas these are Immich (server, Postgres), Copyparty, Gitea (and its runner) and pics. Garage and Crafty keep their paths: leave them running. Then run the command again: no listed path may still be mounted by a running container.

## 2. Move (pinas)

```bash
T=/mnt/t7
sudo install -d -o "$USER" -g "$USER" "$T/appdata/immich" "$T/appdata/copyparty"

mv_new $T/appdata/immich_postgres      $T/appdata/immich/postgres
mv_new $T/photos                       $T/appdata/immich/photos
mv_new $T/appdata/copyparty_config     $T/appdata/copyparty/config
mv_new $T/appdata/copyparty-hist       $T/appdata/copyparty/hist
```

Gitea and pics change a folder into a folder of the same name, so each goes through a temporary name. Run each block once. If one stops halfway, look at the folders by hand instead of running it again.

Gitea (the old folder becomes the new `data` inside a folder of the old name):

```bash
mv_new $T/appdata/gitea                $T/appdata/gitea-old
sudo install -d -o "$USER" -g "$USER" $T/appdata/gitea
mv_new $T/appdata/gitea-old            $T/appdata/gitea/data
mv_new $T/appdata/gitea_runner         $T/appdata/gitea/runner
```

pics:

```bash
mv_new $T/appdata/pics                 $T/appdata/pics-old
sudo install -d -o "$USER" -g "$USER" $T/appdata/pics
mv_new $T/appdata/pics-old             $T/appdata/pics/data
mv_new $T/apps/pics/photos             $T/appdata/pics/photos
mv_new $T/apps/pics/trash              $T/appdata/pics/trash
```

A host that used the Copyparty `/fast` volume also needs `mv_new $T/fast $T/scratch` here. Neither of your hosts does.

Then check that nothing is left behind: `ls -A $T $T/appdata $T/apps`.

## 3. Stray folders on pinas

Each is checked, looked at and only then deleted. Step 1's list shows whether a container mounts it.

- [ ] `$T/copyparty-hist` (top level): confirm no container mounts it, then `ls -la` and `du -sh` it. Copyparty rebuilds its thumbnail data, so delete it if it holds only that.
- [ ] `$T/backups`: `ls -A` it. Remove it with `rmdir` only if it is empty.
- [ ] `$T/apps`: `rmdir $T/apps/pics $T/apps` once the pics folders have moved.

## 4. Deploy

- [ ] `just deploy '' --limit pinas`. The service roles recreate their containers on the new paths.
- [ ] Check the mounts point at the new paths and nothing points at the old ones:

  ```bash
  docker ps -q | xargs -r docker inspect -f '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}' | grep -E '/mnt/t7/' | sort
  ls -A $T $T/appdata
  ```
- [ ] Open each service: Immich shows the photos, Gitea shows the repositories and the runner is online, pics and Copyparty show the photos.
- [ ] Run `/opt/services/scripts/backup-restic-local.sh` and check `restic snapshots`. Restic stores the moved files again as paths, but deduplicates the content, so little is uploaded.

## 5. pi4

Same order, and a checked backup first (step 0): stop Copyparty (step 1), then

```bash
T=/mnt/apps
sudo install -d -o "$USER" -g "$USER" "$T/appdata/copyparty"
mv_new $T/appdata/copyparty_config $T/appdata/copyparty/config
mv_new $T/appdata/copyparty-hist   $T/appdata/copyparty/hist
```

then `just deploy '' --limit pi4` and check Copyparty. pi4's `/mnt/t7/photos` is not one of this repo's paths: look at it by hand.

## Rollback

Stop the same containers and run the `mv` lines backwards (new to old). Gitea and pics first need their folder out of the way: `mv appdata/gitea/data appdata/gitea-old`, remove the empty `appdata/gitea` after moving `runner` back, then `mv appdata/gitea-old appdata/gitea`; the same for `appdata/pics` (and `install -d $T/apps/pics` before moving the photos back). Then `git checkout main` and deploy. The deploy before the move is the only step that cannot be undone with `mv` alone (an empty Postgres cluster started on the new path): never do it.

## Done

- [ ] Both hosts migrated and checked, a backup after the move checked.
- [ ] `git grep -w` for each old setting name (`immich_upload_location`, `immich_db_data_location`, `homebridge_config_dir`, `garage_data_dir`, `appdata_dir`, `copyparty_fast_dir`) finds nothing (`git grep <name> -- ':!plans'`; `-w` keeps `fast_appdata_dir` from matching `appdata_dir`).
- [ ] Merge the branch to `main`, then delete this file.
