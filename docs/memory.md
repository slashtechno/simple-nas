# Memory on a small host

A host can run out of RAM when its services add up to more than it has (Immich's machine learning, Crafty and a build are the largest). Check `free -m` after a deploy. Signs of running out: load average far above the core count, SSH that stalls, and kills in `journalctl -k | grep -i "out of memory"`.

## Check

| Command | Shows |
|---|---|
| `free -m` | RAM and swap in use |
| `zramctl` | zram size, data held and its compressed size (`COMPR`) |
| `journalctl -b -1 -k \| grep -E "Out of memory\|Free swap"` | kills in the previous boot, and whether swap was full |
| `docker info 2>&1 \| grep -i "memory limit"` | `No memory limit support` means the kernel cannot enforce limits |
| `docker inspect <container> --format '{{.HostConfig.Memory}}'` | `0` means that container has no limit, whatever its compose file says |

## Memory limits

Raspberry Pi firmware starts the kernel with the memory cgroup off. Docker then ignores `mem_limit` (such as `crafty_memory_limit`) and one container can take all the RAM.

- **On by default on a Raspberry Pi.** `pi_enabled` is `auto`: the deploy reads `/proc/device-tree/model`, and on a Pi adds `cgroup_enable=memory cgroup_memory=1` to the single line of `pi_cmdline_file`. Other hosts are skipped. `true` stops on a host that is not a Pi; `false` turns it off.
- **Apply:** deploy, `sudo reboot`, then recreate the containers that have a `mem_limit`: `just deploy <service> -e docker_recreate=always`. A container created while the cgroup was off stored no limit, and a reboot keeps it that way. A host with `encrypted_folders` needs `unlock.sh` after the reboot ([encryption.md](./encryption.md)).
- **Check:** `memory` is in `cat /sys/fs/cgroup/cgroup.controllers`, `docker info` no longer says `No memory limit support`, and the container's `HostConfig.Memory` is not `0`.
- **A limit below the app's need kills the app inside its container.** Crafty's servers must fit in `crafty_memory_limit` together.
- **Turn off:** `pi_enabled: false`, deploy, then `just teardown <host> --tags pi` to take the arguments out again. Both apply after a reboot.
- **Backup of the file:** every change leaves the old file beside it as `cmdline.txt.<id>~`. If the Pi does not boot, put the root drive in another machine and copy it over `cmdline.txt` in the boot partition.

## Swap

- **Turn on:** `zram_enabled: true`, deploy, then `sudo reboot`. `zram_ram_fraction` sets the size as a fraction of RAM.
- **Needed when** `free -m` shows the host using swap under normal load; a host with spare RAM can leave it off.
- **Which tool:** Raspberry Pi OS sizes zram through `rpi-swap` (drop-in in `/etc/rpi/swap.conf.d/`); other hosts get `systemd-zram-generator` (drop-in in `/etc/systemd/zram-generator.conf.d/`). Teardown removes the drop-in.
- **Cost:** zram keeps compressed pages in RAM, so a full device uses a fraction of its size in memory (the `COMPR` column of `zramctl`). Poorly compressible data costs more.
- **Writeback (Raspberry Pi OS):** `zram_writeback_enabled` lets `rpi-swap` move idle pages to `/var/swap` on the root drive, first after a delay, then daily. That frees RAM but writes to the root drive; `false` keeps everything in RAM and deletes the file. Options: `man swap.conf`.
- **Limits of swap:** more swap delays kills but does not help when the working set is larger than RAM. Memory limits and the Immich settings below do.

## Immich

Job settings are stored in Immich's database, so the backup dump keeps them.

- **Set them from the repo:** `immich_job_concurrency` maps a queue name to how many jobs run at once, for example `{thumbnailGeneration: 1, smartSearch: 1}`. Every deploy sets those queues and leaves all other Immich settings as saved. Empty (the default) sets nothing. It needs `vault_immich_api_key` (the same key as the [Tinyauth sign-in](./auth-reference.md#sign-in-with-tinyauth-oidc)). A queue name Immich does not have stops the deploy and lists the real ones.
- **Or in the UI:** Administration → Settings → Job Settings. The next deploy overwrites a queue named in `immich_job_concurrency`.
- **Heaviest:** smart search and face detection (machine learning). Pause them on Administration → Jobs during a large import and resume afterwards.
- **Video:** Administration → Settings → Video Transcoding. Transcoding runs `ffmpeg` on the CPU; a policy that converts every video keeps the host busy for hours.
- **An import resumes all paused jobs at once** when it ends. Expect a burst of load then.
