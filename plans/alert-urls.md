# One alert URL per sender

Status: not built. A refactor, so it goes on a branch. Waiting for the owner's go.

Every sender of alerts shares `ntfy_alert_url` and the one `vault_ntfy_token`. `alert.sh` sends that token to whatever server the URL names, so a second target (another host's ntfy, ntfy.sh) cannot have its own token. Each sender should be able to alert to its own ntfy, with the token that belongs to it.

## Senders

From `grep -rn "ntfy_alert_url\|vault_ntfy_token" ansible/roles`:

- `alert.sh` (`roles/common`): backup jobs and the connectivity watchdog. Reads the token from `ntfy_token_file`.
- Scrutiny (`roles/scrutiny/templates/docker-compose.yml.j2`): a Shoutrrr URL.
- pics (`roles/pics/templates/pics.env.j2`): an Apprise URL.

A service that never alerts gets no setting, and there is no generic mechanism.

## Shape

- Each sender gets a URL setting and a token setting side by side, for example `backup_alert_url` with `vault_backup_alert_token`, `scrutiny_alert_url`, `pics_alert_url`.
- The defaults are today's pair, written once: the URL defaults to `{{ ntfy_alert_url }}` and the token to `{{ vault_ntfy_token | default('') }}`. With no override nothing changes.
- An override names its token next to its URL, so a URL and its token travel together (the same rule as a user name and its password).
- `alert.sh` keeps reading its token from a file, so the token is never on a command line. One token file per sender that needs it, removed by teardown like today's.

## Test

A render test that each sender gets its own URL and token, and that with no override the output matches today's.

## Documentation to change

`docs/encryption.md` says `vault_ntfy_token` suits an ntfy you run, not ntfy.sh. That line and the `ntfy_alert_url` comment in `group_vars/all/defaults.yml` change when this lands. With per-sender URLs, backup alerts can go to a public ntfy.sh topic (use a long random topic name and a token) while the self-hosted ntfy keeps its data in an encrypted folder.
