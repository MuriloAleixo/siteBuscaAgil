// =============================================================
// Profile Page Logic (Aurora Theme)
// =============================================================

lucide.createIcons();
if (!requireAuth()) throw new Error('Not authenticated');

const user = getCurrentUser();

// Populate
setAvatar(document.getElementById('sidebar-avatar'), user);
setAvatar(document.getElementById('header-avatar'), user);
if (document.getElementById('sidebar-name')) document.getElementById('sidebar-name').textContent = user.name;

setAvatar(document.getElementById('profile-avatar'), user);
if (document.getElementById('profile-name')) document.getElementById('profile-name').textContent = user.name;
if (document.getElementById('profile-email')) document.getElementById('profile-email').textContent = user.email;
if (document.getElementById('profile-plan')) document.getElementById('profile-plan').textContent = user.plan + ' Plan';

// Member since
const joined = new Date(user.joinedAt);
if (document.getElementById('member-since')) {
  document.getElementById('member-since').textContent = joined.toLocaleDateString('pt-BR', {
    day: '2-digit', month: 'long', year: 'numeric'
  });
}

// Stats — precisa carregar os arquivos reais primeiro (MOCK_FILES começa
// vazio; ver loadUploadedFiles em catalog-client.js), senão fica sempre em 0.
(async () => {
  await loadUploadedFiles();
  const stats = getStorageStats();
  if (document.getElementById('stat-total')) document.getElementById('stat-total').textContent = stats.totalFiles;
  if (document.getElementById('stat-images')) document.getElementById('stat-images').textContent = stats.byType.image ? stats.byType.image.count : 0;
  if (document.getElementById('stat-pdfs')) document.getElementById('stat-pdfs').textContent = stats.byType.pdf ? stats.byType.pdf.count : 0;
  if (document.getElementById('stat-videos')) document.getElementById('stat-videos').textContent = stats.byType.video ? stats.byType.video.count : 0;
})();

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
