"""
processar_upload.py

Ponto de entrada a ser chamado pelo backend do site, no momento em que o
cliente envia um arquivo (ou link), ANTES de subir para o Google Drive.

Fluxo:
    1. recebe o caminho local do arquivo que o cliente enviou (ou uma URL)
    2. extrai/prepara o conteúdo (extrator_conteudo)
    3. envia para o Gemini classificar (categorizer_gemini)
    4. salva o retorno no catalog.json local
    5. devolve o file_id + a classificação, para o seu backend seguir com
       o upload real ao Drive e depois chamar catalog.update_cloud_path(...)

Uso via linha de comando (teste manual):
    python -m scripts.processar_upload /caminho/do/arquivo.pdf
    python -m scripts.processar_upload "https://exemplo.com/pagina"

Uso programático (dentro do seu backend):
    from scripts.processar_upload import processar_upload

    resultado = processar_upload("/tmp/uploads/arquivo_do_cliente.xlsx")
    # resultado = {
    #     "file_id": "f_a1b2c3d4",
    #     "categoria_principal": "financeiro",
    #     "tags": ["financeiro", "relatorio tecnico"],
    #     "descricao": "Planilha com o fechamento de caixa de julho/2026.",
    #     "scores": {...}
    # }
    #
    # ... aqui seu backend faz o upload real pro Drive ...
    #
    # depois, com o link/ID que o Drive retornou:
    from scripts.file_catalog import FileCatalog
    catalog = FileCatalog("catalog.json")
    catalog.update_cloud_path(resultado["file_id"], drive_file_url)
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from scripts.extrator_conteudo import preparar_conteudo, eh_link
    from scripts.categorizer_gemini import GeminiCategorizer
    from scripts.file_catalog import FileCatalog
else:
    from .extrator_conteudo import preparar_conteudo, eh_link
    from .categorizer_gemini import GeminiCategorizer
    from .file_catalog import FileCatalog


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

CATALOG_PATH = "catalog.json"


def processar_upload(origem: str, catalog_path: str = CATALOG_PATH) -> dict:
    """
    origem: caminho local do arquivo enviado pelo cliente, OU uma URL.
    Retorna um dict com o file_id gerado e a classificação completa.
    """
    nome_arquivo = origem if eh_link(origem) else Path(origem).name

    conteudo = preparar_conteudo(origem)

    categorizer = GeminiCategorizer()
    classificacao = categorizer.classificar(conteudo, CATEGORIAS_POSSIVEIS)

    scores_dict = {item.categoria: item.score for item in classificacao.scores}

    catalog = FileCatalog(catalog_path)
    file_id = catalog.add_file(
        filename=nome_arquivo,
        cloud_path=None,  # ainda não subiu pro Drive nesse momento
        category=classificacao.categoria_principal,
        tags=classificacao.tags,
        description=classificacao.descricao,
        extra_metadata={"classificacao_scores": scores_dict},
    )

    return {
        "file_id": file_id,
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
