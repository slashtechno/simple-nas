# Pi NAS Project

This is a self-hosted NAS setup for Raspberry Pi with Immich (photos), Copyparty (files), and Gitea (git).

## Project Structure

- `SETUP_GUIDE.md` - Complete setup instructions
- `BACKUPS.md` - Backup and restore procedures
- `GIT-MIGRATE.md` - Git repository migration guide
- `docker-compose.yml` - Docker services configuration
- `.env.example` - Environment configuration template
- `scripts/` - Executable scripts
  - `backup-restic-local.sh` - Daily local backup script
  - `backup-restic-cloud.sh` - Weekly cloud backup script
  - `backup-paths.txt` - Cloud backup paths (newline-delimited)
- `README.md` - Project overview

## Key Features

- Photo management with Immich
- File sharing with Copyparty
- Git hosting with Gitea
- Automated backups with restic
- Secure remote access via Tailscale

## Development Notes

- Scripts are designed for Linux (Raspberry Pi OS)
- Docker Compose manages all services
- Backups use restic for deduplication
- Configuration via .env file
- This project is intended to be simple, self-contained, and easy to replicate
    - It's intended to be reliable and straightforward for a single home user, but still easy to configure and extend if needed. 