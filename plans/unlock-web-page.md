# Unlock encrypted folders from a web page

Status: not built. Nothing in the repo depends on it. Waiting for the owner's decisions below.

A small web page (probably on Vercel) that unlocks the encrypted folders from a computer you do not control. `unlock.sh` takes the passphrase on stdin and holds all the unlock logic, so the page only has to deliver a passphrase and run that command.

## Decide first

1. How the page reaches the host without opening it to the internet: Tailscale Funnel, or the Cloudflare tunnel with a login in front.
2. Whether the page's server may see the passphrase, or the browser encrypts it to a public key whose private key stays on the host.
3. Rate limits on guesses.

SSH from an untrusted computer needs a key or password on it, and the page does not. The page still sees the typed passphrase, so change the passphrase with `gocryptfs -passwd` after use ([encryption.md](../docs/encryption.md)).
