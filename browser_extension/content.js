/**
 * content.js — NEO In-Page DOM Controller
 * Runs in active page to query DOM elements, simulate verified clicks, and extract content.
 */

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const { action, selector, text, script } = request;

  try {
    switch (action) {
      case "get_page_content": {
        const textContent = document.body ? document.body.innerText.slice(0, 15000) : "";
        sendResponse({
          success: true,
          message: "Page content extracted",
          data: {
            title: document.title,
            url: window.location.href,
            text: textContent
          }
        });
        break;
      }

      case "query_dom": {
        const elements = Array.from(document.querySelectorAll(selector || "button, a, input, select, textarea"))
          .slice(0, 30)
          .map((el, i) => {
            const rect = el.getBoundingClientRect();
            return {
              index: i,
              tagName: el.tagName.toLowerCase(),
              id: el.id || null,
              className: el.className || null,
              text: (el.innerText || el.value || "").trim().slice(0, 50),
              visible: rect.width > 0 && rect.height > 0,
              rect: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }
            };
          });
        sendResponse({ success: true, message: `Found ${elements.length} elements`, data: { elements } });
        break;
      }

      case "click": {
        let el = null;
        if (selector) {
          el = document.querySelector(selector);
        }
        if (!el && text) {
          // Search by text content
          const candidates = Array.from(document.querySelectorAll("button, a, span, div, input[type='submit'], input[type='button']"));
          el = candidates.find(c => (c.innerText || c.value || "").trim().toLowerCase() === text.trim().toLowerCase());
        }

        if (!el) {
          sendResponse({ success: false, message: `Element not found: '${selector || text}'` });
          return;
        }

        // Verified click sequence
        el.scrollIntoView({ behavior: "instant", block: "center" });
        el.focus();
        el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window }));
        el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window }));
        el.click();

        sendResponse({ success: true, message: `Clicked element '${selector || text}' successfully.` });
        break;
      }

      case "type": {
        const input = document.querySelector(selector);
        if (!input) {
          sendResponse({ success: false, message: `Input element not found: '${selector}'` });
          return;
        }

        input.scrollIntoView({ behavior: "instant", block: "center" });
        input.focus();
        input.value = text || "";
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));

        sendResponse({ success: true, message: `Typed into '${selector}' successfully.` });
        break;
      }

      case "eval_js": {
        const result = window.eval(script || text);
        sendResponse({ success: true, message: "Script evaluated", data: { result: String(result) } });
        break;
      }

      default:
        sendResponse({ success: false, message: `Unknown content action '${action}'` });
    }
  } catch (err) {
    sendResponse({ success: false, message: `Error executing '${action}': ${err.message}` });
  }

  return true; // Keep message channel open for async response
});
