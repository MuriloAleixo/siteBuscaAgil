"""
extrator_conteudo.py

Prepara o conteúdo de um arquivo (ou link) para ser enviado ao Gemini.

Duas saídas possíveis:
  - {"tipo": "texto", "conteudo": "..."}          -> vai como texto no prompt
  - {"tipo": "arquivo", "caminho": "...", "mime_type": "..."} -> vai como
    parte binária nativa (imagem/PDF), o Gemini processa diretamente

Formatos cobertos: txt, csv, xlsx, xls, doc, docx, jpg, jpeg, png, e links (http/https).
"""

from pathlib import Path
from urllib.parse import urlparse


MIME_TYPES_NATIVOS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def eh_link(origem: str) -> bool:
    return urlparse(origem).scheme in ("http", "https")


def _extrair_txt(caminho: str) -> str:
    return Path(caminho).read_text(encoding="utf-8", errors="ignore")


def _extrair_csv(caminho: str) -> str:
    # manda o CSV cru como texto — o Gemini entende bem tabela em texto puro,
    # não precisa parsear em DataFrame só pra classificar o conteúdo
    return Path(caminho).read_text(encoding="utf-8", errors="ignore")


def _extrair_xlsx_xls(caminho: str) -> str:
    """
    Requer: pip install openpyxl xlrd --break-system-packages
    (openpyxl para .xlsx, xlrd para .xls antigo)
    """
    import pandas as pd

    planilhas = pd.read_excel(caminho, sheet_name=None)  # todas as abas
    partes = []
    for nome_aba, df in planilhas.items():
        partes.append(f"### Aba: {nome_aba}\n{df.to_csv(index=False)}")
    return "\n\n".join(partes)


def _extrair_docx(caminho: str) -> str:
    """Requer: pip install python-docx --break-system-packages"""
    import docx

    doc = docx.Document(caminho)
    partes = [p.text for p in doc.paragraphs]
    for tabela in doc.tables:
        for linha in tabela.rows:
            partes.append(" | ".join(c.text for c in linha.cells))
    return "\n".join(partes)


def _extrair_doc(caminho: str) -> str:
    """
    .doc é um formato binário legado (não é ZIP como .docx), então
    python-docx não lê. Requer o utilitário 'antiword' instalado no sistema:
        sudo apt-get install antiword
    Se preferir não instalar dependência de sistema, converta o .doc para
    .docx antes (LibreOffice: soffice --headless --convert-to docx arquivo.doc)
    e chame _extrair_docx nele.
    """
    import subprocess

    try:
        resultado = subprocess.run(
            ["antiword", caminho], capture_output=True, text=True, check=True
        )
        return resultado.stdout
    except FileNotFoundError:
        raise RuntimeError(
            "Utilitário 'antiword' não encontrado para ler .doc legado. "
            "Instale com 'sudo apt-get install antiword' ou converta o "
            "arquivo para .docx antes de processar."
        )


def _extrair_link(url: str) -> str:
    """Requer: pip install requests beautifulsoup4 --break-system-packages"""
    import requests
    from bs4 import BeautifulSoup

    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    texto = soup.get_text(separator="\n")
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    return "\n".join(linhas)


def preparar_conteudo(origem: str) -> dict:
    """
    origem: caminho de arquivo local OU uma URL.
    Retorna um dict pronto pra passar ao classificador Gemini.
    """
    if eh_link(origem):
        texto = _extrair_link(origem)
        return {"tipo": "texto", "conteudo": texto, "nome_display": origem}

    caminho = Path(origem)
    ext = caminho.suffix.lower()

    if ext in MIME_TYPES_NATIVOS:
        return {
            "tipo": "arquivo",
            "caminho": str(caminho),
            "mime_type": MIME_TYPES_NATIVOS[ext],
            "nome_display": caminho.name,
        }

    extratores_texto = {
        ".txt": _extrair_txt,
        ".csv": _extrair_csv,
        ".xlsx": _extrair_xlsx_xls,
        ".xls": _extrair_xlsx_xls,
        ".docx": _extrair_docx,
        ".doc": _extrair_doc,
    }

    if ext not in extratores_texto:
        raise ValueError(f"Formato não suportado: {ext}")

    texto = extratores_texto[ext](str(caminho))
    return {"tipo": "texto", "conteudo": texto, "nome_display": caminho.name}
