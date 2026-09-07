#!/usr/bin/env bash
# install.sh — sobe o BuscaÁgil inteiro (Django, Celery+Redis, IA local via
# Ollama) do zero, só com Docker instalado. Veja README.md, seção
# "Rodar Com Docker (Recomendado)".
set -euo pipefail
cd "$(dirname "$0")"

TEXT_MODEL="qwen2.5:3b-instruct"
VISION_MODEL="moondream"

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

echo "==> Subindo o Django (web) e o worker do Celery..."
docker compose up -d web worker

echo "==> Dando um tempo pros containers recém-criados terminarem de subir..."
sleep 5

echo
echo "==> Rodando smoke tests..."
echo

smoke_fail=0

# 1. Ollama respondendo e com os dois modelos baixados. Output é capturado
# numa variável e comparado com 'case' (em vez de "| grep -q") de propósito:
# com "set -o pipefail", "cmd | grep -q X" pode contar como falha mesmo
# quando X é encontrado, porque o "-q" fecha o pipe assim que acha o
# primeiro match e isso pode derrubar "cmd" com SIGPIPE antes dela terminar.
ollama_list_output=$(docker compose exec -T ollama ollama list 2>/dev/null) || true
ollama_ok_models=false
case "$ollama_list_output" in
    *"$TEXT_MODEL"*"$VISION_MODEL"*|*"$VISION_MODEL"*"$TEXT_MODEL"*) ollama_ok_models=true ;;
esac
if [ "$ollama_ok_models" = true ]; then
    echo "  [OK]     Ollama respondendo, com $TEXT_MODEL e $VISION_MODEL baixados"
else
    echo "  [FALHOU] Ollama não respondeu ou os modelos não foram baixados"
    smoke_fail=1
fi

# 2. Django respondendo em :8000 (curl já devolve "000" em %{http_code}
# quando a conexão falha, então não precisa de fallback extra aqui).
http_code="000"
for _ in $(seq 1 15); do
    http_code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ 2>/dev/null)
    [ "$http_code" != "000" ] && [ -n "$http_code" ] && break
    http_code="000"
    sleep 1
done
if [ "$http_code" = "200" ] || [ "$http_code" = "302" ]; then
    echo "  [OK]     Django respondendo em http://localhost:8000/ (HTTP $http_code)"
else
    echo "  [FALHOU] Django não respondeu como esperado em :8000 (HTTP $http_code)"
    smoke_fail=1
fi

# 3. Worker do Celery respondendo a um ping via broker — rodado a partir do
# container "web" (não do "worker"), de propósito: o worker conversando com
# o próprio Redis é só localhost dentro do mesmo container e não prova nada
# sobre a rede entre containers, que é o caminho que o /upload de verdade
# usa (CELERY_BROKER_URL=redis://worker:6379/0 visto do lado do web). Já
# aconteceu do Redis do worker recusar conexão vinda de fora (protected
# mode) enquanto esse ping "de dentro" continuava respondendo normalmente.
celery_ok=false
for _ in $(seq 1 5); do
    ping_output=$(docker compose exec -T web celery -A busca_agil inspect ping --timeout 10 2>/dev/null) || true
    case "$ping_output" in
        *pong*) celery_ok=true; break ;;
    esac
    sleep 3
done
if [ "$celery_ok" = true ]; then
    echo "  [OK]     Worker respondeu ao ping enviado pelo web (broker acessível pela rede)"
else
    echo "  [FALHOU] Web não conseguiu falar com o worker pelo broker Redis"
    smoke_fail=1
fi

# 4. Classificação de arquivo ponta-a-ponta (IA local, com fallback pro
# Gemini já embutido no próprio processar_upload) — não derruba o setup se
# falhar, só avisa, já que depende de GEMINI_API_KEY/rede como plano B.
echo "teste smoke install.sh: contrato de prestação de serviços" > /tmp/install_smoke_test.txt
docker compose cp /tmp/install_smoke_test.txt web:/tmp/install_smoke_test.txt >/dev/null 2>&1 || true
classify_output=$(docker compose exec -T web python -m scripts.processar_upload /tmp/install_smoke_test.txt 2>/dev/null) || true
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
docker compose exec -T web rm -f /tmp/install_smoke_test.txt >/dev/null 2>&1 || true

echo
if [ "$smoke_fail" -ne 0 ]; then
    echo "Alguns smoke tests falharam — confira 'docker compose logs' antes de usar."
    exit 1
fi

echo "Tudo pronto! Acesse: http://localhost:8000/"
echo
echo "Comandos úteis:"
echo "  docker compose logs -f        # acompanhar os logs de tudo"
echo "  docker compose logs -f worker # só o worker (classificação de arquivos)"
echo "  docker compose down           # parar tudo"
echo "  ./install.sh                  # rodar de novo (idempotente)"
echo "  ./uninstall.sh                # remover containers/imagens/volumes/cache"
