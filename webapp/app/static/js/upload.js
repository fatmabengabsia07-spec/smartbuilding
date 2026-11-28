/* Page Upload (SB-87) : glisser-déposer, validation client, progression,
   aperçu, injection et liste des fichiers. Les données viennent de l'API REST. */
(function () {
  "use strict";

  const MAX_BYTES = (window.SB_MAX_UPLOAD_MB || 100) * 1024 * 1024;
  const ALLOWED = ["csv", "json"];
  const PER_PAGE = 10;
  const BUSY_STATUSES = ["validating", "queued", "ingesting"];
  const STATUS_LABELS = {
    uploaded: ["Envoyé", "secondary"],
    validating: ["Validation", "info"],
    queued: ["En file", "warning"],
    ingesting: ["Ingestion", "primary"],
    indexed: ["Indexé", "success"],
    error: ["Erreur", "danger"],
  };
  const HTTP_MESSAGES = {
    400: "Fichier invalide.",
    413: "Fichier trop volumineux.",
    415: "Extension non acceptée (CSV ou JSON uniquement).",
    429: "Limite de dépôts dépassée. Réessayez plus tard.",
  };

  const $ = (id) => document.getElementById(id);
  const dropzone = $("dropzone");
  const fileInput = $("file-input");
  const typeSelect = $("file-type");
  const state = { page: 1, status: "", date: "", sort: "date", order: "desc" };
  let currentFileId = null;
  let uploading = false;
  let pollTimer = null;

  /* ---------- utilitaires ---------- */
  function escapeHtml(v) {
    return String(v === null || v === undefined ? "" : v).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function extOf(name) {
    const i = name.lastIndexOf(".");
    return i < 0 ? "" : name.slice(i + 1).toLowerCase();
  }
  function formatSize(b) {
    if (b < 1024) return b + " o";
    if (b < 1048576) return (b / 1024).toFixed(1) + " Ko";
    return (b / 1048576).toFixed(1) + " Mo";
  }
  function formatDate(iso) {
    // MongoDB renvoie des dates UTC sans fuseau : on ajoute "Z" pour afficher l'heure locale
    const d = new Date(/(Z|[+-]\d\d:?\d\d)$/.test(iso) ? iso : iso + "Z");
    return isNaN(d) ? "" : d.toLocaleString("fr-FR");
  }
  function showAlert(message, kind) {
    $("alert-zone").innerHTML =
      `<div class="alert alert-${kind || "danger"} alert-dismissible fade show">` +
      `${escapeHtml(message)}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>`;
  }
  function clearAlert() { $("alert-zone").innerHTML = ""; }
  function setProgress(pct, label) {
    $("progress-wrap").classList.remove("d-none");
    $("progress-bar").style.width = pct + "%";
    $("progress-label").textContent = label + (pct < 100 ? " (" + pct + " %)" : "");
  }

  /* ---------- étape 1 : choix, contrôle et envoi du fichier ---------- */
  function validateFile(file, ext) {
    if (!ALLOWED.includes(ext)) return "Extension non acceptée : seuls les fichiers CSV et JSON sont autorisés.";
    if (file.size === 0) return "Le fichier est vide.";
    if (file.size > MAX_BYTES) return `Fichier trop volumineux (maximum ${window.SB_MAX_UPLOAD_MB || 100} Mo).`;
    return null;
  }

  function resetPreview() {
    $("preview-card").classList.add("d-none");
    $("preview-head").innerHTML = "";
    $("preview-body").innerHTML = "";
    currentFileId = null;
  }

  function resetUpload() {
    resetPreview();
    $("progress-wrap").classList.add("d-none");
    $("file-name").textContent = "";
    fileInput.value = "";
    uploading = false;
  }

  function handleFile(file) {
    if (!file || uploading) return;
    clearAlert();
    resetPreview();
    const ext = extOf(file.name);
    if (ALLOWED.includes(ext)) typeSelect.value = ext; // le type suit l'extension
    const problem = validateFile(file, ext);
    if (problem) {
      showAlert(problem);
      fileInput.value = "";
      $("file-name").textContent = "";
      $("progress-wrap").classList.add("d-none");
      return;
    }
    $("file-name").textContent = `${file.name} (${formatSize(file.size)})`;
    sendFile(file);
  }

  function failUpload(message) {
    uploading = false;
    $("progress-wrap").classList.add("d-none");
    showAlert(message);
  }

  function sendFile(file) {
    uploading = true;
    setProgress(0, "Envoi en cours");
    const form = new FormData();
    form.append("file", file);
    const xhr = new XMLHttpRequest(); // XMLHttpRequest : fetch ne donne pas la progression d'envoi
    xhr.open("POST", "/upload");
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setProgress(Math.round((e.loaded / e.total) * 100), "Envoi en cours");
    };
    xhr.upload.onload = () => setProgress(100, "Contrôle du fichier…");
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (e) { /* réponse non JSON */ }
      if (xhr.status === 200 && data.file_id) {
        uploading = false;
        showPreview(data);
      } else {
        failUpload(data.error || HTTP_MESSAGES[xhr.status] || `Erreur serveur (${xhr.status}).`);
      }
    };
    xhr.onerror = () => failUpload("Connexion au serveur impossible.");
    xhr.send(form);
  }

  function showPreview(data) {
    currentFileId = data.file_id;
    setProgress(100, "Fichier reçu");
    const preview = data.preview || {};
    const cols = preview.columns || [];
    const rows = preview.rows || [];
    $("preview-info").textContent = `${data.original_name} · ${data.rows === undefined ? "?" : data.rows} ligne(s) détectée(s)`;
    $("preview-head").innerHTML = "<tr>" + cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("") + "</tr>";
    $("preview-body").innerHTML = rows.map((row) => {
      const cells = Array.isArray(row) ? row : cols.map((c) => row[c]);
      return "<tr>" + cells.map((v) => `<td>${escapeHtml(v)}</td>`).join("") + "</tr>";
    }).join("");
    $("preview-card").classList.remove("d-none");
    loadFiles();
  }

  /* ---------- étape 2 : confirmation de l'injection ---------- */
  async function confirmUpload() {
    if (!currentFileId) return;
    const btn = $("confirm-btn");
    btn.disabled = true;
    try {
      const res = await fetch(`/upload/${encodeURIComponent(currentFileId)}/confirm`,
        { method: "POST", headers: { Accept: "application/json" } });
      const data = await res.json().catch(() => ({}));
      if (res.status === 202) {
        resetUpload();
        showAlert("Fichier mis en file d'ingestion. Son statut est suivi dans la liste ci-dessous.", "success");
        await loadFiles();
      } else {
        showAlert(data.error || HTTP_MESSAGES[res.status] || `Erreur (${res.status}).`);
      }
    } catch (e) {
      showAlert("Connexion au serveur impossible.");
    } finally {
      btn.disabled = false;
    }
  }

  function cancelUpload() {
    resetUpload();
    showAlert("Envoi annulé : le fichier n'a pas été injecté.", "info");
  }

  /* ---------- liste des fichiers ---------- */
  function statusBadge(f) {
    const [label, color] = STATUS_LABELS[f.status] || [f.status, "secondary"];
    const tip = f.error_message ? ` title="${escapeHtml(f.error_message)}"` : "";
    return `<span class="badge text-bg-${color}"${tip}>${escapeHtml(label)}</span>`;
  }

  function renderFiles(items) {
    const body = $("files-body");
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="5" class="text-muted">Aucun fichier.</td></tr>';
      return;
    }
    body.innerHTML = items.map((f) =>
      `<tr><td>${escapeHtml(f.original_name)}</td><td>${escapeHtml(formatDate(f.uploaded_at))}</td>` +
      `<td>${escapeHtml(formatSize(f.size_bytes || 0))}</td><td>${statusBadge(f)}</td>` +
      `<td class="text-end">${f.logs_count === undefined || f.logs_count === null ? "—" : escapeHtml(f.logs_count)}</td></tr>`
    ).join("");
  }

  function renderPagination(total) {
    const pages = Math.max(1, Math.ceil(total / PER_PAGE));
    const items = [];
    const add = (label, page, disabled, active) =>
      items.push(`<li class="page-item${disabled ? " disabled" : ""}${active ? " active" : ""}">` +
                 `<a class="page-link" href="#" data-page="${page}">${label}</a></li>`);
    add("Précédent", state.page - 1, state.page <= 1, false);
    const start = Math.max(1, Math.min(state.page - 2, pages - 4));
    const end = Math.min(pages, start + 4);
    for (let p = start; p <= end; p++) add(p, p, false, p === state.page);
    add("Suivant", state.page + 1, state.page >= pages, false);
    $("files-pagination").innerHTML = items.join("");
    $("files-total").textContent = `${total} fichier(s)`;
  }

  async function loadFiles() {
    clearTimeout(pollTimer);
    const params = new URLSearchParams({ page: state.page, per_page: PER_PAGE,
                                         sort: state.sort, order: state.order });
    if (state.status) params.set("status", state.status);
    if (state.date) {
      // Jour choisi en heure locale, converti en UTC pour le serveur
      params.set("from", new Date(state.date + "T00:00:00").toISOString());
      params.set("to", new Date(state.date + "T23:59:59.999").toISOString());
    }
    try {
      const res = await fetch(`/api/v1/files?${params}`, { headers: { Accept: "application/json" } });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || res.status);
      const items = data.items || [];
      renderFiles(items);
      renderPagination(data.total || 0);
      // Suivi en temps réel : on réinterroge tant qu'un fichier est en cours de traitement
      if (items.some((f) => BUSY_STATUSES.includes(f.status))) pollTimer = setTimeout(loadFiles, 3000);
    } catch (e) {
      $("files-body").innerHTML =
        `<tr><td colspan="5" class="text-danger">Impossible de charger la liste (${escapeHtml(e.message)}).</td></tr>`;
    }
  }

  /* ---------- événements ---------- */
  ["dragover", "drop"].forEach((evt) => window.addEventListener(evt, (e) => e.preventDefault()));
  dropzone.addEventListener("dragover", () => dropzone.classList.add("dragover"));
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => {
    dropzone.classList.remove("dragover");
    handleFile(e.dataTransfer.files[0]);
  });
  $("browse-btn").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => handleFile(fileInput.files[0]));
  $("confirm-btn").addEventListener("click", confirmUpload);
  $("cancel-btn").addEventListener("click", cancelUpload);
  $("status-filter").addEventListener("change", (e) => {
    state.status = e.target.value;
    state.page = 1;
    loadFiles();
  });
  $("files-pagination").addEventListener("click", (e) => {
    const link = e.target.closest("a[data-page]");
    if (!link) return;
    e.preventDefault();
    if (link.parentElement.classList.contains("disabled") || link.parentElement.classList.contains("active")) return;
    state.page = Number(link.dataset.page);
    loadFiles();
  });

  function updateSortIndicators() {
    document.querySelectorAll("th[data-sort]").forEach((th) => {
      const ind = th.querySelector(".sort-ind");
      ind.textContent = th.dataset.sort === state.sort ? (state.order === "asc" ? " ▲" : " ▼") : "";
    });
  }
  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const field = th.dataset.sort;
      if (state.sort === field) {
        state.order = state.order === "asc" ? "desc" : "asc";
      } else {
        state.sort = field;
        state.order = (field === "name" || field === "status") ? "asc" : "desc";
      }
      state.page = 1;
      updateSortIndicators();
      loadFiles();
    });
  });
  $("date-filter").addEventListener("change", (e) => {
    state.date = e.target.value;
    state.page = 1;
    loadFiles();
  });
  $("reset-filters").addEventListener("click", () => {
    Object.assign(state, { page: 1, status: "", date: "", sort: "date", order: "desc" });
    $("status-filter").value = "";
    $("date-filter").value = "";
    updateSortIndicators();
    loadFiles();
  });

  updateSortIndicators();
  loadFiles();
})();
