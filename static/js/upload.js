// =============================================================
// Upload Logic
// =============================================================

lucide.createIcons();
if (!requireAuth()) throw new Error('Not authenticated');

const user = getCurrentUser();
document.getElementById('sidebar-avatar').src = user.avatar;
document.getElementById('sidebar-name').textContent = user.name;
const UPLOAD_API_URL = window.BUSCA_AGIL_UPLOAD_URL || (window.location.protocol === 'file:' ? 'http://localhost:8000/upload' : '/upload');
const ADD_LINK_API_URL = window.BUSCA_AGIL_ADD_LINK_URL || (window.location.protocol === 'file:' ? 'http://localhost:8000/add-link' : '/add-link');
const FILE_STATUS_API_URL = window.BUSCA_AGIL_FILE_STATUS_URL || (window.location.protocol === 'file:' ? 'http://localhost:8000/files' : '/files');

// Faz polling em GET /files/<id>/status até a classificação assíncrona
// (worker Celery, via fila Redis) terminar. Best-effort: se não terminar
// dentro do timeout, o item fica com o status mostrado no upload mesmo, e o
// usuário vê o resultado final na próxima vez que a lista for recarregada.
function pollFileStatus(fileId, { intervalMs = 2000, timeoutMs = 40000, onUpdate } = {}) {
  const startedAt = Date.now();
  const tick = async () => {
    try {
      const res = await fetch(`${FILE_STATUS_API_URL}/${encodeURIComponent(fileId)}/status`, { cache: 'no-store' });
      const data = await res.json();
      if (res.ok && data.success) {
        if (data.status === 'done' || data.status === 'error') {
          onUpdate && onUpdate(data);
          return;
        }
      }
    } catch (e) {
      // rede instável durante o polling: apenas tenta de novo no próximo tick
    }
    if (Date.now() - startedAt < timeoutMs) {
      setTimeout(tick, intervalMs);
    }
  };
  setTimeout(tick, intervalMs);
}

// ── Sidebar Toggle ──
document.getElementById('sidebar-toggle').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebar-overlay').classList.toggle('open');
});
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('open');
}

let fileQueue = []; // { file, status: 'pending'|'uploading'|'done'|'error', progress: 0 }

// ── Drop Zone Events ──
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');

dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const files = Array.from(e.dataTransfer.files);
  addFilesToQueue(files);
});

fileInput.addEventListener('change', () => {
  const files = Array.from(fileInput.files);
  addFilesToQueue(files);
  fileInput.value = ''; // Reset so same file can be selected again
});

function addFilesToQueue(files) {
  const MAX_SIZE = 100 * 1024 * 1024; // 100 MB
  files.forEach((file) => {
    if (file.size > MAX_SIZE) {
      showToast(`"${file.name}" excede 100 MB e foi ignorado.`, 'error');
      return;
    }
    if (fileQueue.find((q) => q.file.name === file.name && q.file.size === file.size)) return; // dedupe
    fileQueue.push({ file, status: 'pending', progress: 0, id: `q_${Date.now()}_${Math.random()}` });
  });
  renderQueue();
}

function renderQueue() {
  const container = document.getElementById('file-queue');
  const actions = document.getElementById('upload-actions');
  const countLabel = document.getElementById('upload-count-label');

  if (fileQueue.length === 0) {
    container.innerHTML = '';
    actions.classList.add('hidden');
    return;
  }

  const pendingCount = fileQueue.filter((q) => q.status === 'pending').length;
  if (pendingCount > 0) {
    actions.classList.remove('hidden');
    countLabel.textContent = pendingCount === 1 ? '1 arquivo' : `${pendingCount} arquivos`;
  } else {
    actions.classList.add('hidden');
  }

  container.innerHTML = fileQueue.map((item) => renderQueueItem(item)).join('');
  lucide.createIcons();
}

function renderQueueItem(item) {
  const typeInfo = getFileTypeInfo(detectFileType(item.file));
  const sizeFmt = formatFileSize(item.file.size);

  let statusHtml = '';
  if (item.status === 'pending') {
    statusHtml = `<span class="text-xs px-2 py-0.5 rounded-full" style="background:var(--bg-surface);color:var(--text-muted)">Pendente</span>`;
  } else if (item.status === 'uploading') {
    statusHtml = `
      <div class="flex-1 min-w-0 mt-2">
        <div class="progress-bar-wrap"><div class="progress-bar" style="width:${item.progress}%"></div></div>
        <p class="text-xs mt-1" style="color:var(--text-muted)">${item.progress}%</p>
      </div>`;
  } else if (item.status === 'done') {
    statusHtml = `<span class="text-xs px-2 py-0.5 rounded-full" style="background:rgba(34,197,94,0.12);color:var(--success)">✓ Enviado</span>`;
  } else if (item.status === 'error') {
    statusHtml = `<span class="text-xs px-2 py-0.5 rounded-full" style="background:rgba(239,68,68,0.12);color:var(--error)">Erro</span>`;
  }

  const removeBtn = item.status === 'pending'
    ? `<button onclick="removeFromQueue('${item.id}')" class="btn btn-ghost btn-icon" style="padding:6px;color:var(--text-muted)"><i data-lucide="x" style="width:14px;height:14px"></i></button>`
    : '';

  return `
    <div class="flex items-center gap-4 p-4 rounded-2xl" style="background:var(--bg-card);border:1px solid var(--border)">
      <div class="file-list-icon flex-shrink-0" style="background:${typeInfo.bg}">
        <i data-lucide="${typeInfo.icon}" style="color:${typeInfo.color};width:20px;height:20px"></i>
      </div>
      <div class="flex-1 min-w-0">
        <p class="text-sm font-medium truncate">${item.file.name}</p>
        <p class="text-xs" style="color:var(--text-muted)">${sizeFmt}</p>
        ${item.status === 'uploading' ? statusHtml : ''}
      </div>
      ${item.status !== 'uploading' ? statusHtml : ''}
      ${removeBtn}
    </div>`;
}

function removeFromQueue(id) {
  fileQueue = fileQueue.filter((q) => q.id !== id);
  renderQueue();
}

function clearQueue() {
  fileQueue = fileQueue.filter((q) => q.status !== 'pending');
  renderQueue();
}

function uploadFileToMedia(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', UPLOAD_API_URL, true);
    xhr.responseType = 'json';

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onerror = () => reject(new Error('Falha de rede ao enviar o arquivo.'));

    xhr.onload = () => {
      const response = xhr.response || (xhr.responseText ? JSON.parse(xhr.responseText) : null);
      if (xhr.status >= 200 && xhr.status < 300 && response && response.success) {
        resolve(response);
        return;
      }
      reject(new Error((response && response.error) || `Falha ao enviar o arquivo (${xhr.status}).`));
    };

    const formData = new FormData();
    formData.append('files', file, file.name);
    xhr.send(formData);
  });
}

// ── Start Uploads ──
async function startUploads() {
  const pending = fileQueue.filter((q) => q.status === 'pending');
  if (pending.length === 0) return;

  document.getElementById('upload-btn').disabled = true;

  for (const item of pending) {
    item.status = 'uploading';
    renderQueue();
    try {
      const response = await uploadFileToMedia(item.file, (progress) => {
        item.progress = progress;
        renderQueue();
      });
      const savedFile = response.files && response.files[0] ? response.files[0] : null;
      if (savedFile) {
        const fileId = savedFile.saved_name || `f_${Date.now()}`;
        MOCK_FILES.unshift({
          id: fileId,
          name: savedFile.original_name || item.file.name,
          type: detectFileType(item.file),
          size: item.file.size,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          previewUrl: item.file.type.startsWith('image/') ? savedFile.public_url : null,
          driveUrl: savedFile.public_url || savedFile.relative_path || '#',
          starred: false,
          tags: [],
        });

        // Classificação via IA roda assíncrona (worker Celery); avisa quando terminar.
        pollFileStatus(fileId, {
          onUpdate: (statusData) => {
            const mockEntry = MOCK_FILES.find((f) => f.id === fileId);
            if (mockEntry && statusData.status === 'done') {
              mockEntry.tags = statusData.tags || [];
              mockEntry.category = statusData.category || null;
              mockEntry.description = statusData.description || '';
              mockEntry.driveUrl = statusData.url || mockEntry.driveUrl;
              showToast(`"${item.file.name}" salvo no Drive e classificado: ${statusData.category || 'sem categoria'}.`, 'success');
            } else if (statusData.status === 'error') {
              showToast(`Não foi possível concluir o envio de "${item.file.name}" ao Drive. Tente novamente.`, 'error');
            }
          },
        });
      }
      item.status = 'done';
      showToast(`"${item.file.name}" recebido, enviando para o seu Google Drive...`, 'success');
    } catch (e) {
      item.status = 'error';
      showToast(e.message || `Erro ao enviar "${item.file.name}". Tente novamente.`, 'error');
    }
    renderQueue();
  }

  document.getElementById('upload-btn').disabled = false;

  const allDone = fileQueue.every((q) => q.status === 'done' || q.status === 'error');
  const anySuccess = fileQueue.some((q) => q.status === 'done');

  if (allDone && anySuccess) {
    setTimeout(() => {
      document.getElementById('file-queue').classList.add('hidden');
      document.getElementById('upload-actions').classList.add('hidden');
      document.getElementById('state-done').classList.remove('hidden');
      document.getElementById('drop-zone').classList.add('hidden');
      lucide.createIcons();
    }, 600);
  }
}

function resetUpload() {
  fileQueue = [];
  document.getElementById('file-queue').classList.remove('hidden');
  document.getElementById('drop-zone').classList.remove('hidden');
  document.getElementById('state-done').classList.add('hidden');
  renderQueue();
}

// ── Add Link ──
async function addLink() {
  const input = document.getElementById('link-input');
  const btn = document.getElementById('add-link-btn');
  const url = input.value.trim();
  if (!url) {
    showToast('Digite uma URL válida.', 'error');
    return;
  }

  btn.disabled = true;
  try {
    const res = await fetch(ADD_LINK_API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.error || `Falha ao cadastrar o link (${res.status}).`);
    }

    const f = data.file;
    MOCK_FILES.unshift({
      id: f.id,
      name: f.name,
      type: f.type,
      size: f.size,
      createdAt: f.created_at,
      updatedAt: f.created_at,
      previewUrl: null,
      driveUrl: f.url,
      starred: false,
      tags: f.tags || [],
      category: f.category || null,
      description: f.description || '',
    });

    pollFileStatus(f.id, {
      onUpdate: (statusData) => {
        const mockEntry = MOCK_FILES.find((m) => m.id === f.id);
        if (mockEntry && statusData.status === 'done') {
          mockEntry.tags = statusData.tags || [];
          mockEntry.category = statusData.category || null;
          mockEntry.description = statusData.description || '';
        }
      },
    });

    input.value = '';
    showToast(`Link "${f.name}" cadastrado com sucesso.`, 'success');
  } catch (e) {
    showToast(e.message || 'Erro ao cadastrar o link. Tente novamente.', 'error');
  }
  btn.disabled = false;
}

// ── Toast ──
function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  const icons = { success: 'check-circle', error: 'x-circle', info: 'info' };
  const colors = { success: 'var(--success)', error: 'var(--error)', info: 'var(--primary)' };
  toast.innerHTML = `<i data-lucide="${icons[type]}" style="color:${colors[type]};width:18px;height:18px;flex-shrink:0"></i><span>${msg}</span>`;
  container.appendChild(toast);
  lucide.createIcons();
  setTimeout(() => { toast.style.animation = 'toastOut 0.3s ease forwards'; setTimeout(() => toast.remove(), 300); }, 4000);
}
