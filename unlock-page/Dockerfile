FROM python:3.14.9-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY app.py .
EXPOSE 8080
CMD ["python3", "app.py"]
