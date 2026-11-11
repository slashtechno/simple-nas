# Unlock encrypted folders from a web page

Status: not built. Nothing in the repo depends on it. Waiting for the owner's go on the design below.

A page you open in any browser and type an access password into; it runs `unlock.sh` on the host. `unlock.sh` reads the gocryptfs passphrase from stdin and holds all the unlock logic, so the page only checks a password, feeds the passphrase to that command and shows the output.

## Optional, on top of encryption

Encryption works on its own: `encrypted_folders` empty means no encryption, and unlocking by hand over SSH (`just unlock <host>`) is the default. The page is a further optional layer with one switch, off by default: `unlock_access_enabled`, on the host being unlocked. It installs the forced-command SSH key below and nothing else, and fails the deploy when `encrypted_folders` is empty. Ansible does not deploy the page: the repo ships its code and a short doc, and the owner runs it wherever suits (see "Where it runs").

## The page

One small program in this repo (`unlock-page/`), one file, standard library only, in a language the owner can read and change (decide when building). It has no database, session or auth library.

- `GET` serves a form with one field; `POST` does the work.
- **Login:** the field is the page password, compared in constant time with a hash in a setting. A password needs no database and works from a browser you do not control. Passkeys can be added later but are never the only route.
- **Settings** (environment variables): the password hash, the gocryptfs passphrase, the hosts to unlock (name and address) and the SSH key.
- **Passphrase:** held by whatever runs the page, never typed in a browser and never sent to one. Its secrecy is that platform's: keep its members to the owner, use two-factor sign-in, and make the passphrase long, random and used nowhere else. A leaked passphrase plus a stolen drive opens the data.
- **A captured page password** (a keylogger on a browser you do not control) lets someone trigger an unlock, and an unlock helps only if they can also bring a stolen host back onto the tailnet. If a host is stolen, remove it from the tailnet and stop the page. Changing the page password after an untrusted browser is optional hygiene. The forced command below means a leaked password can trigger unlock attempts and nothing else.

## How the forced SSH command works

The page's SSH key is not a login key. On the host, its line in `authorized_keys` carries `restrict,command="sudo /opt/services/scripts/unlock.sh"` (Ansible's `authorized_key` takes `key_options`). Whatever the client asks for, `sshd` runs that one command and ignores the request; `restrict` turns off shell, forwarding and TTY. The ansible user has passwordless sudo, so without the forced command a stolen key is root. The passphrase goes over the SSH connection to the command's stdin.

## Where it runs

The program only needs to reach port 22 of the host over the tailnet, so where it runs is the owner's choice. Pick one when building; the code does not depend on it.

- **A container or process on a machine that is already on the tailnet**: plain `ssh`, no extra network code. Run it with whatever you already use (a compose file, Dockge, a systemd unit) and expose it any way you like. Run it somewhere other than the host being unlocked, or it is locked out with it.
- **A serverless platform** (Vercel, Lambda or similar): the function joins the tailnet as an ephemeral tagged node with Tailscale's `tsnet` (userspace networking, no tun device) and SSHes from there. This adds the tailnet-join code, so it is only worth it if no host can be reached from outside. Docs only, with one worked example; nothing else in the repo names a platform.

## Limits to build in

- **Tailnet identity:** a tagged node, with an ACL that lets the tag reach only port 22 of the hosts. For the serverless route the key is reusable, ephemeral and expires after at most 90 days: rotate it by hand within that time.
- **A daily self-test, so the page works on the day it is needed.** A scheduled job (cron where the page runs, or the platform's scheduler) runs the same command with empty input, never the passphrase: sending it would unlock any host that boots on the tailnet without anyone asking. On an unlocked host it prints "Already unlocked." and exits 0; on a locked host it prints "no passphrase given" and exits 1. Either result proves the whole path works. A connection failure means the key or the route broke, and the job alerts. It also reports a locked host.
- A Tailscale OAuth client (`auth_keys` scope, never expires) can mint a key on each request instead of rotating by hand; use it if rotation becomes a chore.
- Rate-limit guesses: each attempt is slow (an SSH connection plus a password hash), and the page can refuse after a few failures in a row.

## Verify before building

- The plain route: that the program's `ssh` reaches the target over the tailnet from where it runs (from inside a container, if used).
- The serverless route, only if chosen: a `tsnet` node in the platform's function (Tailscale documents it for AWS Lambda), the cold-start join time, a relay when no direct path exists, the runtime's duration limit, and whether its firewall offers rate limits and its scheduler a daily job on the free plan.
- Later, for passkeys: Better Auth's passkey plugin (needs a database table; an older version had an advisory about deleting passkeys, so use a patched one), Auth.js's WebAuthn provider (marked experimental), or SimpleWebAuthn.

## Other ways in

- `just unlock <host>` over SSH covers your own computers.
- `tailscale up --ssh` and any SSH app on a phone; one setting in `roles/tailscale`.
- A page served on the tailnet only (`tailscale serve`) covers your own devices without any public route, but not a computer that cannot join the tailnet.
