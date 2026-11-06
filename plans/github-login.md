# GitHub login next to the password login

> **Status: active plan. Delete this file when done; git history keeps it.** It records one owner's steps, not conventions: the rules are in AGENTS.md and the code.

Waiting on the owner. Goal: sign in to Tinyauth with the password or with GitHub as the same person ([rule](../docs/auth-reference.md#sign-in-with-github-google-or-another-openid-connect-provider)).

Done: the vault user is `slashtechno`, `copyparty_sso_admins` and `service_users` use it, and pi4 and pinas are deployed.

1. In the vault, give the `slashtechno` user `email:` (the GitHub account's primary email).
2. Make the GitHub OAuth app (callback `https://auth.pinas.slashtechno.com/api/oauth/callback/github`) and put `TINYAUTH_OAUTH_PROVIDERS_GITHUB_CLIENTID` and `_CLIENTSECRET` in `tinyauth_environment` (secret in the vault).
3. Deploy: `just deploy tinyauth,copyparty,pics,immich,gitea --limit pinas`.
4. The rename gave the user a new id in Immich and Gitea. Immich may link the new login by email; if not, link it in user settings. Gitea shows a link page on the first login: sign in with the Gitea password. Unlink the old one first under Settings > Security > Linked accounts if needed.
5. Check: sign in by password and by GitHub, and open Copyparty, Dozzle, pics and Immich each time.
