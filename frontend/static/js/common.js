async function apiGet(url) {
  const response = await fetch(url, { cache: "no-store" });
  const data = await response.json();
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("Login required");
  }
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

async function hydrateAuthMenu() {
  const menu = document.querySelector(".menu");
  if (!menu) return;
  try {
    const session = await apiGet("/api/auth/session");
    if (!menu.querySelector('a[href="/guide"]')) {
      const guideLink = document.createElement("a");
      guideLink.href = "/guide";
      guideLink.textContent = "Guide";
      if (window.location.pathname === "/guide") {
        guideLink.className = "active";
      }
      menu.appendChild(guideLink);
    }
    if (session.user?.role === "admin" && !menu.querySelector('a[href="/admin"]')) {
      const adminLink = document.createElement("a");
      adminLink.href = "/admin";
      adminLink.textContent = "Admin";
      menu.appendChild(adminLink);
    }
    const userBadge = document.createElement("span");
    userBadge.className = "user-chip";
    userBadge.textContent = session.user?.display_name || session.user?.username || "User";
    menu.appendChild(userBadge);

    const logoutButton = document.createElement("button");
    logoutButton.className = "nav-button";
    logoutButton.type = "button";
    logoutButton.textContent = "Logout";
    logoutButton.addEventListener("click", async () => {
      await fetch("/api/auth/logout", { method: "POST" });
      window.location.href = "/login";
    });
    menu.appendChild(logoutButton);
  } catch (error) {
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }
}

hydrateAuthMenu();
