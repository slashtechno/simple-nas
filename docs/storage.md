# Storage: drive roles

Every `nas_drives` entry in `group_vars/nas/vars.yml` lists the `roles:` it fills. One drive can hold several roles (a one-drive NAS is `roles: [fast, primary, backup]` on a single entry). Each role is claimed by exactly one drive; the storage role's assert fails the deploy on duplicates or unknown names.

| Role | Holds |
|---|---|
| `fast` | Random-IO data (Docker, Immich database, configs) and caches (restic cache, Copyparty `hist`) |
| `primary` | Bulk data (photos, files) |
| `backup` | The restic repo, service dumps, logs |

Service paths come from `fast_drive`, `main_drive` and `backup_drive`, worked out from `nas_drives` in `group_vars/nas/derived.yml`. When roles share a drive nothing changes on disk. Adding a dedicated drive for a role later moves that role's paths to the new mount point, and you move the data there once.

To add or replace a drive:
1. Format it and add or point a `nas_drives` entry at it (a new UUID, either on the same mount or a new `mount:` with updated `roles`).
2. `just deploy storage`.
3. Copy the data over, for example `rsync -aHAX`.

The step-by-step plan for the next drive upgrade is in [plans/drive-migration.md](./plans/drive-migration.md). A backup drive that drops out and comes back is covered in [backups.md](./backups.md#if-the-backup-drive-disconnects).
