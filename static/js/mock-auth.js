// =============================================================
// MOCK AUTH — Replace with real Google OAuth when backend is ready
// =============================================================

const AUTH_KEY = "busca_agil_auth";
const DRIVE_AUTH_KEY = "busca_agil_drive_auth";

// Simulate login with Google
async function mockLoginWithGoogle() {
  return new Promise((resolve) => {
    setTimeout(() => {
      sessionStorage.setItem(AUTH_KEY, JSON.stringify({ userId: MOCK_USER.id, ts: Date.now() }));
      resolve({ success: true, user: MOCK_USER });
    }, 1500);
  });
}

// Simulate Google Drive authorization
async function mockAuthorizeDrive() {
  return new Promise((resolve) => {
    setTimeout(() => {
      sessionStorage.setItem(DRIVE_AUTH_KEY, "true");
      resolve({ success: true });
    }, 1800);
  });
}

// Check if user is logged in
function isLoggedIn() {
  return !!sessionStorage.getItem(AUTH_KEY);
}

// Check if Drive is authorized
function isDriveAuthorized() {
  return !!sessionStorage.getItem(DRIVE_AUTH_KEY);
}

// Get current user
function getCurrentUser() {
  if (!isLoggedIn()) return null;
  return MOCK_USER;
}

// Simulate logout
function mockLogout() {
  sessionStorage.removeItem(AUTH_KEY);
  sessionStorage.removeItem(DRIVE_AUTH_KEY);
  window.location.href = "index.html";
}

// Guard — redirect to login if not authenticated
function requireAuth() {
  if (!isLoggedIn()) {
    window.location.href = "index.html";
    return false;
  }
  if (!isDriveAuthorized()) {
    window.location.href = "auth.html";
    return false;
  }
  return true;
}

// Simulate file upload
async function mockUploadFile(file, onProgress) {
  return new Promise((resolve, reject) => {
    let progress = 0;
    const interval = setInterval(() => {
      progress += Math.floor(Math.random() * 18) + 5;
      if (progress >= 100) {
        progress = 100;
        clearInterval(interval);
        onProgress && onProgress(100);

        // Simulate occasional error (10% chance)
        if (Math.random() < 0.1) {
          reject(new Error("Falha no upload. Tente novamente."));
        } else {
          const newFile = {
            id: "f_" + Date.now(),
            name: file.name,
            type: detectFileType(file),
            size: file.size,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
            driveUrl: "#",
            starred: false,
            tags: [],
          };
          MOCK_FILES.unshift(newFile);
          resolve({ success: true, file: newFile });
        }
      } else {
        onProgress && onProgress(progress);
      }
    }, 200);
  });
}

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
