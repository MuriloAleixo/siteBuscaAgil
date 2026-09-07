#!/bin/sh
set -e

redis-server --daemonize yes --save "" --dir /tmp --bind 0.0.0.0 --protected-mode no
exec celery -A busca_agil worker --loglevel=info
