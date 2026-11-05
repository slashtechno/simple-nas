# Words used in these docs

Each word is defined once, here. The other docs link to this page instead of explaining the word again. Encryption has its own list of terms at the top of [encryption.md](./encryption.md).

## Backups

- **Repository.** The folder (or cloud location) where restic stores all of its backups. One repository holds many snapshots.
- **Snapshot.** One backup run: a record of your files at that moment, which you can browse and restore from. Restic stores each piece of data once, so a new snapshot of mostly unchanged files adds very little.
- **Deduplication and chunks.** Restic cuts files into small chunks by content and stores each different chunk once. That is why a second backup of the same files is small. The *chunker settings* are how it cuts; two repositories only share chunks if they cut the same way, which is why a second repository is created with the first one's settings ([backups.md](./backups.md#offline-copy-on-a-second-drive)).
- **Retention.** The rule for which old snapshots to keep (`restic_local_retention`, for example the last 7 daily ones).
- **Forget and prune.** `forget` removes snapshots that rule no longer keeps, and `prune` then frees the disk space they used. Both are needed to get space back.
- **Snapshot group.** Restic groups snapshots by host and by the list of paths backed up. Changing the path list starts a new group ([backups.md](./backups.md#choosing-what-is-backed-up)).
- **Dump.** A database exporting its own contents into one file while it runs. A copy of a running database's files can catch it half-written and fail to open; a dump always restores. That is why Immich, Gitea and Garage are dumped before every backup.
- **Cron.** Linux's built-in scheduler: a command and a time, and the host runs it by itself. The backups run because cron starts them. If the host is off at 02:00, that run does not happen and is not made up later.

## Drives and Docker

- **UUID.** A random ID written to a drive when it is formatted. Device names like `/dev/sdb1` can change between boots or when drives are plugged in a different order; the UUID does not. The `drives` list and `/etc/fstab` use it, so a drive always mounts at its configured path. A reformatted drive has a new UUID and needs its entry updated.
- **fstab and mount units.** `/etc/fstab` is the file that lists which drives to mount, where and how. systemd turns each line into units (named things it manages, such as `mnt-data.mount` and `mnt-data.automount`). After a change, `daemon-reload` makes systemd rebuild them; the drive guard in [storage.md](./storage.md#how-a-drive-is-mounted) starts working after the next reboot.
- **Bind mount and volume.** Docker can give a container data in two ways. A *volume* is a private store inside Docker's own directory, out of sight of your drives. A *bind mount* shows a folder on the host, such as `/mnt/data/photos`, inside the container. This repo uses bind mounts for all state, so every service's data is a folder on a drive you chose and the backup can see it.
- **Published port.** A container normally listens only on Docker's private network. A published port (`host:container` in a compose `ports:` list) also listens on the host's real address, reachable by anything on your network, and it does not go through Caddy or Tinyauth. That is why a published port skips the login.
- **Docker socket.** The file `/var/run/docker.sock`, through which Docker accepts commands. Whatever can read it can do everything Docker can: start and stop containers and read every container's files. Caddy and Dockge mount it, so only software you trust gets it.
- **`network_mode: host`.** The container shares the host's network address instead of getting its own. Homebridge needs this so HomeKit can discover it. The cost is that it is not on the Docker network, so Caddy names and the Cloudflare tunnel cannot reach it by container name.
- **FUSE and overlay2.** FUSE lets a program, not the kernel, present a folder; gocryptfs uses it to show the decrypted view. overlay2 is how Docker stacks a container's writable layer over its image, and it does not work on a FUSE folder. So Docker's own storage cannot be in an encrypted folder.
- **LMDB.** A key-value database that is one memory-mapped file on disk. Garage keeps its metadata in one.
- **SMART.** Health counters built into drives (errors, reallocated sectors, temperature). Scrutiny reads them over time, which can show a drive failing before it dies. Some USB enclosures do not pass these queries through.

## Names, logins and the web

- **Tailnet and MagicDNS.** Your tailnet is your private Tailscale network: the devices you added and nothing else. MagicDNS gives each device a name that resolves anywhere on it, so `http://pi4:<port>` works from your laptop away from home.
- **Forward auth.** Caddy, the web front door, asks a separate login service (Tinyauth) about each request before passing it on. A service joins by importing `tinyauth_forwarder` in its Caddy labels; one without it has no login at its Caddy name.
- **Redirect (302) and 401.** 302 means "go to this other address", which a browser follows, so you land on the login page. 401 means "not allowed" and stops there, which a script or phone app shows as an error. Browsers get the login page; other clients fail loudly.
- **TLS termination.** TLS is the encryption of https. Terminating it means decrypting it at some point and passing plain http on. Behind a Cloudflare tunnel, Cloudflare does that at its edge, so Caddy receives plain http and has no use for a certificate (ACME is the protocol Caddy uses to get one).
- **OAuth app.** To offer "sign in with GitHub", you register your own login as an application with GitHub. It gives you a *client id* (the app's name) and a *client secret* (its password), and you tell it a *callback URL* it may send the browser back to.
- **OpenID Connect (OIDC).** The same arrangement with Tinyauth as the provider and Gitea, Immich or pics as the apps.
- **Hash and salt.** A hash is a one-way scramble of a password, so a config file can hold something that checks a login without holding the password. A salt is extra random input mixed in so equal passwords give different hashes. This repo uses a fixed salt for some hashes so the file does not change on every deploy.
- **S3, bucket and access key.** S3 is Amazon's storage API, which many tools use; Garage answers the same commands. A bucket is a named container for stored objects. An access key is the id and secret an app signs in with.

## Ansible

- **Handler.** A task that runs only when something changed earlier in the same deploy, such as restarting a service whose config file was just rewritten. A deploy that changes nothing restarts nothing.
- **Terminfo.** A table that tells programs how a given terminal draws text. The host needs Ghostty's entry for Ghostty's SSH sessions to display correctly.
