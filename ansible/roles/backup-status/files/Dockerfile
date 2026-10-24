ARG RESTIC_IMAGE
ARG PYTHON_IMAGE
FROM ${RESTIC_IMAGE} AS restic

FROM ${PYTHON_IMAGE}

COPY --from=restic /usr/bin/restic /usr/local/bin/restic

WORKDIR /app
COPY app.py index.html pico.min.css ./

# Runs as root: the security boundary is the read-only bind mounts in docker-compose.yml, which the
# kernel enforces for any user.
EXPOSE 8080
CMD ["python3", "app.py"]
