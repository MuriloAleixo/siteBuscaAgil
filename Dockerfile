FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        antiword \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Imagem compartilhada por "api" e "worker" (docker-compose.yml) — cada
# serviço sobrescreve o comando: a api roda o Flask (abaixo), o worker roda
# o Celery via worker/entrypoint.sh.
CMD ["flask", "--app", "api.app", "run", "--host=0.0.0.0", "--port=5000"]
