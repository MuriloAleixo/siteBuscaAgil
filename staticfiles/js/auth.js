// =============================================================
// AUTH — login real com Google (django-allauth), sem sessionStorage.
//
// window.__BUSCA_AGIL_USER__ é injetado inline em cada template (server-
// side, via core/context_processors.busca_agil_user) a partir de
// request.user. Se o usuário não estiver logado, o Django já bloqueia a
// página com @login_required antes mesmo desse script rodar — as funções
// abaixo existem pra o front-end (JS que roda no navegador) continuar
// funcionando do mesmo jeito que antes.
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
  window.location.href = "/accounts/google/login/?process=login";
}

function logout() {
  window.location.href = "/accounts/logout/";
}

// Guard client-side (best-effort — a proteção real é @login_required no
// Django). Mantido pelo mesmo motivo de sempre: evitar telas quebradas se
// o usuário abrir a página com JS desatualizado em cache.
function requireAuth() {
  if (!isLoggedIn()) {
    window.location.href = "index.html";
    return false;
  }
  return true;
}
