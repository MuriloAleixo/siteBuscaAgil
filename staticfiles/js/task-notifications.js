// =============================================================
// Notificação persistente de "arquivo processado". Roda em toda página
// autenticada (ver templates) e continua de olho em uploads/links que
// ainda estão sendo classificados pelo worker Celery — mesmo depois de
// recarregar a página ou navegar pra outra — porque a lista de tarefas
// pendentes fica em localStorage, não em memória (memória morre junto com
// o JS da página quando o usuário navega). Sem isso, o polling de curto
// prazo em upload.js (40s) simplesmente desiste em silêncio se a
// classificação demorar mais que isso (comum com a IA local em CPU,
// principalmente vídeo/áudio).
// =============================================================

const BUSCA_AGIL_TASKS_STORAGE_KEY = "busca_agil_pending_tasks";
const BUSCA_AGIL_TASKS_POLL_INTERVAL_MS = 5000;
const BUSCA_AGIL_TASKS_MAX_AGE_MS = 60 * 60 * 1000; // 1h — só rede de segurança

let _buscaAgilTasksTimer = null;

function _buscaAgilReadPending() {
  try {
    return JSON.parse(localStorage.getItem(BUSCA_AGIL_TASKS_STORAGE_KEY) || "[]");
  } catch (e) {
    return [];
  }
}

function _buscaAgilWritePending(list) {
  try {
    localStorage.setItem(BUSCA_AGIL_TASKS_STORAGE_KEY, JSON.stringify(list));
  } catch (e) {
    // localStorage indisponível (modo privado etc.) — sem persistência, sem crash
  }
}

function _buscaAgilShowToast(msg, type = "info") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    container.id = "toast-container";
    document.body.appendChild(container);
  }
  const colors = { success: "#4ade80", error: "#f87171", info: "var(--violet-light)" };
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  const bullet = document.createElement("span");
  bullet.style.color = colors[type] || colors.info;
  bullet.textContent = "●";
  const text = document.createElement("span");
  text.textContent = msg;
  toast.appendChild(bullet);
  toast.appendChild(document.createTextNode(" "));
  toast.appendChild(text);
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = "toastOut 0.3s ease forwards";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function _buscaAgilStopPollingIfEmpty() {
  if (_buscaAgilReadPending().length === 0 && _buscaAgilTasksTimer) {
    clearInterval(_buscaAgilTasksTimer);
    _buscaAgilTasksTimer = null;
  }
}

function _buscaAgilEnsurePolling() {
  if (_buscaAgilTasksTimer) return;
  _buscaAgilTasksTimer = setInterval(_buscaAgilTick, BUSCA_AGIL_TASKS_POLL_INTERVAL_MS);
}

async function _buscaAgilCheckOne(task) {
  try {
    const res = await fetch(`${UPLOADED_FILES_API_URL}/${encodeURIComponent(task.id)}/status`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (data.success && (data.status === "done" || data.status === "error")) {
      return data;
    }
  } catch (e) {
    // rede instável durante o polling: tenta de novo no próximo ciclo
  }
  return null;
}

function _buscaAgilRefreshCurrentView() {
  if (typeof loadUploadedFiles !== "function") return;
  loadUploadedFiles()
    .then(() => {
      if (typeof renderFiles === "function") renderFiles();
      if (typeof runSearch === "function") runSearch();
    })
    .catch(() => {});
}

async function _buscaAgilTick() {
  const pending = _buscaAgilReadPending();
  if (pending.length === 0) {
    _buscaAgilStopPollingIfEmpty();
    return;
  }

  const now = Date.now();
  const stillPending = [];
  let anyResolved = false;

  for (const task of pending) {
    if (now - task.addedAt > BUSCA_AGIL_TASKS_MAX_AGE_MS) {
      continue; // tarefa velha demais — desiste em silêncio (rede de segurança)
    }

    const result = await _buscaAgilCheckOne(task);
    if (result === null) {
      stillPending.push(task);
      continue;
    }

    anyResolved = true;
    if (result.status === "done") {
      const categoria = result.category || "sem categoria";
      _buscaAgilShowToast(`"${task.name}" foi processado — categoria: ${categoria}.`, "success");
    } else {
      _buscaAgilShowToast(`Não foi possível concluir o processamento de "${task.name}".`, "error");
    }
  }

  _buscaAgilWritePending(stillPending);
  if (anyResolved) _buscaAgilRefreshCurrentView();
  _buscaAgilStopPollingIfEmpty();
}

const BuscaAgilTasks = {
  // Registra um arquivo/link recém-enviado como "ainda processando" —
  // continua sendo verificado mesmo se o usuário sair desta página.
  track(fileId, displayName) {
    if (!fileId) return;
    const pending = _buscaAgilReadPending();
    if (pending.some((t) => t.id === fileId)) return;
    pending.push({ id: fileId, name: displayName || fileId, addedAt: Date.now() });
    _buscaAgilWritePending(pending);
    _buscaAgilEnsurePolling();
  },
  // Remove da lista sem notificar — usado quando outra parte da página já
  // mostrou o próprio aviso de conclusão (ex.: o polling rápido do upload.js
  // resolveu a tempo).
  resolve(fileId) {
    const pending = _buscaAgilReadPending();
    const next = pending.filter((t) => t.id !== fileId);
    if (next.length !== pending.length) {
      _buscaAgilWritePending(next);
    }
    _buscaAgilStopPollingIfEmpty();
  },
};

(function buscaAgilTasksInit() {
  if (typeof isLoggedIn === "function" && !isLoggedIn()) return;
  if (_buscaAgilReadPending().length > 0) {
    _buscaAgilEnsurePolling();
  }
})();
