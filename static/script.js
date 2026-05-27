const state = {
  payload: null,
  allResults: [],
  filteredResults: [],
  searchQuery: "",
};

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

function setStatus(message) {
  const badge = document.getElementById("status-badge");
  if (badge) {
    badge.textContent = message;
  }
}

function setLastUpdated(value) {
  const el = document.getElementById("last-updated");
  if (el) {
    el.textContent = value || "-";
  }
}

function formatName(result) {
  return `${result.prenom} ${result.nom}`;
}

function updateSuggestionLists(results) {
  const fullnamesList = document.getElementById("fullnames-list");
  if (!fullnamesList) return;

  const names = new Set();

  (results || []).forEach((result) => {
    const fullName = formatName(result).trim();
    if (fullName) names.add(fullName);
  });

  fullnamesList.innerHTML = "";

  [...names].sort().forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    fullnamesList.appendChild(option);
  });
}

function applySearchFilter() {
  const query = normalizeText(state.searchQuery);

  const filtered = (state.allResults || []).filter((result) => {
    const fullName = normalizeText(formatName(result));
    return !query || fullName.includes(query);
  });

  state.filteredResults = filtered;
  renderResults(filtered);

  const countEl = document.getElementById("result-count");
  if (countEl) {
    countEl.textContent = String(filtered.length);
  }

  if (query) {
    setStatus(`${filtered.length} résultat(s)`);
  } else if (state.payload) {
    setStatus(state.payload.count ? "Pret" : "Vide");
  }
}

function renderEmpty(message) {
  const body = document.getElementById("results-body");
  if (!body) return;
  body.innerHTML = "";
  const row = document.createElement("tr");
  row.className = "empty-row";
  const cell = document.createElement("td");
  cell.colSpan = 5;
  cell.textContent = message;
  row.appendChild(cell);
  body.appendChild(row);
}

function renderResults(results) {
  const body = document.getElementById("results-body");
  if (!body) return;
  body.innerHTML = "";

  if (!results || results.length === 0) {
    renderEmpty("Aucune performance exceptionnelle trouvee.");
    return;
  }

  results.forEach((result, index) => {
    const row = document.createElement("tr");
    row.className = `rank-${index + 1}`;

    const cells = [
      result.date || "N/A",
      formatName(result),
      String(result.points_joueur ?? "-"),
      String(result.points_adv ?? "-"),
      `+${result.ecart ?? 0}`,
    ];

    cells.forEach((value, cellIndex) => {
      const cell = document.createElement("td");
      if (cellIndex === cells.length - 1) {
        cell.className = "progress-cell";
        cell.innerHTML = `<span class="progress-pill">${value}</span>`;
      } else {
        cell.textContent = value;
      }
      row.appendChild(cell);
    });

    body.appendChild(row);
  });
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function loadTop3(forceRefresh = false) {
  setStatus(forceRefresh ? "Rafraichissement..." : "Chargement...");
  try {
    const payload = await fetchJson(`/api/top3${forceRefresh ? "?refresh=1" : ""}`);
    state.payload = payload;
    state.allResults = payload.results || [];
    updateSuggestionLists(state.allResults);
    applySearchFilter();
    const countEl = document.getElementById("result-count");
    if (countEl) {
      countEl.textContent = String((state.filteredResults || state.allResults || []).length);
    }
    setLastUpdated(payload.generated_at || "-");
    if (!state.searchQuery || String(state.searchQuery).trim() === "") {
      setStatus(payload.count ? "Pret" : "Vide");
    }
  } catch (error) {
    console.error(error);
    renderEmpty("Impossible de recuperer les resultats FFTT.");
    setStatus("Erreur");
  }
}

async function loadPlayersSummary() {
  try {
    const payload = await fetchJson("/api/players");
    const club = document.getElementById("club-number");
    if (club) {
      club.textContent = `${payload.club} (${payload.count})`;
    }
  } catch (error) {
    console.error(error);
  }
}

async function copyResults() {
  if (!state.payload || !state.payload.text) {
    await loadTop3(false);
  }
  if (!state.payload || !state.payload.text) {
    setStatus("Aucun texte a copier");
    return;
  }
  await navigator.clipboard.writeText(state.payload.text);
  setStatus("Copie dans le presse-papiers");
}

function downloadResults() {
  window.location.href = "/api/save";
}

function syncSearchInputs() {
  const searchInput = document.getElementById("search-name");

  state.searchQuery = searchInput ? searchInput.value : "";
}

async function executeSearch() {
  syncSearchInputs();

  if (!state.payload) {
    await loadTop3(false);
    return;
  }

  applySearchFilter();
}

function resetSearch() {
  const searchInput = document.getElementById("search-name");
  if (searchInput) searchInput.value = "";

  state.searchQuery = "";
  applySearchFilter();
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("load-btn")?.addEventListener("click", () => loadTop3(false));
  document.getElementById("refresh-btn")?.addEventListener("click", () => loadTop3(true));
  document.getElementById("copy-btn")?.addEventListener("click", () => copyResults());
  document.getElementById("save-btn")?.addEventListener("click", () => downloadResults());
  document.getElementById("search-btn")?.addEventListener("click", () => executeSearch());
  document.getElementById("reset-search-btn")?.addEventListener("click", () => resetSearch());

  document.getElementById("search-name")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      executeSearch();
    }
  });

  document.getElementById("search-name")?.addEventListener("input", () => {
    syncSearchInputs();
    if (state.payload) {
      applySearchFilter();
    }
  });

});
