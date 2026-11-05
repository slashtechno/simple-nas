# pics volumes: move off the Copyparty files folder

Status: code done; waits for the owner to run the move on pinas (outside upload hours).

pinas still holds pics' photos in `copyparty_files_dir/photos` and `photos-trash`: `host_vars/pinas/vars.yml` sets `pics_photos_dir` and `pics_trash_dir` to those folders so a deploy does not point pics at empty ones. The defaults are `primary_drive/apps/pics/photos` and `primary_drive/apps/pics/trash`.

1. Deploy `copyparty,pics` once with the pinned folders. Copyparty is recreated (new mounts), so do it when no upload is running. Check pics still lists its photos.
2. Stop pics (`docker compose -f /opt/services/pics/docker-compose.yml stop`), then on pinas `PRIMARY=/mnt/t7` (the mount of the `primary` drive), `mkdir -p $PRIMARY/apps/pics` and `mv` the two folders: `mv $PRIMARY/files/photos $PRIMARY/apps/pics/photos`, `mv $PRIMARY/files/photos-trash $PRIMARY/apps/pics/trash`.
3. Delete the two lines from `host_vars/pinas/vars.yml`, deploy `copyparty,pics`, start pics.
4. Copyparty rebuilds its index for the new volumes on first start (slow on a big folder); restart Copyparty once after the `mv` so `/files` drops the moved folders from its index. If pics shows a photo as missing, `pics reindex` (pics `docs/deploy.md`) rebuilds its database from the volume.
