# Pi 4 after the move to pi5

pi5 (`pinas`) runs the NAS. The Pi 4 (`pi4`) is off the NAS.

- **Role:** an ad-hoc server for experiments. No fixed service list.
- **If pi5 is unstable:** troubleshoot pi5. The fallback is to deploy the NAS settings to the Pi 4 (copy `host_vars/pi5` to `host_vars/pi4`, move the drives, `just deploy '' --limit pi4`).
- **No reason to keep it off:** nothing on the Pi 4 is needed for a rollback. The drives, data and restic repositories are on pi5.
- **Settings to change before it runs services again:** `host_vars/pi4/vars.yml` still lists the NAS services and the drive UUIDs. Replace both. Keep `cloudflared_enabled` and `backup_cloud_enabled` false: one host owns the tunnel and the offsite repository.
- **Desktop plus services:** possible on Ubuntu Desktop. NetworkManager is the network stack, so the direct link works. The `common` role masks the sleep targets. The USB automount rule and the desktop's own automounter both mount drives; leave `usb_automount_enabled` false there. A desktop uses about 0.5 to 1 GB of RAM.
