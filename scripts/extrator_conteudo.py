"""
extrator_conteudo.py

Prepara o conteúdo de um arquivo (ou link) para ser enviado ao classificador
(Gemini ou IA local).

Duas saídas possíveis:
  - {"tipo": "texto", "conteudo": "..."}          -> vai como texto no prompt
  - {"tipo": "arquivo", "caminho": "...", "mime_type": "..."} -> vai como
    parte binária nativa (imagem/PDF), o Gemini processa diretamente

Formatos cobertos: txt, py, csv, xlsx, xls, doc, docx, jpg, jpeg, png, pdf,
e links (http/https) — com tratamento especial pra YouTube (título +
transcrição/legenda do vídeo, não só o HTML da página) e priorização de
título/meta-descrição pra qualquer outro link (ver `_extrair_link`).
"""

import logging
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


MIME_TYPES_NATIVOS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def eh_link(origem: str) -> bool:
    return urlparse(origem).scheme in ("http", "https")


def _eh_youtube(url: str) -> bool:
    # Checa se "youtube.com"/"youtu.be" aparece no host (em vez de bater
    # contra um set fixo de hosts exatos) pra cobrir subdomínios que
    # aparecem na prática (m.youtube.com, music.youtube.com, links
    # compartilhados de dentro do app etc.) sem precisar listar cada um.
    host = urlparse(url).netloc.lower()
    return host.endswith("youtube.com") or host.endswith("youtu.be")


def _extrair_txt(caminho: str) -> str:
    return Path(caminho).read_text(encoding="utf-8", errors="ignore")


def _extrair_csv(caminho: str) -> str:
    # manda o CSV cru como texto — o classificador entende bem tabela em
    # texto puro, não precisa parsear em DataFrame só pra classificar
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


def _extrair_pptx(caminho: str) -> str:
    """Requer: pip install python-pptx --break-system-packages

    Extrai o texto de cada slide (título, corpo, tabelas) e também as
    anotações do apresentador (speaker notes) — muitas vezes é lá que está
    o contexto real do que o slide fala, não só no texto visível."""
    from pptx import Presentation

    prs = Presentation(caminho)
    partes = []
    for i, slide in enumerate(prs.slides, start=1):
        textos_slide = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragrafo in shape.text_frame.paragraphs:
                    texto = "".join(run.text for run in paragrafo.runs)
                    if texto.strip():
                        textos_slide.append(texto)
            if shape.has_table:
                for linha in shape.table.rows:
                    textos_slide.append(" | ".join(celula.text for celula in linha.cells))

        notas = ""
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            notas = slide.notes_slide.notes_text_frame.text.strip()

        bloco = f"### Slide {i}\n" + "\n".join(textos_slide)
        if notas:
            bloco += f"\nAnotações: {notas}"
        partes.append(bloco)

    return "\n\n".join(partes)


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
    """Requer: pip install requests beautifulsoup4 --break-system-packages

    Título e meta-descrição vêm PRIMEIRO no texto retornado, de propósito:
    o classificador trunca o conteúdo em 12000 caracteres (ver
    categorizer_gemini.py/categorizer_local.py) — numa página longa, sem
    isso o sinal mais confiável (o que a própria página diz que é) podia
    nem chegar a ser lido."""
    import requests
    from bs4 import BeautifulSoup

    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    partes_prioritarias = []
    if soup.title and soup.title.string and soup.title.string.strip():
        partes_prioritarias.append(f"Título da página: {soup.title.string.strip()}")
    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    if meta_desc and meta_desc.get("content"):
        partes_prioritarias.append(f"Descrição da página: {meta_desc['content'].strip()}")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    texto = soup.get_text(separator="\n")
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    corpo = "\n".join(linhas)

    return "\n\n".join(partes_prioritarias + [corpo]) if partes_prioritarias else corpo


def _extrair_video_id_youtube(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if "youtu.be" in host:
        video_id = parsed.path.strip("/")
        return video_id or None

    if "youtube.com" in host:
        query = parse_qs(parsed.query)
        if "v" in query:
            return query["v"][0]
        partes = [p for p in parsed.path.split("/") if p]
        if len(partes) >= 2 and partes[0] in ("shorts", "embed", "live"):
            return partes[1]

    return None


def _extrair_youtube(url: str) -> str:
    """Título/canal via oEmbed (endpoint público do YouTube, sem precisar de
    API key) + transcrição/legenda do vídeo (se existir) — dá pra
    classificar pelo CONTEÚDO real falado no vídeo, não só pelo título.
    O HTML puro da página do YouTube não serve pra nada aqui: é uma SPA
    renderizada via JS, praticamente sem texto útil no `requests.get` cru.
    """
    import requests

    video_id = _extrair_video_id_youtube(url)
    logger.info("Extraindo conteúdo do YouTube: url='%s' video_id='%s'", url, video_id)

    partes = []
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=10,
        )
        resp.raise_for_status()
        info = resp.json()
        if info.get("title"):
            partes.append(f"Título do vídeo: {info['title']}")
        if info.get("author_name"):
            partes.append(f"Canal: {info['author_name']}")
    except (requests.RequestException, ValueError) as exc:
        # ValueError cobre resp.json() falhando (corpo não é JSON válido) —
        # requests.exceptions.JSONDecodeError é subclasse de ValueError, não
        # de RequestException, então sem isso o erro escapava sem log.
        logger.warning("Não foi possível buscar metadados oEmbed do YouTube para '%s': %s", url, exc)

    if video_id:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            # API 1.x: instância + .fetch() (o classmethod .get_transcript()
            # da 0.6.x foi removido) — devolve um FetchedTranscript iterável
            # de snippets com atributo .text.
            transcript = YouTubeTranscriptApi().fetch(video_id, languages=["pt", "pt-BR", "en"])
            texto_legendas = " ".join(snippet.text for snippet in transcript).strip()
            if texto_legendas:
                partes.append(f"Transcrição/legenda do vídeo:\n{texto_legendas}")
        except Exception as exc:  # noqa: BLE001 - nem todo vídeo tem legenda; melhor sem do que quebrar
            logger.warning("Não foi possível obter a transcrição do YouTube '%s': %s", video_id, exc)

    if not partes:
        # NUNCA cai pro scraping genérico de HTML aqui: a página do YouTube
        # é uma SPA praticamente vazia de conteúdo real no HTML cru — o que
        # sobra é rodapé institucional (links "Sobre"/"Imprensa"/direitos
        # autorais da Google LLC), que já classificou vídeos errado no
        # passado por parecer conteúdo real sem ser. Melhor falhar alto e
        # deixar o arquivo sem categoria do que classificar com lixo.
        raise RuntimeError(
            f"Não foi possível obter título nem transcrição do vídeo do YouTube '{url}' "
            "(oEmbed e legendas falharam — confira os logs do worker pra ver o motivo)."
        )

    return "\n\n".join(partes)


def preparar_conteudo(origem: str) -> dict:
    """
    origem: caminho de arquivo local OU uma URL.
    Retorna um dict pronto pra passar ao classificador.
    """
    if eh_link(origem):
        texto = _extrair_youtube(origem) if _eh_youtube(origem) else _extrair_link(origem)
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
        ".py": _extrair_txt,
        ".csv": _extrair_csv,
        ".xlsx": _extrair_xlsx_xls,
        ".xls": _extrair_xlsx_xls,
        ".docx": _extrair_docx,
        ".doc": _extrair_doc,
        ".pptx": _extrair_pptx,
    }

    if ext not in extratores_texto:
        raise ValueError(f"Formato não suportado: {ext}")

    texto = extratores_texto[ext](str(caminho))
    return {"tipo": "texto", "conteudo": texto, "nome_display": caminho.name}
