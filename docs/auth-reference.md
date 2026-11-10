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
  TINYAUTH_OAUTH_AUTOREDIRECT: github   # optional: skip the login page and go straight to GitHub
```

- **Who may sign in.** A provider accepts any of its accounts, so the whitelists limit it by email: only the emails of the users in `vault_tinyauth_users` that have an `email:`, and a limited service lets in only the emails of the users `service_users` lists for it.
- **The deploy stops** if no user has an email, if a listed user has none, or if `tinyauth_environment` sets a whitelist itself.
- **Name the user after the GitHub login**, with your email: `{name: slashtechno, password: ..., email: you@example.com}` (lower-case letters, digits and `-`). Both logins then give apps the same name, so they see one person. If the names differ: [one person, several names](#one-person-several-names).
- `google` is the same with `GOOGLE`, but Google gives the user name `you_example.com`, so name the user that to match. Another provider (Pocket ID, Authentik, Keycloak) is any other id plus `_AUTHURL`, `_TOKENURL`, `_USERINFOURL`, `_SCOPES` and `_NAME` ([guide](https://tinyauth.app/docs/guides/other-oauth/)).

## Sign in with Tinyauth (OIDC)

OIDC stands for OpenID Connect, the login standard most apps support. The app sends your browser to Tinyauth to log in, and Tinyauth tells the app who you are; the app never sees your password. Gitea, Immich and pics can do this, so one Tinyauth login opens them, and each keeps its own accounts and permissions.

Setup:

1. Turn it on for an app on the host: `gitea_sso_enabled: true`, `immich_sso_enabled: true` or `pics_sso_enabled: true` in its `vars.yml`. It needs `tinyauth_enabled` and `caddy_enabled`.
2. The client secrets `vault_gitea_oidc_secret`, `vault_immich_oidc_secret` and `vault_pics_oidc_secret` are random values that `just setup <host>` adds to the host's vault; rerun it if they are missing.
3. Deploy: `just deploy tinyauth,gitea,immich,pics --limit <host>`.

Behaviour:

- The app's own password login stays, so a Tinyauth problem does not lock you out.
- Every user in `vault_tinyauth_users` can sign in, but the app decides who gets in: [Who may use what](#who-may-use-what).
- **Immich:** the deploy sets only the sign-in block and the settings `immich_job_concurrency`, `immich_transcode_policy` and `immich_accepted_video_codecs` name, through Immich's API; the settings page stays editable. It needs a non-empty `immich_port` and `vault_immich_api_key`: deploy Immich with `immich_sso_enabled` off first, sign in as an admin, create a key under Account Settings > API Keys with only `systemConfig.read` and `systemConfig.update`, and put it in the vault. Turning `immich_sso_enabled` off leaves the block; clear it under Administration > Settings > Authentication.

Addresses an app is opened at (the first private domain is Tinyauth's own):

- **Immich and pics** return you to the address you opened them on: Tinyauth trusts every Caddy name, and `immich_extra_origins` / `pics_extra_origins` add others (a tunnel hostname, `http://<host>:8100`). pics needs a build where `HUB_OIDC_REDIRECT_URL` is optional (`pics_version`).
- **Gitea** (`gitea_root_url`) sends one fixed address, so Tinyauth sign-in works on that name only; its password login works on every name.

First login:

- **Immich** matches a login to an account by email: the user's `email` in `vault_tinyauth_users`, else `<user>@<private domain>`. Give the Immich account that address; a login with no matching account is refused, so an admin creates it first.
- **Gitea** creates no accounts. It shows its link page once, where you enter an existing Gitea account's user name and password to attach the Tinyauth login to it; after that the Tinyauth button signs in to that account. A login with no account to attach stops there, so an admin creates the Gitea account first.

## Protect an app of your own

For a Dockge stack or any container on the host. Needs `tinyauth_enabled`, Caddy with `caddy_private_domains`, and the app on the same host as Tinyauth.

1. Name the app under the host's first private domain and add the `tinyauth_forwarder` label, on the `services` network ([label syntax](./caddy-reference.md#label-syntax)):

   ```yaml
   services:
     whoami:
       image: traefik/whoami
       networks: [services]
       labels:
         caddy: whoami.pi4.example.com             # under the first private domain
         caddy.import: tinyauth_forwarder          # the login
         caddy.reverse_proxy: "{{upstreams 80}}"
       # no ports: here

   networks:
     services:
       external: true
   ```

2. Publish no port for the app: a published port skips Caddy and the login.
3. Start the stack. Open the name in a private browser window: it shows the Tinyauth login (`curl` gets 401).

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

How a listed service is limited depends on how it signs people in:

- **Behind the Caddy login** (Dozzle, Scrutiny, Dockge, the backup dashboard and the other services with a login in front): the deploy gives Tinyauth a rule for that service's exact web address, so a user not listed gets "forbidden" after signing in. Copyparty is in this group only with `copyparty_sso_enabled`. Its admins are `copyparty_sso_admins`, not this list; `service_users.copyparty` only limits who may open the page ([Copyparty](./services.md#copyparty-accounts-and-volumes)).
- **pics** (`pics_sso_enabled`): Tinyauth cannot limit an OIDC client, so the deploy passes the list to pics, which lets in only those users. pics needs `service_users.pics`, and each listed user is a full owner. The deploy stops without it.
- **Immich and Gitea** decide by their own accounts: a Tinyauth login creates none, so only people with an account there get in.

A list limits the users in `vault_tinyauth_users`; a person who signs in with GitHub or Google is limited by the email whitelists above (pics checks its own list by name). Rules beyond a user list (a path, an IP range) are Tinyauth environment variables in `tinyauth_environment`, for example `TINYAUTH_APPS_DOZZLE_PATH_BLOCK: ^/api`. The app id is the service key in capitals with dashes (`BACKUP-STATUS`). Leave `TINYAUTH_AUTH_ACLS_POLICY` at its default: `deny` locks out every service not listed in `service_users`. Details: [Tinyauth access controls](https://tinyauth.app/docs/guides/access-controls/).

## Tailscale

Two routes, neither used by the deploy by default:

- **Continue with Tailscale** is built into Tinyauth: `TINYAUTH_TAILSCALE_ENABLED: "true"`, `TINYAUTH_TAILSCALE_APITOKEN` (an API token from the Tailscale admin console, in the vault) and `TINYAUTH_TAILSCALE_TAILNET`. It works out who you are from the device your request comes from, so Tinyauth must see the real client IP: also set `TINYAUTH_AUTH_TRUSTEDPROXIES` to the `services` network's subnet (`docker network inspect services`). Tagged devices are not recognised.
- **[tsidp](https://github.com/tailscale/tsidp)** is a separate small service that makes your tailnet an OpenID Connect provider; Tinyauth then uses it as another provider (the three URLs above, and `TINYAUTH_OAUTH_PROVIDERS_<ID>_CLAIMS_USERNAME: username`). Neither project documents the pair.

A Tailscale login is checked like a password user: by user name against `service_users`, not by the email whitelists, and it skips two-factor. A service without a `service_users` entry is open to the whole tailnet, so list who may use it.

## One person, several names

Password, GitHub, Google and Tailscale logins each give the session a different name, and Tinyauth cannot link them: a name that is not a user in `vault_tinyauth_users` is another person to the apps. Where the same person needs the same access under another name, add that name there too:

- `copyparty_sso_admins` and `service_users.pics`: list both names.
- Behind the Caddy login: a GitHub or Google login is let in by email, so there is nothing to add. A password or Tailscale login is let in by name, so list that name in `service_users`.
- Immich and Gitea: the second name is a new login; link it to the same account by hand ([first login](#sign-in-with-tinyauth-oidc)).

`service_users` takes only names from `vault_tinyauth_users` (the deploy checks), so a name that exists only at Tailscale (`you_example.com`) needs that check widened first.

## Access gotchas

- An `email:` opens the login: that person can sign in with GitHub or Google and reach every service without a `service_users` entry. A service with no entry is open to every user (the whole tailnet, for Tailscale).
- Lists match names. Do not give an `email:` to someone whose GitHub login equals another user's name: they would be that user in Copyparty, pics, Immich and Gitea.
- Use GitHub or Google. Tinyauth does not verify a provider's emails, so a provider where anyone may register any address lets anyone in.
- GitHub, Google and Tailscale logins skip two-factor.
- Renaming a user gives it a new Immich and Gitea id: relink those accounts.

## Session length

`TINYAUTH_AUTH_SESSIONEXPIRY` is seconds, default one day, and it slides while you use the site. `TINYAUTH_AUTH_SESSIONMAXLIFETIME` caps the total age (default none). Sessions are stored in `tinyauth_data_dir`, so a redeploy keeps them.
