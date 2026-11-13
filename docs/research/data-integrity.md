# Research: finding silent file corruption

**Status: research note. Nothing here is built. It is not kept current (checked November 2026).**

A backup copies what is on the drive. This note asks how the owner learns that a file went bad without a read error, and which existing tools do that.

## Summary

- Restic skips a file when its size and times are unchanged. A file that rots in place usually stays out of new snapshots. Older snapshots keep the good copy until they expire.
- Studies found that silent corruption is rare. It is more common on cheap drives. Firmware and controllers cause part of it. No study of USB bridges was found.
- Only a stored checksum shows that a file changed without a write. A checksum can come from the filesystem or from a tool.
- Only btrfs has a packaged scheduler for its checks (`btrfsmaintenance`). The best ext4 tool, cshatag, is not packaged.
- ZFS is not a fit. It is an add-on kernel module. It needs more RAM than a 4 GB host has to spare. Its own community advises against USB drives.

## What the current setup already covers

- **Restic.** It decides what to read from size, modification time, change time and inode ([restic docs](https://restic.readthedocs.io/en/stable/040_backup.html)). `backup --force` reads every file again. Then `restic diff` shows what changed ([forum thread](https://forum.restic.net/t/checking-local-files-integrity-agains-repo/3445/3)). A forced backup stores a corrupt file as the newest version.
- **gocryptfs.** Each block has an authentication tag. A changed block fails to read with an I/O error ([security notes](https://nuetzlich.net/cgit/gocryptfs/tree/SECURITY.md?h=v0.5-rc1)). A block of all zeros and the file size are not protected.
- **Restic through gocryptfs.** Restic reads the unlocked folder, so a damaged block should make a backup report an error. This was not tested.

## Options

| Option | What was verified | Limit |
|---|---|---|
| btrfs and `btrfsmaintenance` | Both are in apt. A systemd timer runs the scrub. One file, `/etc/default/btrfsmaintenance`, sets `BTRFS_SCRUB_PERIOD` ([FreedomBox thread](https://discuss.freedombox.org/t/btrfs-filesystem-maintenance-automation-with-btrfsmaintenance-package/2876)) | The drive needs a new filesystem. On one drive a scrub finds bad files but cannot repair them |
| cshatag | It stores a SHA-256 and the modification time in each file's attributes. It reports `<corrupt>` when only the content changed. Exit code 5 means corruption ([README](https://github.com/rfjakob/cshatag)) | Not in apt. The prebuilt binary is for amd64 only. It has no scheduler. The last release is from 2024 |
| SnapRAID | In apt. It stores hashes and scrubs on schedule ([guide](https://perfectmediaserver.com/02-tech-stack/snapraid/)) | It is built around a parity disk. Whether it runs without one was not checked |
| dm-integrity | `cryptsetup-bin` is in apt. It detects flipped bits under ext4 ([Red Hat](https://www.redhat.com/en/blog/what-bit-rot-and-how-can-i-detect-it-rhel)) | It needs a reformat. It writes data twice by default ([mailing list](https://listman.redhat.com/archives/dm-devel/2017-July/031586.html)). It cannot repair errors |
| ZFS | Kernel 6.12 needs OpenZFS 2.2.7 or newer. The Pi apt repository has `zfs-dkms` 2.4.4. `copies=2` allows a scrub to repair errors on one drive ([TrueNAS forum](https://forums.truenas.com/t/cold-storage-on-single-zfs-disk/13512)) | The module is rebuilt after kernel updates ([failure report](https://dietpi.com/forum/t/problem-module-zfs-not-found-in-directory-lib-modules-6-12-47-rpt-rpi-v8/24062)). Ubuntu's kernel team [recommends 4 GB or more](https://bugs.launchpad.net/bugs/1852119) |

## btrfs facts

- A scrub reads every block and checks its checksum. With the default `single` data profile you restore the file from backup. The `dup` profile keeps two copies on one drive and doubles the space.
- Debian's README calls periodic balancing not recommended for most uses ([README.Debian](https://metadata.ftp-master.debian.org/changelogs/main/b/btrfsmaintenance/btrfsmaintenance_0.5.2-1_README.Debian)). Its trim setting is off, because `fstrim.timer` does that job.
- `btrfs-convert` converts only ext2, ext3 and ext4. Its documentation says a new filesystem and a copy may be better. A balance afterwards ends the rollback option ([docs](https://btrfs.readthedocs.io/en/latest/Convert.html)).
- The manual warns against `btrfs check --repair` without expert advice ([scrub guide](https://knightli.com/en/2026/05/09/btrfs-scrub-check-repair-guide/)).
- Power loss on USB drives gives mixed reports. A btrfs developer says [USB bridge chips differ even within one model](https://lore.kernel.org/all/20200202233446.GT13306@hungrycats.org/).

## Not verified

- How `df` and `btrfs filesystem usage` differ, and how often a drive runs out of space while it looks half empty.
- Whether two btrfs drives with the same UUID cause trouble.
- How btrfs behaves on an SMR drive.
- Whether the `storage` role mounts btrfs. The `fstype` setting exists. It was not tried.
- How ext4 reacts when dm-integrity reports a mismatch.

## What a change touches

The storage docs and role assume ext4: `mkfs.ext4`, `e2fsck`, `reserved_percent` (ext only) and the `fsck -y` in USB automount. A btrfs drive needs a counterpart for each one. Sizing that work needs a read of the role.

## Tests to run before a drive holds NAS data

1. Format the drive btrfs. Run a scrub and the sustained write test from [plans/drive-migration.md](../../plans/drive-migration.md). Go back to ext4 if writes collapse.
2. Damage one block of an encrypted test folder. Run a backup. Check that restic reports an error and stores nothing.
3. If ext4 stays: build cshatag for aarch64, run it on a test folder, and decide how to schedule it.

## Sources

- NetApp study of 1.5 million drives: [FAST 2008](https://static.usenix.org/events/fast08/tech/full_papers/bairavasundaram/bairavasundaram_html/index.html). It found corruption on cheap drives about ten times as often as on enterprise drives, according to a secondary summary.
- CERN data integrity work: [summary](https://storagemojo.com/2007/09/19/cerns-data-corruption-research/). It traced part of the errors to firmware.
