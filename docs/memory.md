# Memory on a small host

A host can run out of RAM when its services add up to more than it has. Immich's machine learning, Crafty and a build are the largest. Signs: load average far above the core count, SSH that stalls, kills in `journalctl -k | grep -i "out of memory"`. Check `free -m` after a deploy. Terms like zram, cgroup and OOM kill are in the [glossary](./glossary.md#memory).

| Problem | Fix |
|---|---|
| A container uses all the RAM | [Memory limits](#memory-limits) (a Pi needs the memory cgroup on first) |
| Swap is in constant use | [Swap](#swap) (zram), or switch a service off |
| Load spikes after a photo import | [Immich](#immich): lower job concurrency |

## Check

| Command | Shows |
|---|---|
| `free -m` | RAM and swap in use |
| `zramctl` | zram size, data held and its compressed size (`COMPR`) |
| `journalctl -b -1 -k \| grep -E "Out of memory\|Free swap"` | kills in the previous boot, and whether swap was full |
| `docker info 2>&1 \| grep -i "memory limit"` | `No memory limit support` means the kernel cannot enforce limits |
| `docker inspect <container> --format '{{.HostConfig.Memory}}'` | `0` means that container has no limit, whatever its compose file says |

## Memory limits

Raspberry Pi firmware starts the kernel with the memory cgroup off. It adds `cgroup_disable=memory` itself, so that argument never appears in `cmdline.txt`, and the `cgroup_enable=memory` that the deploy adds overrides it. Docker then ignores `mem_limit` (such as `crafty_memory_limit`) and one container can take all the RAM.

- **On by default on a Raspberry Pi.** `pi_enabled` is `auto`: the deploy reads `/proc/device-tree/model`, and on a Pi adds `cgroup_enable=memory cgroup_memory=1` to the single line of `pi_cmdline_file`. The role skips other hosts. `false` turns it off.
- **Apply:**
  1. Deploy, then `sudo reboot`.
  2. On a host with `encrypted_folders`, run `unlock.sh` ([encryption.md](./encryption.md)).
  3. Recreate each container that has a `mem_limit`: `just deploy <service> -e docker_recreate=always`. A container created while the cgroup was off stored no limit, and a reboot does not add it.
- **Check:** `memory` is in `cat /sys/fs/cgroup/cgroup.controllers`, `docker info` does not say `No memory limit support`, and the container's `HostConfig.Memory` is not `0`.
- **Other limits:** `immich_machine_learning_memory_limit` caps Immich's machine-learning container, the usual cause of a load spike after an import.
- **A limit below the app's need kills the app inside its container.** Crafty's servers must fit in `crafty_memory_limit` together.
- **If a Raspberry Pi does not boot** after a change: every change leaves the old file beside it as `cmdline.txt.bak`. Put the root drive in another machine and copy it over `cmdline.txt` in the boot partition.
- **Turn off:** `pi_enabled: false`, deploy, then `just teardown <host> --tags pi`, then reboot. Teardown cannot tell the two arguments from ones you added by hand, and removes them either way.

## Swap

- **Turn on:** `zram_enabled: true`, deploy, then `sudo reboot`. `zram_ram_fraction` sets the size as a fraction of RAM.
- **Turn off:** `zram_enabled: false`, deploy, then `just teardown <host> --tags zram` to remove the drop-in, then `sudo reboot`.
- **Needed when** `free -m` shows the host using swap under normal load. A host with spare RAM can leave it off.
- **Limits of swap:** more swap delays kills but does not help when the working set is larger than RAM. Memory limits and the Immich settings below do.

<details>
<summary>Which tool, cost, writeback</summary>

- **Which tool:** Raspberry Pi OS sizes zram through `rpi-swap` (drop-in in `/etc/rpi/swap.conf.d/`). Other hosts get `systemd-zram-generator` (drop-in in `/etc/systemd/zram-generator.conf.d/`). Teardown removes the drop-in.
- **Cost:** zram keeps compressed pages in RAM, so a full device uses a fraction of its size in memory (the `COMPR` column of `zramctl`). Poorly compressible data costs more.
- **Writeback (Raspberry Pi OS):** `zram_writeback_enabled` (default on) lets `rpi-swap` move idle pages to `/var/swap` on the root drive (up to 2 GiB), at a few writes a day. `false` keeps everything in RAM and `rpi-swap` removes that file. Options: `man swap.conf`.

</details>

## Immich

Immich keeps job settings in its database, so the backup dump saves them.

- **Set them from the repo:** `immich_job_concurrency` maps a queue name to how many jobs run at once, for example `{thumbnailGeneration: 1, smartSearch: 1}`. Every deploy sets those queues and leaves all other Immich settings as saved. Empty (the default) sets nothing. It needs `vault_immich_api_key` (the key the [sign-in setup](./auth-reference.md#sign-in-with-tinyauth-oidc) also uses). With Immich down, a full deploy stops at this step. A queue name Immich does not have stops the deploy and lists the real ones.
- **Or in the UI:** Administration → Settings → Job Settings. The next deploy overwrites a queue named in `immich_job_concurrency`.
- **Heaviest:** smart search and face detection (machine learning). Pause them on Administration → Jobs during a large import and resume afterwards.
- **Transcode policy:** when `immich_transcode_policy` is set, every deploy sets it. `disabled` makes no second copy of any video. `required` copies only videos that will not play as they are. Transcoding runs `ffmpeg` on the CPU, so a policy that converts every video keeps the host busy for hours.
- **An import resumes all paused jobs at once** when it ends. Expect a burst of load then.

<details>
<summary>Transcode policy details</summary>

- `required` copies a video with an unaccepted video or audio codec, or HDR (tone-mapped to SDR). `roles/immich/defaults/main.yml` describes `optimal`, `bitrate` and `all`.
- A policy change frees nothing by itself: run Transcode Videos on All (Administration → Jobs) once, and Immich removes the copies it does not need.
- Under `required`, `immich_accepted_video_codecs` lists the codecs played as they are, so listing `hevc` and `av1` stops copies of phone video. HDR and uncompressed audio still get one.
- `disabled` sends HDR as it is, which browsers other than Safari may show washed out.
- A resolution or bitrate cap makes copies of videos that already play only under `optimal` and `bitrate`.
- The same settings are in the UI at Administration → Settings → Video Transcoding.

</details>
