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
