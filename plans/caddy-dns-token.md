# Give Caddy its own vault token

Status: code done and pushed; waits for the owner to add one vault entry. Delete this file when both hosts deploy `caddy`.

Caddy's DNS challenge now reads `vault_caddy_dns_api_token` (`caddy_dns_api_token` in `defaults-cloudflare.yml`). There is no default and no fallback to `vault_cloudflared_api_token`, so the next `caddy` deploy on a host with `caddy_private_domains` stops until the entry exists.

- [ ] In the vault that holds `vault_cloudflared_api_token`: `ansible-vault edit --vault-password-file .vault-pass group_vars/all/vault.yml`. Add `vault_caddy_dns_api_token`. The same value as the other token is fine. A token with only `Zone:DNS:Edit` on the zone of `caddy_private_domains` is the smaller one.
- [ ] `just deploy caddy --limit pi4`, then `--limit pinas`. With the same value Caddy's compose file does not change.
