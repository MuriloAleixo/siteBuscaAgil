// =============================================================
// Histórico de Processamento — um item por arquivo/link (status vem do
// catálogo, GET /files), filtrável por status. Cada item pode ser
// expandido pra ver a linha do tempo detalhada de eventos (GET
// /processing-log, ver api/processing_log.py) — o motivo real de um erro,
// por exemplo, em vez de só um badge genérico "com erro".
// =============================================================

lucide.createIcons();
if (!requireAuth()) throw new Error('Not authenticated');

const user = getCurrentUser();
setAvatar(document.getElementById('sidebar-avatar'), user);
setAvatar(document.getElementById('header-avatar'), user);
document.getElementById('sidebar-name').textContent = user.name;

// ── Sidebar Toggle ──
document.getElementById('sidebar-toggle').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebar-overlay').classList.toggle('open');
});
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('open');
}

const HISTORY_POLL_INTERVAL_MS = 4000;

const HISTORY_FILTERS = [
  { key: 'all', label: 'Todos' },
  { key: 'processing', label: 'Ativos' },
  { key: 'done', label: 'Concluídos' },
  { key: 'error', label: 'Com erro' },
];

const HISTORY_EMPTY_TEXT = {
  all: ['Nada por aqui ainda', 'Os arquivos que você enviar aparecem aqui.'],
  processing: ['Nada em processamento no momento', 'Os arquivos que você enviar aparecem aqui enquanto a IA classifica.'],
  done: ['Nenhum item concluído ainda', 'Assim que uma classificação terminar com sucesso, aparece aqui.'],
  error: ['Nenhum erro registrado — tudo certo', 'Itens que falharem ao classificar/subir pro Drive aparecem aqui.'],
};

const STATUS_BADGE = {
  processing: { icon: 'loader-2', spin: true, color: 'var(--violet-light)', bg: 'rgba(124,58,237,0.12)', label: 'Classificando...' },
  done: { icon: 'check-circle', spin: false, color: 'var(--success)', bg: 'rgba(34,197,94,0.12)', label: 'Concluído' },
  error: { icon: 'x-circle', spin: false, color: 'var(--error)', bg: 'rgba(239,68,68,0.12)', label: 'Erro' },
};

const LOG_STEP_LABELS = {
  task: 'Processamento',
  classify: 'Classificação',
  upload_drive: 'Envio ao Drive',
  catalog_sync: 'Sincronização do catálogo',
  reprocess: 'Reprocessamento',
};

let currentHistoryFilter = 'all';
const expandedIds = new Set(); // ids com a linha do tempo aberta

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
  if (hours < 24) return `há ${hours}h`;
  const days = Math.floor(hours / 24);
  return `há ${days}d`;
}

// DOM ids são derivados do id do arquivo (pode ter pontos, ex.:
// "abc_arquivo.xlsx") — sempre usar getElementById (não querySelector) pra
// não precisar escapar caractere nenhum.
function timelineElId(fileId) {
  return `history-timeline-${fileId}`;
}

// ── Filtros ──
function renderFilterChips() {
  const container = document.getElementById('history-filters');
  container.innerHTML = HISTORY_FILTERS.map((f) => {
    const count = f.key === 'all' ? MOCK_FILES.length : MOCK_FILES.filter((x) => x.status === f.key).length;
    const active = f.key === currentHistoryFilter ? ' active' : '';
    return `<button class="filter-chip${active}" data-status="${f.key}" onclick="setHistoryFilter('${f.key}')">${f.label} (${count})</button>`;
  }).join('');
}

function setHistoryFilter(key) {
  currentHistoryFilter = key;
  document.querySelectorAll('#history-filters .filter-chip').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.status === key);
  });
  renderHistoryList();
}

// ── Lista ──
function renderHistoryItem(f) {
  const typeInfo = getFileTypeInfo(f.type);
  const badge = STATUS_BADGE[f.status] || STATUS_BADGE.done;
  const badgeExtra = f.status === 'done' ? ` — ${escapeHtml(f.category || 'sem categoria')}` : '';
  const isOpen = expandedIds.has(f.id);

  return `
    <div class="flex flex-col gap-3 p-4 rounded-2xl" style="background:var(--bg-card);border:1px solid var(--border)">
      <div class="flex items-center gap-4">
        <div class="result-icon flex-shrink-0" style="background:${typeInfo.bg}">
          <i data-lucide="${typeInfo.icon}" style="color:${typeInfo.color};width:20px;height:20px"></i>
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium truncate">${escapeHtml(f.name)}</p>
          <p class="text-xs" style="color:var(--text-muted)">${
            f.status === 'processing'
              ? `Iniciado ${timeAgo(f.processingStartedAt)}`
              : `Enviado ${timeAgo(f.createdAt)}`
          }</p>
        </div>
        <div class="flex items-center gap-2 text-xs px-3 py-1.5 rounded-full flex-shrink-0" style="background:${badge.bg};color:${badge.color}">
          <i data-lucide="${badge.icon}" class="${badge.spin ? 'spin' : ''}" style="width:14px;height:14px"></i>
          ${badge.label}${badgeExtra}
        </div>
        ${f.status === 'processing' ? `
        <button class="btn btn-ghost btn-sm flex-shrink-0" onclick="restartItem('${f.id}')" title="Reiniciar">
          <i data-lucide="rotate-ccw" class="w-4 h-4"></i>
        </button>
        <button class="btn btn-ghost btn-sm flex-shrink-0" onclick="cancelItem('${f.id}')" title="Cancelar">
          <i data-lucide="ban" class="w-4 h-4" style="color:var(--error)"></i>
        </button>` : ''}
        <button class="btn btn-ghost btn-sm flex-shrink-0 timeline-toggle-btn" onclick="toggleTimeline('${f.id}')" title="Ver linha do tempo">
          <i data-lucide="chevron-down" class="w-4 h-4" style="transition:transform .15s ease${isOpen ? ';transform:rotate(180deg)' : ''}"></i>
        </button>
      </div>
      <div id="${timelineElId(f.id)}" class="${isOpen ? '' : 'hidden'}">${isOpen ? '<p class="text-xs pl-1" style="color:var(--text-muted)">Carregando...</p>' : ''}</div>
    </div>`;
}

function renderHistoryList() {
  const container = document.getElementById('history-list');
  const empty = document.getElementById('history-empty');

  const files = currentHistoryFilter === 'all'
    ? MOCK_FILES
    : MOCK_FILES.filter((f) => f.status === currentHistoryFilter);

  if (files.length === 0) {
    container.innerHTML = '';
    const [title, text] = HISTORY_EMPTY_TEXT[currentHistoryFilter] || HISTORY_EMPTY_TEXT.all;
    document.getElementById('history-empty-title').textContent = title;
    document.getElementById('history-empty-text').textContent = text;
    empty.classList.remove('hidden');
    lucide.createIcons();
    return;
  }
  empty.classList.add('hidden');

  container.innerHTML = files.map(renderHistoryItem).join('');
  lucide.createIcons();

  // Linhas do tempo que já estavam abertas continuam carregadas depois de
  // cada refresh (o innerHTML acima recria o container do zero).
  expandedIds.forEach((id) => {
    if (MOCK_FILES.some((f) => f.id === id)) loadTimeline(id);
  });
}

// ── Linha do tempo (GET /processing-log?file_id=) ──
function renderTimelineEvent(ev) {
  const style = STATUS_BADGE[ev.status === 'started' ? 'processing' : ev.status] || STATUS_BADGE.done;
  const stepLabel = LOG_STEP_LABELS[ev.step] || ev.step;
  return `
    <div class="flex items-start gap-3">
      <div class="flex items-center justify-center flex-shrink-0 rounded-full" style="width:24px;height:24px;background:${style.bg};color:${style.color}">
        <i data-lucide="${style.icon}" style="width:12px;height:12px"></i>
      </div>
      <div class="flex-1 min-w-0">
        <p class="text-xs font-medium" style="color:var(--text)">${escapeHtml(stepLabel)}${ev.message ? ' — ' + escapeHtml(ev.message) : ''}</p>
        <p class="text-xs mt-0.5" style="color:var(--text-muted)">${timeAgo(ev.created_at)}</p>
      </div>
    </div>`;
}

async function loadTimeline(fileId) {
  const el = document.getElementById(timelineElId(fileId));
  if (!el) return;
  try {
    const res = await fetch(`/processing-log?file_id=${encodeURIComponent(fileId)}`, { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();
    if (!data.success) return;

    el.innerHTML = data.events.length === 0
      ? `<p class="text-xs pl-1" style="color:var(--text-muted)">Nenhum evento registrado pra este item.</p>`
      : `<div class="flex flex-col gap-3 pt-3 mt-1" style="border-top:1px solid var(--border)">${data.events.map(renderTimelineEvent).join('')}</div>`;
    lucide.createIcons();
  } catch (e) {
    // rede instável — mantém o que já estava mostrado
  }
}

function toggleTimeline(fileId) {
  const el = document.getElementById(timelineElId(fileId));
  if (!el) return;
  const willOpen = el.classList.contains('hidden');
  el.classList.toggle('hidden', !willOpen);
  if (willOpen) {
    expandedIds.add(fileId);
    el.innerHTML = `<p class="text-xs pl-1" style="color:var(--text-muted)">Carregando...</p>`;
    loadTimeline(fileId);
  } else {
    expandedIds.delete(fileId);
  }
  // Só gira o ícone do botão clicado (em vez de trocar chevron-down por
  // chevron-up) — lucide.createIcons() já trocou o <i data-lucide> original
  // por <svg>, então mudar o ícone exigiria recriá-lo; girar com CSS é mais
  // simples e não precisa re-renderizar a lista inteira (perderia o estado
  // de scroll/outras linhas do tempo abertas).
  const icon = el.previousElementSibling?.querySelector('.timeline-toggle-btn svg, .timeline-toggle-btn i');
  if (icon) icon.style.transform = willOpen ? 'rotate(180deg)' : '';
}

// ── Ações sobre um item ativo: reiniciar ou cancelar ──
// Não existe "pausar" de verdade: a classificação é uma chamada síncrona
// (Ollama/Gemini/ffmpeg) sem checkpoint no meio pra suspender e retomar —
// só dá pra matar a tarefa (cancelar) ou matar e começar de novo (reiniciar).
// Ver api/app.py::_revoke_task.
async function postAction(path, fileId) {
  const res = await fetch(`/files/${encodeURIComponent(fileId)}/${path}`, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrfToken() },
  });
  const data = await res.json();
  if (!res.ok || !data.success) {
    throw new Error(data.error || `Falha ao ${path} (${res.status}).`);
  }
  return data;
}

async function restartItem(fileId) {
  try {
    await postAction('restart', fileId);
    showToast('Reiniciando classificação...', 'info');
    refreshHistory();
  } catch (e) {
    showToast(e.message || 'Erro ao reiniciar.', 'error');
  }
}

async function cancelItem(fileId) {
  if (!confirm('Cancelar esta classificação em andamento?')) return;
  try {
    await postAction('cancel', fileId);
    showToast('Classificação cancelada.', 'info');
    refreshHistory();
  } catch (e) {
    showToast(e.message || 'Erro ao cancelar.', 'error');
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

// ── Estatísticas da fila (broker + catálogo) ──
async function refreshQueueStats() {
  try {
    const res = await fetch('/queue', { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();
    if (!data.success) return;

    document.getElementById('queue-stat-processing').textContent = `${data.counts.processing || 0} processando`;
    document.getElementById('queue-stat-done').textContent = `${data.counts.done || 0} concluídos`;
    document.getElementById('queue-stat-error').textContent = `${data.counts.error || 0} com erro`;
    document.getElementById('queue-stat-broker').textContent =
      data.pending_in_broker === null ? 'broker indisponível' : `${data.pending_in_broker} no broker`;
  } catch (e) {
    // rede instável — mantém os últimos valores exibidos
  }
}

async function refreshHistory() {
  await loadUploadedFiles();
  renderFilterChips();
  renderHistoryList();
}

(async function initProcessing() {
  renderFilterChips();
  await Promise.all([refreshHistory(), refreshQueueStats()]);
  setInterval(refreshHistory, HISTORY_POLL_INTERVAL_MS);
  setInterval(refreshQueueStats, HISTORY_POLL_INTERVAL_MS);
})();
