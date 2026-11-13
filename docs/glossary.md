# Words used in these docs

This page defines each word once. The other docs link to it. [encryption.md](./encryption.md) has its own terms in its *How it works* section. The last section covers the Ansible parts you meet while editing the repo.

## Backups

- **Repository.** Where restic keeps all its backups, in a folder or in the cloud.
- **Snapshot.** One backup run: your files at that moment, browsable and restorable. Restic stores each piece of data once, so a snapshot of mostly unchanged files adds little.
- **Deduplication and chunks.** Restic cuts files into chunks by content and stores each different chunk once. The *chunker settings* are how it cuts. Two repositories share chunks only if they cut the same way, so you create a second repository with the first one's settings ([backups.md](./backups.md#offline-copy-on-a-second-drive)).
- **Retention.** Which old snapshots to keep (`restic_local_retention`, for example the last 7 daily ones).
- **Forget and prune.** `forget` drops snapshots that the retention rule does not keep. `prune` then frees their disk space. You need both to get space back.
- **Snapshot group.** Restic groups snapshots by host and by the list of paths. Changing the path list starts a new group ([backups.md](./backups.md#choosing-what-is-backed-up)).
- **Dump.** A database writing its own contents to one file while it runs. Copying a running database's files can catch it half-written. A dump always restores. Immich, Gitea and Garage get a dump before every backup.
- **Cron.** Linux's scheduler. The backups start from cron. If the host is off at 02:00, cron skips that run and does not make it up.

## Drives and Docker

- **UUID.** An ID written when you format a drive. Names like `/dev/sdb1` change with plug order. The UUID does not, so `drives` and `/etc/fstab` use it. A reformatted drive has a new UUID.
- **fstab and mount units.** `/etc/fstab` lists what to mount, where and how. systemd turns each line into units (`mnt-data.mount`, `mnt-data.automount`). See [how a drive is mounted](./storage.md#how-a-drive-is-mounted).
- **Bind mount and volume.** A *volume* is a private store inside Docker's own directory. A *bind mount* shows a host folder (such as `/mnt/data/photos`) inside the container. This repo uses bind mounts for all state, so every service's data is a folder on a drive you chose and the backup sees it.
- **Published port.** A compose `ports:` entry (`host:container`) listens on the host's real address, reachable by anything on your network, and skips Caddy and Tinyauth.
- **Docker socket.** `/var/run/docker.sock`. Whatever can read it can do everything Docker can, including reading every container's files. Caddy, Dockge and Dozzle mount it, so give it only to software you trust.
- **`network_mode: host`.** The container shares the host's network address. Homebridge needs it for HomeKit discovery. The cost is that Caddy names and the Cloudflare tunnel cannot reach it by container name.
- **FUSE and overlay2.** FUSE lets a program present a folder (gocryptfs shows the decrypted view this way). overlay2, Docker's storage driver, does not work on a FUSE folder, so Docker's own storage cannot be in an encrypted folder.
- **LMDB.** A key-value database held in one memory-mapped file. Garage keeps its metadata in one.
- **SMART.** Health counters built into drives. Scrutiny reads them over time, which can show a drive failing before it dies. Some USB enclosures do not pass the queries through.

## Names, logins and the web

- **Tailnet and MagicDNS.** Your tailnet is your private Tailscale network. MagicDNS gives each device a name that resolves anywhere on it, so `http://pi4:<port>` works from your laptop away from home.
- **Forward auth.** Caddy asks the login service (Tinyauth) about each request before passing it on. A service joins by importing `tinyauth_forwarder` in its Caddy labels. One without it has no login at its Caddy name.
- **Redirect (302) and 401.** A browser follows a 302 to the login page. A script or phone app gets a 401 and fails loudly.
- **TLS termination.** TLS is the encryption of https. Terminating it means decrypting there and passing plain http on. Behind a Cloudflare tunnel Cloudflare does it, so Caddy gets plain http and needs no certificate (ACME is how Caddy gets one).
- **OAuth app.** To offer "sign in with GitHub", you register an application with GitHub. It gives you a *client id* (its name) and a *client secret* (its password). You tell it the *callback URL* it may send the browser back to.
- **OpenID Connect (OIDC).** The same arrangement with Tinyauth as the provider and Gitea, Immich or pics as the apps. The *client secret* is a random value only that app and Tinyauth know.
- **IdP header key.** A header whose *name* is a secret (`vault_copyparty_idp_key`), added by Caddy on Copyparty's web address only. Copyparty trusts `Remote-User` only on requests that carry it, so the published port and the tunnel cannot claim to be a user.
- **Hash and salt.** A hash is a one-way scramble of a password, so a config file can check a login without holding the password. A salt is random input so equal passwords hash differently. Some hashes here use a fixed salt, so the file does not change on every deploy.
- **S3, bucket and access key.** S3 is Amazon's storage API, which Garage also answers. A bucket is a named container for objects. An access key is the id and secret an app signs in with.

## Commands

- **`rsync -aHAX <from>/ <to>/`.** Copies a folder and keeps everything about its files. Run it with `sudo`, so it can keep owners. If it stops half way, run the same command again: it copies only what is missing or changed.

  | Part | What it does |
  |---|---|
  | `-a` | Keeps owner, permissions, dates and symbolic links |
  | `-H`, `-A`, `-X` | Also keep hard links, access lists and extended attributes |
  | `/` at the end of `<from>/` | Copies what is inside the folder. Without it, rsync makes a folder called `<from>` inside `<to>`. |
  | `-n` (dry run) | Shows what it would copy and copies nothing. Add `-v` to list the files. |
  | `--progress` | Shows each file as it copies |
  | `--remove-source-files` | Deletes each source file after it copied. Empty folders stay. |

## Memory

- **zram and swap.** Swap is disk used as overflow RAM. zram is swap kept compressed in RAM: fast, no disk wear, but it takes some RAM. Writeback moves idle pages to a file.
- **Memory cgroup and `mem_limit`.** A cgroup caps a group of processes. With the memory cgroup on, Docker enforces `mem_limit`. With it off, Docker ignores the limit.
- **OOM kill.** When RAM and swap run out, the kernel kills a process. `journalctl -k` shows "Out of memory".

## Ansible

You describe the desired state in YAML and a run makes each host match it. Each step checks first and skips itself when it already matches, so running twice is safe and puts a drifted host back. Operating the repo: [ansible/README.md](../ansible/README.md). Which file holds what and which wins: [ansible/README.md](../ansible/README.md#which-files-hold-what).

- **Inventory.** `groups → hosts → connection vars`. One group, `servers`, carries no settings. You set what a host runs in its `host_vars/<host>/vars.yml`. A host key (`pi4`) is a nickname that names that directory. `ansible_host`, `ansible_user` and `ansible_ssh_private_key_file` say how to SSH in.
- **`requirements.yml`.** Installs the collections (bundles of modules) `community.general`, `community.docker`, `ansible.posix` and `artis3n.tailscale`, and the role `geerlingguy.docker`, which installs Docker.
- **Playbook and play.** A playbook is a list of plays. Each runs roles or tasks on a group. `site.yml` is one play over `servers`. Each service is a task that imports its role, and the task's `when` is the service's flag. Service flags default to false, so a service runs only on a host that sets it.

  ```yaml
  - name: Deploy immich
    ansible.builtin.import_role:
      name: immich
    tags: [immich]
    when: immich_enabled | bool
  ```

- **`pre_tasks`.** Run first, tagged `always`. `site.yml` uses them to check the OS, that Docker is not a snap, and that every web service has a port or a name. They also check that every Tinyauth app has Tinyauth, Caddy and its vault secret.
- **`teardown.yml`.** Refuses to run without `--limit`. Its `remove_data: false` is what `-e remove_data=true` overrides. One looped `include_tasks` of `teardown_service.yml` removes each entry of `services` (`-e only=a,b` picks some). With `remove_data=true` it deletes each data folder the service lists, then the service's own folder above them (`appdata/copyparty`) if that is empty. Without `-e confirm_remove_data=<host>` it stops first and prints the folders it would delete and the ones that stay (`stacks`).
- **`import_*` vs `include_*`.** Ansible reads `import_role` and `import_tasks` when the playbook loads, so `--tags` reach inside. `include_*` runs at run time, and tags do not reach inside. The repo uses it only where a role runs mid-task (tailscale, pics).
- **Role directories.**

  | Directory | Holds |
  |---|---|
  | `tasks/main.yml` | The steps |
  | `handlers/main.yml` | Tasks that run only when notified |
  | `templates/*.j2` | Jinja2 files rendered with variables |
  | `files/*` | Static files copied as-is |
  | `defaults/main.yml` | The role's own fallback values (lowest precedence) |
  | `meta/main.yml` | Roles to run first (only `common`: it runs `geerlingguy.docker` before its own tasks) |

  `template` substitutes `{{ variable }}`. `copy` copies the bytes. `copy` on a file containing `{{ }}` does not error, it leaves the text as is, which is why Dockerfiles get their base image through `ARG` and compose `build.args`.
- **Modules.** Every task calls one. The ones this repo uses most: `assert` (fail early with a message), `file`, `template`, `copy`, `stat`, `set_fact`, `command`, `uri` (HTTP APIs, such as Cloudflare's), `docker_compose_v2` (`up`/`down` a compose directory), `cron` (one entry, found by its `name:`, so a re-run updates it and teardown removes it), `apt`, `systemd`. For any other, `ansible-doc <module>`. Dedicated modules check state and change only what is wrong. `command` always runs, so it carries `changed_when` or `failed_when`.
- **Task keywords.** `when` (run conditionally), `loop`, `register` (capture a result), `changed_when` / `failed_when`, `notify` (a changed task triggers a handler once at the end of the play, so an unchanged `docker-compose.yml` leaves the container alone), `delegate_to: localhost` (run on your Mac: the Cloudflare calls), `check_mode: false` (run a read-only task under `--check`), `block` (group tasks under one `when` or `tags`). `ignore_errors` carries a `noqa` comment saying why.
- **Tags.** `--tags immich` or `--tags backup,storage` runs a subset.
- **Jinja.** `{{ ... }}` is Jinja2. `|` passes the value through a filter like a shell pipe. Most of the repo uses `{{ name }}`, `| bool`, `| length`, `| default(x)`, `| list`, `| map(...)`, `| selectattr(...)` and `| quote` (shell-quotes a value). The less common ones:

  | Expression | Means |
  |---|---|
  | `{{ undef(hint='...') }}` | No default: the owner must set it. Reading it unset stops the run and prints the hint. |
  | `x \| mandatory('message')` | Stops the run with that message if `x` is missing. |
  | `a \| combine(b)` | Merges two dictionaries, and `b` wins. |
  | `a \| difference(b)`, `a \| intersect(b)` | Items of `a` not in `b`, and items in both. |
  | `dict \| dict2items` | A dictionary as `key` / `value` pairs, so it can be looped. |
  | `list \| subelements('volumes')` | One pair per item and per entry of its sub-list. |
  | `x \| default(y, true)` | Uses `y` when `x` is undefined **or empty**. Plain `default(y)` covers only undefined. |
  | `names \| map('extract', hostvars)` | Looks each host name up in `hostvars`, the variables of every inventory host. |

  Try one without deploying: `ansible localhost -m debug -a "msg={{ ['a','b'] | difference(['a']) }}"`.
