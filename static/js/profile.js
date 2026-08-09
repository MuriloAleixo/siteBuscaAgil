// =============================================================
// Profile Page Logic (Aurora Theme)
// =============================================================

lucide.createIcons();
if (!requireAuth()) throw new Error('Not authenticated');

const user = getCurrentUser();
const stats = getStorageStats();

// Populate
if (document.getElementById('sidebar-avatar')) document.getElementById('sidebar-avatar').src = user.avatar;
if (document.getElementById('sidebar-name')) document.getElementById('sidebar-name').textContent = user.name;

if (document.getElementById('profile-avatar')) document.getElementById('profile-avatar').src = user.avatar;
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

// Storage
const storagePct = (user.storageUsed / user.storageTotal * 100).toFixed(1);
if (document.getElementById('storage-text')) {
  document.getElementById('storage-text').textContent = `${user.storageUsed} GB de ${user.storageTotal} GB (${storagePct}%)`;
}
setTimeout(() => {
  if (document.getElementById('storage-bar')) document.getElementById('storage-bar').style.width = storagePct + '%';
}, 300);

// Stats
if (document.getElementById('stat-total')) document.getElementById('stat-total').textContent = stats.totalFiles;
if (document.getElementById('stat-images')) document.getElementById('stat-images').textContent = stats.byType.image ? stats.byType.image.count : 0;
if (document.getElementById('stat-pdfs')) document.getElementById('stat-pdfs').textContent = stats.byType.pdf ? stats.byType.pdf.count : 0;
if (document.getElementById('stat-videos')) document.getElementById('stat-videos').textContent = stats.byType.video ? stats.byType.video.count : 0;

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
