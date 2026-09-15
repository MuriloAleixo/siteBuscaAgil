#!/usr/bin/env bash
# backup.sh — faz e restaura backup do ESTADO LOCAL do BuscaÁgil: tudo que
# não é reconstruído sozinho por ./install.sh nem vive no Google Drive do
# usuário (que é a fonte da verdade dos arquivos em si, ver ARQUITETURA.md).
# Depois de um ./install.sh do zero numa máquina nova, rodar
# `./backup.sh --in <arquivo>` deixa o sistema no mesmo ponto de quando o
# backup foi feito com `./backup.sh --out <arquivo>` — mesmo log de
# processamento, mesmos uploads pendentes, mesma configuração. Só falta
# logar com Google de novo (não entra no backup, ver "fica de fora" abaixo).
#
# O que ENTRA no backup:
#   data/processing.db  log de eventos de processamento — SQLite, só existe
#                        aqui, não tem nenhum espelho no Drive (ver
#                        api/processing_log.py) — sem isso, perdido pra sempre
#   media/               uploads que ainda não confirmaram no Drive (raro;
#                        normalmente vazio — só sobra algo aqui se um envio
#                        falhou antes de subir, ver worker/tasks.py)
#   .env                 chaves/config (GEMINI_API_KEY, OAuth, limites de
#                        CPU/RAM etc.) — contém segredo, guarde o backup com
#                        o mesmo cuidado que guardaria o próprio .env
#
# O que fica DE FORA de propósito:
#   data/users/<id>/    cache local (catálogo + tokens OAuth, ver
#                        api/stores.py) — 100% reconstruível: é só um espelho
#                        do que já está no Drive, e o próximo login já
#                        recria tudo sozinho (acha a pasta buscaagil_upload
#                        existente e baixa o catálogo de novo, ver
#                        ARQUITETURA.md § 4). Sem backup, o único efeito é
#                        precisar logar de novo depois de restaurar — nenhum
#                        dado é perdido, então não compensa carregar tokens
#                        OAuth extras dentro do arquivo de backup.
#   modelos do Ollama (volume ollama_data, alguns GB, baixados de novo por
#     ./install.sh)
#   fila pendente no Redis (broker — perder uma tarefa em voo por causa de
#     restart já é esperado num sistema de fila, não faz sentido persistir)
#   código-fonte (isso é o git)
#
# Uso:
#   ./backup.sh --out backup.tar.gz          # cria o backup nesse arquivo
#   ./backup.sh --out ./backups/             # nome com timestamp automático
#   ./backup.sh --in backup.tar.gz           # restaura (pede confirmação)
#   ./backup.sh --in backup.tar.gz --yes     # restaura sem confirmar (scripts/CI)
set -euo pipefail
cd "$(dirname "$0")"

MODE=""
TARGET=""
ASSUME_YES=false

usage() {
    echo "Uso:"
    echo "  ./backup.sh --out <arquivo.tar.gz|diretório>   # cria um backup"
    echo "  ./backup.sh --in <arquivo.tar.gz>               # restaura um backup"
    echo "  ./backup.sh --in <arquivo.tar.gz> --yes         # restaura sem confirmar"
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --out)
            [ -n "$MODE" ] && { echo "Use --out OU --in, não os dois."; usage; }
            MODE="out"; TARGET="${2:-}"; shift 2 ;;
        --in)
            [ -n "$MODE" ] && { echo "Use --out OU --in, não os dois."; usage; }
            MODE="in"; TARGET="${2:-}"; shift 2 ;;
        --yes|-y)
            ASSUME_YES=true; shift ;;
        -h|--help)
            usage ;;
        *)
            echo "Opção desconhecida: $1"; usage ;;
    esac
done

[ -z "$MODE" ] && usage
[ -z "$TARGET" ] && { echo "Faltou o caminho do arquivo depois de --$MODE."; usage; }

# Nomes fixos dentro do .tar.gz — independem de onde o backup foi criado ou
# vai ser restaurado.
MANIFEST_NAME="backup-manifest.txt"

# ---------------------------------------------------------------------------
# Snapshot seguro do SQLite: se a api estiver no ar, pede pra ela mesma fazer
# a cópia (sqlite3 Connection.backup() — consistente mesmo com o worker
# escrevendo ao mesmo tempo, ver api/processing_log.py). Sem container no
# ar, copia o arquivo direto — seguro, porque nada estaria escrevendo nele.
#
# O snapshot é escrito em /tmp DENTRO do container, não em data/ (bind
# mount) — os containers rodam como root (sem USER no Dockerfile), então um
# arquivo criado direto em data/ nasceria dono root no host, e o host não
# consegue nem apagar depois. "docker compose cp" tira o arquivo do
# container pro host já com o dono de quem roda este script.
# ---------------------------------------------------------------------------
snapshot_processing_db() {
    local dest="$1" # caminho de destino do snapshot
    if [ ! -f data/processing.db ]; then
        return 0
    fi
    if command -v docker >/dev/null 2>&1 \
        && docker compose ps api 2>/dev/null | grep -qi "running\|Up"; then
        docker compose exec -T api rm -f /tmp/buscaagil_backup_snapshot.db >/dev/null 2>&1 || true
        if docker compose exec -T api python -c "
import sqlite3
src = sqlite3.connect('data/processing.db')
dst = sqlite3.connect('/tmp/buscaagil_backup_snapshot.db')
src.backup(dst)
dst.close()
src.close()
" 2>/dev/null && docker compose cp api:/tmp/buscaagil_backup_snapshot.db "$dest" >/dev/null 2>&1; then
            docker compose exec -T api rm -f /tmp/buscaagil_backup_snapshot.db >/dev/null 2>&1 || true
            return 0
        fi
        docker compose exec -T api rm -f /tmp/buscaagil_backup_snapshot.db >/dev/null 2>&1 || true
        echo "    (aviso: backup consistente via container falhou, copiando o arquivo direto)"
    fi
    cp data/processing.db "$dest"
}

# ---------------------------------------------------------------------------
# Corrige o dono de data/ e media/ pro usuário que roda este script. Sem
# isso, arquivos criados pelos containers (root, sem USER no Dockerfile) na
# primeira vez que subiram ficam intocáveis pro host — nem apagar dá.
# Precisa de um container no ar (ele mesmo faz o chown de dentro); sem
# container, não tem como corrigir por aqui (mostra o que rodar na mão).
# ---------------------------------------------------------------------------
fix_data_ownership() {
    if ! command -v docker >/dev/null 2>&1 || ! docker compose ps api 2>/dev/null | grep -qi "running\|Up"; then
        return 0
    fi
    docker compose exec -T api chown -R "$(id -u):$(id -g)" /app/data /app/media 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# --out: criar o backup
# ---------------------------------------------------------------------------
do_backup() {
    local out_file="$TARGET"
    if [ -d "$out_file" ] || [[ "$out_file" == */ ]]; then
        mkdir -p "$out_file"
        out_file="${out_file%/}/buscaagil-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    else
        mkdir -p "$(dirname "$out_file")"
    fi

    fix_data_ownership

    echo "==> Preparando snapshot..."
    local stage
    stage=$(mktemp -d)
    trap '[ -n "${stage:-}" ] && rm -rf "$stage"; true' EXIT

    mkdir -p "$stage/data"
    if [ -f data/processing.db ]; then
        snapshot_processing_db "$stage/data/processing.db"
        echo "    data/processing.db copiado (snapshot consistente)"
    else
        echo "    data/processing.db não existe ainda — pulado"
    fi

    if [ -d media ]; then
        mkdir -p "$stage/media"
        find media -mindepth 1 -not -name '.gitkeep' -exec cp -a {} "$stage/media/" \; 2>/dev/null || true
        echo "    media/ copiado (só o que ainda não subiu pro Drive, normalmente vazio)"
    fi

    if [ -f .env ]; then
        cp .env "$stage/.env"
        echo "    .env copiado (contém segredo — trate o backup como tal)"
    else
        echo "    .env não existe — pulado (rode ./install.sh antes de restaurar)"
    fi

    {
        echo "BuscaÁgil — backup criado em $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        echo "host: $(hostname 2>/dev/null || echo desconhecido)"
    } > "$stage/$MANIFEST_NAME"

    echo "==> Compactando..."
    tar -czf "$out_file" -C "$stage" .

    echo
    echo "Backup criado em: $out_file ($(du -h "$out_file" | cut -f1))"
}

# ---------------------------------------------------------------------------
# --in: restaurar o backup
# ---------------------------------------------------------------------------
do_restore() {
    local in_file="$TARGET"
    if [ ! -f "$in_file" ]; then
        echo "Arquivo de backup não encontrado: $in_file"
        exit 1
    fi

    local stage
    stage=$(mktemp -d)
    trap '[ -n "${stage:-}" ] && rm -rf "$stage"; true' EXIT
    tar -xzf "$in_file" -C "$stage"

    if [ -f "$stage/$MANIFEST_NAME" ]; then
        echo "==> Backup selecionado:"
        sed 's/^/    /' "$stage/$MANIFEST_NAME"
        echo
    fi

    echo "Isto vai SOBRESCREVER o estado local atual:"
    [ -f data/processing.db ] && echo "  - data/processing.db (log de processamento)"
    [ -d media ] && echo "  - media/ (uploads temporários)"
    [ -f .env ] && echo "  - .env (chaves/config)"
    echo "O estado atual (se existir) é movido pra *.before-restore-<timestamp>"
    echo "ao lado, não é apagado — dá pra recuperar na mão se precisar."
    echo

    if [ "$ASSUME_YES" != true ]; then
        read -rp "Confirma a restauração? [s/N]: " confirm
        case "$confirm" in
            [sS]|[sS][iI][mM]) ;;
            *) echo "Cancelado."; exit 0 ;;
        esac
    fi

    # Precisa rodar ANTES de parar os containers (fix_data_ownership exec
    # pra dentro do "api" pra corrigir o dono de data/media no host).
    fix_data_ownership

    local stopped_containers=false
    if command -v docker >/dev/null 2>&1 && docker compose ps -q 2>/dev/null | grep -q .; then
        echo "==> Parando api/worker pra restaurar sem concorrência de escrita..."
        docker compose stop api worker >/dev/null 2>&1 || true
        stopped_containers=true
    fi

    local ts
    ts=$(date +%Y%m%d-%H%M%S)

    echo "==> Restaurando..."
    if [ -f "$stage/data/processing.db" ]; then
        mkdir -p data
        [ -f data/processing.db ] && mv data/processing.db "data/processing.db.before-restore-$ts"
        rm -f data/processing.db-wal data/processing.db-shm
        cp -a "$stage/data/processing.db" data/processing.db
        echo "    data/processing.db restaurado"
    fi

    if [ -d "$stage/media" ]; then
        mkdir -p media
        if [ -d media ] && [ -n "$(find media -mindepth 1 -not -name '.gitkeep' 2>/dev/null)" ]; then
            mkdir -p "media.before-restore-$ts"
            find media -mindepth 1 -not -name '.gitkeep' -exec mv {} "media.before-restore-$ts/" \;
        fi
        find "$stage/media" -mindepth 1 -exec cp -a {} media/ \; 2>/dev/null || true
        echo "    media/ restaurado"
    fi

    if [ -f "$stage/.env" ]; then
        [ -f .env ] && mv .env ".env.before-restore-$ts"
        cp "$stage/.env" .env
        echo "    .env restaurado"
    fi

    if [ "$stopped_containers" = true ]; then
        echo "==> Religando api/worker..."
        docker compose start api worker >/dev/null 2>&1 || true
    fi

    echo
    echo "Restauração concluída. Se os containers não estavam no ar, suba com:"
    echo "  ./install.sh"
}

if [ "$MODE" = "out" ]; then
    do_backup
else
    do_restore
fi
