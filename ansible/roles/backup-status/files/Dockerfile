FROM restic/restic:latest AS restic

FROM python:3.14-slim

COPY --from=restic /usr/bin/restic /usr/local/bin/restic

WORKDIR /app
COPY app.py index.html pico.min.css ./

# Runs as root (the image default) because the actual security boundary is
# the read-only bind mount docker-compose sets up for the repo and password
# file, not the container's UID — even root here gets EROFS on a write
# attempt, since :ro is enforced by the kernel regardless of who's asking.
EXPOSE 8080
CMD ["python3", "app.py"]
