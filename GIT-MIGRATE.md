# Migrate Git Repositories to Gitea

---

## Setup

Edit Gitea config:

```bash
nano /mnt/t7/docker/gitea/gitea/conf/app.ini
```

Add under `[repository]`:

```ini
[repository]
ENABLE_PUSH_CREATE_USER = true
ENABLE_PUSH_CREATE_ORG = true
```

Restart Gitea:

```bash
docker compose restart gitea
```

---

## Migrate a Repo

```bash
# Mirror clone (all history, branches, tags, notes)
git clone --mirror https://github.com/username/repo.git repo.git

# Push to Gitea (creates repo automatically)
cd repo.git
git push --mirror ssh://git@your-machine.user-xxxxx.ts.net:2222/your-username/repo-name.git
```

Done.

---

## Verify

```bash
git clone ssh://git@your-machine.user-xxxxx.ts.net:2222/your-username/repo-name.git /tmp/test
cd /tmp/test
git log --oneline | head -5
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| SSH auth fails | Add SSH key to Gitea (Settings → SSH Keys) |
| Repo not created | Check push-to-create enabled and Gitea restarted |
| `app.ini` location | `docker exec gitea cat /etc/gitea/app.ini \| grep ROOT` |
