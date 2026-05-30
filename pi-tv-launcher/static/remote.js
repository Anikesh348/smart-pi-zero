const statusText = document.getElementById("statusText");
const messageText = document.getElementById("messageText");
const pinInput = document.getElementById("pinInput");

function pinValue() {
  return pinInput ? pinInput.value : "";
}

function labelFor(command) {
  return command.replaceAll("_", " ");
}

function showMessage(text, ok) {
  messageText.textContent = text;
  messageText.className = ok ? "message ok" : "message error";
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({...body, pin: pinValue()})
  });
  const data = await response.json().catch(() => ({ok: false, error: "Invalid response"}));
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

async function command(cmd, extra = {}) {
  try {
    await postJson("/api/cmd", {cmd, ...extra});
    showMessage(`${labelFor(cmd)} sent`, true);
    refreshStatus();
  } catch (error) {
    showMessage(error.message, false);
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    const data = await response.json();
    const mode = data.dry_run ? " | dry run" : "";
    const browser = data.browser_running ? "running" : "stopped";
    statusText.textContent = `Browser: ${browser} | Command: ${data.browser_command || "unset"}${mode}`;
  } catch (error) {
    statusText.textContent = "Status unavailable";
  }
}

document.querySelectorAll("[data-cmd]").forEach((button) => {
  button.addEventListener("click", () => {
    const cmd = button.dataset.cmd;
    if (cmd === "reboot" && !confirm("Reboot the Pi now?")) {
      return;
    }
    command(cmd);
  });
});

document.getElementById("sendText").addEventListener("click", async () => {
  const input = document.getElementById("textInput");
  try {
    await postJson("/api/type", {text: input.value});
    showMessage("Text sent", true);
    input.value = "";
  } catch (error) {
    showMessage(error.message, false);
  }
});

document.getElementById("openUrl").addEventListener("click", () => {
  const input = document.getElementById("urlInput");
  command("open_url", {url: input.value.trim()});
});

document.getElementById("statusRefresh").addEventListener("click", refreshStatus);

refreshStatus();
setInterval(refreshStatus, 10000);
