// =============================================================
// Dedicated Search Page Logic (Spotlight Search Engine)
// =============================================================

lucide.createIcons();

if (!requireAuth()) throw new Error('Not authenticated');

const user = getCurrentUser();
document.getElementById('sidebar-avatar').src = user.avatar;
document.getElementById('sidebar-name').textContent = user.name;
document.getElementById('header-avatar').src = user.avatar;

let currentFilter = 'all';

// Sidebar Toggle
document.getElementById('sidebar-toggle').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebar-overlay').classList.toggle('open');
});
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('open');
}

// Elements
const searchInput = document.getElementById('search-page-input');
const clearBtn = document.getElementById('clear-btn');
const resultsList = document.getElementById('search-results-list');
const emptyState = document.getElementById('search-empty');
const emptyText = document.getElementById('search-empty-text');
const resultsInfo = document.getElementById('search-results-info');

// Debounce search — maior que o filtro local puro porque cada busca com
// texto dispara uma chamada ao backend (análise via Gemini).
let timer;
searchInput.addEventListener('input', () => {
  clearTimeout(timer);
  const q = searchInput.value.trim();
  clearBtn.classList.toggle('hidden', q.length === 0);
  timer = setTimeout(runSearch, 400);
});

function clearSearchInput() {
  searchInput.value = '';
  clearBtn.classList.add('hidden');
  runSearch();
  searchInput.focus();
}

function setSearchFilter(type) {
  currentFilter = type;
  document.querySelectorAll('#search-filter-chips .filter-chip').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.type === type);
  });
  runSearch();
}

let searchRequestId = 0;

async function runSearch() {
  const query = searchInput.value.trim();

  if (query) {
    resultsInfo.textContent = `Analisando "${query}"...`;
  }

  const requestId = ++searchRequestId;
  const files = await smartSearchFiles(query, currentFilter);
  if (requestId !== searchRequestId) return; // resposta obsoleta, ignora

  renderSearchResults(files, query);
}

function renderSearchResults(files, query) {
  // Sort
  const sortVal = document.getElementById('search-sort').value;
  files.sort((a, b) => {
    if (sortVal === 'date-desc') return new Date(b.createdAt) - new Date(a.createdAt);
    if (sortVal === 'name-asc')  return a.name.localeCompare(b.name);
    if (sortVal === 'size-desc') return b.size - a.size;
    return 0;
  });

  if (query) {
    resultsInfo.textContent = `Buscando por "${query}" (${files.length} resultados)`;
  } else if (currentFilter !== 'all') {
    resultsInfo.textContent = `Filtro: ${getFileTypeInfo(currentFilter).label} (${files.length} resultados)`;
  } else {
    resultsInfo.textContent = `Todos os ${files.length} arquivos catalogados`;
  }

  if (files.length === 0) {
    resultsList.innerHTML = '';
    emptyState.classList.remove('hidden');
    emptyText.textContent = query
      ? `Nenhum arquivo encontrado para "${query}".`
      : 'Nenhum arquivo neste formato.';
    return;
  }

  emptyState.classList.add('hidden');
  resultsList.innerHTML = files.map(f => renderSearchCard(f, query)).join('');
  lucide.createIcons();
}

function highlightQuery(text, query) {
  if (!query) return text;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`(${escaped})`, 'gi');
  return text.replace(regex, '<mark class="q-highlight">$1</mark>');
}

function renderSearchCard(file, query) {
  const typeInfo = getFileTypeInfo(file.type);
  const titleHtml = highlightQuery(file.name, query);

  const iconOrThumb = file.previewUrl
    ? `<img src="${file.previewUrl}" alt="${file.name}" class="result-preview" />`
    : `<div class="result-icon" style="background:${typeInfo.bg}">
         <i data-lucide="${typeInfo.icon}" style="color:${typeInfo.color};width:22px;height:22px"></i>
       </div>`;

  return `
    <div class="result-card" onclick="window.location.href='file-view.html?id=${file.id}'">
      ${iconOrThumb}
      <div class="flex-1 min-w-0">
        <div class="result-name">${titleHtml}</div>
        <div class="result-meta mt-0.5">${typeInfo.label} • ${formatFileSize(file.size)} • Criado em ${formatDate(file.createdAt)}</div>
      </div>
      <span class="type-pill hidden sm:inline-flex" style="background:${typeInfo.bg};color:${typeInfo.color}">${typeInfo.label}</span>
      <i data-lucide="arrow-right" class="w-4 h-4" style="color:var(--text-3)"></i>
    </div>
  `;
}

// Check URL query param
const urlParams = new URLSearchParams(window.location.search);
const qParam = urlParams.get('q');
if (qParam) {
  searchInput.value = qParam;
  clearBtn.classList.remove('hidden');
}

// Initial Run — load real uploaded files first, then search
(async function initSearch() {
  await loadUploadedFiles();
  runSearch();
})();
