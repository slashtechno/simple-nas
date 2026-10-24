# Pi 4

The Pi 4 (`pi4`) is an ad-hoc server for experiments. pi5 (`pinas`) runs the NAS, and the NAS is not tied to either board.

- **Rollback:** if pi5 is unstable, troubleshoot pi5. To run the NAS on the Pi 4 instead, follow the runbook ([multi-host.md](./multi-host.md)) with the Pi 4 as the target.
- **One owner per shared resource:** the host that runs the tunnel and the offsite backup keeps `cloudflared_enabled` and `backup_cloud_enabled` true; the other keeps both false.
- **Host settings:** `host_vars/pi4/vars.yml` lists the services and drive UUIDs of the host it deploys. Set both to what the Pi 4 runs. A listed drive that is not attached makes the deploy fail.
- **Desktop plus services:** Ubuntu Desktop works. NetworkManager is the network stack, so the direct link works, and the `common` role masks the sleep targets. Both the USB automount rule and the desktop mount drives: keep `usb_automount_enabled` false there. A desktop uses about 0.5 to 1 GB of RAM.
