function renderChecks(checks) {
  const list = document.getElementById("checksList");
  list.innerHTML = "";
  for (const check of checks || []) {
    const row = document.createElement("div");
    row.className = "check-row";
    row.innerHTML = `
      <span>${check.label}</span>
      <strong class="${check.ok ? "ok" : "fail"}">${check.ok ? "OK" : "Needs attention"}</strong>
    `;
    list.appendChild(row);
  }
}

async function loadAiStatus() {
  setBusy(true);
  try {
    const data = await apiGet("/api/ai-results");
    document.getElementById("engineText").textContent = data.engine || "-";
    document.getElementById("maskText").textContent = data.mask_source || "-";
    document.getElementById("meshText").textContent = data.mesh_source || "-";
    document.getElementById("shapeText").textContent = formatShape(data.volume_shape);
    document.getElementById("aiWarning").textContent = data.warning || "Viewer only. Not for diagnosis.";
    renderChecks(data.checks);
  } finally {
    setBusy(false);
  }
}

document.getElementById("refreshAiBtn")?.addEventListener("click", () => {
  loadAiStatus().catch(showPageError);
});

loadAiStatus().catch(showPageError);
