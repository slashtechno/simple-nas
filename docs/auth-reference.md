# Login (Tinyauth) reference

Tinyauth is the login in front of the web services: what it does and how a service joins it is in [services.md](./services.md#tinyauth-login). This page is how to use it: users, two-factor codes, sign in with GitHub or Google, OpenID Connect, Tailscale and sessions. Its own settings are `TINYAUTH_*` environment variables ([all of them](https://tinyauth.app/docs/reference/configuration/)); the role takes extra ones in `tinyauth_environment` (host `vars.yml`).

## Users and passwords

`vault_tinyauth_users` in `group_vars/all/vault.yml` gives every host's own Tinyauth the same logins; a host that wants different users sets `vault_tinyauth_users` in its own host vault, which wins. Each host runs its own Tinyauth, so a login on one host does not sign you in on another. To add a user or change a password, edit the vault and `just deploy tinyauth --limit <host>`.

## Two-factor codes (TOTP)

A user with a `totp` key is asked for a six-digit code after the password. The password stays; the code is added to it.

1. Make a secret: `python3 -c "import base64, os; print(base64.b32encode(os.urandom(20)).decode())"`.
2. Add a `totp: "THE32LETTERSECRET"` line to that user in `vault_tinyauth_users` (the list's shape is in `group_vars/all/vault.yml.example`).
3. Deploy, then add the account in an authenticator app by choosing "enter a setup key" and pasting the secret (time-based, 6 digits, 30 seconds are the defaults).

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

- **Always set the whitelist.** The deploy stops if a provider is set without it. It is either one regex for the whole value, wrapped in slashes (`/@example\.com$/`), or a comma-separated list of exact addresses; a value that mixes the two matches no regex and only the exact entries. A login through a public provider is only as restrictive as this list.
- `google` is the same with `GOOGLE` in the names. Another provider (Pocket ID, Authentik, Keycloak) is any other id, plus `_AUTHURL`, `_TOKENURL`, `_USERINFOURL`, `_SCOPES` and `_NAME` in the same pattern ([guide](https://tinyauth.app/docs/guides/other-oauth/)).
- Password logins stay available next to the provider: the role needs `vault_tinyauth_users`.
- Only a provider that sends groups puts them in the app's `Remote-Groups` header; GitHub and Google send none.

## Sign in with Tinyauth (OIDC)

OIDC stands for OpenID Connect, the login standard most apps support. The app sends your browser to Tinyauth to log in, and Tinyauth tells the app who you are; the app never sees your password. Gitea, Immich and pics can do this, so one Tinyauth login opens them, and each keeps its own accounts and permissions.

- Turn it on for an app on the host: `gitea_sso_enabled: true`, `immich_sso_enabled: true` or `pics_sso_enabled: true` in its `vars.yml`. It needs `tinyauth_enabled` and `caddy_enabled`.
- Put the client secret in the vault: `vault_gitea_oidc_secret`, `vault_immich_oidc_secret` or `vault_pics_oidc_secret` (`openssl rand -hex 24`), then `just deploy tinyauth,gitea,immich,pics --limit <host>`.
- The app's own password login stays, so a Tinyauth problem does not lock you out.
- Every user in `vault_tinyauth_users` is offered to every app: Tinyauth cannot restrict a client to some of its users. pics therefore checks the user itself: `pics_oidc_owner` (a user name or email address) is the one account that may open it.
- First login: Immich matches you by email, and Tinyauth makes that address `<user>@<private domain>` from the user name unless the user name is already an address, so give the Immich account that email (user `alice` on `pi4.example.com`: `alice@pi4.example.com`). A Tinyauth user with no matching Immich account gets a new one automatically. Gitea creates no accounts: it shows its link page once, to attach the Tinyauth login to an existing Gitea account, and a login with no account to attach stops there (an admin creates the Gitea account first).
- With `immich_sso_enabled`, Immich reads its settings from a file the deploy writes and refuses to save changes from its settings page. The file carries the OAuth client and the password-login switch, and every other setting is Immich's default.

## Tailscale

Two routes, neither used by the deploy by default and neither tested here:

- **Continue with Tailscale** is built into Tinyauth: `TINYAUTH_TAILSCALE_ENABLED: "true"`, `TINYAUTH_TAILSCALE_APITOKEN` (an API token from the Tailscale admin console, in the vault) and `TINYAUTH_TAILSCALE_TAILNET`. It works out who you are from the device your request comes from, so Tinyauth must see the real client IP: also set `TINYAUTH_AUTH_TRUSTEDPROXIES` to the `services` network's subnet (`docker network inspect services`). Tagged devices are not recognised.
- **[tsidp](https://github.com/tailscale/tsidp)** is a separate small service that makes your tailnet an OpenID Connect provider; Tinyauth then uses it as another provider (the three URLs above, and `TINYAUTH_OAUTH_PROVIDERS_<ID>_CLAIMS_USERNAME: username`). Neither project documents the pair.

## Session length

`TINYAUTH_AUTH_SESSIONEXPIRY` is seconds, default one day, and it slides while you use the site. `TINYAUTH_AUTH_SESSIONMAXLIFETIME` caps the total age (default none). Sessions are stored in `tinyauth_data_dir`, so a redeploy keeps them.
