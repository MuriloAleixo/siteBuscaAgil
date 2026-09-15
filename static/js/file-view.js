// =============================================================
// File View Logic (Aurora Theme)
// =============================================================

lucide.createIcons();
if (!requireAuth()) throw new Error('Not authenticated');

const user = getCurrentUser();
setAvatar(document.getElementById('sidebar-avatar'), user);
if (document.getElementById('sidebar-name')) document.getElementById('sidebar-name').textContent = user.name;
setAvatar(document.getElementById('header-avatar'), user);

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

  // Description
  renderDescription(file);

  // Metadata
  renderMeta(file, typeInfo);

  // Classificação (categoria + tags, com fallback manual)
  renderClassification(file);

  lucide.createIcons();
}

function renderPreview(file, typeInfo) {
  const area = document.getElementById('preview-area');

  if (file.type === 'image' && file.previewUrl) {
    // previewUrl pode ser o webViewLink do Drive (página HTML, não uma
    // imagem de verdade) — se o <img> falhar, cai pro ícone em vez de
    // ficar quebrado/vazio.
    area.innerHTML = `<img src="${file.previewUrl}" alt="${file.name}" style="width:100%;max-height:520px;object-fit:contain;" onerror="onImagePreviewError('${typeInfo.icon}','${typeInfo.color}','${typeInfo.bg}')" />`;
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

function onImagePreviewError(icon, color, bg) {
  document.getElementById('preview-area').innerHTML =
    renderIconPreview({ icon, color, bg }, 'Abra no Google Drive para visualizar a imagem');
  lucide.createIcons();
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

function renderDescription(file) {
  const box = document.getElementById('description-box');
  if (!file.description) {
    box.classList.add('hidden');
    return;
  }
  document.getElementById('description-text').textContent = file.description;
  box.classList.remove('hidden');
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
    container.innerHTML = '';
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

// ── Classificação: exibição + fallback manual quando o Gemini não classifica ──
function renderClassification(file) {
  const warning = document.getElementById('classification-warning');
  const lowConfidenceWarning = document.getElementById('low-confidence-warning');
  const categoryEl = document.getElementById('classification-category');
  const hasCategory = !!file.category;

  warning.classList.toggle('hidden', hasCategory);
  lowConfidenceWarning.classList.toggle('hidden', !hasCategory || !isLowConfidence(file));
  categoryEl.innerHTML = hasCategory
    ? `<span class="type-pill" style="background:var(--bg-card);color:var(--text-2);border:1px solid var(--border)">${file.category}</span>`
    : `<span class="text-xs" style="color:var(--text-3)">Não classificado</span>`;

  renderTags(file);

  document.getElementById('edit-category-input').value = file.category || '';
  document.getElementById('edit-tags-input').value = (file.tags || []).join(', ');
  document.getElementById('edit-description-input').value = file.description || '';
}

function toggleClassificationEdit(show) {
  const view = document.getElementById('classification-view');
  const form = document.getElementById('classification-form');
  const shouldShow = show === undefined ? form.classList.contains('hidden') : show;
  view.classList.toggle('hidden', shouldShow);
  form.classList.toggle('hidden', !shouldShow);
  lucide.createIcons();
}

async function saveClassification() {
  if (!currentFile) return;
  const btn = document.getElementById('save-classification-btn');
  const category = document.getElementById('edit-category-input').value.trim();
  const tags = document.getElementById('edit-tags-input').value
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
  const description = document.getElementById('edit-description-input').value.trim();

  btn.disabled = true;
  try {
    const res = await fetch(`${UPLOADED_FILES_API_URL}/${encodeURIComponent(currentFile.id)}/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
      body: JSON.stringify({ category, tags, description }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.error || `Falha ao salvar (${res.status}).`);
    }

    const f = data.file;
    currentFile.category = f.category || null;
    currentFile.tags = f.tags || [];
    currentFile.description = f.description || '';
    // Reclassificação manual: backend já zerou confidence/scores (ver
    // api/app.py::update_file_metadata) — refletir aqui pra badge de
    // baixa confiança sumir sem precisar recarregar a página.
    currentFile.confidence = null;
    currentFile.classificationSource = 'manual';

    const idx = MOCK_FILES.findIndex((x) => x.id === currentFile.id);
    if (idx !== -1) {
      MOCK_FILES[idx].category = currentFile.category;
      MOCK_FILES[idx].tags = currentFile.tags;
      MOCK_FILES[idx].description = currentFile.description;
      MOCK_FILES[idx].confidence = currentFile.confidence;
      MOCK_FILES[idx].classificationSource = currentFile.classificationSource;
    }

    renderClassification(currentFile);
    renderDescription(currentFile);
    toggleClassificationEdit(false);
    showToast('Classificação salva com sucesso!', 'success');
  } catch (e) {
    showToast(e.message || 'Erro ao salvar a classificação.', 'error');
  }
  btn.disabled = false;
}

// Reprocessar: reclassifica um item já existente (baixa de novo do Drive se
// for arquivo, sem duplicar upload — ver worker/tasks.py::_run_reclassification)
// sem precisar reenviar do zero. Útil quando a classificação original falhou
// por instabilidade passageira da IA (ver Histórico de Processamento em
// processing.html pro motivo exato).
function pollReprocessStatus(fileId, { intervalMs = 2000, timeoutMs = 360000 } = {}) {
  const startedAt = Date.now();
  const tick = async () => {
    try {
      const res = await fetch(`${UPLOADED_FILES_API_URL}/${encodeURIComponent(fileId)}/status`, { cache: 'no-store' });
      const data = await res.json();
      if (res.ok && data.success && (data.status === 'done' || data.status === 'error')) {
        onReprocessFinished(data);
        return;
      }
    } catch (e) {
      // rede instável durante o polling: só tenta de novo no próximo tick
    }
    if (Date.now() - startedAt < timeoutMs) {
      setTimeout(tick, intervalMs);
    } else {
      onReprocessFinished(null); // timeout — some caso raro (vídeo bem longo)
    }
  };
  setTimeout(tick, intervalMs);
}

function setReprocessBtnBusy(busy) {
  const btn = document.getElementById('reprocess-btn');
  const label = document.getElementById('reprocess-btn-label');
  btn.disabled = busy;
  label.textContent = busy ? 'Reprocessando…' : 'Reprocessar Classificação';
  // lucide.createIcons() já trocou o <i data-lucide> original por um <svg> —
  // procura os dois pra funcionar tanto antes quanto depois da conversão.
  btn.querySelector('svg, i')?.classList.toggle('spin', busy);
}

async function reprocessFile() {
  if (!currentFile) return;
  setReprocessBtnBusy(true);
  try {
    const res = await fetch(`${UPLOADED_FILES_API_URL}/${encodeURIComponent(currentFile.id)}/reprocess`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken() },
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.error || `Falha ao reprocessar (${res.status}).`);
    }
    showToast('Reprocessando classificação — pode levar alguns minutos (vídeos demoram mais).', 'info');
    pollReprocessStatus(currentFile.id);
  } catch (e) {
    showToast(e.message || 'Erro ao reprocessar.', 'error');
    setReprocessBtnBusy(false);
  }
}

function onReprocessFinished(statusData) {
  setReprocessBtnBusy(false);
  if (!statusData) {
    showToast('Reprocessamento está demorando mais que o esperado — confira o Histórico de Processamento.', 'info');
    return;
  }
  if (statusData.status === 'error') {
    showToast('Não foi possível reclassificar — confira o Histórico de Processamento pra ver o motivo.', 'error');
    return;
  }

  currentFile.category = statusData.category || null;
  currentFile.tags = statusData.tags || [];
  currentFile.description = statusData.description || '';
  currentFile.classificationSource = 'ai';

  const idx = MOCK_FILES.findIndex((x) => x.id === currentFile.id);
  if (idx !== -1) {
    MOCK_FILES[idx].category = currentFile.category;
    MOCK_FILES[idx].tags = currentFile.tags;
    MOCK_FILES[idx].description = currentFile.description;
    MOCK_FILES[idx].classificationSource = currentFile.classificationSource;
  }

  renderClassification(currentFile);
  renderDescription(currentFile);
  lucide.createIcons();
  showToast(`Reclassificado: ${currentFile.category || 'sem categoria encontrada'}.`, 'success');
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

async function downloadFile() {
  if (!currentFile) return;

  if (currentFile.type === 'link') {
    showToast('Links não têm arquivo para baixar — use "Acessar URL externa".', 'info');
    return;
  }

  showToast('Preparando download...', 'info');
  try {
    const url = `${UPLOADED_FILES_API_URL}/${encodeURIComponent(currentFile.id)}/download`;
    const res = await fetch(url);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `Falha ao baixar (${res.status}).`);
    }

    const blob = await res.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = currentFile.name || 'arquivo';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(blobUrl);

    showToast('Download iniciado!', 'success');
  } catch (e) {
    showToast(e.message || 'Erro ao baixar o arquivo.', 'error');
  }
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
    const res = await fetch(`${UPLOADED_FILES_API_URL}/${encodeURIComponent(currentFile.id)}/delete`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken() },
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.error || `Falha ao excluir (${res.status}).`);
    }

    closeDeleteModal();
    showToast('Arquivo excluído!', 'success');
    setTimeout(() => { window.location.href = 'dashboard.html'; }, 1200);
  } catch (e) {
    closeDeleteModal();
    showToast(e.message || 'Erro ao excluir.', 'error');
    btn.textContent = 'Excluir';
    btn.disabled = false;
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
