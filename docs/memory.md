# Memory on a small host

A 4 GB host running Immich, Crafty and Gitea together can run out of RAM. Signs: load average far above the core count, SSH that stalls, and kills in `journalctl -k | grep -i "out of memory"`.

## Check

| Command | Shows |
|---|---|
| `free -m` | RAM and swap in use |
| `zramctl` | zram size, data held and its compressed size (`COMPR`) |
| `journalctl -b -1 -k \| grep -E "Out of memory\|Free swap"` | kills in the previous boot, and whether swap was full |
| `docker info 2>&1 \| grep -i "memory limit"` | `No memory limit support` means container limits are off |

## Memory limits

Raspberry Pi firmware starts the kernel with the memory cgroup off. Docker then ignores `mem_limit` (such as `crafty_memory_limit`) and one container can take all the RAM.

- **Turn on:** `pi_enabled: true` in the host's `vars.yml`, `just deploy pi --limit <host>`, then `sudo reboot`. Containers start with their limits after the reboot. A host with `encrypted_folders` needs `unlock.sh` after it ([encryption.md](./encryption.md)).
- **What it does:** adds `cgroup_enable=memory cgroup_memory=1` to the single line of `pi_cmdline_file`. The old file stays beside it as `cmdline.txt.<id>~`.
- **Check:** `memory` is in `cat /sys/fs/cgroup/cgroup.controllers`, and `docker info` no longer says `No memory limit support`.
- **Stops on anything but a Raspberry Pi** with a message naming the flag. Only a Pi needs it: other hosts have the controller on.
- **A limit below the app's need kills the app inside its container.** Crafty's servers must fit in `crafty_memory_limit` together.
- **If the Pi does not boot:** put the root drive in another machine and copy `cmdline.txt.<id>~` over `cmdline.txt` in the boot partition.
- **Turn off:** remove the two arguments by hand. Teardown leaves the file alone.

## Swap

- **Turn on:** `zram_enabled: true`, `just deploy zram --limit <host>`, then `sudo reboot`. `zram_max_mib` caps the size; a host with less RAM gets its RAM size.
- **Which tool:** Raspberry Pi OS sizes zram through `rpi-swap` (drop-in in `/etc/rpi/swap.conf.d/`); other hosts get `systemd-zram-generator` (drop-in in `/etc/systemd/zram-generator.conf.d/`). Teardown removes the drop-in.
- **Cost:** zram keeps compressed pages in RAM, so a full device uses a fraction of its size in memory (the `COMPR` column of `zramctl`). Poorly compressible data costs more.
- **Limits of swap:** more swap delays kills but does not help when the working set is larger than RAM. Memory limits and the Immich settings below do.
- **Writeback to the root drive:** `rpi-swap` also moves idle zram pages to `/var/swap`, first after a delay, then daily. To stop those writes (a microSD root drive), put `[Main]` and `Mechanism=zram` in a file in `/etc/rpi/swap.conf.d/` and reboot; the file is deleted. Options: `man swap.conf`.

## Immich

Job settings are stored in Immich's database, so the backup dump keeps them, and the deploy never overwrites them.

- **Concurrency:** Administration → Jobs. Lower thumbnail, metadata, smart search, face detection and video conversion to 1 or 2 on a small host.
- **Heaviest:** smart search and face detection (machine learning). Pause them during a large import and resume afterwards.
- **Video:** Administration → Settings → Video Transcoding. Transcoding runs `ffmpeg` on the CPU; a policy that converts every video keeps the host busy for hours.
- **An import resumes all paused jobs at once** when it ends. Expect a burst of load then.
