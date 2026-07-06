async function apiGet(url) {
  const response = await fetch(url, { cache: "no-store" });
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || response.statusText);
  }
  return data;
}

function setBusy(isBusy) {
  for (const button of document.querySelectorAll("button")) {
    button.disabled = isBusy;
  }
}

function showPageError(error) {
  const message = error instanceof Error ? error.message : String(error);
  const banner = document.createElement("div");
  banner.className = "card";
  banner.style.borderColor = "#f1b4b4";
  banner.style.background = "#fff5f5";
  banner.textContent = message;
  document.querySelector("main")?.prepend(banner);
}

function formatShape(shape) {
  return Array.isArray(shape) ? shape.join(" x ") : "-";
}

function formatSpacing(spacing) {
  return Array.isArray(spacing) ? spacing.map((value) => Number(value).toFixed(2)).join(" / ") : "-";
}

function defaultPlane(status) {
  return String(status?.info?.Plane || "sagittal").toLowerCase();
}

function planeLength(shape, plane) {
  if (!Array.isArray(shape)) return 1;
  if (plane === "sagittal") return shape[2];
  if (plane === "coronal") return shape[1];
  return shape[0];
}
