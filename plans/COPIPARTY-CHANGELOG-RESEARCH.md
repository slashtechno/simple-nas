# Research: copyparty changelog deep-dive for this NAS (Pi 5 4GB, Docker, Cloudflare Tunnel + Tailscale)

> Produced by a research subagent (2026-10-04) against a local depth-1 clone of `9001/copyparty`
> at HEAD (`docs/changelog.md` read end-to-end, v1.20.23 → 2020; plus `README.md`, `scripts/docker/README.md`,
> `scripts/docker/make.sh`, `copyparty/__main__.py`, `copyparty/__version__.py`).
> Limitation discovered mid-run: no web tools were available to the subagent, so online state
> (e.g. Docker Hub tags) was not verified live; tag naming was verified from `scripts/docker/make.sh`.

## Summary
Pin **v1.20.23** (latest tagged release, 2026-09-06; repo HEAD is unreleased `1.20.24`).
RAW thumbnails are built in since v1.19.4 via rawpy-or-libraw — no config needed beyond having
rawpy or libraw installed (our Dockerfile already does). The per-volume `daw` repetition can be
deleted (`daw` is also a global option), and the thumbnail/index/transcode cache can be moved
wholesale to an SSD with one global flag (`--hist`, plus `--dbpath` to split DB from thumbs).

## 0. What to pin TODAY
- Latest tagged release in the changelog: **`v1.20.23`** — `# 2026-0906-2249 v1.20.23 "rcm once again"`
  (hotfix release; "this release is a hotfix for that; see v1.20.22 for all the other new stuff"). `docs/changelog.md` line 4.
- Repo HEAD version constant: `copyparty/__version__.py` → `VERSION = (1, 20, 24)`, `BUILD_DT = (2026, 9, 19)` — v1.20.24 exists only as unreleased HEAD; no v1.20.24 changelog entry.
- Docker: **`copyparty/ac:1.20.23`** / **`ghcr.io/9001/copyparty-ac:1.20.23`** — tags are pushed un-prefixed
  (`:$ver` where `getver()` yields `1.20.23`, plus `:beta` and `:latest`) per `scripts/docker/make.sh`.
  Anything ≥ v1.20.19 is required for security anyway (FTP vuln fix); 1.20.23 satisfies that.

## 1. RAW image support — since v1.19.4, formats, config

**Claim:** Camera-RAW thumbnails are supported since **v1.19.4 (2025-08-17, "#567")**, via rawpy
(preferred) or libraw's `dcraw_emu` (fallback); .ARW remained rawpy-only (v1.20.7 note), and since
**v1.20.16** the official docker images use libraw directly.

Direct changelog quotes:
- v1.19.4 (2025-0817): *"#567 .raw image thumbnails (thx @ar-nelson!) 0177a9b4 — available in docker-images `iv` and `dj`"*
- v1.20.7 (2026-0214): *"thumbnails: use libvips as fallback for rawpy 27ae2e1e — libvips doesn't support .arw files (sony) yet, so still need rawpy"*
- v1.20.16 (2026-0526): *"docker: rawpy is no longer bundled; now using libraw directly 348b4bb5 — creating thumbnails of .raw photos is now MUCH slower but quality is also much better"*

**From actual `--help` source (`copyparty/__main__.py`, `add_thumbnail`)** — the authoritative format list:
```
--th-r-raw  (default) "3fr,arw,cr2,cr3,crw,dcr,dng,erf,k25,kdc,mdc,mef,mos,mrw,nef,nrw,orf,pef,raf,raw,rw2,sr2,srf,srw,x3f"
  "image formats to decode using rawpy (if available) or libraw's dcraw_emu"
--th-dec (default) "raw,pil,ff,vips"  # "image decoders, in order of preference" — raw first
```
So: **.CR3 ✓ .CR2 ✓ .NEF ✓ .ARW ✓ .DNG ✓ .RAF ✓** (+ 3fr/crw/erf/k25/mef/mrw/nrw/orf/pef/rw2/sr2/srf/srw/x3f).
Other thumbnail backends (Pillow/pyvips/ffmpeg) handle jpg/png/heif/avif/jxl etc.
README "optional dependencies": *"**RAW photos:** either `libraw dcraw_emu` or `rawpy`, plus either `pyvips` or `Pillow`"*.

**Config needed:** none — automatic as soon as `rawpy` or `libraw/dcraw_emu` is installed.
Our Dockerfile already installs libraw-dev and compiles rawpy. Official images (iv/dj) bundle
libraw since v1.20.16; keeping our rawpy build gives *much faster* RAW thumbs than the dcraw_emu
fallback (per the v1.20.16 quote). Chickenbits if you want to disable: `PRTY_NO_DCRAW`, `PRTY_NO_RAWPY`.

**EXIF indexing for photos:** the `e2ts` metadata indexer targets audio/video tags (+ codec/resolution);
the changelog shows **no built-in EXIF tag indexing of photos**. For EXIF/geodata there is the
`geotag.py` mtp plugin added in v1.19.21 (2025-12-02): *"new mtag plugin, geotag.py: read image geotags with exiftool"*.

## 2. Thumbnail / cache location — exact flags

**Claim:** Everything copyparty caches (per-volume `up2k.db` + WAL/snapshot, thumbnails incl.
video/audio spectrograms, on-the-fly audio transcodes, folder thumbnails) lives in a `.hist/`
folder inside each volume by default; the `--hist` global option (also a volflag) relocates it,
and `--dbpath` moves *only* the database.

Evidence:
- `copyparty/__main__.py`: `--hist ... "where to store volume data (db, thumbs); default is a folder named \".hist\" inside each volume (volflag=hist)"` and `--dbpath ... "override where the volume databases are to be placed; default is the same as --hist (volflag=dbpath)"`.
- README "database location": *"putting the hist-folders on an SSD is strongly recommended for performance"*; combining is documented: "`--hist` is applied to thumbnails, `--dbpath` to the db" (v1.16.19, 2025-04-08, #149 intro'd `--dbpath`).
- README "database location" example:
  ```yaml
  [global]
    hist: ~/.cache/copyparty  # put db/thumbs/etc. here by default
  [/pics]
    flags:
      hist: /ssd/cache/   # per-volume override possible
  ```
- Docker tip (`scripts/docker/README.md`): *"copyparty will generally create a `.hist` folder at the top of each volume... Add the line `hist: /cfg/hists/` inside the `[global]` section... to store these inside the config folder instead."*
- v0.11.12 (2021): "`--hist` stores the per-volume databases and thumbnails all in one place, instead of the `.hist` subfolders in each volume".

**What's cached & growth:** thumbnails generated on demand, cached for **`--th-maxage`**
(default 604800 s = 1 week), cleaned every **`--th-clean`** (default 43200 s = 12 h); audio
transcodes expire per `--ac-maxage` (default 86400 s = 1 day). README size figures:
*each regular thumbnail ≈ 16 KiB, each 3x-size thumb ≈ 96 KiB, each opus/mp3 transcode ≈ 6 MiB*.
On-demand cache holds only browsed/played files, then expires. Markdown edit-history stays in a
local `.hist` subfolder next to the file by default (`--md-hist s`; `v` = volume histpath, `n` = off).

**For us:** add `hist: /ssd/cpp-hist/` in `[global]` (mount the SSD into the container), optionally
keep DBs local via `dbpath`. One-time cost: moving `hist` to an empty dir means a fresh DB →
`e2dsa` rescan on next boot; old thumbnails regenerate lazily (or migrate the folders manually first).

## 3. Config simplifications; `daw` inheritance; deprecated flags

**`daw` repetition can be deleted.** Two facts:
- The template author's belief is **correct**: there is **no volflag inheritance** between volumes —
  nothing in the 9040-line changelog adds it; each volume is independent.
- But **`daw` is also a global option**: `copyparty/__main__.py` `add_webdav`: `--daw "enable full
  write support, even if client may not be webdav... WARNING: This has side-effects -- PUT-operations
  will now OVERWRITE existing files... You might want to instead set this as a volflag where needed."`
  And `--help-flags` states: *"if global config defines a volflag for all volumes, you can unset it
  for a specific volume with -flag"*. README (webdav section): *"some webdav clients will also require
  the `daw` volflag or global-option"*.
- → Put `daw` once in `[global]`, delete all the `flags: daw` blocks; our `-e2d` negation in
  `/drives` volumes is exactly the documented negation pattern (v1.6.14: *"unset a volflag (override
  a global option) by negating it (setting volflag -flagname)"*). Alternatives to scope the
  overwrite side-effect: `dav-port` (v1.20.9: *"webdav: dav-port can be used as an alternative to daw"*),
  `--dav-ua1`/`--ua-nodav`, or `--no-dav` per volume.

**Flag-by-flag status of the config (none deprecated — verified in current argparse source + changelog):**
- `e2dsa`, `e2ts` — current, still the recommended pair (README file-indexing example says "these are recommended").
- `xff-src: lan,100.64.0.0/10` — current. v1.16.2 fixed mixing `lan` with CIDRs; v1.11.0 added CIDR support. docs/xff.md: *"if you are behind cloudflare, it is recommended to also set `--xff-hdr=cf-connecting-ip`"* — we do.
- `xff-hdr: cf-connecting-ip` — current (README "permanent cloudflare tunnel" shows exactly `[global] xff-hdr: cf-connecting-ip`); keep header names lowercase (warned since v1.20.7 — ours already is).
- `rproxy: 1` — current; **mandatory since v1.19.0** (2025-07-30): *"when a reverse-proxy is detected, force explicit configuration of --rproxy to obtain correct client IP"*. `1 = origin (first x-fwd, unsafe)` — correct choice behind `cf-connecting-ip` (exactly one IP in the header).
- `shr: /shares` — current (`--shr-who`/`shr_who` volflag since v1.19.8).
- `ui-filesz: 5c` — current (valid values `0,1,2,2c,...,7,7c,fuzzy`).
- `sftp: 3922` + `sftp-pw` — current. SFTP server exists since **v1.20.0** (2026-01-02); `--sftp-pw "allow password-authentication with sftp (not just ssh-keys)"`. Consider `--sftp-key` (v1.20.x) instead of passwords.
- Actually-deprecated args in current `__main__.py` (none of which we use): `--salt`→`--warksalt`, `--hdr-au-usr`→`--idp-h-usr`, `--idp-h-sep`→`--idp-gsep`, `--th-no-crop`→`--th-crop=n`, `--never-symlink`→`--hardlink-only`.

**Blocks we can delete:** all per-volume `daw` groups. Nothing else in the config list is stale.

## 4. Docker deployment — published, versioned, ARM64 ✓

- Versioned published images since **v1.9.16 (2023-11-04)**: *"#58 versioned docker images! no longer just latest"*. Editions (`scripts/docker/README.md`): **`min` (57 MiB) / `im` (70) / `ac` (163, ffmpeg+transcoding+sftp; "recommended") / `iv` (211, + vips) / `dj` (309, + bpm/keyfinder)**; GHCR mirror: replace `copyparty/ac` with `ghcr.io/9001/copyparty-ac`.
- **ARM64:** `AArch64 v8` can run all five editions; since v1.20.16 `iv` is x86/i386/aarch64 only. v1.20.17 added image LABELs for version/creationtime.
- **Relevance:** our Dockerfile is `FROM copyparty/ac` (implicit floating `:latest`!) plus hand-rolled
  vips/libraw/rawpy/heif/avif — i.e. we re-create `iv`+extras on every deploy. Cleaner:
  1. **Pin + slim:** `FROM copyparty/iv:1.20.23` — ffmpeg, vips, RAW (libraw), sftp already included;
     keep only the legal-codec extras the official images intentionally dropped (v1.20.8, 2026-0214:
     *"due to legal reasons, the docker-images ... are now unable to create thumbnails of HEVC/h265
     videos and heif/heic images ... this primarily means photos/videos taken with iphones"*) →
     keep `pillow-heif` / `pillow-avif-plugin` (+ libheif).
  2. **No build:** `image: copyparty/iv:1.20.23` — but then HEIC/AVIF/HEVC thumbs are lost
     (bad for an iPhone-photo NAS).

## 5. Pi-relevant resource options (RAM/CPU/indexing)

- Thumbnailer RAM cap: **`--th-ram-max`** (v1.9.29; default = 60% of RAM, clamped 0.3–6 GiB → ≈ 2.4 GiB on 4 GB). `th-ram-max: 1` is a reasonable Pi 5 value.
- v1.16.0: conservative defaults below 1 GiB RAM; 4 GB is comfortably fine.
- jxl/RAM: libvips-jxl default-enabled only on alpine (musl+mallocng) — i.e., fine in docker; v1.20.7: *"just don't enable mimalloc"*. mimalloc (optional in images) = 2x speed, **2x RAM** — skip it.
- v1.20.19: *"the libvips thumbnailer was demoted to last-fallback due to frequently using excessive amounts of ram"*; default `--th-dec raw,pil,ff,vips` already puts vips last.
- RAW thumb speed: libraw-only path (v1.20.16) is *"MUCH slower but quality much better"* — keeping our rawpy compile helps a lot on Pi.
- Listing speed on big photo folders: `--no-dirsz` (~30% faster listings, volflag `nodirsz`); `--no-hash '<pattern>'` skips content-hashing of huge read-only archives during `e2dsa`.
- Indexing: **`fika`** (v1.20.7): *"now possible to upload/delete files while the filesystem-indexer is still busy ... default is upload+copy+delete"* — removes the old indexer-blocks-uploads stall.
- Threads: `--th-mt` (default = all cores; Pi 5 = 4), `--hash-mt`, `--mtag-mt`; `PRTY_NO_MP` to disable multiprocessing in a pinch.
- ffmpeg sandbox: bwrap off by default since v1.20.18; images set `use-bwrap: n` — nothing to do.
- Safety net: version-checker (v1.20.11): `[global] vc-url: https://api.copyparty.eu/advisories`.

## 6. Other major recent features relevant to this NAS (2024-09 → now)

- **Cloudflare upload limit gone:** v1.15.8 (2024-10-16) *"subchunks; avoid the Cloudflare filesize limit entirely"*; default `u2sz 64,96` is tuned for CF's 100 MiB — no config needed.
- **Shares UX:** creation UI v1.14.1; uploads-into-shares (write-only drop-off URLs) v1.15.10; `--shr-who` v1.19.8; get-only shares by read-users v1.20.16; `/?shares` lists v1.19.20; security fixes v1.19.8 (CVE-2025-58753), v1.20.12, v1.20.19, v1.20.21. Likely replaces manual link juggling for `/collab`.
- **SFTP server:** v1.20.0 — already in use.
- **Deduplication:** default-disabled since v1.15.0 (2024-09-08); `--reflink` CoW dedup v1.18.6; `nodupe` volflags; `--redup`. ⚠️ ext4 → **no reflink** (btrfs/xfs/zfs only); if enabled use `--dedup` (symlink) or `--hardlink-only` + `--safe-dedup 1`.
- **SSO/IdP:** full IdP support v1.11.0 (Authelia/authentik examples); **Tailscale auto-login** v1.19.4 (*"#504 automatic login through tailscale auth"*) + README generic-header-auth (`idp-hm-usr`) — directly applicable to the Tailscale leg.
- **Audio player:** m3u/m3u8 playlists v1.17.0; OPDS books v1.19.14; skip-silence v1.20.7; mka playback v1.20.16.
- **Text/markdown:** xattrs indexed+searchable v1.20.2; search by wark v1.19.15; config `${VAR}` expansion v1.20.14. **No paperless-style full-text/OCR search exists.**
- **Office/WOPI:** edit via Collabora (WOPI) v1.20.19; onlyoffice-probable v1.20.20; office-doc thumbnailing plugin v1.20.22.
- **Photo pipeline:** thumbnail pregeneration `--th-pregen` v1.20.13; `.hidden` filter v1.20.13; cbz reader v1.19.17; epub thumbs v1.19.4; **`phonecam-sorter.py` hook v1.20.22** ("automate organizing of pics/vids synced from phone to nas"); `reloc-by-wark` hooks v1.20.14.

## Recommended changes for this setup

1. **Pin v1.20.23.**
   ```dockerfile
   FROM copyparty/iv:1.20.23      # was: FROM copyparty/ac  (floating :latest!)
   # iv already includes: ffmpeg, vips, libraw (RAW thumbs), sftp
   # keep only the legal-codec extras the official images dropped in v1.20.8:
   RUN apk add --no-cache libheif-dev && \
       python3 -m pip install --break-system-packages --no-cache-dir pillow-heif pillow-avif-plugin
   # keep rawpy-from-source only if RAW thumbnail speed matters (v1.20.16: libraw path is MUCH slower)
   ```
2. **Dedup the config:** add `daw` under `[global]`; delete every per-volume `flags: daw` block
   (keep `/drives` `-e2d` as-is; negation is a documented feature).
3. **Cache on SSD:** `hist: /ssd/cpp-hist/` in `[global]` + mount the fast drive into compose
   (`- /mnt/t7/cpp-hist:/ssd/cpp-hist`). Defaults: thumbs expire after 1 week, cleaned every 12 h,
   transcodes after 24 h. One-time: fresh `e2dsa` reindex on first boot after moving (db starts empty);
   optionally `--dbpath` (v1.16.19+) to keep DBs on the data drive and only thumbs on SSD.
4. **Pi 5 4GB tuning (optional):** `th-ram-max: 1`; avoid mimalloc; `no-dirsz` on big photo volumes;
   `fika` default already unblocks uploads during indexing.
5. **Consider adopting:** dedup (`--dedup --safe-dedup 1`, symlink-type on ext4) for near-duplicate uploads;
   Tailscale header auth (`idp-hm-usr`) for passwordless accounts on the tailnet leg; share-UX for the
   collab folder; `phonecam-sorter.py` hook if Immich isn't absorbing phone dumps; version-checker `vc-url`.

## Contradictions
- **`ac` vs `iv`:** `scripts/docker/README.md` says *"`ac` is recommended since the additional features
  available in `iv` and `dj` are rarely useful"* — but RAW thumbnails were bundled **only** into `iv`/`dj`
  (v1.19.4), and this setup is photo-heavy. For this NAS, `iv` is the right edition.

## Missing evidence
- No **built-in EXIF/photo-tag indexing** for images: `e2ts` tags are audio/video-oriented; photo-EXIF
  search requires an `mtp` plugin (`bin/mtag/geotag.py` + exiftool, v1.19.21).
- **No paperless-style full-text/OCR search** anywhere in changelog or README.
- Docker Hub manifest state for tag `1.20.23` per-arch could not be checked online from the session;
  tag logic verified in `scripts/docker/make.sh` and arch matrix in `scripts/docker/README.md`.
- When the `--daw` global option first appeared is not stated in the changelog (exists in current source).
- If the currently-deployed build predates v1.19.4, upgrading triggers a **one-way `up2k.db` format
  upgrade** at v1.19.4 (automatic `.bak` created; downgrade instructions in that release's notes).

## Sources
`docs/changelog.md` (full read v1.20.23 → 2020); `README.md` (full read); `scripts/docker/README.md` + `scripts/docker/make.sh`;
`copyparty/__main__.py` (full read — argparse/volflag definitions; `--th-r-raw` format list; deprecated-args list);
`copyparty/__version__.py` (HEAD version). Online sources unreachable from the subagent session (no web tools);
memory-based claims excluded per no-speculation rule.