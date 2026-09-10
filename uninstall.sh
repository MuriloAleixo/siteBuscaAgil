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
echo "    (inclui o volume do Ollama — os modelos baixados, ~3GB, serão"
echo "    apagados e baixados de novo no próximo ./install.sh)"
echo "  - Remover as imagens Docker buildadas localmente (api/worker/"
echo "    frontend) e a imagem do Ollama"
echo "  - Apagar o conteúdo de media/ e o cache local em data/users/"
echo "    (catálogo + tokens OAuth de cada usuário — sem banco de dados"
echo "    nenhum, é tudo JSON em disco, ver api/stores.py)"
echo "  - Limpar __pycache__/*.pyc do projeto (fora da venv/)"
echo
read -rp "Confirma? Essa ação não pode ser desfeita [s/N]: " confirm
case "$confirm" in
    [sS]|[sS][iI][mM]) ;;
    *) echo "Cancelado."; exit 0 ;;
esac

echo
echo "==> Parando e removendo containers, rede, volumes e imagens locais..."
docker compose down --volumes --rmi local --remove-orphans 2>/dev/null || true

echo "==> Removendo a imagem do Ollama..."
docker rmi ollama/ollama:latest >/dev/null 2>&1 || true

echo "==> Limpando uploads temporários (media/) e cache local do catálogo/perfil (data/users/)..."
find media -mindepth 1 -not -name '.gitkeep' -delete 2>/dev/null || true
find data/users -mindepth 1 -delete 2>/dev/null || true

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
