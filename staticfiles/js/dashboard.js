// =============================================================
// Dashboard Search & File Management Logic (Aurora Theme)
// =============================================================

lucide.createIcons();

if (!requireAuth()) throw new Error('Not authenticated');

const user = getCurrentUser();

let currentView = 'grid';
let currentType = 'all';

// Populate user details
document.getElementById('header-avatar').src = user.avatar;
document.getElementById('sidebar-avatar').src = user.avatar;
document.getElementById('sidebar-name').textContent = user.name;

function renderStorageBar() {
  // Cota real do Google Drive do usuário (buscada no login, ver
  // core/context_processors.py) — não usa mais o valor fixo do mock.
  const storagePct = (user.storageUsed / user.storageTotal * 100).toFixed(1);
  document.getElementById('storage-label').textContent = `${user.storageUsed} GB / ${user.storageTotal} GB`;
  setTimeout(() => {
    document.getElementById('storage-bar').style.width = storagePct + '%';
  }, 300);
}
renderStorageBar();

// View Toggle (Grid vs List)
function setView(v) {
  currentView = v;
  document.getElementById('view-grid-btn').style.color = v === 'grid' ? 'var(--violet-light)' : 'var(--text-3)';
  document.getElementById('view-list-btn').style.color = v === 'list' ? 'var(--violet-light)' : 'var(--text-3)';
  renderFiles();
}

// Filter Type
function setTypeFilter(type) {
  currentType = type;
  document.querySelectorAll('.filter-chip').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.type === type);
  });
  renderFiles();
}

function filterByType(type) {
  setTypeFilter(type);
}

// Clear Search & Filters
function clearSearchAndFilters() {
  document.getElementById('main-search-input').value = '';
  setTypeFilter('all');
}

// Keyboard Shortcut: Ctrl+K or Cmd+K to focus search input
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const input = document.getElementById('main-search-input');
    input.focus();
    input.select();
  }
});

// Real-time Search Listener
const mainSearchInput = document.getElementById('main-search-input');
let searchTimer;
mainSearchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  // Maior que o filtro local puro porque cada busca com texto dispara uma
  // chamada ao backend (análise via Gemini).
  searchTimer = setTimeout(renderFiles, 400);
});

// Sort Handler
function getSortedFiles(files) {
  const sortVal = document.getElementById('sort-select').value;
  return [...files].sort((a, b) => {
    if (sortVal === 'date-desc') return new Date(b.createdAt) - new Date(a.createdAt);
    if (sortVal === 'date-asc')  return new Date(a.createdAt) - new Date(b.createdAt);
    if (sortVal === 'name-asc')  return a.name.localeCompare(b.name);
    if (sortVal === 'size-desc') return b.size - a.size;
    return 0;
  });
}

// Highlight matched query in title
function highlightQuery(text, query) {
  if (!query) return text;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`(${escaped})`, 'gi');
  return text.replace(regex, '<mark class="q-highlight">$1</mark>');
}

// Main Render Function
let renderFilesRequestId = 0;

async function renderFiles() {
  const query = mainSearchInput.value.trim();

  const requestId = ++renderFilesRequestId;
  let files = await smartSearchFiles(query, currentType);
  if (requestId !== renderFilesRequestId) return; // resposta obsoleta, ignora

  files = getSortedFiles(files);

  const container = document.getElementById('files-container');
  const emptyState = document.getElementById('empty-state');
  const statusText = document.getElementById('search-status-text');
  const countBadge = document.getElementById('search-count-badge');

  // Update Stats text
  if (query) {
    statusText.textContent = `Resultados da busca por "${query}"`;
  } else if (currentType !== 'all') {
    const typeLabel = getFileTypeInfo(currentType).label;
    statusText.textContent = `Filtrado por formato: ${typeLabel}`;
  } else {
    statusText.textContent = 'Exibindo todos os arquivos enviados';
  }
  countBadge.textContent = `${files.length} arquivo(s)`;

  if (files.length === 0) {
    container.innerHTML = '';
    emptyState.classList.remove('hidden');
    document.getElementById('empty-message-text').textContent = query
      ? `Nenhum arquivo encontrado correspondente a "${query}".`
      : 'Nenhum arquivo encontrado para este filtro.';
    return;
  }

  emptyState.classList.add('hidden');

  if (currentView === 'grid') {
    container.innerHTML = `<div class="files-grid">${files.map(f => renderFileGridCard(f, query)).join('')}</div>`;
  } else {
    container.innerHTML = `<div class="flex flex-col gap-2">${files.map(f => renderResultCard(f, query)).join('')}</div>`;
  }

  lucide.createIcons();
}

function renderFileGridCard(file, query) {
  const typeInfo = getFileTypeInfo(file.type);
  const titleHtml = highlightQuery(file.name, query);

  const preview = file.previewUrl
    ? `<img src="${file.previewUrl}" alt="${file.name}" class="file-grid-preview" loading="lazy" />`
    : `<div class="file-grid-icon-area" style="--icon-glow:${typeInfo.color}33">
         <i data-lucide="${typeInfo.icon}" style="color:${typeInfo.color};width:38px;height:38px;position:relative;z-index:2"></i>
       </div>`;

  const star = file.starred ? `<span class="file-star"><i data-lucide="star" style="width:16px;height:16px;fill:#fbbf24"></i></span>` : '';
  const confidenceBadge = isLowConfidence(file)
    ? `<span class="low-confidence-badge" title="Classificação automática com baixa confiança — vale revisar">
         <i data-lucide="help-circle" style="width:13px;height:13px"></i>
       </span>`
    : '';

  return `
    <div class="file-grid-card" onclick="openFile('${file.id}')">
      ${preview}
      ${star}
      ${confidenceBadge}
      <div class="file-grid-body">
        <div class="file-grid-name" title="${file.name}">${titleHtml}</div>
        <div class="flex items-center justify-between mt-2">
          <span class="type-pill" style="background:${typeInfo.bg};color:${typeInfo.color}">${typeInfo.label}</span>
          <span class="file-grid-meta">${formatFileSize(file.size)}</span>
        </div>
        <div class="file-grid-meta mt-1">${formatDate(file.createdAt)}</div>
      </div>
    </div>`;
}

function renderResultCard(file, query) {
  const typeInfo = getFileTypeInfo(file.type);
  const titleHtml = highlightQuery(file.name, query);

  const iconOrThumb = file.previewUrl
    ? `<img src="${file.previewUrl}" alt="${file.name}" class="result-preview" />`
    : `<div class="result-icon" style="background:${typeInfo.bg}">
         <i data-lucide="${typeInfo.icon}" style="color:${typeInfo.color};width:20px;height:20px"></i>
       </div>`;

  return `
    <div class="result-card" onclick="openFile('${file.id}')">
      ${iconOrThumb}
      <div class="flex-1 min-w-0">
        <div class="result-name" title="${file.name}">${titleHtml}</div>
        <div class="result-meta mt-0.5">${typeInfo.label} • ${formatFileSize(file.size)} • ${formatDate(file.createdAt)}</div>
      </div>
      ${isLowConfidence(file) ? `<i data-lucide="help-circle" class="w-4 h-4" style="color:#f97316" title="Classificação automática com baixa confiança"></i>` : ''}
      <span class="type-pill hidden sm:inline-flex" style="background:${typeInfo.bg};color:${typeInfo.color}">${typeInfo.label}</span>
      <i data-lucide="chevron-right" class="w-4 h-4" style="color:var(--text-3)"></i>
    </div>`;
}

function openFile(id) {
  window.location.href = `file-view.html?id=${id}`;
}

// Sidebar Mobile Toggle
document.getElementById('sidebar-toggle').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebar-overlay').classList.toggle('open');
});

function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('open');
}

// Initial View Render — load real uploaded files first, then render
(async function initDashboard() {
  await loadUploadedFiles();
  renderStorageBar();
  setView('grid');
})();
