# Service notes

Setup steps and gotchas for services that need more than `<name>_enabled: true`. Deploy any of them with `just deploy <tag>`. Backups are in [backups.md](./backups.md).

| Service | Role | Section |
|---|---|---|
| Copyparty | `roles/copyparty` | [Accounts and volumes](#copyparty-accounts-and-volumes) |
| pics | `roles/pics`, `roles/github_clone` | [pics](#pics-photo-culling-and-sharing), [Private GitHub repo](#clone-a-private-github-repo) |
| Cloudflare Tunnel | `roles/cloudflared` | [Public hostname](#cloudflare-add-a-public-hostname) |
| Tailscale | `roles/tailscale` | [Funnel](#tailscale-funnel) |
| Garage | `roles/garage` | [Garage](#garage-s3) |
| Crafty | `roles/crafty` | [Crafty](#crafty-minecraft-servers) |
| Homebridge | `roles/homebridge` | [Homebridge](#homebridge) |
| Direct Ethernet link | `roles/network` | [Direct Ethernet link](#direct-ethernet-link) |

## Copyparty accounts and volumes

The config is rendered by `roles/copyparty/templates/copyparty.conf.j2` into the config volume. The admin account is `copyparty_user` / `copyparty_pass`. Collaborators come from `vault_copyparty_collab_users` in the vault.

Apps that talk to Copyparty get a service account. Add an entry to `copyparty_service_accounts` in `vars.yml` (user, password variable, and one or more volumes, each a folder plus permissions) and put its password in the vault. Each volume is mounted at `/<folder>`, stored in `copyparty_files_dir/<folder>`, with the admin as owner. Those folders then disappear for every other account with access to `/`, such as pocketpi's. Leave out `d` unless the app must delete: without it Copyparty also refuses to overwrite, so the app can't destroy anything. `vars.yml.example` has an example.

To change anything else, edit `copyparty.conf.j2` or the variables, then `just deploy copyparty`. The base image version is in `ansible/group_vars/nas/versions.yml`; see "Update service images" in [ansible/README.md](../ansible/README.md).

## Clone a private GitHub repo

This repo is public, so the clone uses a read-only fine-grained token from the vault (`vault_github_read_token`; `vault.yml.example` says how to create it, scoped to the one repo). A role calls `roles/github_clone` with `repo` and `dest`. The token reaches git through its environment, so it never lands in `.git/config` on the NAS. If the token expires, the clone step fails: make a new one and run `ansible-vault edit` on the vault.

## pics: photo culling and sharing

Opt-in (`pics_enabled: true`). The `pics` role clones the private `lab` repo, builds the image on the Pi (several minutes the first time; later runs rebuild only when the repo's commit changed) and runs it on `nas-services`. It talks to Copyparty as the `photos` service account, so set that account up first.

1. In `vars.yml`, copy the `pics_*` entries and the `photos.example.com` entry in `cloudflared_ingress` from `vars.yml.example`. The app has two ports: the owner app (cull UI, everything, password-gated) on `pics_port`, and a guest surface (share pages and portfolio, no owner routes) on `pics_public_port`. Only the owner port is published: `http://<pi>:<pics_port>` on the LAN, `http://<pi-tailscale-ip>:<pics_port>` on the tailnet. The tunnel points at `http://pics:<pics_public_port>`, so its Cloudflare entry needs no `path` rule.
2. In the vault add `vault_pics_password` (12+ characters) and `vault_pics_secret_key` (`openssl rand -base64 48`). Use values without single quotes.
3. `just deploy copyparty,pics,cloudflared`. `copyparty` creates the `photos` account and its two volumes first.

The database is in `pics_data_dir`, covered by the nightly backup. The app also writes its own daily snapshots there. `teardown.yml --tags pics` keeps that data unless `remove_data=true`.

## Cloudflare: add a public hostname

In `vars.yml`:

```yaml
cloudflared_ingress:
  - hostname: newservice.example.com
    service: "http://newservice:8080"
```

Then `just deploy cloudflared`. Each hostname's DNS record is created in the zone from `cf_zones` (domain: zone ID), using the longest matching domain. A hostname on a new domain needs that domain in `cf_zones`, and the API token needs DNS:Edit on that zone. A hostname with no matching domain is skipped with a warning. An optional `path` regex on a rule limits what the hostname forwards; the rest gets the catch-all 404.

## Tailscale Funnel

Set `tailscale_funnel_enabled: true` in `vars.yml` to expose Copyparty at your ts.net hostname, then `just deploy tailscale`.

## Garage (S3)

Set `garage_enabled: true`, fill in `vault_garage_rpc_secret`, `vault_garage_admin_token`, `vault_garage_webui_user` and `vault_garage_webui_pass`, then `just deploy garage,cloudflared`.

On a first deploy (the `meta/` data directory is empty) Ansible adds `--single-node` to the compose command to bootstrap the cluster layout, and leaves it out afterwards. Open `https://garage.example.com`, log in with the web UI credentials, and create buckets and access keys there. Apps connect with endpoint `https://s3.example.com`, region `garage`, and the key pair from the web UI.

## Crafty (Minecraft servers)

Opt-in (`crafty_enabled: true`). One container runs every server. Everything is under `crafty_data_dir` (`servers/ backups/ logs/ config/ import/`), so moving or backing up all worlds is one directory.

- Panel: `https://<pi-ip>:28443` (`crafty_panel_port`, self-signed certificate). The first admin password is in `docker logs crafty` or `<crafty_data_dir>/config/default-creds.txt`. Change it in the panel, then delete that file.
- Each server needs a port inside `crafty_mc_ports` (default 25565-25575); set it when creating the server.
- `crafty_memory_limit` caps all servers combined. On a 4 GB Pi it competes with Immich, so start small.
- Not behind Cloudflare Tunnel (raw TCP and self-signed HTTPS don't fit). Friends join over the LAN, a router port-forward of the game port, or Tailscale. The panel and game ports are published on all interfaces, so don't forward the panel port.
- The live `servers/` directory is in the daily restic backup; Crafty's own `backups/` archives are not (see [backups.md](./backups.md)).

## Homebridge

Runs with `network_mode: host` (HomeKit's mDNS discovery needs it), so it can't join `nas-services` and is left out of `cloudflared_ingress`.

Remote Apple Home access needs a HomeKit hub (Apple TV or HomePod) on your LAN. Tailscale doesn't substitute: HomeKit decides local versus remote by Wi-Fi network identity and multicast mDNS, not IP reachability, so off Wi-Fi the Home app shows the bridge offline even with Tailscale connected. Tailscale does reach Homebridge's admin UI at `http://<pi-tailscale-ip>:8581`, which is a plain HTTP page.

The role only deploys the container; the image creates its own `config.json` and `auth.json` on first start. Log in with `admin`/`admin` and change the password at once. The HomeKit PIN and plugins are configured there and persist across deploys.

## Direct Ethernet link

The Pi's Ethernet port is idle (the Pi normally runs on wifi). Cabled straight to a laptop, it gives about 117 MB/s, against about 4.3 MB/s over Tailscale on wifi (measured). The Pi side is a static `10.10.20.1`. The laptop gets `10.10.20.2` from a `dnsmasq` instance scoped to that port.

1. Set `direct_link_enabled: true` in `host_vars/<host>/vars.yml`, then `just deploy network`.
2. Plug the cable into the Pi and the laptop. The laptop picks up its address automatically.
3. Open `https://10.10.20.1:3923` for Copyparty. Expect a certificate warning: Copyparty serves its own self-signed certificate on the same port as HTTP.

The link can't reach the internet or collide with a VPN:
- `dnsmasq` hands out DHCP only (no DNS, no gateway), and neither end has a gateway, so there is no route off the cable.
- `10.10.20.0/30` has two usable addresses, too small to overlap common VPN or home-router ranges such as `10.8.0.0/24` or `192.168.1.0/24`.
