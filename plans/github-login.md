# GitHub login next to the password login

> **Status: active plan. Delete this file when done; git history keeps it.** It records one owner's steps, not conventions: the rules are in AGENTS.md and the code.

Waiting on the owner. Goal: sign in to Tinyauth with the password or with GitHub as the same person ([rule](../docs/auth-reference.md#sign-in-with-github-google-or-another-openid-connect-provider)).

Done: the vault user is `slashtechno` with its `email:`, `copyparty_sso_admins` and `service_users` use it, pi4 and pinas are deployed, and Immich and Gitea are linked to the new login.

1. Make the GitHub OAuth app (callback `https://auth.pinas.slashtechno.com/api/oauth/callback/github`) and put `TINYAUTH_OAUTH_PROVIDERS_GITHUB_CLIENTID` and `_CLIENTSECRET` in `tinyauth_environment` (secret in the vault).
2. Deploy: `just deploy tinyauth,copyparty,pics,immich,gitea --limit pinas`.
3. Check: sign in by password and by GitHub, and open Copyparty, Dozzle, pics and Immich each time.
