// =============================================================
// Fila de Processamento — lista ao vivo dos arquivos/links que ainda
// estão sendo classificados pela IA (status "processing" em /files).
// Fonte de dados é sempre o backend (loadUploadedFiles, catalog-client.js),
// não o localStorage do task-notifications.js — assim funciona mesmo se o
// processamento foi iniciado em outra aba/dispositivo.
// =============================================================

lucide.createIcons();
if (!requireAuth()) throw new Error('Not authenticated');

const user = getCurrentUser();
document.getElementById('sidebar-avatar').src = user.avatar;
document.getElementById('sidebar-name').textContent = user.name;
document.getElementById('header-avatar').src = user.avatar;

// ── Sidebar Toggle ──
document.getElementById('sidebar-toggle').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebar-overlay').classList.toggle('open');
});
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('open');
}

const PROCESSING_POLL_INTERVAL_MS = 4000;
const PROCESSING_TRANSITION_DISPLAY_MS = 3000;

// Itens que acabaram de sair de "processing" — ficam visíveis com o
// resultado final por alguns segundos antes de sumir da lista, em vez de
// desaparecer sem aviso.
const transitioning = {};

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function timeAgo(isoString) {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const seconds = Math.max(0, Math.floor(diffMs / 1000));
  if (seconds < 60) return `há ${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `há ${hours}h`;
}

function renderProcessingItem(f) {
  const typeInfo = getFileTypeInfo(f.type);
  return `
    <div class="flex items-center gap-4 p-4 rounded-2xl" style="background:var(--bg-card);border:1px solid var(--border)">
      <div class="file-list-icon flex-shrink-0" style="background:${typeInfo.bg}">
        <i data-lucide="${typeInfo.icon}" style="color:${typeInfo.color};width:20px;height:20px"></i>
      </div>
      <div class="flex-1 min-w-0">
        <p class="text-sm font-medium truncate">${escapeHtml(f.name)}</p>
        <p class="text-xs" style="color:var(--text-muted)">Enviado ${timeAgo(f.createdAt)}</p>
      </div>
      <div class="flex items-center gap-2 text-xs px-3 py-1.5 rounded-full flex-shrink-0" style="background:rgba(124,58,237,0.12);color:var(--violet-light)">
        <i data-lucide="loader-2" class="spin" style="width:14px;height:14px"></i>
        Classificando...
      </div>
    </div>`;
}

function renderTransitionItem(id, t) {
  const typeInfo = getFileTypeInfo(t.type);
  const badge = t.status === 'done'
    ? `<span class="text-xs px-3 py-1.5 rounded-full flex-shrink-0" style="background:rgba(34,197,94,0.12);color:var(--success)">✓ ${escapeHtml(t.category || 'sem categoria')}</span>`
    : `<span class="text-xs px-3 py-1.5 rounded-full flex-shrink-0" style="background:rgba(239,68,68,0.12);color:var(--error)">✗ Erro ao classificar</span>`;
  return `
    <div class="flex items-center gap-4 p-4 rounded-2xl" style="background:var(--bg-card);border:1px solid var(--border)">
      <div class="file-list-icon flex-shrink-0" style="background:${typeInfo.bg}">
        <i data-lucide="${typeInfo.icon}" style="color:${typeInfo.color};width:20px;height:20px"></i>
      </div>
      <div class="flex-1 min-w-0">
        <p class="text-sm font-medium truncate">${escapeHtml(t.name)}</p>
      </div>
      ${badge}
    </div>`;
}

function renderProcessingQueue() {
  const container = document.getElementById('processing-list');
  const empty = document.getElementById('processing-empty');

  const processing = MOCK_FILES.filter((f) => f.status === 'processing');
  const transitioningIds = Object.keys(transitioning);

  if (processing.length === 0 && transitioningIds.length === 0) {
    container.innerHTML = '';
    empty.classList.remove('hidden');
    lucide.createIcons();
    return;
  }
  empty.classList.add('hidden');

  const rows = [
    ...processing.map(renderProcessingItem),
    ...transitioningIds.map((id) => renderTransitionItem(id, transitioning[id])),
  ];

  container.innerHTML = rows.join('');
  lucide.createIcons();
}

async function refreshAndRender() {
  const wasProcessing = new Map(
    MOCK_FILES.filter((f) => f.status === 'processing').map((f) => [f.id, f])
  );

  await loadUploadedFiles();

  wasProcessing.forEach((f, id) => {
    if (transitioning[id]) return;
    const updated = MOCK_FILES.find((m) => m.id === id);
    if (updated && updated.status === 'processing') return; // ainda processando

    transitioning[id] = {
      name: f.name,
      type: f.type,
      status: updated ? updated.status : 'error',
      category: updated ? updated.category : null,
    };
    setTimeout(() => {
      delete transitioning[id];
      renderProcessingQueue();
    }, PROCESSING_TRANSITION_DISPLAY_MS);
  });

  renderProcessingQueue();
}

(async function initProcessing() {
  await refreshAndRender();
  setInterval(refreshAndRender, PROCESSING_POLL_INTERVAL_MS);
})();
