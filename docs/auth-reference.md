# Login (Tinyauth) reference

Tinyauth is the login in front of the web services (`tinyauth_enabled`; setup in [services.md](./services.md#tinyauth-login)). Caddy asks it about every request to a protected name; a signed-in browser passes, a browser without a session is redirected to `https://auth.<first private domain>`, and any other client gets a 401. An app that reads a proxy's user header takes the signed-in name from `Remote-User`; Copyparty's browser name does with `copyparty_sso_enabled` ([Copyparty accounts and volumes](./services.md#copyparty-accounts-and-volumes)). Every setting below is a `TINYAUTH_*` environment variable ([all of them](https://tinyauth.app/docs/reference/configuration/)); the role takes extra ones in `tinyauth_environment` (host `vars.yml`), and the deploy is `just deploy tinyauth --limit <host>`.

## Users and passwords

`vault_tinyauth_users` is a list of logins, each with a `name` and a `password`, in plain text because the vault is already encrypted; the deploy hashes the passwords for Tinyauth. Shape: [vault.yml.example](../ansible/group_vars/all/vault.yml.example). Put it in `group_vars/all/vault.yml` and every host with Tinyauth accepts the same logins; put it in a host's `vault.yml` for users of that host only (the host's value wins). Each host runs its own Tinyauth, so a login on one host does not sign you in on another. To change a password, edit the vault and `just deploy tinyauth --limit <host>`.

## Two-factor codes (TOTP)

A user with a `totp` key is asked for a six-digit code after the password. The password stays; the code is added to it.

1. Make a secret: `python3 -c "import base64, os; print(base64.b32encode(os.urandom(20)).decode())"`.
2. Add it to that user in the vault:

   ```yaml
   vault_tinyauth_users:
     - name: you
       password: "..."
       totp: "THE32LETTERSECRET"
   ```
3. `just deploy tinyauth --limit <host>`, then add the account in an authenticator app by choosing "enter a setup key" and pasting the secret (time-based, 6 digits, 30 seconds are the defaults).

- **Lost phone:** there are no recovery codes. The vault is the recovery: delete that user's `totp` line, deploy, and enrol again with a new secret. Keep the vault password somewhere other than the phone.
- Two-factor applies to password logins only. A login through OAuth, LDAP or Tailscale skips it, so restrict who may use those (below).
- A user with two-factor cannot use HTTP basic auth, so a script that sends a password cannot go through Tinyauth for that user.

## Sign in with GitHub, Google or another OpenID Connect provider

Make an OAuth app at the provider with the callback URL `https://auth.<first private domain>/api/oauth/callback/<id>` (`github`, `google`, or the name you choose below). Then, in the host's `vars.yml`, with the secret in a vault:

```yaml
tinyauth_environment:
  TINYAUTH_OAUTH_PROVIDERS_GITHUB_CLIENTID: "the client id"
  TINYAUTH_OAUTH_PROVIDERS_GITHUB_CLIENTSECRET: "{{ vault_tinyauth_github_secret }}"
  TINYAUTH_OAUTH_WHITELIST: "you@example.com"
  TINYAUTH_OAUTH_AUTOREDIRECT: github   # optional: skip the login page and go straight to GitHub
```

- **Always set the whitelist.** It lists the allowed email addresses, each exact or a regex wrapped in slashes (`/@example\.com$/`). A login through a public provider is only as restrictive as this list.
- `google` is the same with `GOOGLE` in the names. Another provider (Pocket ID, Authentik, Keycloak) is any other id, plus `_AUTHURL`, `_TOKENURL`, `_USERINFOURL`, `_SCOPES` and `_NAME` in the same pattern ([guide](https://tinyauth.app/docs/guides/other-oauth/)).
- Password logins stay available next to the provider: the role needs `vault_tinyauth_users`.
- Only a custom provider's groups reach the app as `Remote-Groups`; GitHub and Google send none.

## Tailscale

Two routes, neither used by the deploy by default and neither tested here:

- **Continue with Tailscale** is built into Tinyauth: `TINYAUTH_TAILSCALE_ENABLED: "true"`, `TINYAUTH_TAILSCALE_APITOKEN` (an API token from the Tailscale admin console, in the vault) and `TINYAUTH_TAILSCALE_TAILNET`. It works out who you are from the device your request comes from, so Tinyauth must see the real client IP: also set `TINYAUTH_AUTH_TRUSTEDPROXIES` to the `services` network's subnet (`docker network inspect services`). Tagged devices are not recognised.
- **[tsidp](https://github.com/tailscale/tsidp)** is a separate small service that makes your tailnet an OpenID Connect provider; Tinyauth then uses it as another provider (the three URLs above, and `TINYAUTH_OAUTH_PROVIDERS_<ID>_CLAIMS_USERNAME: username`). Neither project documents the pair.

## Session length

`TINYAUTH_AUTH_SESSIONEXPIRY` is seconds, default one day, and it slides while you use the site. `TINYAUTH_AUTH_SESSIONMAXLIFETIME` caps the total age (default none). Sessions are stored in `tinyauth_data_dir`, so a redeploy keeps them.

## Several hosts

- **Separate logins (what the deploy does):** one Tinyauth per host, each at its own address, so a host's logins and sessions are its own and one host being down never locks out another. Shared users are the group vault entry above.
- **One shared instance:** not built. The session cookie is set for the parent of Tinyauth's own address and there is no setting to change that, so one instance can only protect names under that parent. For two hosts that means an address above both, such as `auth.example.com`, and every protected name under `example.com`. The reasons not to, and the design if it is wanted, are in [research/shared-tinyauth.md](./research/shared-tinyauth.md).
