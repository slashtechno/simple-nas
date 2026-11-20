# Crafty (Minecraft servers)

A bundled plugin ([how plugins work](../../../docs/writing-a-plugin.md)). Needs the `primary` drive role and RAM headroom; switch it on with `crafty_enabled: true` in a host's `vars.yml`.

One container runs every server. All data is under `crafty_data_dir` (`appdata/crafty` on the primary drive: `servers/ backups/ logs/ config/ import/`).

- Panel: `https://<host-ip>:28443` (`crafty_port`, self-signed certificate). The first admin password is in `<crafty_data_dir>/config/default-creds.txt` (Crafty makes it and has no setting for it). Behind Tinyauth it is the second login, so change it in the panel to something short, then delete the file.
- Each server needs a port inside `crafty_mc_ports` (default 25565-25575). Set it when creating the server.
- `crafty_memory_limit` caps all servers combined. On a Raspberry Pi Docker enforces it once the memory cgroup is on ([memory.md](../../../docs/memory.md#memory-limits)). It competes with Immich on a small host: size the two so they leave room for the rest.
- Not behind Cloudflare Tunnel: players join over the LAN, a router port-forward of the game port, or Tailscale. Docker publishes the panel and game ports on all interfaces, so do not forward the panel port.
- The live `servers/` directory is in the daily backup; restic copies worlds while the server runs, so a world written mid-backup can be inconsistent. Crafty's own `backups/` archives are not in it ([backups.md](../../../docs/backups.md#what-is-backed-up-where)); to include them add `- !<crafty_data_dir>/backups` to `restic_local_extra_rules`. `teardown.yml -e remove_data=true` removes the archives too.

To change what it needs, edit `defaults.yml` (settings the repo reads) or `defaults/main.yml` (the role's own: `crafty_mc_ports`, `crafty_bedrock_enabled`, `crafty_memory_limit`).
