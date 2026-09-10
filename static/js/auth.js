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
