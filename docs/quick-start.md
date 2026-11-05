# Quick start: a complete home server

From a fresh clone to one host running **Immich**, **Copyparty**, **Dockge** for your own apps behind a **Tinyauth** login and **Caddy** names, daily **backups**, and **encrypted** data folders, on **three drives**. About an hour, plus the time the drives take to format.

Details for each part are in [services.md](./services.md); this page is the order to do things in.

## You need

- A Debian-family host (Raspberry Pi OS, Debian 12+, Ubuntu) with SSH and your SSH key on it.
- Three drives formatted ext4, and their UUIDs: [Preparing a drive](./storage.md#preparing-a-drive).
- A domain on Cloudflare, plus an API token with **Zone:DNS:Edit** ([why](./caddy-reference.md#web-addresses-and-https)), and the domain's zone ID.
- A Tailscale account, and a password manager (for the encryption passphrase and master key).

## 1. Install and add the host

Follow [First-time setup and Add a host](../ansible/README.md#first-time-setup) (steps 1 to 4) in `ansible/README.md`: install the tools, add the host to `inventory/hosts.yml`, then `just setup home` ("home" is the host's nickname). `just setup` creates the vault password, `host_vars/home/vars.yml` and both vault files, with random values for every secret that can be random, and lists the ones left for you.

## 2. Fill in your values

`group_vars/all/vars.yml` (shared by all hosts; the shape is in `vars.yml.example`):

```yaml
timezone: Europe/London
ssh_authorized_keys: ["ssh-ed25519 AAAA... you@laptop"]
cloudflare_zones: {example.com: your_zone_id}
```

`host_vars/home/vars.yml`:

```yaml
immich_enabled: true
copyparty_enabled: true
dockge_enabled: true
dockge_port: ""                  # Dockge is reachable only through Caddy and the login
caddy_enabled: true
tinyauth_enabled: true
backup_local_enabled: true
dozzle_enabled: true             # container logs, https://logs.home.example.com
scrutiny_enabled: true           # drive health, https://disks.home.example.com (drives that pass SMART)
caddy_private_domains: [home.example.com]   # apps get https://<app>.home.example.com, on your tailnet only

drives:
  - {uuid: "aaaa-...", mount: /mnt/fast,    roles: [fast]}      # databases, configs, stacks
  - {uuid: "bbbb-...", mount: /mnt/primary, fstype: ext4, options: "defaults,nofail", roles: [primary]}   # photos, files
  - {uuid: "cccc-...", mount: /mnt/backup,  fstype: ext4, options: "defaults,nofail", roles: [backup]}    # restic repository

encrypted_folders:               # what each holds: [storage.md](./storage.md#what-lives-where)
  - /mnt/fast/appdata
  - /mnt/fast/stacks
  - /mnt/primary/photos
  - /mnt/primary/files
```

The vault files (`ansible-vault edit --vault-password-file .vault-pass <file>`) need the values `just setup` could not invent:

| File | Entry | Value |
|---|---|---|
| `group_vars/all/vault.yml` | `vault_cloudflared_api_token` | your Cloudflare token |
| | `vault_tinyauth_users` | a login: `name` and `password` |
| `host_vars/home/vault.yml` | `vault_copyparty_user`, `vault_copyparty_pass` | the Copyparty admin account |

## 3. Prepare the host

```bash
just deploy storage,common,tailscale --limit home -K    # -K asks for the sudo password, this once
ssh <user>@<host> sudo tailscale up                     # open the link it prints
```

## 4. Create the encrypted folders (before any service starts)

`photos` and `files` are your personal data. `appdata` (every service's databases and configs) and `stacks` (your Dockge apps' compose files and data) add the rest. With any of them encrypted, the services that use them wait for an unlock after each boot ([encryption.md](./encryption.md#how-it-works)).

```bash
just deploy encryption,backup --limit home
ssh -t <user>@<host>
sudo /opt/services/scripts/init-encrypted-folder.sh /mnt/fast/appdata     # once per folder
sudo /opt/services/scripts/init-encrypted-folder.sh /mnt/fast/stacks     # same passphrase each time
sudo /opt/services/scripts/init-encrypted-folder.sh /mnt/primary/photos  # save each master key in your password manager
sudo /opt/services/scripts/init-encrypted-folder.sh /mnt/primary/files
sudo /opt/services/scripts/unlock.sh
```

The folders are empty, so there is nothing to move in. More: [encryption.md](./encryption.md#set-up-a-folder).

## 5. Deploy everything

```bash
just deploy '' --limit home
```

Then reboot once (`sudo reboot`; the drive guard arms at boot) and unlock: `sudo /opt/services/scripts/unlock.sh`.

## 6. Check it

- `https://dockge.home.example.com`, `https://immich.home.example.com`, `https://copyparty.home.example.com` open after the Tinyauth login (`https://auth.home.example.com`).
- `https://logs.home.example.com` ([Dozzle](./services.md#dozzle-container-logs): every container's log) and `https://disks.home.example.com` ([Scrutiny](./services.md#scrutiny-drive-health): each drive's SMART health; the deploy stops if no drive answers SMART).
- Run a backup by hand (`/opt/services/scripts/backup-restic-local.sh`, [as your user](./backups.md)), then [check the encrypted folders are in it](./encryption.md#dumps-and-backups).
- Practice a restore once: [backups.md](./backups.md).

## After every reboot

Nothing with encrypted data runs, and no backup runs, until you `sudo /opt/services/scripts/unlock.sh`. Set `ntfy_alert_url` to hear about a locked host ([encryption.md](./encryption.md#unlocking)).

## Next

[Offsite backup](./backups.md), [Immich with Tinyauth login](./auth-reference.md#sign-in-with-tinyauth-oidc), [more services](./services.md#services).
