#!/usr/bin/env bash
# install.sh — sobe o BuscaÁgil inteiro (frontend nginx, api Flask, worker
# Celery, broker Redis, IA local via Ollama) do zero, só com Docker
# instalado. Veja README.md, seção "Rodar Com Docker (Recomendado)".
#
# Isso aqui sobe em modo DESENVOLVIMENTO (Flask --debug por padrão). Não há
# perfil separado de produção — projeto propositalmente simples, um único
# docker-compose.yml.
set -euo pipefail
cd "$(dirname "$0")"

TEXT_MODEL="qwen2.5:7b-instruct"
VISION_MODEL="moondream"
# Modelo menor, dedicado à busca (LOCAL_AI_SEARCH_MODEL) — diferente do
# TEXT_MODEL acima: busca dispara uma chamada a CADA consulta digitada, não
# uma vez por arquivo, então precisa ser rápido (ver
# scripts/local_ai/busca_analyzer_local.py).
SEARCH_MODEL="qwen2.5:3b-instruct"

echo "==> Verificando pré-requisitos..."
if ! command -v docker >/dev/null 2>&1; then
    echo "Docker não encontrado. Instale o Docker (ou ative a integração WSL"
    echo "do Docker Desktop) e rode este script de novo:"
    echo "  https://docs.docker.com/engine/install/"
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "O plugin 'docker compose' não foi encontrado. Instale"
    echo "docker-compose-plugin e rode este script de novo."
    exit 1
fi

echo "==> Conferindo .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Criei o .env a partir do .env.example."
    echo "Edite o .env e preencha GEMINI_API_KEY / GOOGLE_OAUTH_CLIENT_ID /"
    echo "GOOGLE_OAUTH_CLIENT_SECRET antes de continuar (ver README.md,"
    echo "seção 'Configurar Login E Drive Com O Google')."
    read -rp "Pressione ENTER quando terminar de editar o .env (ou Ctrl+C pra sair e editar com calma)... "
fi

echo "==> Preparando pastas locais..."
# Criadas AQUI (pelo usuário do host) de propósito: api/worker rodam como
# root dentro do container (sem USER no Dockerfile) — se essas pastas não
# existirem ainda quando o container subir, é ele quem cria (mkdir
# automático em api/stores.py/processing_log.py), e o bind mount reflete
# esse dono root de volta pro host. Depois disso o próprio usuário do host
# não consegue mais escrever/apagar ali (ex.: ./backup.sh, ./uninstall.sh).
# Pré-criando como o host, os containers só criam ARQUIVOS dentro de uma
# pasta que já é do host — e um arquivo root dentro de uma pasta do host
# ainda pode ser apagado/renomeado pelo dono da pasta.
mkdir -p data/users media

echo "==> Construindo as imagens..."
docker compose build

echo "==> Subindo a IA local (Ollama)..."
docker compose up -d ollama

echo "==> Esperando o Ollama ficar pronto..."
ollama_ok=false
for _ in $(seq 1 30); do
    if docker compose exec -T ollama ollama list >/dev/null 2>&1; then
        ollama_ok=true
        break
    fi
    sleep 2
done
if [ "$ollama_ok" != true ]; then
    echo "O Ollama não respondeu a tempo. Confira 'docker compose logs ollama'."
    exit 1
fi

echo "==> Baixando os modelos de IA local (pode demorar alguns minutos na primeira vez)..."
docker compose exec -T ollama ollama pull "$TEXT_MODEL"
docker compose exec -T ollama ollama pull "$VISION_MODEL"
docker compose exec -T ollama ollama pull "$SEARCH_MODEL"

echo "==> Subindo a api (Flask), o worker do Celery e o frontend (nginx)..."
docker compose up -d api worker frontend

echo "==> Dando um tempo pros containers recém-criados terminarem de subir..."
sleep 5

echo
echo "==> Rodando smoke tests..."
echo

smoke_fail=0

# 1. Ollama respondendo e com os três modelos baixados. Output é capturado
# numa variável e comparado com 'case' (em vez de "| grep -q") de propósito:
# com "set -o pipefail", "cmd | grep -q X" pode contar como falha mesmo
# quando X é encontrado, porque o "-q" fecha o pipe assim que acha o
# primeiro match e isso pode derrubar "cmd" com SIGPIPE antes dela terminar.
ollama_list_output=$(docker compose exec -T ollama ollama list 2>/dev/null) || true
ollama_ok_models=true
for m in "$TEXT_MODEL" "$VISION_MODEL" "$SEARCH_MODEL"; do
    case "$ollama_list_output" in
        *"$m"*) ;;
        *) ollama_ok_models=false ;;
    esac
done
if [ "$ollama_ok_models" = true ]; then
    echo "  [OK]     Ollama respondendo, com $TEXT_MODEL, $VISION_MODEL e $SEARCH_MODEL baixados"
else
    echo "  [FALHOU] Ollama não respondeu ou algum modelo não foi baixado"
    smoke_fail=1
fi

# 2. Frontend (nginx) respondendo em :80 (curl já devolve "000" em
# %{http_code} quando a conexão falha, então não precisa de fallback extra
# aqui).
http_code="000"
for _ in $(seq 1 15); do
    http_code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost/ 2>/dev/null)
    [ "$http_code" != "000" ] && [ -n "$http_code" ] && break
    http_code="000"
    sleep 1
done
if [ "$http_code" = "200" ] || [ "$http_code" = "302" ]; then
    echo "  [OK]     Frontend respondendo em http://localhost/ (HTTP $http_code)"
else
    echo "  [FALHOU] Frontend não respondeu como esperado em :80 (HTTP $http_code)"
    smoke_fail=1
fi

# 3. Worker do Celery respondendo a um ping via broker — rodado a partir do
# container "api" (não do "worker"), de propósito: o worker conversando com
# o próprio Redis seria só rede interna dele e não prova nada sobre a rede
# entre containers, que é o caminho que o /upload de verdade usa
# (CELERY_BROKER_URL=redis://redis:6379/0 visto do lado da api).
celery_ok=false
for _ in $(seq 1 5); do
    ping_output=$(docker compose exec -T api celery -A worker.celery_app inspect ping --timeout 10 2>/dev/null) || true
    case "$ping_output" in
        *pong*) celery_ok=true; break ;;
    esac
    sleep 3
done
if [ "$celery_ok" = true ]; then
    echo "  [OK]     Worker respondeu ao ping enviado pela api (broker acessível pela rede)"
else
    echo "  [FALHOU] Api não conseguiu falar com o worker pelo broker Redis"
    smoke_fail=1
fi

# 4. Classificação de arquivo ponta-a-ponta (IA local, com fallback pro
# Gemini já embutido no próprio processar_upload) — não derruba o setup se
# falhar, só avisa, já que depende de GEMINI_API_KEY/rede como plano B.
echo "teste smoke install.sh: contrato de prestação de serviços" > /tmp/install_smoke_test.txt
docker compose cp /tmp/install_smoke_test.txt api:/tmp/install_smoke_test.txt >/dev/null 2>&1 || true
classify_output=$(docker compose exec -T api python -m scripts.processar_upload /tmp/install_smoke_test.txt 2>/dev/null) || true
case "$classify_output" in
    *categoria_principal*)
        echo "  [OK]     Classificação de arquivo (IA local/Gemini) funcionando"
        ;;
    *)
        echo "  [AVISO]  Classificação de arquivo não retornou resultado (ok se LOCAL_AI_ENABLED"
        echo "           estiver desligado sem GEMINI_API_KEY configurada)"
        ;;
esac
rm -f /tmp/install_smoke_test.txt
docker compose exec -T api rm -f /tmp/install_smoke_test.txt >/dev/null 2>&1 || true

# 5. Log de processamento (SQLite, ver api/processing_log.py) — grava e lê
# um evento de teste de dentro do container "api", confirmando que o
# volume compartilhado com o "worker" (data/processing.db) é gravável e o
# modo WAL funciona no filesystem real usado pelos containers.
log_check=$(docker compose exec -T api python -c "
import sqlite3
from api import processing_log
processing_log.log_event('smoke', 'install_smoke_test', 'task', 'done', 'install.sh')
eventos = processing_log.list_events('smoke', entry_id='install_smoke_test')
print('OK' if eventos else 'VAZIO')
with sqlite3.connect(processing_log.DB_PATH) as conn:
    conn.execute(\"DELETE FROM processing_events WHERE user_id = 'smoke'\")
" 2>/dev/null) || true
case "$log_check" in
    *OK*)
        echo "  [OK]     Log de processamento (SQLite, data/processing.db) gravando e lendo"
        ;;
    *)
        echo "  [FALHOU] Não foi possível gravar/ler o log de processamento"
        smoke_fail=1
        ;;
esac

echo
if [ "$smoke_fail" -ne 0 ]; then
    echo "Alguns smoke tests falharam — confira 'docker compose logs' antes de usar."
    exit 1
fi

echo "Tudo pronto! Acesse: http://localhost/"
echo
echo "Comandos úteis:"
echo "  docker compose logs -f        # acompanhar os logs de tudo"
echo "  docker compose logs -f worker # só o worker (classificação de arquivos)"
echo "  docker compose down           # parar tudo"
echo "  ./install.sh                  # rodar de novo (idempotente)"
echo "  ./uninstall.sh                # remover containers/imagens/volumes/cache"
echo "  ./backup.sh --out ./backups/  # backup do log de processamento/.env/uploads pendentes"
