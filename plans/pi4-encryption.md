# Encrypt pi4 (and run the unlock page there)

> **Status: active plan. Delete this file when pi4 is encrypted and the page works; git history keeps it.** It records one owner's steps, not conventions: the rules are in AGENTS.md and the code.

Branch: `unlock-page-role`, merged to `main` before step 4 (the hosts deploy from `main`).

Decisions: encrypt `/mnt/apps/appdata`, `/mnt/apps/stacks` and `/mnt/apps/files`. `stacks` holds 21 GB, mostly the media and download folders, so the first setup runs at the encrypted write speed (3 to 5 MB/s, over an hour for `stacks`). ntfy, Caddy and Tinyauth stay plain under `/mnt/apps/plain/`: ntfy so alerts work while locked, Caddy and Tinyauth so the unlock page can be reached. The page runs on pi4 and unlocks pi4 only; pinas follows the same steps later.

## 1. Settings (on your machine)

- [ ] In `host_vars/pi4/vars.yml`:

  ```yaml
  encrypted_folders: [/mnt/apps/appdata, /mnt/apps/stacks, /mnt/apps/files]
  ntfy_data_dir: /mnt/apps/plain/ntfy
  caddy_data_dir: /mnt/apps/plain/caddy
  tinyauth_data_dir: /mnt/apps/plain/tinyauth
  unlock_page_enabled: true
  ```
- [ ] `just check`, then `just preview '' --limit pi4` and read the diff. A path that moves shows as a new folder.

## 2. Backup and stop

- [ ] On pi4: `/opt/services/scripts/backup-restic-local.sh`, then `restic snapshots` ([connecting](../docs/backups.md#connecting)). The newest snapshot must be from today. Three root-owned files in `stacks/cortex` report a read error: that is known.
- [ ] Save what is running, then stop it: `docker ps --format '{{.Names}}' > ~/running.txt && xargs -r docker stop < ~/running.txt`. Then `docker ps` lists nothing. Your own stacks are not started by a deploy or an unlock, so step 6 starts them from this file.

## 3. Move the plain folders (pi4)

```bash
T=/mnt/apps
sudo install -d -o "$USER" -g "$USER" $T/plain
for s in ntfy caddy tinyauth; do
  [ -e $T/plain/$s ] || sudo mv -v $T/appdata/$s $T/plain/$s
done
ls -A $T/plain $T/appdata
```

`mv` onto an existing folder would nest it, so the loop moves a folder only when its target is missing.

## 4. Deploy the encryption scripts

- [ ] `just deploy encryption,backup --limit pi4`. It fails if a listed folder holds the page, Caddy or Tinyauth data. It installs the scripts. The backups now refuse to run until the folders are unlocked.

## 5. Encrypt each folder (in a terminal on pi4)

```bash
ssh -t user@pi4.ferret-ordinal.ts.net
sudo /opt/services/scripts/setup-encrypted-folder.sh /mnt/apps/appdata
sudo /opt/services/scripts/setup-encrypted-folder.sh /mnt/apps/files
sudo /opt/services/scripts/setup-encrypted-folder.sh /mnt/apps/stacks   # the long one: run it in tmux or zellij
```

- [ ] Type the passphrase from the vault each time. Save each master key and cipher settings in your password manager.
- [ ] After a lost connection run the same command again ([what the script checks](../docs/encryption.md#set-up-a-folder)).

## 6. Deploy everything and check

- [ ] `just deploy '' --limit pi4` starts the services Ansible manages. Then start the rest: `xargs -r docker start < ~/running.txt` on pi4. (The setup script leaves the folders mounted, so `just unlock pi4` would only say "Already unlocked.")
- [ ] `just encryption-status pi4`: every folder unlocked, no container waiting.
- [ ] Open Dockge and the media apps, and run `/opt/services/scripts/backup-restic-local.sh`. Then `restic ls latest | grep gocryptfs.conf` prints one line per folder.

## 7. The page and lock

- [ ] On pi4: `docker exec unlock-page python3 app.py check` prints each folder as unlocked, and `systemctl status unlock-page.socket` shows it listening.
- [ ] `just lock pi4`: the containers that use the folders stop, the folders unmount. `just encryption-status pi4` shows them locked and the waiting containers. ntfy, Caddy, Tinyauth and the page keep running.
- [ ] Open `https://unlock.pi4.slashtechno.com`, log in with Tinyauth, type the passphrase and press Unlock. Everything starts again. Press Lock, then Unlock once more.
- [ ] Reboot pi4 and unlock from the page: nothing runs on the encrypted folders before that.

## Rollback

Per folder, in a terminal on pi4 with the containers stopped: `sudo /opt/services/scripts/remove-encrypted-folder.sh <folder>` ([turning it off](../docs/encryption.md#turning-it-off)). Then remove the folders from `encrypted_folders` and deploy.
