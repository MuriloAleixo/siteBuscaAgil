// =============================================================
// AUTH — login real com Google (api/auth.py, sem allauth), sem
// sessionStorage.
//
// window.__BUSCA_AGIL_USER__ é populado por uma chamada síncrona a GET /me
// (bootstrap inline no topo de cada página, ver frontend/pages/*.html) —
// antes disso era injetado pelo servidor (Django); agora a própria página
// estática busca o usuário logado assim que carrega, antes de qualquer
// outro script rodar.
// =============================================================

function isLoggedIn() {
  return !!window.__BUSCA_AGIL_USER__;
}

// Login com Google já pede o escopo de Drive na mesma tela de consentimento
// do Google — não existe mais um passo separado de "autorizar o Drive".
function isDriveAuthorized() {
  return isLoggedIn();
}

function getCurrentUser() {
  return window.__BUSCA_AGIL_USER__ || null;
}

function loginWithGoogle() {
  window.location.href = "/auth/login";
}

function logout() {
  window.location.href = "/auth/logout";
}

// Guard client-side (proteção real é @login_required nas rotas de
// api/app.py, que devolvem 401 sem sessão válida). Mantido pelo mesmo
// motivo de sempre: evitar telas quebradas se o usuário abrir a página com
// JS desatualizado em cache.
function requireAuth() {
  if (!isLoggedIn()) {
    window.location.href = "index.html";
    return false;
  }
  return true;
}

// Preenche um <img> de avatar com a foto de perfil do Google, com duas
// proteções contra o ícone de "imagem quebrada":
//   1. referrerPolicy="no-referrer" — o CDN de fotos do Google
//      (lh3.googleusercontent.com) pode recusar a requisição dependendo do
//      header Referer mandado pelo navegador; sem essa política, a foto
//      falhava silenciosamente pra algumas contas/navegadores.
//   2. onerror com fallback pra um avatar gerado (iniciais do nome) — cobre
//      o caso de a conta Google não ter foto (user.avatar vazio) ou a
//      imagem falhar de qualquer outro jeito.
function setAvatar(imgEl, user) {
  if (!imgEl || !user) return;
  const initial = (user.name || user.email || "?").trim().charAt(0).toUpperCase();
  const fallback =
    "data:image/svg+xml," +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" rx="32" fill="#7c3aed"/><text x="32" y="43" font-family="'Space Grotesk',sans-serif" font-size="28" fill="#fff" text-anchor="middle">${initial}</text></svg>`
    );
  imgEl.referrerPolicy = "no-referrer";
  imgEl.onerror = () => {
    imgEl.onerror = null;
    imgEl.src = fallback;
  };
  imgEl.src = user.avatar || fallback;
}
