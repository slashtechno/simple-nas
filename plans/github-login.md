# GitHub login next to the password login

> **Status: active plan. Delete this file when done; git history keeps it.** It records one owner's steps, not conventions: the rules are in AGENTS.md and the code.

Waiting on the owner. Goal: sign in to Tinyauth with the password or with GitHub as the same person ([rule](../docs/auth-reference.md#sign-in-with-github-google-or-another-openid-connect-provider)).

1. In the vault (`just edit vault --all`), rename the Tinyauth user `angad` to the GitHub login (`slashtechno`) and add `email:` with the GitHub account's primary email.
2. In `host_vars/pinas/vars.yml`, replace `angad` with the new name in `copyparty_sso_admins` and `service_users`.
3. Make the GitHub OAuth app (callback `https://auth.pinas.slashtechno.com/api/oauth/callback/github`) and put `TINYAUTH_OAUTH_PROVIDERS_GITHUB_CLIENTID` and `_CLIENTSECRET` in `tinyauth_environment` (secret in the vault).
4. Push the lab repo (the pics change that makes `HUB_OIDC_REDIRECT_URL` optional is committed there but not pushed), then `just deploy tinyauth,copyparty,pics,immich,gitea --limit pinas`.
5. The renamed user has a new `sub` in Immich and Gitea: sign in with the password, then unlink and link again (Immich: user settings; Gitea: Settings > Security > Linked accounts), or let the email match relink it.
6. Check: sign in by password and by GitHub, and open Copyparty, Dozzle, pics and Immich each time.
