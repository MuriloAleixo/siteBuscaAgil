"""
processar_upload.py

Ponto de entrada chamado pelo worker Celery (core/tasks.py) no momento em
que o cliente envia um arquivo (ou link), ANTES de subir para o Google
Drive.

Fluxo:
    1. recebe o caminho local do arquivo que o cliente enviou (ou uma URL)
    2. extrai/prepara o conteúdo (extrator_conteudo)
    3. envia para o Gemini classificar (categorizer_gemini)
    4. devolve a classificação, para o backend seguir com o upload real ao
       Drive (core/google_drive.py) e gravar o resultado no catálogo do
       usuário (core/uploaded_files_store.py)

Uso via linha de comando (teste manual):
    python -m scripts.processar_upload /caminho/do/arquivo.pdf
    python -m scripts.processar_upload "https://exemplo.com/pagina"

Uso programático:
    from scripts.processar_upload import processar_upload

    resultado = processar_upload("/tmp/uploads/arquivo_do_cliente.xlsx")
    # resultado = {
    #     "categoria_principal": "financeiro",
    #     "tags": ["financeiro", "relatorio tecnico"],
    #     "descricao": "Planilha com o fechamento de caixa de julho/2026.",
    #     "scores": {...}
    # }
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from scripts.extrator_conteudo import preparar_conteudo
    from scripts.categorizer_gemini import GeminiCategorizer
else:
    from .extrator_conteudo import preparar_conteudo
    from .categorizer_gemini import GeminiCategorizer


CATEGORIAS_POSSIVEIS = [
    "financeiro",
    "juridico",
    "recursos humanos",
    "contrato",
    "nota fiscal",
    "relatorio tecnico",
    "marketing",
    "outros",
]


def processar_upload(origem: str) -> dict:
    """
    origem: caminho local do arquivo enviado pelo cliente, OU uma URL.
    Retorna a classificação (categoria, tags, descrição e scores).
    """
    conteudo = preparar_conteudo(origem)

    categorizer = GeminiCategorizer()
    classificacao = categorizer.classificar(conteudo, CATEGORIAS_POSSIVEIS)

    scores_dict = {item.categoria: item.score for item in classificacao.scores}

    return {
        "categoria_principal": classificacao.categoria_principal,
        "tags": classificacao.tags,
        "descricao": classificacao.descricao,
        "scores": scores_dict,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python -m scripts.processar_upload <caminho_do_arquivo_ou_url>")
        sys.exit(1)

    resultado = processar_upload(sys.argv[1])
    print("\nClassificação concluída:")
    for chave, valor in resultado.items():
        print(f"  {chave}: {valor}")
