// Hace un clic "real" (isTrusted: true) en el botón de saltar usando chrome.debugger.
// YouTube ignora los clics hechos con element.click() desde una extensión.
const attached = new Set();

async function trustedClick(tabId, x, y) {
  const target = { tabId };
  if (!attached.has(tabId)) {
    await chrome.debugger.attach(target, '1.3');
    attached.add(tabId);
  }
  const base = { x, y, button: 'left', clickCount: 1 };
  await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', { type: 'mousePressed', ...base });
  await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', { type: 'mouseReleased', ...base });
}

async function detach(tabId) {
  if (!attached.has(tabId)) return;
  attached.delete(tabId);
  try { await chrome.debugger.detach({ tabId }); } catch (e) { /* ya estaba suelto */ }
}

chrome.debugger.onDetach.addListener(({ tabId }) => attached.delete(tabId));
chrome.tabs.onRemoved.addListener((tabId) => attached.delete(tabId));

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const tabId = sender.tab && sender.tab.id;
  if (tabId == null) return;
  if (msg.type === 'trusted-click') {
    trustedClick(tabId, msg.x, msg.y)
      .then(() => sendResponse({ ok: true }))
      .catch((err) => { attached.delete(tabId); sendResponse({ ok: false, error: String(err) }); });
    return true;
  }
  if (msg.type === 'ad-finished') {
    // Soltar el depurador en cuanto acaba el anuncio para quitar el aviso amarillo.
    detach(tabId);
  }
});
