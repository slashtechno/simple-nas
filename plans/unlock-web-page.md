# Unlock encrypted folders from a web page

Status: not built. Nothing in the repo depends on it. Waiting for the owner's go on the design below.

A page you open in any browser and type the gocryptfs passphrase into; it runs `unlock.sh` on the host. `unlock.sh` reads the passphrase from stdin and holds all the unlock logic, so the page only delivers a passphrase and runs that command.

## Design

- **Page:** one Go function in a Vercel project of its own (it is not Ansible-deployed). `GET` serves a form, `POST` does the work. No session, cookie or auth library.
- **Login:** the form has two fields, the page password and the gocryptfs passphrase, sent in one `POST`. The function compares the password with a hash held in an environment variable (constant-time compare). A password needs no database, and it works from a browser you do not control. Passkeys can be added later but are never the only route.
- **Reach:** the function joins the tailnet as an ephemeral, tagged node with Tailscale's `tsnet` (userspace networking, no tun device), SSHes to the host and runs the unlock command. No port on the host is open to the internet; the only public surface is the page.
- **Passphrase:** held in the function's memory while it runs. After using an untrusted browser, change the gocryptfs passphrase (`gocryptfs -passwd`, [encryption.md](../docs/encryption.md)) and the page password.
- **Guessing:** each attempt is slow (a tailnet join plus scrypt), and a leaked page password lets someone trigger unlock attempts and nothing else, because of the forced command below.

## Limits to build in

- **Tailnet key:** reusable, ephemeral and tagged, with an ACL that lets the tag reach only port 22 of the hosts. It expires after at most 90 days: rotate it by hand within that time.
- **SSH key on the host:** in `authorized_keys` as `restrict,command="sudo /opt/services/scripts/unlock.sh"` (Ansible's `authorized_key` takes `key_options`). The ansible user has passwordless sudo, so without the forced command a stolen key is root.
- **A daily self-test, so the page works on the day it is needed.** A scheduled job runs the same command with empty input. On an unlocked host it prints "Already unlocked." and exits 0; on a locked host it prints "no passphrase given" and exits 1. Either result proves the whole path works. A connection failure means the key or the route broke, and the job alerts. It also reports a locked host.
- A Tailscale OAuth client (`auth_keys` scope, never expires) can mint a key on each request instead of rotating by hand; use it if rotation becomes a chore.

## Verify before building

- A `tsnet` node in a Vercel function (Tailscale documents it for AWS Lambda): how long the join takes on a cold start, and that it connects through a relay when no direct path exists. Vercel's Go runtime is marked Beta; the duration limit on the Hobby plan is documented as 300 s but not confirmed for Go.
- Whether Vercel Firewall rate-limit rules are available on the Hobby plan, and how often a Vercel Cron job may run there.
- Later, for passkeys: Better Auth's passkey plugin (needs a database table; an older version had an advisory about deleting passkeys, so use a patched one), Auth.js's WebAuthn provider (marked experimental), or SimpleWebAuthn.

## Other ways in

- `just unlock <host>` over SSH covers your own computers.
- `tailscale up --ssh` and any SSH app on a phone; one setting in `roles/tailscale`.
- A page served on the tailnet only (`tailscale serve` and a small listener on the host) covers your own devices without Vercel, but not a computer that cannot join the tailnet.
