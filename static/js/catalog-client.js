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
// core/uploaded_files_store.py).
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

function searchFiles(query, filterType = "all") {
  let results = [...MOCK_FILES];
  if (filterType && filterType !== "all") {
    results = results.filter((f) => f.type === filterType);
  }
  if (query && query.trim() !== "") {
    const q = query.toLowerCase();
    results = results.filter(
      (f) =>
        f.name.toLowerCase().includes(q) ||
        (f.tags && f.tags.some((t) => t.toLowerCase().includes(q)))
    );
  }
  return results;
}

// =============================================================
// Real uploaded files — fetched from the Django backend (/files)
// and merged into MOCK_FILES so dashboard/search reflect uploads.
// =============================================================
const UPLOADED_FILES_API_URL =
  window.BUSCA_AGIL_FILES_URL ||
  (window.location.protocol === "file:" ? "http://localhost:8000/files" : "/files");

const SMART_SEARCH_API_URL =
  window.BUSCA_AGIL_SEARCH_URL ||
  (window.location.protocol === "file:" ? "http://localhost:8000/search-query" : "/search-query");

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
