/**
 * background.js — NEO Browser Companion Background Service Worker
 * Maintains WebSocket bridge to NEO desktop assistant and routes commands to active tabs.
 */

const NEO_WS_URL = "ws://127.0.0.1:8765/extension";
let socket = null;
let reconnectTimer = null;
let isConnected = false;

function connectToNeo() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    socket = new WebSocket(NEO_WS_URL);

    socket.onopen = () => {
      isConnected = true;
      console.log("[NEO Companion] Connected to NEO Desktop Assistant.");
      notifyStatusChange(true);
      sendTabInventory();
    };

    socket.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleNeoCommand(msg);
      } catch (err) {
        console.error("[NEO Companion] Parse error:", err);
      }
    };

    socket.onclose = () => {
      isConnected = false;
      notifyStatusChange(false);
      scheduleReconnect();
    };

    socket.onerror = (err) => {
      isConnected = false;
      socket.close();
    };
  } catch (err) {
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectToNeo();
  }, 2500);
}

async function sendTabInventory() {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  const tabs = await chrome.tabs.query({});
  const activeTabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const active = activeTabs[0] || null;

  socket.send(JSON.stringify({
    type: "tab_inventory",
    tabs: tabs.map(t => ({ id: t.id, title: t.title, url: t.url, active: t.active })),
    activeTab: active ? { id: active.id, title: active.title, url: active.url } : null
  }));
}

async function handleNeoCommand(msg) {
  const reqId = msg.id;
  const action = msg.action;

  // Retrieve active tab
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];

  if (!tab || !tab.id) {
    sendResponse(reqId, false, "No active tab found in browser.");
    return;
  }

  if (action === "list_tabs") {
    const allTabs = await chrome.tabs.query({});
    sendResponse(reqId, true, "Tabs retrieved", {
      tabs: allTabs.map(t => ({ id: t.id, title: t.title, url: t.url }))
    });
    return;
  }

  // Forward command to content script of active tab
  chrome.tabs.sendMessage(tab.id, msg, (response) => {
    if (chrome.runtime.lastError) {
      sendResponse(reqId, false, `Content script error: ${chrome.runtime.lastError.message}`);
    } else {
      sendResponse(reqId, response?.success ?? true, response?.message ?? "Done", response?.data);
    }
  });
}

function sendResponse(id, success, message, data = null) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({
    type: "response",
    id: id,
    success: success,
    message: message,
    data: data
  }));
}

function notifyStatusChange(status) {
  chrome.runtime.sendMessage({ type: "connection_status", connected: status }).catch(() => {});
}

// Listen for tab switches
chrome.tabs.onActivated.addListener(() => sendTabInventory());
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "complete") sendTabInventory();
});

// Startup
connectToNeo();
