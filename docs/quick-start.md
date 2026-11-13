# Quick start: a complete home server

From a fresh clone to one host running **Immich**, **Copyparty** and **Dockge** for your own apps, behind a **Tinyauth** login. It has **Caddy** names, daily **backups** and **encrypted** data folders. Data sits on **three drives**: `fast` for app data, `primary` for your files and `backup` for backups. About an hour, plus the time the drives take to format.

Each step links to the doc that explains it. You do not need every part. Skip step 4 and leave out `encrypted_folders` for no encryption, and drop any flag in step 2 you do not want ([pick what you use](../ansible/README.md#pick-what-you-use)).

## You need

- A Debian-family host (Raspberry Pi OS, Debian 12+, Ubuntu) with SSH and your SSH key on it.
- Three drives formatted ext4, and their UUIDs: [Preparing a drive](./storage.md#preparing-a-drive).
- A domain on Cloudflare, an API token with **Zone:DNS:Edit** ([why](./caddy-reference.md#web-addresses-and-https)) and the domain's zone ID.
- A Tailscale account, and a password manager (for the encryption passphrase and master keys).

## 1. Install and add the host

Install the tools ([First-time setup](../ansible/README.md#first-time-setup)), then follow steps 1 to 3 of [Add a host](../ansible/README.md#add-a-host): check the host, add it to `inventory/hosts.yml`, then `just setup home`. "home" is the host's nickname. Stop before its step 4: the first deploy comes in step 3 below.

## 2. Fill in your values

- `group_vars/all/vars.yml`: your timezone, SSH key and Cloudflare zone ID (`vars.yml.example` shows the shape).
- `host_vars/home/vars.yml`:

  ```yaml
  immich_enabled: true
  copyparty_enabled: true
  dockge_enabled: true
  dockge_port: ""                  # Dockge is reachable only through Caddy and the login
  caddy_enabled: true
  tinyauth_enabled: true
  backup_local_enabled: true
  dozzle_enabled: true
  scrutiny_enabled: true           # needs drives that answer SMART
  caddy_private_domains: [home.example.com]
  ```

  plus `drives` (one role each for `fast`, `primary` and `backup`: [the three-drive example](./storage.md#examples)) and `encrypted_folders` (`appdata`, `stacks` and `shared`: [which folders](./encryption.md#which-folders-to-list)).
- The vault (`just edit vault`): the secrets `just setup` listed ([which file holds what](../ansible/README.md#vault-secrets)). For Copyparty, add your own login to `vault_copyparty_accounts` with `admin: true` (`vault.yml.example` shows the shape).

## 3. Prepare the host

```bash
just deploy storage,common,tailscale --limit home -K    # -K asks for the host's sudo password
ssh <user>@<host> sudo tailscale up                     # open the link it prints
```

`just deploy` takes the tags first. See [Commands](../ansible/README.md#commands) for the rest.

## 4. Create the encrypted folders (before any service starts)

```bash
just deploy encryption --limit home
```

Then [set up each encrypted folder](./encryption.md#set-up-a-folder) and unlock. The folders are empty, so there is nothing to move in. The script stops on a folder that does not exist, so create the ones the storage deploy did not make, on your own mounts. For example: `sudo mkdir -p /mnt/fast/stacks /mnt/primary/shared`.

## 5. Deploy everything

```bash
just deploy '' --limit home
```

This also deploys the backup, after Immich: the backup refuses to deploy until Immich's dump script is installed. Reboot once (`sudo reboot`) and [unlock](./encryption.md#unlocking).

## 6. Check it

- `https://dockge.home.example.com`, `https://immich.home.example.com` and `https://copyparty.home.example.com` open after the Tinyauth login, from a device on your tailnet (these names resolve only there). In Copyparty, sign in with your admin login: `/files` holds your files ([folders and logins](./services.md#copyparty-folders-and-logins)). [Dozzle](./services.md#dozzle-container-logs) and [Scrutiny](./services.md#scrutiny-drive-health) do too.
- Dockge asks you to create its own account on the first visit. Create it, then run `just deploy dockge --limit home` ([why](./services.md#ad-hoc-app-platform)).
- Run a backup by hand ([backups.md](./backups.md)), then [check the encrypted folders are in it](./encryption.md#dumps-and-backups).
- Practice a restore once: [backups.md](./backups.md).

## Next

[Offsite backup](./backups.md), [Immich with Tinyauth login](./auth-reference.md#sign-in-with-tinyauth-oidc), [more services](./services.md#services).
