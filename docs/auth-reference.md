# Login (Tinyauth) reference

| I want to | Go to |
|---|---|
| Add a user, change a password | [Users and passwords](#users-and-passwords) |
| Add a second factor | [Two-factor codes](#two-factor-codes-totp) |
| Sign in with GitHub or Google | [GitHub, Google](#sign-in-with-github-google-or-another-openid-connect-provider) |
| Log in to Gitea, Immich or pics with Tinyauth | [OIDC](#sign-in-with-tinyauth-oidc) |
| Put my own app behind the login | [Protect an app](#protect-an-app-of-your-own) |
| Let only some users open a service | [Who may use what](#who-may-use-what) |
| Reach a protected service away from Tailscale | [From outside](#reach-a-protected-service-from-outside-the-tailnet) |
| Get in while Tinyauth is down | [If Tinyauth is down](#if-tinyauth-is-down) |

Tinyauth is the login page in front of the web services. [services.md](./services.md#tinyauth-login) says what it does and how a service joins it. This page covers users, two-factor codes, GitHub and Google sign-in, OpenID Connect and sessions.

Tinyauth's own settings are `TINYAUTH_*` environment variables ([all of them](https://tinyauth.app/docs/reference/configuration/)). Put extra ones in `tinyauth_environment` in the host's `vars.yml`.

## Users and passwords

1. Add the user to `vault_tinyauth_users` in `group_vars/all/vault.yml`: a `name` and a `password` (shape: `vault.yml.example`). Every host gets the same users. A host that needs different users sets `vault_tinyauth_users` in its own host vault, which wins.
2. Run `just deploy tinyauth --limit <host>`. To change a password, edit the vault and deploy again.

Each host runs its own Tinyauth, so a login on one host does not sign you in on another.

<details>
<summary>Why the vault holds plain passwords</summary>

Tinyauth wants bcrypt hashes, so the deploy hashes the vault passwords. It uses a fixed salt: the same password gives the same hash on every run, so the deploy reports a change only when a password changes.

</details>

## Two-factor codes (TOTP)

Tinyauth asks a user with a `totp` key for a six-digit code after the password. The password stays, and the code adds to it.

1. Make a secret: `python3 -c "import base64, os; print(base64.b32encode(os.urandom(20)).decode())"`.
2. Add `totp: "THE32LETTERSECRET"` to that user in `vault_tinyauth_users`.
3. Deploy, then add the account in an authenticator app. Choose "enter a setup key" and paste the secret. The defaults (time-based, 6 digits, 30 seconds) are right.

- **Lost phone:** there are no recovery codes. Delete that user's `totp` line, deploy, and enrol again with a new secret. Keep the vault password somewhere other than the phone.
- **Skipped codes:** a login through GitHub, Google or Tailscale skips two-factor, so limit who may use those (below).
- **No basic auth:** Tinyauth accepts a password sent as HTTP Basic auth, but refuses it for a user with two-factor, so a script or WebDAV client cannot sign in as that user.

## Sign in with GitHub, Google or another OpenID Connect provider

1. Make an OAuth app at the provider. Its callback URL is `https://auth.<first private domain>/api/oauth/callback/<id>` (`github`, `google`, or a name you choose).
2. Add the client to the host's `vars.yml`. Keep the secret in the vault:

   ```yaml
   tinyauth_environment:
     TINYAUTH_OAUTH_PROVIDERS_GITHUB_CLIENTID: "the client id"
     TINYAUTH_OAUTH_PROVIDERS_GITHUB_CLIENTSECRET: "{{ vault_tinyauth_github_secret }}"
     TINYAUTH_OAUTH_AUTOREDIRECT: github   # optional: skip the login page and go straight to GitHub
   ```

3. Give each person who may sign in an `email` in `vault_tinyauth_users`, and name the user after their GitHub login: `{name: <github-login>, password: ..., email: you@example.com}`. The name is lower-case letters, digits and `-`.

The password login and the GitHub login then give apps the same name, so apps see one person. If the names differ: [one person, several names](#one-person-several-names).

- **Who may sign in:** a provider accepts any of its accounts, so the deploy limits it by email. It lets in only the emails of the users who have an `email`. A limited service lets in only the emails of the users `service_users` lists for it.
- **The deploy stops** if no user has an email, if a user listed for a service behind the login has none, or if `tinyauth_environment` sets a whitelist itself.
- **Google** is the same with `GOOGLE`. Google gives the user name `you_example.com`, so name the user that.
- **Another provider** (Pocket ID, Authentik, Keycloak) is any other id, plus `_AUTHURL`, `_TOKENURL`, `_USERINFOURL`, `_SCOPES` and `_NAME` ([guide](https://tinyauth.app/docs/guides/other-oauth/)).

Do not give an `email` to someone whose GitHub login equals another user's name: they would become that user in Copyparty, pics, Immich and Gitea. Use only GitHub or Google. Tinyauth does not verify a provider's emails, so a provider where anyone may register any address lets anyone in.

## Sign in with Tinyauth (OIDC)

OIDC (OpenID Connect) is the login standard most apps support. The app sends your browser to Tinyauth, and Tinyauth tells the app who you are. The app never sees your password. One Tinyauth login then opens Gitea, Immich and pics, and each keeps its own accounts and permissions.

1. Set `gitea_sso_enabled`, `immich_sso_enabled` or `pics_sso_enabled` to `true` in the host's `vars.yml`. Each needs `tinyauth_enabled` and `caddy_enabled`.
2. Check the vault holds `vault_gitea_oidc_secret`, `vault_immich_oidc_secret` and `vault_pics_oidc_secret`. `just setup <host>` adds them: rerun it if they are missing.
3. Run `just deploy tinyauth,gitea,immich,pics --limit <host>`.

To change a secret, put a new value in the vault and run the same deploy. Each role writes the secret to its app, so do not edit it in the app.

- **Password login stays,** so a Tinyauth problem does not lock you out.
- **Who gets in:** every user in `vault_tinyauth_users` can sign in, but the app decides who may enter ([Who may use what](#who-may-use-what)).
- **Addresses:** Immich and pics return you to the address you opened them on. Tinyauth trusts every Caddy name, and `immich_extra_origins` and `pics_extra_origins` add others, such as a tunnel hostname. Gitea sends one fixed address (`gitea_root_url`), so Tinyauth sign-in works on that name only. Its password login works on every name.

**Immich** needs one extra step. The deploy sets the sign-in block, and the settings that `immich_job_concurrency`, `immich_transcode_policy` and `immich_accepted_video_codecs` name, through Immich's API. It needs a non-empty `immich_port` and `vault_immich_api_key`:

1. Deploy Immich with `immich_sso_enabled` off, and sign in as an admin.
2. Create a key under Account Settings > API Keys with only `systemConfig.read` and `systemConfig.update`.
3. Put the key in the vault, then deploy with `immich_sso_enabled` on.

Turning `immich_sso_enabled` off leaves the block in place. Clear it under Administration > Settings > Authentication.

**First sign-in:**

- **Immich** matches a login to an account by email: the user's `email` in `vault_tinyauth_users`, otherwise `<user>@<private domain>`. An admin creates the Immich account with that address first. A login with no matching account fails.
- **Gitea** creates no accounts. On the first sign-in it asks for an existing Gitea user name and password, and links them to the Tinyauth login. After that the Tinyauth button signs in to that account. An admin creates the Gitea account first.

## Protect an app of your own

For a Dockge stack or any container on the host. It needs `tinyauth_enabled`, Caddy with `caddy_private_domains`, and the app on the same host as Tinyauth.

1. Name the app under the host's first private domain and add the `tinyauth_forwarder` label. Put the app on the `services` network ([label syntax](./caddy-reference.md#label-syntax)):

   ```yaml
   labels:
     caddy: whoami.<host>.example.com    # under the first private domain
     caddy.import: tinyauth_forwarder    # the login
     caddy.reverse_proxy: "{{upstreams 80}}"
   ```

2. Publish no host port for the app: a host port skips Caddy and the login.
3. Start the stack and open the name in a private browser window. It shows the Tinyauth login. (A private window has no old session. `curl` gets 401.)

The app receives the user in the `Remote-User`, `Remote-Name`, `Remote-Email` and `Remote-Groups` headers. Tinyauth sends `Remote-Groups` only for LDAP and OAuth logins. Give each user an account of the same name in the app.

If the app also has its own login, pick the first option that fits:

1. **It speaks OpenID Connect (Gitea, Immich, pics):** Tinyauth is its OIDC provider ([above](#sign-in-with-tinyauth-oidc)). For an app of your own, add a client in `tinyauth_environment`: `TINYAUTH_OIDC_CLIENTS_<ID>_CLIENTID`, `_CLIENTSECRET`, `_TRUSTEDREDIRECTURIS` and `_NAME` (see `roles/tinyauth/templates/docker-compose.yml.j2`). Give the app the issuer `https://auth.<first private domain>`.
2. **It trusts a proxy's user header (Dozzle, Copyparty):** the app takes the name from `Remote-User`. If you can name the header, make the name a secret, so another container cannot forge it.
3. **It has an off switch (Dockge; the role switches it off itself):** turn the app's login off. Every user then shares one app account.
4. **Its login is optional (Homepage):** leave it unset, so Tinyauth is the only login.
5. **Nothing fits (Crafty):** the app's own login stays, and you sign in twice.

The forwarder stops clients that cannot use a web login page (mobile apps, API tokens, git, WebDAV, webhooks) with a 401. For those, leave the label off, so the app's own login protects it (as for Immich and Gitea). Or give them a second name without the label.

## Reach a protected service from outside the tailnet

The login and its session cookie belong to the private domain: Tinyauth takes the cookie domain from its own address, one parent domain per instance. A public name on any other domain cannot share the session. Options, best first:

1. **Tailscale on the device.** Nothing to change: the private names resolve to the tailnet address.
2. **Publish the names through Caddy, under the same private domain.** Point the tunnel at Caddy, not the container, and publish the login page too, because a browser with no session goes there. In the host's `vars.yml`:

   ```yaml
   cloudflared_enabled: true
   cloudflared_ingress:
     - {hostname: dockge.<host>.example.com, service: "http://caddy:80"}
     - {hostname: auth.<host>.example.com, service: "http://caddy:80"}
   caddy_sites:
     http://dockge.<host>.example.com: {import: tinyauth_forwarder, reverse_proxy: "dockge:5001"}
     http://auth.<host>.example.com: {reverse_proxy: "tinyauth:3000"}
   ```

   Then run `just deploy caddy,cloudflared --limit <host>`. This puts the login page on the internet, so give every user a `totp` secret first ([above](#two-factor-codes-totp)). Cloudflare ends the TLS, so the sites are `http://` ([With cloudflared](./caddy-reference.md#with-cloudflared)).
3. **The app's own login, exposed directly:** a tunnel entry to the container, only for an app that has a login ([which](./services.md#tinyauth-login)). Never for Dozzle, Scrutiny, the Garage web UI or Dockge with its login off.

A second Tinyauth for another domain does not fit: it needs its own users, container and forwarder snippet by hand. Tailscale Funnel gives another domain (`ts.net`), so the login cannot follow it.

## If Tinyauth is down

The names Tinyauth protects do not open. First find the cause: `docker ps -a --filter name=tinyauth` and `docker logs tinyauth`. Then run `just deploy tinyauth --limit <host>`. To work while it is down:

- **A service with a host port** (`<name>_port` is not `""`) opens on `http://<host>:<port>` with no login ([ports](./caddy-reference.md#web-addresses-and-https)). Dockge's `dockge_port` is 5001 unless you set it to `""`.
- **A service with no host port:** use ssh, or the steps in [Dockge](./services.md#ad-hoc-app-platform).
- **Encrypted folders:** the [unlock page](./encryption.md#unlock-page) is behind the login too, so run `just unlock <host>`.

## Who may use what

By default every user in `vault_tinyauth_users` can open every service. To limit a service, list its users in `service_users`. To leave a service open to all, write no entry for it. Each service has its own list.

```yaml
service_users:       # in group_vars/all/vars.yml or the host's vars.yml
  pics: [alice, bob]
  dozzle: [alice]
```

The keys are service keys from `group_vars/all/services.yml`. The names must be users in `vault_tinyauth_users`. The deploy stops for an unknown name, an unknown service, or an empty list (an empty list would leave the service open).

| Service | What `service_users` does | With no entry |
|---|---|---|
| **Behind the Caddy login** (Crafty, Dockge, Dozzle, Scrutiny, Homepage, the backup dashboard, the unlock page, the Garage web UI; Copyparty with `copyparty_sso_enabled`) | Tinyauth gets a rule for the service's web address. A user not listed gets "forbidden" after signing in. | Every Tinyauth user can open it |
| **pics** (`pics_sso_enabled`) | Tinyauth cannot limit an OIDC client, so the deploy passes the list to pics. pics lets in only those users, and each is a full owner. | The deploy stops |
| **Immich and Gitea** | Not used. Their own accounts decide: a Tinyauth login creates none, so only people with an account there get in. | Same |

- **Copyparty:** `service_users.copyparty` limits only who may open the page. Folder access comes from `vault_copyparty_accounts` ([Copyparty](./services.md#copyparty-folders-and-logins)). The entry needs `copyparty_sso_enabled`: the deploy stops without it.
- **GitHub and Google users** are let in by email, so a list limits them through the emails of its users.
- **Rules beyond a user list** (a path, an IP range) are Tinyauth variables in `tinyauth_environment`, for example `TINYAUTH_APPS_DOZZLE_PATH_BLOCK: ^/api`. The app id is the service key in capitals with dashes (`BACKUP-STATUS`). Do not set `TINYAUTH_AUTH_ACLS_POLICY: deny`: it locks out every service not in `service_users`. Details: [Tinyauth access controls](https://tinyauth.app/docs/guides/access-controls/).

## Tailscale

<details>
<summary>Tailscale as a login provider (two routes)</summary>

Neither route is used by the deploy by default.

- **Continue with Tailscale** comes with Tinyauth: `TINYAUTH_TAILSCALE_ENABLED: "true"`, `TINYAUTH_TAILSCALE_APITOKEN` (an API token from the Tailscale admin console, in the vault) and `TINYAUTH_TAILSCALE_TAILNET`. It works out who you are from the device your request comes from, so Tinyauth must see the real client IP. Also set `TINYAUTH_AUTH_TRUSTEDPROXIES` to the `services` network's subnet (`docker network inspect services`). Tinyauth does not recognise tagged devices.
- **[tsidp](https://github.com/tailscale/tsidp)** is a separate small service that makes your tailnet an OpenID Connect provider. Tinyauth then uses it as another provider (the three URLs above, and `TINYAUTH_OAUTH_PROVIDERS_<ID>_CLAIMS_USERNAME: username`). Neither project documents the pair.

Tinyauth checks a Tailscale login like a password user: by user name against `service_users`, not by email, and it skips two-factor. A service with no `service_users` entry is open to the whole tailnet, so list who may use it.

</details>

## One person, several names

<details>
<summary>When one person has a password, a GitHub and a Tailscale login</summary>

Password, GitHub, Google and Tailscale logins each give the session a different name, and Tinyauth cannot link them. A name that is not a user in `vault_tinyauth_users` is another person to the apps. Where one person needs the same access under another name, add that name too:

- **Copyparty and pics:** use the same name in the `user` of the Copyparty login and in `service_users.pics`.
- **Behind the Caddy login:** a GitHub or Google login is let in by email, so there is nothing to add. A password or Tailscale login is let in by name, so list that name in `service_users`.
- **Immich and Gitea:** the second name is a new login. Link it to the same account by hand ([first sign-in](#sign-in-with-tinyauth-oidc)).

`service_users` takes only names from `vault_tinyauth_users` (the deploy checks), so a name that exists only at Tailscale (`you_example.com`) needs that check widened first. Renaming a user gives it a new Immich and Gitea id: relink those accounts.

</details>

## Session length

<details>
<summary>Session settings</summary>

`TINYAUTH_AUTH_SESSIONEXPIRY` is in seconds. The default is one day, and it slides while you use the site. `TINYAUTH_AUTH_SESSIONMAXLIFETIME` caps the total age (default none). Tinyauth keeps sessions in `tinyauth_data_dir`, so a redeploy keeps them.

</details>
