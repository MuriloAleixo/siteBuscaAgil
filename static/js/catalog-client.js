// =============================================================
// MOCK DATA — o usuário já vem do backend real (ver static/js/auth.js e
// core/context_processors.py); o que resta aqui é só o catálogo de tipos
// de arquivo (ícones/cores) e a lista de arquivos, populada em runtime.
// =============================================================

const FILE_TYPES = {
  image:    { label: "Imagem",    icon: "image",        color: "#06b6d4",  bg: "rgba(6,182,212,0.12)" },
  pdf:      { label: "PDF",       icon: "file-text",    color: "#f97316",  bg: "rgba(249,115,22,0.12)" },
  video:    { label: "Vídeo",     icon: "play-circle",  color: "#a855f7",  bg: "rgba(168,85,247,0.12)" },
  doc:      { label: "Documento", icon: "file",         color: "#3b82f6",  bg: "rgba(59,130,246,0.12)" },
  sheet:    { label: "Planilha",  icon: "table",        color: "#22c55e",  bg: "rgba(34,197,94,0.12)"  },
  link:     { label: "Link",      icon: "link",         color: "#eab308",  bg: "rgba(234,179,8,0.12)"  },
  audio:    { label: "Áudio",     icon: "music",        color: "#ec4899",  bg: "rgba(236,72,153,0.12)" },
  archive:  { label: "Arquivo",   icon: "archive",      color: "#8888aa",  bg: "rgba(136,136,170,0.12)"},
};

// Sem dados estáticos: a lista é populada em runtime por loadUploadedFiles(),
// que busca os arquivos reais em /files (catálogo do usuário logado, ver
// api/stores.py).
const MOCK_FILES = [];

// =============================================================
// Helper Functions
// =============================================================

function formatFileSize(bytes) {
  if (bytes === 0) return "—";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

function formatDate(isoString) {
  const date = new Date(isoString);
  return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

function getFileTypeInfo(type) {
  return FILE_TYPES[type] || FILE_TYPES["archive"];
}

function getFileById(id) {
  return MOCK_FILES.find((f) => f.id === id) || null;
}

// Lê o cookie "csrftoken" que a api seta em toda resposta (ver
// api/csrf.py) — precisa ir no header X-CSRFToken de qualquer POST
// (upload, add-link, editar classificação, excluir), senão a api recusa
// com 403.
function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

// =============================================================
// Critério de busca local (fallback quando a query é vazia ou quando o
// smart_search do backend falha/está indisponível) — mesma lógica de
// core/text_match.py (normalizar acento + fuzzy matching), aplicada aos
// MESMOS campos (nome, descrição, categoria, tags), pra não ter mais dois
// motores de busca com critério diferente.
// =============================================================

const SEARCH_FUZZY_THRESHOLD = 80;

// Só pro tier "solto" (fuzzy sobre nome+descrição+categoria+tags, quando
// nada mais específico bateu) — mais rígido que o SEARCH_FUZZY_THRESHOLD
// geral pra não deixar uma query curta bater raso em qualquer arquivo
// (mesmo critério de api/text_match.py::FALLBACK_FUZZY_THRESHOLD).
const FALLBACK_FUZZY_THRESHOLD = 85;

function normalizeText(text) {
  return (text || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function levenshteinDistance(a, b) {
  if (a === b) return 0;
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;

  let prevRow = new Array(b.length + 1);
  let currRow = new Array(b.length + 1);
  for (let j = 0; j <= b.length; j++) prevRow[j] = j;

  for (let i = 1; i <= a.length; i++) {
    currRow[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      currRow[j] = Math.min(prevRow[j] + 1, currRow[j - 1] + 1, prevRow[j - 1] + cost);
    }
    [prevRow, currRow] = [currRow, prevRow];
  }
  return prevRow[b.length];
}

function similarityRatio(a, b) {
  if (!a.length && !b.length) return 100;
  const dist = levenshteinDistance(a, b);
  return (1 - dist / Math.max(a.length, b.length)) * 100;
}

// Aproximação do rapidfuzz.partial_ratio usado no backend: acha a janela de
// `candidate` do mesmo tamanho de `query` com maior similaridade, em vez de
// comparar o candidate inteiro (senão uma query curta nunca bateria bem
// contra um texto longo, tipo uma descrição).
function fuzzyScore(query, candidate) {
  const q = normalizeText(query);
  const c = normalizeText(candidate);
  if (!q || !c) return 0;
  if (c.includes(q)) return 100;
  if (q.length >= c.length) return similarityRatio(q, c);

  let best = 0;
  for (let i = 0; i <= c.length - q.length; i++) {
    best = Math.max(best, similarityRatio(q, c.slice(i, i + q.length)));
    if (best >= 100) break;
  }
  return best;
}

function fileRelevance(file, query) {
  const category = normalizeText(file.category);
  const tags = (file.tags || []).map(normalizeText);
  const normQuery = normalizeText(query);
  const normName = normalizeText(file.name);

  if (category && category === normQuery) return 100;
  if (tags.includes(normQuery)) return 98;
  // A consulta aparece literalmente no nome do arquivo — sinal forte
  // demais pra depender só de bater exato com a categoria/tag (evita
  // falso negativo quando o nome do arquivo já entrega a resposta).
  if (normQuery && normName.includes(normQuery)) return 96;

  const haystack = [file.name, file.description, file.category, (file.tags || []).join(" ")]
    .filter(Boolean)
    .join(" ");
  const fallbackScore = fuzzyScore(query, haystack);
  return fallbackScore < FALLBACK_FUZZY_THRESHOLD ? 0 : fallbackScore;
}

function searchFiles(query, filterType = "all") {
  let results = [...MOCK_FILES];
  if (filterType && filterType !== "all") {
    results = results.filter((f) => f.type === filterType);
  }
  const q = (query || "").trim();
  if (q) {
    results = results
      .map((file) => ({ file, score: fileRelevance(file, q) }))
      .filter(({ score }) => score >= SEARCH_FUZZY_THRESHOLD)
      .sort((a, b) => b.score - a.score)
      .map(({ file }) => file);
  }
  return results;
}

// =============================================================
// Real uploaded files — fetched from the api backend (/files)
// and merged into MOCK_FILES so dashboard/search reflect uploads.
// =============================================================
const UPLOADED_FILES_API_URL =
  window.BUSCA_AGIL_FILES_URL ||
  (window.location.protocol === "file:" ? "http://localhost/files" : "/files");

const SMART_SEARCH_API_URL =
  window.BUSCA_AGIL_SEARCH_URL ||
  (window.location.protocol === "file:" ? "http://localhost/search-query" : "/search-query");

// Abaixo disso, uma classificação feita por IA é considerada "duvidosa" e
// vale sinalizar na UI pra revisão — classificação manual nunca entra aqui
// (ver classificationSource).
const LOW_CONFIDENCE_THRESHOLD = 0.55;

function isLowConfidence(file) {
  return (
    file.classificationSource === "ai" &&
    typeof file.confidence === "number" &&
    file.confidence < LOW_CONFIDENCE_THRESHOLD
  );
}

function mapUploadedFileToCard(f) {
  const tags = [...(f.tags || [])];
  if (f.category && !tags.includes(f.category)) tags.push(f.category);
  return {
    id: f.id,
    name: f.name,
    type: f.type,
    size: f.size,
    createdAt: f.created_at,
    updatedAt: f.created_at,
    previewUrl: f.type === "image" ? f.url : null,
    driveUrl: f.url,
    starred: false,
    tags,
    category: f.category || null,
    description: f.description || "",
    status: f.status || "done",
    confidence: typeof f.confidence === "number" ? f.confidence : null,
    classificationSource: f.classification_source || null,
  };
}

async function loadUploadedFiles() {
  try {
    const bustCache = UPLOADED_FILES_API_URL + (UPLOADED_FILES_API_URL.includes("?") ? "&" : "?") + "_=" + Date.now();
    const res = await fetch(bustCache, { cache: "no-store" });
    if (!res.ok) return [];
    const data = await res.json();
    const uploaded = (data.files || []).map(mapUploadedFileToCard);

    uploaded.forEach((file) => {
      const idx = MOCK_FILES.findIndex((existing) => existing.id === file.id);
      if (idx !== -1) MOCK_FILES.splice(idx, 1);
    });
    MOCK_FILES.unshift(...uploaded);

    return uploaded;
  } catch (e) {
    console.warn("Não foi possível carregar os arquivos enviados:", e);
    return [];
  }
}

// Busca assistida por IA: envia a consulta para o backend, que pede ao
// Gemini as categorias/tags mais prováveis e filtra data/uploaded_files.json
// por elas (com fallback local em caso de falha/latência).
async function smartSearchFiles(query, filterType = "all") {
  const q = (query || "").trim();

  if (!q) {
    return searchFiles(query, filterType);
  }

  try {
    const url = `${SMART_SEARCH_API_URL}?q=${encodeURIComponent(q)}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data.success) throw new Error(data.error || "busca falhou");

    let results = (data.files || []).map(mapUploadedFileToCard);
    if (filterType && filterType !== "all") {
      results = results.filter((f) => f.type === filterType);
    }
    return results;
  } catch (e) {
    console.warn("Busca assistida por IA indisponível, usando busca local:", e);
    return searchFiles(query, filterType);
  }
}

function getStorageStats() {
  const byType = {};
  MOCK_FILES.forEach((f) => {
    if (!byType[f.type]) byType[f.type] = { count: 0, size: 0 };
    byType[f.type].count++;
    byType[f.type].size += f.size;
  });
  return {
    totalFiles: MOCK_FILES.length,
    totalSize: MOCK_FILES.reduce((acc, f) => acc + f.size, 0),
    byType,
  };
}
