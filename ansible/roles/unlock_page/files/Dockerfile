ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
WORKDIR /app
COPY app.py .
# Runs as root: only root on the host can use the socket.
EXPOSE 8080
CMD ["python3", "app.py"]
