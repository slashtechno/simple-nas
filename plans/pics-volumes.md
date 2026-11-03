# pics volumes: move off the Copyparty files folder

Status: code done; waits for the owner to run the move on pinas (outside upload hours).

pinas still holds pics' photos in `copyparty_files_dir/photos` and `photos-trash`: `host_vars/pinas/vars.yml` sets `pics_photos_dir` and `pics_trash_dir` to those folders so a deploy does not point pics at empty ones. The defaults are `primary_drive/pics/photos` and `primary_drive/pics/trash`.

1. In the vault, rename `vault_copyparty_photos_pass` to `vault_pics_copyparty_pass` (same value). The Copyparty account is now named `pics`, not `photos`.
2. Deploy `copyparty,pics` once with the pinned folders. Copyparty is recreated (new mounts), so do it when no upload is running. Check pics still lists its photos.
3. Stop pics (`docker compose -f /opt/services/pics/docker-compose.yml stop`), then on pinas `mkdir -p /mnt/primary/pics` and `mv` the two folders: `mv /mnt/primary/files/photos /mnt/primary/pics/photos`, `mv /mnt/primary/files/photos-trash /mnt/primary/pics/trash`.
4. Delete the two lines from `host_vars/pinas/vars.yml`, deploy `copyparty,pics`, start pics.
5. Copyparty rebuilds its index for the volumes on first start (slow on a big folder). If pics shows a photo as missing, `pics reindex` (pics `docs/deploy.md`) rebuilds its database from the volume.
