async function loadUsers() {
  const data = await apiGet("/api/admin/users");
  const body = document.getElementById("usersBody");
  body.innerHTML = "";
  for (const user of data.users) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(user.username)}</td>
      <td>${escapeHtml(user.display_name)}</td>
      <td>${escapeHtml(user.role)}</td>
      <td>${escapeHtml((user.created_at || "").slice(0, 10))}</td>
    `;
    body.appendChild(row);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

document.getElementById("createUserForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.getElementById("createUserMessage");
  message.textContent = "";
  setBusy(true);
  try {
    const response = await fetch("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("newUsername").value,
        display_name: document.getElementById("newDisplayName").value,
        role: document.getElementById("newRole").value,
        password: document.getElementById("newPassword").value,
      }),
    });
    const data = await response.json();
    if (!response.ok || data.error) {
      throw new Error(data.error || "User creation failed");
    }
    event.target.reset();
    message.textContent = "Account created.";
    await loadUsers();
  } catch (error) {
    message.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    setBusy(false);
  }
});

loadUsers().catch(showPageError);
