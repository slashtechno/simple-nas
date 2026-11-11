# Unlock page

Not an Ansible-deployed service on purpose: it runs on whatever machine you choose, with a plain compose file. A web page that unlocks the encrypted folders of your hosts ([encryption.md](../docs/encryption.md)). Optional: `unlock.sh` over SSH (`just unlock <host>`) always works. Use the page when you must unlock from a browser you do not control.

You type a password. The page then runs `unlock.sh` on each host over SSH and sends it the gocryptfs passphrase, which only the page can read. The browser never sees the passphrase.

## Set it up

1. Make a key for the page. Put its files in a `secrets` folder next to `compose.yml`:

   ```bash
   mkdir secrets && ssh-keygen -t ed25519 -N '' -C unlock-page -f secrets/ssh_key
   ```

2. Give the public key to each host. Set `unlock_page_public_key` to the contents of `secrets/ssh_key.pub` in the host's `vars.yml`, then run `just deploy encryption --limit <host>`. The host accepts that key to run `unlock.sh` and nothing else ([how](#how-the-key-is-limited)).
3. Record each host's SSH identity, so the page cannot be sent to a fake host: `ssh-keyscan <address> >> secrets/known_hosts`.
4. Save the passphrase: `printf %s '<the gocryptfs passphrase>' > secrets/passphrase`.
5. Make the password hash for the page: `python3 app.py hash`. Put the result in `UNLOCK_PASSWORD_HASH` in `compose.yml`. Write each `$` twice there.
6. Set `UNLOCK_HOSTS` in `compose.yml` to `name=user@address` for each host, comma separated. Start it: `docker compose up -d --build`.
7. Serve it over HTTPS (the password crosses the network). Options: Caddy ([caddy-reference.md](../docs/caddy-reference.md#names-of-your-own)), `tailscale serve`, or Cloudflare.

Test it: `docker compose exec unlock-page python3 app.py check` says for each host whether it is unlocked, locked, or cannot be reached. It sends no passphrase.

## Settings

| Variable | Meaning |
|---|---|
| `UNLOCK_HOSTS` | `name=user@address`, comma separated. Required. |
| `UNLOCK_LOGIN` | `password` (default) or `none`. |
| `UNLOCK_PASSWORD_HASH` | From `python3 app.py hash`. Required when the login is `password`. |
| `UNLOCK_SSH_KEY`, `UNLOCK_KNOWN_HOSTS`, `UNLOCK_PASSPHRASE_FILE` | Paths of the three secret files. Default: `/run/unlock/ssh_key`, `.../known_hosts`, `.../passphrase`. |
| `PORT` | Default 8080. |

## Where to run it

The page must reach port 22 of each host over the tailnet, and it must stay up while the hosts are locked.

- **Another machine on the tailnet.** Plain `ssh`, nothing else needed.
- **The host it unlocks.** It works: Docker, SSH, Caddy and Tailscale run while folders are locked. Keep the page's files, Caddy's data and Tinyauth's data outside every listed folder ([which folders](../docs/encryption.md#which-folders-to-list)). Unlocking restarts only the containers that mount a listed folder, so the page keeps running.
- **A serverless platform** (Vercel and similar) cannot reach port 22 of a tailnet host unless it joins the tailnet, for example with Tailscale's [`tsnet`](https://tailscale.com/kb/1244/tsnet). This page does not do that. Without a way in, it cannot unlock anything.

## Login

- **The page's own password** (the default). It needs no database and works from any browser. One request runs at a time, and a wrong password costs 2 seconds. A password is no protection without HTTPS.
- **Tinyauth.** Set `UNLOCK_LOGIN=none` and put the page behind this repo's Caddy with `{import: tinyauth_forwarder}` ([how](../docs/caddy-reference.md#names-of-your-own)). The page then has no password of its own: anyone Tinyauth lets in can unlock. Tinyauth and Caddy must be running while the hosts are locked.

Never give `UNLOCK_LOGIN=none` to a page that is reachable without a login in front of it. A missing hash does not open the page: the page refuses to start.

## How the key is limited

On the host, the page's key sits in `authorized_keys` as `restrict,command="sudo /opt/services/scripts/unlock.sh" <key>`.

- `command=` replaces whatever the client asks to run. The page cannot start a shell or any other program.
- `restrict` turns off port forwarding, agent forwarding, X11 and the terminal.
- The ansible user has passwordless sudo, so without the forced command the key would be root.

What a thief of the page can do: run `unlock.sh` on your hosts. That restarts the containers that use the folders, and it unlocks a host only if the host is reachable. What it cannot do: log in, read files, or learn the passphrase from the browser. The passphrase is in the page's `secrets` folder: anyone who reads that folder and holds a stolen drive can read the data. Keep the folder to yourself and make the passphrase long and random.

If a host is stolen, take it off the tailnet and stop the page.

## Check that it works every day

A page you have not used for months fails on the day you need it. Run the check from cron, and alert on a non-zero exit:

```bash
docker compose -f /path/to/unlock-page/compose.yml exec -T unlock-page python3 app.py check
```

Exit 0 means every host answered (unlocked, or locked and ready). Exit 1 means a host could not be reached or the key stopped working.
