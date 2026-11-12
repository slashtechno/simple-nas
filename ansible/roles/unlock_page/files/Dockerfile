ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY app.py .
# Runs as root: the SSH key and the passphrase are in a read-only mount that only root on the host can read.
EXPOSE 8080
CMD ["python3", "app.py"]
