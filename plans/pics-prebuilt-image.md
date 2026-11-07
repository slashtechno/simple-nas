# pics: pull a prebuilt image instead of building on the host

Status: waiting on the pics repo (CI that publishes a multi-arch image). Delete this file when the steps are done.

## Why

pics is the only service built on the host at deploy time (`build: ./src/local/pics`, `roles/pics`). Every other service pulls an image pinned in `group_vars/all/versions.yml`.

- The build (bun install and a web build, then `uv sync`) needs more RAM than a 4 GB host has free next to Immich, Crafty and Gitea. On pinas it exhausted memory, the host stalled in swap, and the hardware watchdog reset it. A deploy that changes pics' source starts that build; a deploy that does not change it skips the build.
- `pics_version: main` is a moving git branch in a file that otherwise holds image versions, so two deploys can run different code.
- `tools/check_platforms.py` checks only `*_image` keys, so it cannot check that pics runs on arm64 and amd64.
- `mem_limit` on a service does not cap `docker compose build`; BuildKit has no per-build limit in compose.

## Steps

1. pics repo: a GitHub Actions workflow builds `linux/arm64` and `linux/amd64` and pushes to a registry the hosts can pull from (GHCR, private). The tag is a release tag or a commit.
2. Pull access: a token with package read scope on each pics host. If it reuses `vault_github_read_token`, that one token needs the scope; do not add a second login for the same account.
3. simple-nas:
   - `versions.yml`: `pics_image: ghcr.io/<owner>/pics:<tag>`; remove `pics_version`.
   - `roles/pics`: the compose file uses `image: "{{ pics_image }}"`; delete the `github_clone` call, the `build:` logic and the "several minutes" comment.
   - Delete `roles/github_clone` and `pics_repo` if nothing else uses them.
   - `docker login` for the registry, as a task in `roles/pics`.
   - Docs: `docs/services.md` (pics section), `ansible/README.md`, the `vault.yml.example` entry for the token.
   - `just platforms` then covers pics.
4. Host: deploy `pics` once, check the app opens, then remove the old source folder and the built `pics-hub` image.

## Decided against

- A per-service memory-limit setting on every role: it does not cap a build, and the right number is the host's RAM. Crafty already has `crafty_memory_limit`.
- Swap or zram changes: swap on a microSD root wears the card and lengthens a stall; the image pull removes the trigger.
- Stopping other services during a build: it trades availability for nothing on hosts where builds are cheap.
- A Pi-detecting task or group: behaviour comes from `<name>_enabled` flags and the `drives` list.
