const rememberBtn = document.getElementById("rememberBtn");
const status = document.getElementById("status");
const searchInput = document.getElementById("searchInput");
const results = document.getElementById("results");
const folderPathInput = document.getElementById("folderPath");
const indexFolderBtn = document.getElementById("indexFolderBtn");
const aiStatus = document.getElementById("aiStatus");

const API_URL = "http://127.0.0.1:8000";
let searchTimeout;
let lastResults = [];

function setStatus(message, isError = false) {
  status.textContent = message;
  status.style.color = isError ? "#fca5a5" : "#a5b4cf";
}

function escapeHTML(text) {
  const div = document.createElement("div");
  div.textContent = String(text ?? "");
  return div.innerHTML;
}

function formatRelativeDate(isoValue) {
  if (!isoValue) return "Recently";

  const then = new Date(isoValue);
  const now = new Date();
  const diffMinutes = Math.max(1, Math.round((now - then) / 60000));

  if (diffMinutes < 60) return `${diffMinutes} min ago`;

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} hr ago`;

  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 30) return `${diffDays} days ago`;

  const diffMonths = Math.round(diffDays / 30);
  return `${diffMonths} mo ago`;
}

function showLoadingState(message = "Searching...") {
  results.innerHTML = `<div class="loading-state">🧠 ${message}</div>`;
}

function showNoResults(message = "No memories found.") {
  results.innerHTML = `<div class="no-results">${message}</div>`;
}

async function loadAiStatus() {
  try {
    const response = await fetch(`${API_URL}/ai-status`);
    const data = await response.json();
    if (!response.ok) throw new Error("AI status unavailable");

    if (data.gemma?.available) {
      aiStatus.textContent = `Local Gemma reasoning · ${data.gemma.model} + local embeddings`;
      aiStatus.classList.remove("fallback");
    } else {
      aiStatus.textContent = "Local semantic search · Gemma runtime not installed";
      aiStatus.classList.add("fallback");
    }
  } catch (error) {
    aiStatus.textContent = "Memory engine unavailable";
    aiStatus.classList.add("fallback");
  }
}

async function rememberCurrentPage() {
  setStatus("Reading this page...");

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      throw new Error("Could not access this tab.");
    }

    const pageResults = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({
        title: document.title,
        url: window.location.href,
        text: document.body ? document.body.innerText.slice(0, 12000) : "",
        saved_at: new Date().toISOString()
      })
    });

    const page = pageResults[0].result;
    const response = await fetch(`${API_URL}/remember-page`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(page)
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Could not save the page.");
    }

    const memory = data.memory || {};
    const saved = await chrome.storage.local.get("memories");
    const memories = Array.isArray(saved.memories) ? saved.memories : [];
    const savedPage = {
      id: memory.id,
      title: memory.title || page.title,
      url: memory.url || page.url,
      saved_at: memory.saved_at || page.saved_at
    };
    const existingIndex = memories.findIndex((item) => item.url === savedPage.url);
    if (existingIndex >= 0) memories[existingIndex] = savedPage;
    else memories.push(savedPage);
    await chrome.storage.local.set({ memories });

    setStatus(`Memory saved: ${memory.title || page.title}`);
  } catch (error) {
    console.error("Remember page error:", error);
    setStatus("This page could not be remembered.", true);
  }
}

async function indexChosenFolder() {
  const path = folderPathInput.value.trim();
  if (!path) {
    setStatus("Choose a folder path first.", true);
    return;
  }

  setStatus("Indexing the chosen folder...");
  indexFolderBtn.disabled = true;

  try {
    const response = await fetch(`${API_URL}/build-memory`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Folder indexing failed.");
    setStatus(`Indexed ${data.files} memories from the chosen folder.`);
  } catch (error) {
    console.error("Folder indexing error:", error);
    setStatus("Could not index that folder. Check the path and engine.", true);
  } finally {
    indexFolderBtn.disabled = false;
  }
}

function renderResults(matches) {
  lastResults = matches || [];

  if (!matches.length) {
    showNoResults("No memories found. Try a broader description.");
    return;
  }

  results.innerHTML = matches.map((memory) => {
    const title = escapeHTML(memory.title || memory.name || "Saved memory");
    const preview = escapeHTML(memory.summary || memory.preview || "Saved content indexed locally.");
    const reason = escapeHTML(memory.reason || "Matches the meaning of your query.");
    const source = escapeHTML((memory.source_type || memory.source || "memory").toString().toUpperCase());
    const date = formatRelativeDate(memory.saved_at || memory.created_at);
    const path = memory.url || memory.file_path || memory.path || "";
    const filename = escapeHTML(path.split(/[\\/]/).pop() || "Saved memory");

    return `
      <article class="memory-result" data-id="${escapeHTML(memory.id || "")}">
        <div class="memory-kicker">MEMORY FOUND</div>
        <h3>🧠 ${title}</h3>
        <p class="preview">${preview}</p>
        <div class="why-label">Why this matches</div>
        <p class="reason">${reason}</p>
        <div class="meta-row">
          <span>${source}</span>
          <span>${date}</span>
        </div>
        <div class="meta-row">
          <span class="filename">${filename}</span>
        </div>
        <div class="result-actions">
          <button class="open-btn" data-action="open" data-id="${escapeHTML(memory.id || "")}">Open</button>
          <button class="forget-btn" data-action="forget" data-id="${escapeHTML(memory.id || "")}">Forget</button>
        </div>
      </article>
    `;
  }).join("");
}

async function searchMemory(query) {
  try {
    const response = await fetch(`${API_URL}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query })
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const data = await response.json();
    renderResults(data.results || []);
  } catch (error) {
    console.error("Search error:", error);
    results.innerHTML = `
      <div class="no-results">
        ❌ Memory engine is unavailable.<br />
        Start the FastAPI server on 127.0.0.1:8000.
      </div>
    `;
  }
}

async function openMemory(memoryId) {
  const memory = lastResults.find((item) => item.id === memoryId);
  if (!memory) return;

  const target = memory.url || memory.file_path || memory.path;
  if (!target) {
    setStatus("This memory has no original source to open.", true);
    return;
  }

  if (target.startsWith("http://") || target.startsWith("https://")) {
    chrome.tabs.create({ url: target });
    return;
  }

  try {
    const response = await fetch(`${API_URL}/open`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: memoryId })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not open the original file.");
    setStatus("Opened the original file.");
  } catch (error) {
    console.error("Open memory error:", error);
    setStatus("Could not open the original file.", true);
  }
}

async function forgetMemory(memoryId) {
  try {
    const response = await fetch(`${API_URL}/forget`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: memoryId })
    });

    if (!response.ok) {
      throw new Error("Forget request failed");
    }

    const nextResults = lastResults.filter((item) => item.id !== memoryId);
    renderResults(nextResults);
    setStatus("Memory forgotten.");
  } catch (error) {
    console.error("Forget error:", error);
    setStatus("The memory could not be forgotten.", true);
  }
}

rememberBtn.addEventListener("click", rememberCurrentPage);
indexFolderBtn.addEventListener("click", indexChosenFolder);

searchInput.addEventListener("input", () => {
  clearTimeout(searchTimeout);
  const query = searchInput.value.trim();

  if (!query) {
    results.innerHTML = "";
    return;
  }

  showLoadingState("Understanding your search...");
  searchTimeout = setTimeout(() => searchMemory(query), 500);
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;

  const action = button.dataset.action;
  const memoryId = button.dataset.id;

  if (action === "open") {
    openMemory(memoryId);
  }

  if (action === "forget") {
    forgetMemory(memoryId);
  }
});

showNoResults("Search will appear here once you remember something or index a folder.");
loadAiStatus();