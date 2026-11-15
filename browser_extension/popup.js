document.addEventListener("DOMContentLoaded", () => {
  const dot = document.getElementById("dot");
  const statusText = document.getElementById("status-text");
  const reconnectBtn = document.getElementById("reconnect-btn");

  // Query background for status
  chrome.runtime.sendMessage({ type: "get_status" }, (res) => {
    updateUI(res?.connected || false);
  });

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "connection_status") {
      updateUI(msg.connected);
    }
  });

  reconnectBtn.addEventListener("click", () => {
    statusText.innerText = "Reconnecting...";
    chrome.runtime.sendMessage({ type: "reconnect" });
  });

  function updateUI(connected) {
    if (connected) {
      dot.className = "status-dot connected";
      statusText.innerText = "Connected to NEO (Active tabs synced)";
      reconnectBtn.style.display = "none";
    } else {
      dot.className = "status-dot";
      statusText.innerText = "Disconnected (NEO Assistant offline)";
      reconnectBtn.style.display = "block";
    }
  }
});
