#!/bin/sh
set -e

# Redis agora é um container próprio (serviço "redis" no docker-compose.yml)
# em vez de embutido aqui — mais fácil de explicar "o worker consome uma
# fila que vive num broker separado", que é o próprio conceito de sistema
# distribuído que este projeto quer mostrar.
# concurrency=1 por padrão: cada tarefa (classificação local) já é pesada e
# CPU-bound sozinha (whisper + Ollama); rodar várias em paralelo só faz
# competir pelos mesmos núcleos/RAM e demorar mais, sem ganho. Ajustável via
# CELERY_WORKER_CONCURRENCY no .env se a máquina aguentar mais.
exec celery -A worker.celery_app worker --loglevel=info --concurrency="${CELERY_WORKER_CONCURRENCY:-1}"
