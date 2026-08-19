// =============================================================
// Utilitários de arquivo ainda simulados no front-end (fora do escopo da
// autenticação, que agora é real — ver static/js/auth.js). Deletar um
// arquivo aqui só remove da lista em memória; não há endpoint de exclusão
// real no backend/Drive ainda.
// =============================================================

// Simulate file deletion
async function mockDeleteFile(fileId) {
  return new Promise((resolve) => {
    setTimeout(() => {
      const idx = MOCK_FILES.findIndex((f) => f.id === fileId);
      if (idx !== -1) MOCK_FILES.splice(idx, 1);
      resolve({ success: true });
    }, 800);
  });
}

// Detect file type from File object
function detectFileType(file) {
  const mime = file.type;
  if (mime.startsWith("image/")) return "image";
  if (mime === "application/pdf") return "pdf";
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("audio/")) return "audio";
  if (mime.includes("spreadsheet") || mime.includes("excel") || file.name.endsWith(".xlsx") || file.name.endsWith(".csv")) return "sheet";
  if (mime.includes("word") || mime.includes("document") || file.name.endsWith(".docx") || file.name.endsWith(".doc")) return "doc";
  if (file.name.endsWith(".zip") || file.name.endsWith(".rar") || file.name.endsWith(".tar")) return "archive";
  return "archive";
}
