# Unlock encrypted folders from a web page

Status: not built. Nothing in the repo depends on it. Waiting for the owner's go on the design below.

A page you open on any computer, sign in to, and type the gocryptfs passphrase into; it runs `unlock.sh` on the host. `unlock.sh` reads the passphrase from stdin and holds all the unlock logic, so the page only delivers a passphrase and runs that command.

## Design

- **Page:** a Vercel project in its own repository (it is not Ansible-deployed).
- **Reach:** the function joins the tailnet as an ephemeral, tagged node with Tailscale's `tsnet` (userspace networking, no tun device), SSHes to the host and runs the unlock command. No port on the host is open to the internet; the only public surface is the page's login.
- **Login:** one gate in front of the page, so strangers cannot try passphrases (this also answers rate limits). A passkey alone, or OAuth alone with an allow-list of the owner's account, is simpler for one user than a password plus another factor. The owner chooses.
- **Passphrase:** typed on the page and held in the function's memory while it runs. Change it with `gocryptfs -passwd` after use on a computer you do not trust ([encryption.md](../docs/encryption.md)).

## Limits to build in

- **Tailnet key:** tagged, with an ACL that lets the tag reach only port 22 of the hosts.
- **SSH key on the host:** in `authorized_keys` as `restrict,command="sudo /opt/services/scripts/unlock.sh"` (Ansible's `authorized_key` takes `key_options`). The ansible user has passwordless sudo, so without the forced command a stolen key is root.
- **The page must still work on the day it is needed.** Auth keys expire (at most 90 days). Use a Tailscale OAuth client with the `auth_keys` scope, which does not expire, to mint a key on each request, and test the page now and then.
- **Two languages:** `tsnet` is Go and the usual login libraries are JavaScript. A Go function can sit beside a JavaScript login page in one Vercel project, at the cost of two toolchains.

## Verify before building

- A `tsnet` node in a Vercel function (Tailscale documents it for AWS Lambda): how long the join takes on a cold start, and that it connects through a relay when no direct path exists. Vercel's Go runtime is marked Beta; the duration limit on the Hobby plan is documented as 300 s but not confirmed for Go.
- Passkeys: Better Auth's passkey plugin (needs a database table; an older version had an advisory about deleting passkeys, so use a patched one), Auth.js's WebAuthn provider (marked experimental), or SimpleWebAuthn for full control. OAuth with a single allowed account needs no database with stateless sessions.
- Whether Vercel's own login (Vercel Authentication, free on every plan) can sit in front of a production deployment; Password Protection is Pro and paid per project.

## Other ways in

- `just unlock <host>` over SSH covers your own computers.
- `tailscale up --ssh` and any SSH app on a phone; one setting in `roles/tailscale`.
- A page served on the tailnet only (`tailscale serve` and a small listener on the host) covers your own devices without Vercel, but not a computer that cannot join the tailnet.
