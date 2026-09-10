"""
processar_upload.py

Ponto de entrada chamado pelo worker Celery (worker/tasks.py) no momento em
que o cliente envia um arquivo (ou link), ANTES de subir para o Google
Drive.

Fluxo:
    1. recebe o caminho local do arquivo que o cliente enviou (ou uma URL)
    2. extrai/prepara o conteúdo (extrator_conteudo)
    3. envia para classificar (IA local primeiro, Gemini como rede de
       segurança — ver local_ai/router.py)
    4. devolve a classificação, para o worker seguir com o upload real ao
       Drive (api/google_drive.py) e gravar o resultado no catálogo do
       usuário (api/stores.py)

Categoria é ABERTA (não uma lista fixa): o classificador cria a categoria
que melhor descreve o conteúdo, reaproveitando uma já usada pelo usuário
quando fizer sentido — ver `categorias_conhecidas` abaixo e
worker/tasks.py, que monta essa lista a partir do catálogo real antes de
chamar processar_upload().

Uso via linha de comando (teste manual, sem catálogo/categorias prévias):
    python -m scripts.processar_upload /caminho/do/arquivo.pdf
    python -m scripts.processar_upload "https://exemplo.com/pagina"

Uso programático:
    from scripts.processar_upload import processar_upload

    resultado = processar_upload(
        "/tmp/uploads/arquivo_do_cliente.xlsx",
        categorias_conhecidas=["financeiro", "contrato"],
    )
    # resultado = {
    #     "categoria_principal": "financeiro",
    #     "confianca": 0.88,
    #     "tags": ["fechamento de caixa", "julho/2026"],
    #     "descricao": "Planilha com o fechamento de caixa de julho/2026.",
    # }
"""

import logging
import sys
from pathlib import Path
from typing import List, Optional

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from scripts.extrator_conteudo import preparar_conteudo
    from scripts.categorizer_gemini import GeminiCategorizer
    from scripts.local_ai.router import classificar_local, local_ai_habilitada
else:
    from .extrator_conteudo import preparar_conteudo
    from .categorizer_gemini import GeminiCategorizer
    from .local_ai.router import classificar_local, local_ai_habilitada

logger = logging.getLogger(__name__)


# Só usado quando o usuário ainda não tem NENHUMA categoria no catálogo
# (primeiro arquivo dele) — exemplos de estilo pro modelo se inspirar, não
# uma lista fechada. Depois do primeiro arquivo, quem manda são as
# categorias reais que o próprio catálogo já acumulou (ver worker/tasks.py).
CATEGORIAS_EXEMPLO = [
    "financeiro",
    "juridico",
    "recursos humanos",
    "contrato",
    "nota fiscal",
    "relatorio tecnico",
    "marketing",
]


def processar_upload(origem: str, categorias_conhecidas: Optional[List[str]] = None) -> dict:
    """
    origem: caminho local do arquivo enviado pelo cliente, OU uma URL.
    categorias_conhecidas: categorias já usadas no catálogo do usuário —
        passadas como referência pro classificador reaproveitar nomenclatura
        em vez de criar uma categoria quase-duplicada a cada arquivo. Vazio/
        None cai nos CATEGORIAS_EXEMPLO acima (só pro primeiro arquivo).
    Retorna a classificação (categoria, confiança, tags e descrição).

    Tenta a IA local (Ollama, ver scripts/local_ai/) primeiro quando
    LOCAL_AI_ENABLED estiver ligado; qualquer falha (container fora do ar,
    tipo ainda não suportado localmente etc.) cai pro Gemini, sem mudar o
    formato do retorno.
    """
    categorias = categorias_conhecidas or CATEGORIAS_EXEMPLO

    if local_ai_habilitada():
        try:
            return classificar_local(origem, categorias)
        except Exception as exc:  # noqa: BLE001 - IA local é best-effort, cai pro Gemini
            logger.warning("IA local não conseguiu classificar '%s', caindo pro Gemini: %s", origem, exc)

    conteudo = preparar_conteudo(origem)

    categorizer = GeminiCategorizer()
    classificacao = categorizer.classificar(conteudo, categorias)

    return {
        "categoria_principal": classificacao.categoria_principal,
        "confianca": classificacao.confianca,
        "tags": classificacao.tags,
        "descricao": classificacao.descricao,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python -m scripts.processar_upload <caminho_do_arquivo_ou_url>")
        sys.exit(1)

    resultado = processar_upload(sys.argv[1])
    print("\nClassificação concluída:")
    for chave, valor in resultado.items():
        print(f"  {chave}: {valor}")
