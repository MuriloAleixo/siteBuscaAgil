#!/bin/sh
set -e

# Redis agora é um container próprio (serviço "redis" no docker-compose.yml)
# em vez de embutido aqui — mais fácil de explicar "o worker consome uma
# fila que vive num broker separado", que é o próprio conceito de sistema
# distribuído que este projeto quer mostrar.
exec celery -A worker.celery_app worker --loglevel=info
