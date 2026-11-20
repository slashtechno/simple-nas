# Plugins: host steps

Status: waits for the owner. The code is on branch `plugins` (not merged); these are the steps that need your hosts and vault. Delete this file when done.

1. **Pin pics.** pics builds the exact commit in `pics_commit`, which has no default. Get the hash of the code you run now with `git ls-remote https://github.com/<pics_repo>.git main`, read what changed if you are unsure, and set `pics_commit` in `group_vars/all/vars.yml`. (The vault token rename to `vault_pics_repo_token` is done.)
2. **Fetch and look.** `just plugins`, then `just preview '' --limit pinas`. The diff should only be what a deploy always shows; Crafty and pics render as before, from `plugins/`. Check `just plugins` prints `crafty` and `pics` with their `login`.
3. **Deploy.** `just deploy '' --limit pinas`, then once per other host that runs either plugin. A core-only host needs nothing.
4. **Optional, move pics to its own repo** (the item in `TODO.md`): copy `ansible/plugins/pics/` into the repo, add a `plugins:` entry with a pinned `commit` hash to `group_vars/all/vars.yml` (`auth:` names the vault token if the repo is private), delete the folder here in one commit, then repeat steps 2 and 3. `pics_version` (the app's own tag) and the plugin's tag are independent.

Rollback: check out `main`; nothing on a host changes until step 3.
