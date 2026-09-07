#!/bin/sh
set -e

redis-server --daemonize yes --save "" --dir /tmp
exec celery -A busca_agil worker --loglevel=info
