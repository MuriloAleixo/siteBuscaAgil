// =============================================================
// MOCK DATA — Replace these with real API calls when backend is ready
// =============================================================

const MOCK_USER = {
  id: "u_001",
  name: "Clara Oliveira",
  email: "clara.oliveira@gmail.com",
  avatar: "https://ui-avatars.com/api/?name=Clara+Oliveira&background=6366f1&color=fff&size=128&bold=true",
  plan: "Pro",
  storageUsed: 4.7,   // GB
  storageTotal: 15,   // GB
  joinedAt: "2024-03-15",
  googleConnected: true,
};

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

const MOCK_FILES = [
  {
    id: "f_001",
    name: "Design System BuscaÁgil.pdf",
    type: "pdf",
    size: 2340000,
    createdAt: "2025-07-28T10:15:00Z",
    updatedAt: "2025-07-28T10:15:00Z",
    previewUrl: null,
    driveUrl: "#",
    starred: true,
    tags: ["design", "ui"],
  },
  {
    id: "f_002",
    name: "Banner Campanha Verão.png",
    type: "image",
    size: 854000,
    createdAt: "2025-07-30T14:22:00Z",
    updatedAt: "2025-07-30T14:22:00Z",
    previewUrl: "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=600&q=80",
    driveUrl: "#",
    starred: false,
    tags: ["marketing", "banner"],
  },
  {
    id: "f_003",
    name: "Reunião de Planejamento Q3.mp4",
    type: "video",
    size: 145200000,
    createdAt: "2025-08-01T09:00:00Z",
    updatedAt: "2025-08-01T09:00:00Z",
    previewUrl: "https://images.unsplash.com/photo-1611532736597-de2d4265fba3?w=600&q=80",
    driveUrl: "#",
    starred: true,
    tags: ["reunião", "q3"],
  },
  {
    id: "f_004",
    name: "Relatório Anual 2024.pdf",
    type: "pdf",
    size: 5100000,
    createdAt: "2025-08-02T11:30:00Z",
    updatedAt: "2025-08-02T11:30:00Z",
    previewUrl: null,
    driveUrl: "#",
    starred: false,
    tags: ["relatório", "financeiro"],
  },
  {
    id: "f_005",
    name: "Foto do Produto — Vista Frontal.jpg",
    type: "image",
    size: 1230000,
    createdAt: "2025-08-03T08:45:00Z",
    updatedAt: "2025-08-03T08:45:00Z",
    previewUrl: "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&q=80",
    driveUrl: "#",
    starred: false,
    tags: ["produto", "foto"],
  },
  {
    id: "f_006",
    name: "Planilha de Orçamento 2025.xlsx",
    type: "sheet",
    size: 430000,
    createdAt: "2025-08-04T16:00:00Z",
    updatedAt: "2025-08-05T09:10:00Z",
    previewUrl: null,
    driveUrl: "#",
    starred: true,
    tags: ["financeiro", "orçamento"],
  },
  {
    id: "f_007",
    name: "Tutorial de Onboarding.mp4",
    type: "video",
    size: 98700000,
    createdAt: "2025-08-05T13:20:00Z",
    updatedAt: "2025-08-05T13:20:00Z",
    previewUrl: "https://images.unsplash.com/photo-1616469829581-73993eb86b02?w=600&q=80",
    driveUrl: "#",
    starred: false,
    tags: ["tutorial", "onboarding"],
  },
  {
    id: "f_008",
    name: "Contrato de Prestação de Serviços.docx",
    type: "doc",
    size: 187000,
    createdAt: "2025-08-05T17:00:00Z",
    updatedAt: "2025-08-06T10:00:00Z",
    previewUrl: null,
    driveUrl: "#",
    starred: false,
    tags: ["contrato", "jurídico"],
  },
  {
    id: "f_009",
    name: "Paleta de Cores Oficial.png",
    type: "image",
    size: 320000,
    createdAt: "2025-08-06T09:30:00Z",
    updatedAt: "2025-08-06T09:30:00Z",
    previewUrl: "https://images.unsplash.com/photo-1500462918059-b1a0cb512f1d?w=600&q=80",
    driveUrl: "#",
    starred: true,
    tags: ["design", "cores"],
  },
  {
    id: "f_010",
    name: "Link — Figma Design System",
    type: "link",
    size: 0,
    createdAt: "2025-08-06T11:15:00Z",
    updatedAt: "2025-08-06T11:15:00Z",
    previewUrl: null,
    driveUrl: "https://figma.com",
    starred: false,
    tags: ["figma", "design"],
    url: "https://figma.com/file/example",
  },
  {
    id: "f_011",
    name: "Podcast Episódio 12 — Inovação.mp3",
    type: "audio",
    size: 42300000,
    createdAt: "2025-08-07T08:00:00Z",
    updatedAt: "2025-08-07T08:00:00Z",
    previewUrl: null,
    driveUrl: "#",
    starred: false,
    tags: ["podcast", "áudio"],
  },
  {
    id: "f_012",
    name: "Proposta Comercial Cliente XYZ.pdf",
    type: "pdf",
    size: 1750000,
    createdAt: "2025-08-07T14:00:00Z",
    updatedAt: "2025-08-07T14:00:00Z",
    previewUrl: null,
    driveUrl: "#",
    starred: true,
    tags: ["proposta", "vendas"],
  },
  {
    id: "f_013",
    name: "Backup Projeto.zip",
    type: "archive",
    size: 78600000,
    createdAt: "2025-08-07T19:30:00Z",
    updatedAt: "2025-08-07T19:30:00Z",
    previewUrl: null,
    driveUrl: "#",
    starred: false,
    tags: ["backup", "projeto"],
  },
  {
    id: "f_014",
    name: "Foto Equipe 2025.jpg",
    type: "image",
    size: 2100000,
    createdAt: "2025-08-08T10:00:00Z",
    updatedAt: "2025-08-08T10:00:00Z",
    previewUrl: "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=600&q=80",
    driveUrl: "#",
    starred: false,
    tags: ["equipe", "foto"],
  },
  {
    id: "f_015",
    name: "Notas de Reunião — Agosto.docx",
    type: "doc",
    size: 95000,
    createdAt: "2025-08-08T15:45:00Z",
    updatedAt: "2025-08-08T15:45:00Z",
    previewUrl: null,
    driveUrl: "#",
    starred: false,
    tags: ["reunião", "notas"],
  },
];

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
    storageUsed: MOCK_USER.storageUsed,
    storageTotal: MOCK_USER.storageTotal,
  };
}
