// =============================================================
// File View Logic (Aurora Theme)
// =============================================================

lucide.createIcons();
if (!requireAuth()) throw new Error('Not authenticated');

const user = getCurrentUser();
if (document.getElementById('sidebar-avatar')) document.getElementById('sidebar-avatar').src = user.avatar;
if (document.getElementById('sidebar-name')) document.getElementById('sidebar-name').textContent = user.name;
if (document.getElementById('header-avatar')) document.getElementById('header-avatar').src = user.avatar;

// Sidebar toggle
const sbToggle = document.getElementById('sidebar-toggle');
if (sbToggle) {
  sbToggle.addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('sidebar-overlay').classList.toggle('open');
  });
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('open');
}

// Get file from URL param
const params = new URLSearchParams(window.location.search);
const fileId = params.get('id');
let currentFile = null;

(async function initFileView() {
  if (!fileId) {
    showNotFound();
    return;
  }
  await loadUploadedFiles();
  const file = getFileById(fileId);
  if (!file) {
    showNotFound();
    return;
  }
  currentFile = file;
  renderFileView(file);
})();

function showNotFound() {
  document.getElementById('skeleton-view').classList.add('hidden');
  document.getElementById('not-found').classList.remove('hidden');
  lucide.createIcons();
}

function renderFileView(file) {
  document.getElementById('skeleton-view').classList.add('hidden');
  document.getElementById('file-view').classList.remove('hidden');

  const typeInfo = getFileTypeInfo(file.type);

  // Title & Badge
  document.getElementById('file-name').textContent = file.name;
  document.title = `${file.name} — BuscaÁgil`;
  document.getElementById('file-type-badge').innerHTML =
    `<span class="type-pill" style="background:${typeInfo.bg};color:${typeInfo.color}">
       <i data-lucide="${typeInfo.icon}" style="width:12px;height:12px"></i> ${typeInfo.label}
     </span>`;

  // Star
  updateStarBtn(file.starred);

  // Preview
  renderPreview(file, typeInfo);

  // Metadata
  renderMeta(file, typeInfo);

  // Tags
  renderTags(file);

  lucide.createIcons();
}

function renderPreview(file, typeInfo) {
  const area = document.getElementById('preview-area');

  if (file.type === 'image' && file.previewUrl) {
    area.innerHTML = `<img src="${file.previewUrl}" alt="${file.name}" style="width:100%;max-height:520px;object-fit:contain;" />`;
  } else if (file.type === 'video') {
    if (file.previewUrl) {
      area.innerHTML = `
        <div class="relative w-full" style="aspect-ratio:16/9;background:#000">
          <img src="${file.previewUrl}" alt="Capa do vídeo" style="width:100%;height:100%;object-fit:cover;opacity:0.5"/>
          <div class="absolute inset-0 flex flex-col items-center justify-center gap-3">
            <div class="w-16 h-16 rounded-full flex items-center justify-center" style="background:rgba(168,85,247,0.25);border:2px solid rgba(168,85,247,0.5)">
              <i data-lucide="play" style="width:28px;height:28px;color:#a855f7;margin-left:4px"></i>
            </div>
            <p class="text-sm font-semibold text-white" style="font-family:'Space Grotesk',sans-serif">Abrir no Google Drive para reproduzir em HD</p>
          </div>
        </div>`;
    } else {
      area.innerHTML = renderIconPreview(typeInfo, 'Abrir no Drive para assistir ao vídeo');
    }
  } else if (file.type === 'audio') {
    area.innerHTML = `
      <div class="flex flex-col items-center justify-center p-12 gap-6 w-full">
        <div class="w-20 h-20 rounded-3xl flex items-center justify-center float" style="background:${typeInfo.bg}">
          <i data-lucide="music" style="width:40px;height:40px;color:${typeInfo.color}"></i>
        </div>
        <div class="text-center">
          <p class="font-bold text-white mb-1" style="font-family:'Space Grotesk',sans-serif">${file.name}</p>
          <p class="text-xs" style="color:var(--text-3)">Áudio • ${formatFileSize(file.size)}</p>
        </div>
      </div>`;
  } else if (file.type === 'link') {
    area.innerHTML = `
      <div class="flex flex-col items-center justify-center p-12 gap-4 w-full">
        <div class="w-20 h-20 rounded-3xl flex items-center justify-center" style="background:${typeInfo.bg}">
          <i data-lucide="link" style="width:40px;height:40px;color:${typeInfo.color}"></i>
        </div>
        <div class="text-center">
          <p class="font-bold text-white mb-1" style="font-family:'Space Grotesk',sans-serif">${file.name}</p>
          <p class="text-xs px-4 py-2 rounded-lg truncate max-w-xs font-mono" style="background:var(--bg-card);color:var(--text-2)">${file.url || '#'}</p>
        </div>
        <a href="${file.url || '#'}" target="_blank" rel="noopener" class="btn btn-violet">
          <i data-lucide="external-link" class="w-4 h-4"></i> Acessar URL externa
        </a>
      </div>`;
  } else {
    area.innerHTML = renderIconPreview(typeInfo, `Abra no Google Drive para visualizar o arquivo completo`);
  }
}

function renderIconPreview(typeInfo, subtitle) {
  return `
    <div class="flex flex-col items-center justify-center p-14 gap-4 w-full">
      <div class="w-24 h-24 rounded-3xl flex items-center justify-center float" style="background:${typeInfo.bg};border:1px solid ${typeInfo.color}44">
        <i data-lucide="${typeInfo.icon}" style="width:48px;height:48px;color:${typeInfo.color}"></i>
      </div>
      <p class="text-xs text-center" style="color:var(--text-3)">${subtitle}</p>
    </div>`;
}

function renderMeta(file, typeInfo) {
  const rows = [
    { label: 'Nome do arquivo', value: file.name },
    { label: 'Formato', value: typeInfo.label },
    { label: 'Tamanho', value: file.size > 0 ? formatFileSize(file.size) : '—' },
    { label: 'Data de criação', value: formatDate(file.createdAt) },
    { label: 'Última modificação', value: formatDate(file.updatedAt) },
    { label: 'Origem', value: 'Google Drive' },
  ];
  document.getElementById('meta-rows').innerHTML = rows.map(r => `
    <div class="meta-row">
      <span class="meta-label">${r.label}</span>
      <span class="meta-value">${r.value}</span>
    </div>`).join('');
}

function renderTags(file) {
  const container = document.getElementById('file-tags');
  const noTags = document.getElementById('no-tags');
  if (!file.tags || file.tags.length === 0) {
    noTags.classList.remove('hidden');
    return;
  }
  noTags.classList.add('hidden');
  container.innerHTML = file.tags.map(tag =>
    `<span class="type-pill cursor-pointer hover:border-purple-400 transition-colors" style="background:var(--bg-card);color:var(--text-2);border:1px solid var(--border)"
       onclick="window.location.href='dashboard.html'">
       #${tag}
     </span>`
  ).join('');
}

// Star toggle
function updateStarBtn(starred) {
  const icon = document.getElementById('star-icon');
  if (!icon) return;
  if (starred) {
    icon.style.color = '#fbbf24';
    icon.style.fill = '#fbbf24';
  } else {
    icon.style.color = 'var(--text-3)';
    icon.style.fill = 'none';
  }
}

function toggleStar() {
  if (!currentFile) return;
  currentFile.starred = !currentFile.starred;
  const idx = MOCK_FILES.findIndex(f => f.id === currentFile.id);
  if (idx !== -1) MOCK_FILES[idx].starred = currentFile.starred;
  updateStarBtn(currentFile.starred);
  showToast(currentFile.starred ? 'Adicionado aos favoritos!' : 'Removido dos favoritos', 'info');
}

function openInDrive() {
  showToast('Abrindo no Google Drive...', 'info');
  setTimeout(() => window.open(currentFile?.driveUrl || '#', '_blank'), 500);
}

function simulateDownload() {
  showToast('Download simulado iniciado com sucesso!', 'success');
}

function copyLink() {
  const url = window.location.href;
  navigator.clipboard.writeText(url).then(() => {
    showToast('Link do arquivo copiado!', 'success');
  }).catch(() => {
    showToast('Link: ' + url, 'info');
  });
}

function openDeleteModal() {
  document.getElementById('delete-modal').classList.add('open');
}
function closeDeleteModal() {
  document.getElementById('delete-modal').classList.remove('open');
}

async function doDelete() {
  const btn = document.getElementById('confirm-delete-btn');
  btn.textContent = 'Excluindo...';
  btn.disabled = true;
  try {
    await mockDeleteFile(currentFile.id);
    closeDeleteModal();
    showToast('Arquivo excluído!', 'success');
    setTimeout(() => { window.location.href = 'dashboard.html'; }, 1200);
  } catch (e) {
    closeDeleteModal();
    showToast('Erro ao excluir.', 'error');
  }
}

function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  const colors = { success: '#4ade80', error: '#f87171', info: 'var(--violet-light)' };
  toast.innerHTML = `<span style="color:${colors[type]}">●</span> <span>${msg}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'toastOut 0.3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
