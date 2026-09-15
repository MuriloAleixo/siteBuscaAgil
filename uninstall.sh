#!/usr/bin/env bash
# uninstall.sh — desfaz tudo que ./install.sh criou: containers, imagens
# buildadas (api/worker/frontend), volumes (incluindo os modelos de IA
# baixados no Ollama e a fila pendente no Redis) e caches locais. Depois de
# rodar, o repositório fica só com código-fonte + arquivos de instrução/
# configuração (README, Dockerfile, docker-compose.yml, install.sh,
# .env.example etc.) — pronto pra rodar ./install.sh de novo do zero, como
# se nunca tivesse sido executado.
set -euo pipefail
cd "$(dirname "$0")"

echo "Isto vai:"
echo "  - Parar e remover os containers, a rede e os volumes deste projeto"
echo "    (inclui o volume do Ollama — os modelos baixados, ~8GB (dois"
echo "    modelos de texto + visão), serão apagados e baixados de novo no"
echo "    próximo ./install.sh)"
echo "  - Remover as imagens Docker buildadas localmente (api/worker/"
echo "    frontend) e a imagem do Ollama"
echo "  - Apagar o conteúdo de media/, o cache local em data/users/ (catálogo"
echo "    + tokens OAuth de cada usuário, JSON em disco, ver api/stores.py)"
echo "    e o log de processamento em data/processing.db (SQLite, ver"
echo "    api/processing_log.py)"
echo "  - Limpar __pycache__/*.pyc do projeto (fora da venv/)"
echo
echo "O log de processamento (data/processing.db) não tem cópia em nenhum"
echo "outro lugar — se quiser guardar antes de apagar, cancele aqui (N) e rode:"
echo "  ./backup.sh --out ./backups/"
echo
read -rp "Confirma? Essa ação não pode ser desfeita [s/N]: " confirm
case "$confirm" in
    [sS]|[sS][iI][mM]) ;;
    *) echo "Cancelado."; exit 0 ;;
esac

echo
echo "==> Corrigindo dono de data/media (containers rodam como root, sem"
echo "    USER no Dockerfile — sem isso, apagar abaixo pode falhar com"
echo "    'Permission denied' em arquivos que o container criou)..."
if docker compose ps api 2>/dev/null | grep -qi "running\|Up"; then
    docker compose exec -T api chown -R "$(id -u):$(id -g)" /app/data /app/media 2>/dev/null || true
fi

echo "==> Parando e removendo containers, rede, volumes e imagens locais..."
docker compose down --volumes --rmi local --remove-orphans 2>/dev/null || true

echo "==> Removendo a imagem do Ollama..."
docker rmi ollama/ollama:latest >/dev/null 2>&1 || true

echo "==> Limpando uploads temporários (media/) e cache local do catálogo/perfil (data/users/)..."
find media -mindepth 1 -not -name '.gitkeep' -delete 2>/dev/null || true
find data/users -mindepth 1 -delete 2>/dev/null || true

echo "==> Limpando o log de processamento (data/processing.db)..."
rm -f data/processing.db data/processing.db-wal data/processing.db-shm

echo "==> Limpando cache do Python (__pycache__, *.pyc)..."
find . -path './venv' -prune -o -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find . -path './venv' -prune -o -type f -name '*.pyc' -exec rm -f {} + 2>/dev/null || true

echo
read -rp "Apagar também o .env (suas chaves GEMINI_API_KEY / GOOGLE_OAUTH_*)? [s/N]: " del_env
case "$del_env" in
    [sS]|[sS][iI][mM])
        rm -f .env
        echo "    .env removido."
        ;;
    *)
        echo "    .env mantido."
        ;;
esac

echo
echo "Pronto. Só sobrou o necessário pra reconstruir o projeto do zero."
echo "Pra subir tudo de novo: ./install.sh"
