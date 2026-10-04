# Drive migration plan (2-drive → 3-drive + drive-role map)

Target state, per the drive-role map in `ansible/group_vars/nas/vars.yml`:

| Role | Drive | Mount | Holds |
|---|---|---|---|
| `fast` | Samsung T7 500GB SSD | `/mnt/t7` | Docker data, Immich DB, configs, restic cache, copyparty hist |
| `primary` | WD_BLACK P10 2TB | `/mnt/main` | photos, files, collab |
| `backup` | Seagate ST4000NM0033 4TB | `/mnt/backup` | restic repo, service dumps, logs |

Today (pre-migration): T7 carries `roles: [fast, primary]`; ST3500418AS 500GB carries `[backup]`.

## 0. Vet the new drives before trusting them (used ST4000NM0033 especially)

```bash
smartctl -a /dev/sdX                      # power-on hours, reallocated/pending sectors
smartctl -t long /dev/sdX                 # full SMART long test — wait for it to finish
```

Hardware notes:
- ST4000NM0033 is 3.5": needs a **powered** USB-SATA dock (12V).
- P10 is bus-powered 2.5"; fine on the Pi's official 3A PSU in a USB3 port (Pi 5: use the 5A PSU for the 1.6A budget).

## 1. Backup drive swap (low risk, do first)

1. Format the ST4000NM0033 as ext4 on the Pi; grab its UUID.
2. Point the existing `nas_drives` backup entry's `uuid:` at it (mount stays `/mnt/backup`).
3. `ansible-playbook site.yml --tags storage,backup --ask-vault-pass`
   - storage role wipes/creates nothing destructive; fstab entry is idempotent.
   - `restic init` runs automatically (new repo on the new drive).
4. Let the 2 AM cron run (or trigger `/opt/nas/scripts/backup-restic-local.sh` manually), then verify:
   ```bash
   restic snapshots && restic check
   ```
5. Keep the old restic repo on the 500GB HDD until 2–3 verified snapshots exist on the new repo.

## 2. Primary drive swap + fast/primary split

1. Format the P10 as ext4 → `nas_drives` entry: `mount: /mnt/main`, `roles: [primary]`.
   Trim the T7 entry to `roles: [fast]`.
2. `ansible-playbook site.yml --tags storage` — mounts `/mnt/main`, creates the dir tree there.
3. Stop services for a consistent copy:
   ```bash
   cd /opt/nas/immich && docker compose down   # likewise gitea/copyparty projects
   rsync -aHAX /mnt/t7/photos/ /mnt/main/photos/
   rsync -aHAX /mnt/t7/files/  /mnt/main/files/
   rsync -aHAX /mnt/t7/collab/ /mnt/main/collab/
   # DBs/docker/config dirs STAY on /mnt/t7 (fast role) — nothing to move
   docker compose start ...
   ```
4. Full deploy: `ansible-playbook site.yml --ask-vault-pass` and verify Immich, Gitea, copyparty.

## 3. Retire the old 500GB HDD

- becomes the offline rotation target: monthly `restic copy latest --repo /mnt/backup/restic-repo`
  to a second repo on the removable drive; unplug and store physically elsewhere.

## Notes

- copyparty first post-migration boot re-runs the `e2dsa` scan (hist DB starts fresh after the
  `hist: /hist` move) — expected, not an error.
- The restic cache (`RESTIC_CACHE_DIR`) lands on the fast drive automatically via the role map.
- Dedup is intentionally NOT enabled: in-place edits through the mounted copyparty volume are a
  primary use-case (hardlinks share content between paths). If wanted later: reflink requires btrfs.