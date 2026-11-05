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

- **Always set the whitelist.** The deploy stops if a provider is set without it. A login through a public provider is only as restrictive as this list.
  - **A regex** for the whole value, wrapped in slashes: `/@example\.com$/`.
  - **Or a comma-separated list** of exact addresses.
  - A value that mixes the two matches no regex and only the exact entries.
- `google` is the same with `GOOGLE` in the names. Another provider (Pocket ID, Authentik, Keycloak) is any other id, plus `_AUTHURL`, `_TOKENURL`, `_USERINFOURL`, `_SCOPES` and `_NAME` in the same pattern ([guide](https://tinyauth.app/docs/guides/other-oauth/)).
- Password logins stay available next to the provider: the role needs `vault_tinyauth_users`.
- Only a provider that sends groups puts them in the app's `Remote-Groups` header; GitHub and Google send none.

## Sign in with Tinyauth (OIDC)

OIDC stands for OpenID Connect, the login standard most apps support. The app sends your browser to Tinyauth to log in, and Tinyauth tells the app who you are; the app never sees your password. Gitea, Immich and pics can do this, so one Tinyauth login opens them, and each keeps its own accounts and permissions.

Setup:

1. Turn it on for an app on the host: `gitea_sso_enabled: true`, `immich_sso_enabled: true` or `pics_sso_enabled: true` in its `vars.yml`. It needs `tinyauth_enabled` and `caddy_enabled`.
2. The client secrets `vault_gitea_oidc_secret`, `vault_immich_oidc_secret` and `vault_pics_oidc_secret` are random values that `just setup <host>` adds to the host's vault; rerun it if they are missing.
3. Deploy: `just deploy tinyauth,gitea,immich,pics --limit <host>`.

Behaviour:

- The app's own password login stays, so a Tinyauth problem does not lock you out.
- Every user in `vault_tinyauth_users` can sign in to an app, but the app decides who gets in: [Who may use what](#who-may-use-what).
- **Immich settings:** with `immich_sso_enabled`, Immich reads its settings from a file the deploy writes and refuses to save changes from its settings page. The file carries the OAuth client and the password-login switch, and every other setting is Immich's default.

With more than one domain in `caddy_private_domains`:

- Tinyauth itself and its issuer address are on the first domain.
- **Immich** sends the address you opened it on, so Tinyauth accepts the Immich sign-in on every domain.
- **pics** (its name under the first domain) and **Gitea** (`gitea_root_url`) send one fixed address, so Tinyauth sign-in works on that name only. Their password login works on every name.

First login:

- **Immich** matches you by email. Tinyauth makes that address `<user>@<private domain>` from the user name unless the user name is already an address, so give the Immich account that email (user `alice` on `pi4.example.com`: `alice@pi4.example.com`). A Tinyauth user with no matching Immich account is refused, so an Immich admin creates the account first.
- **Gitea** creates no accounts. It shows its link page once, to attach the Tinyauth login to an existing Gitea account; a login with no account to attach stops there, so an admin creates the Gitea account first.

## Protect an app of your own

For a Dockge stack or any container on the host. Needs `tinyauth_enabled`, Caddy with `caddy_private_domains`, and the app on the same host as Tinyauth.

1. Name the app under the host's first private domain and add the `tinyauth_forwarder` label, on the `services` network ([label syntax](./caddy-reference.md#label-syntax)).
2. Publish no port for the app: a published port skips Caddy and the login.
3. Start the stack. Open the name in a private browser window: it shows the Tinyauth login. To see the rule Caddy loaded: `docker exec caddy cat /config/caddy/Caddyfile.autosave | grep -A3 app.pi4`. A request without a browser (`curl`) gets 401, not the login page.

The app sits behind Tinyauth and receives the user in the `Remote-User`, `Remote-Name`, `Remote-Email` and `Remote-Groups` headers. If the app also has its own login, pick the first that fits:

1. **It speaks OpenID Connect (Gitea, Immich, pics):** Tinyauth is its OIDC provider when `gitea_sso_enabled`, `immich_sso_enabled` or `pics_sso_enabled` is on, so the app knows who signed in and keeps its own accounts ([above](#sign-in-with-tinyauth-oidc)). For an app of your own, add a client in `tinyauth_environment` (`TINYAUTH_OIDC_CLIENTS_<ID>_CLIENTID`, `_CLIENTSECRET`, `_TRUSTEDREDIRECTURIS`, `_NAME`, as in `roles/tinyauth/templates/docker-compose.yml.j2`) and give the app the issuer `https://auth.<first private domain>`.
2. **It trusts a proxy's user header (Dozzle, Copyparty):** the app takes the name from `Remote-User`, with its own setting for it. Where the app lets you name the header, that name is a secret, so another container on the network cannot forge it.
3. **It has an off switch (Dockge, which the role switches off itself):** turn the app's login off. Every user then shares one app account.
4. **Its login is optional (Homepage):** leave it unset, so Tinyauth is the only login.
5. **Nothing fits:** the app's own login stays and you sign in twice (Crafty).

Clients that cannot log in through a web page (mobile apps, API tokens, git, WebDAV, webhooks) are stopped by the forwarder with a 401. Leave the label off for those, so the app's own login protects it (as for Immich and Gitea), or give them a second name without the label. A script can also send a Tinyauth user and password as HTTP basic auth, for a user without two-factor.

## Reach a protected service from outside the tailnet

The login and its session cookie belong to the private domain. Tinyauth takes the cookie domain from its own address (`TINYAUTH_APPURL`, one parent domain per instance), so a public name on any other domain can never share the session. Options, best first:

1. **Tailscale on the device.** Nothing to change: the private names resolve to the tailnet address. Use this when the device can run Tailscale.
2. **Publish the names through Caddy, under the same private domain.** A tunnel name is an exact proxied record, so it wins over the private wildcard record. Point it at Caddy, not the container, and publish the login page too, because a browser with no session is sent there. In the host's `vars.yml`:

   ```yaml
   cloudflared_enabled: true
   cloudflared_ingress:
     - {hostname: dockge.pi4.example.com, service: "http://caddy:80"}
     - {hostname: auth.pi4.example.com, service: "http://caddy:80"}
   caddy_sites:
     http://dockge.pi4.example.com: {import: tinyauth_forwarder, reverse_proxy: "dockge:5001"}
     http://auth.pi4.example.com: {reverse_proxy: "tinyauth:3000"}
   ```

   Then `just deploy caddy,cloudflared --limit <host>`. The login page is now on the internet: give every user a `totp` secret first (above). Cloudflare ends the TLS, so the sites are `http://` ([With cloudflared](./caddy-reference.md#with-cloudflared)).
3. **The app's own login, exposed directly:** a tunnel entry to the container, only for an app that has a login ([which](./services.md#tinyauth-login)). Never for Dozzle, Scrutiny, the Garage web UI or Dockge with its login off.

A second Tinyauth for another domain does not fit: it needs its own users, container and forwarder snippet by hand. Tailscale Funnel gives another domain (`ts.net`), so the login cannot follow it.

## Who may use what

By default every user in `vault_tinyauth_users` reaches every service. `service_users` limits a service to some of them: Tinyauth user names per service key (the keys in `group_vars/all/services.yml`), in `vars.yml` or a host's `vars.yml`.

```yaml
service_users:
  pics: [alice, bob]
  dozzle: [alice]
```

A service not listed stays open to every Tinyauth user. How a listed service is limited depends on how it signs people in:

- **Behind the Caddy login** (Dozzle, Scrutiny, Dockge, the backup dashboard and the other services with a login in front): the deploy gives Tinyauth a rule for that service's exact web address, so a user not listed gets "forbidden" after signing in. Copyparty is in this group only with `copyparty_sso_enabled`, and then needs `service_users.copyparty`: its users are also its admins.
- **pics** (`pics_sso_enabled`): Tinyauth cannot limit an OIDC client, so the deploy passes the list to pics, which lets in only those users. pics needs `service_users.pics`, and each listed user is a full owner. The deploy stops without it.
- **Immich and Gitea** decide by their own accounts: a Tinyauth login creates none, so only people with an account there get in.

A list limits the users in `vault_tinyauth_users`; a person who signs in with GitHub or Google is limited by `TINYAUTH_APPS_<ID>_OAUTH_WHITELIST` instead. Rules beyond a user list (a path, an IP range) are Tinyauth environment variables in `tinyauth_environment`, for example `TINYAUTH_APPS_DOZZLE_PATH_BLOCK: ^/api`. The app id is the service key in capitals with dashes (`BACKUP-STATUS`). Leave `TINYAUTH_AUTH_ACLS_POLICY` at its default: `deny` locks out every service not listed in `service_users`. A service the host does not run is ignored. Details: [Tinyauth access controls](https://tinyauth.app/docs/guides/access-controls/).

## Tailscale

Two routes, neither used by the deploy by default:

- **Continue with Tailscale** is built into Tinyauth: `TINYAUTH_TAILSCALE_ENABLED: "true"`, `TINYAUTH_TAILSCALE_APITOKEN` (an API token from the Tailscale admin console, in the vault) and `TINYAUTH_TAILSCALE_TAILNET`. It works out who you are from the device your request comes from, so Tinyauth must see the real client IP: also set `TINYAUTH_AUTH_TRUSTEDPROXIES` to the `services` network's subnet (`docker network inspect services`). Tagged devices are not recognised.
- **[tsidp](https://github.com/tailscale/tsidp)** is a separate small service that makes your tailnet an OpenID Connect provider; Tinyauth then uses it as another provider (the three URLs above, and `TINYAUTH_OAUTH_PROVIDERS_<ID>_CLAIMS_USERNAME: username`). Neither project documents the pair.

## Session length

`TINYAUTH_AUTH_SESSIONEXPIRY` is seconds, default one day, and it slides while you use the site. `TINYAUTH_AUTH_SESSIONMAXLIFETIME` caps the total age (default none). Sessions are stored in `tinyauth_data_dir`, so a redeploy keeps them.
