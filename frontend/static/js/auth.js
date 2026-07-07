const form = document.getElementById("loginForm");
const message = document.getElementById("loginMessage");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "";
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("usernameInput").value,
        password: document.getElementById("passwordInput").value,
      }),
    });
    const data = await response.json();
    if (!response.ok || data.error) {
      throw new Error(data.error || "Login failed");
    }
    window.location.href = "/";
  } catch (error) {
    message.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    button.disabled = false;
  }
});
