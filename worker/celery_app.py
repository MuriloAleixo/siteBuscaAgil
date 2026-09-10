"""
worker/celery_app.py

Cria o app Celery direto, sem Django por trás (antes vivia em
busca_agil/celery.py e configurava a partir de `django.conf:settings`).
Broker e result backend são só o Redis — a fila de mensagens que desacopla
"o arquivo chegou" (processo `api`) de "o arquivo foi classificado e subiu
pro Drive" (processo `worker`, ver worker/tasks.py).

Tanto `api` quanto `worker` importam este mesmo `celery_app`: o `api`
só precisa dele pra publicar tarefas (`.delay()`); quem de fato as executa
é o `worker`, rodado via `celery -A worker.celery_app worker`.
"""

from __future__ import annotations

import os

from celery import Celery

# Nome da variável precisa ser "app" (convenção do Celery): é o que o
# comando `celery -A worker.celery_app ...` (ver worker/entrypoint.sh e
# install.sh) procura automaticamente no módulo.
app = Celery(
    "busca_agil",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/0"),
    # Só o processo `worker` de fato roda as tarefas; precisa importar
    # worker/tasks.py pra elas se registrarem no app antes de consumir a
    # fila (o `api` nunca entra aqui — ele importa worker.tasks direto pra
    # publicar com `.delay()`, o que já registra as tarefas nele também).
    include=["worker.tasks"],
)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
