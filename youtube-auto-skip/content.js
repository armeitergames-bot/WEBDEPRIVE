// Pulsa el botón "Saltar anuncio" de YouTube en cuanto aparece y es clicable,
// es decir, cuando termina la cuenta atrás del anuncio.
(() => {
  const SKIP_SELECTORS = [
    '.ytp-skip-ad-button',
    '.ytp-ad-skip-button',
    '.ytp-ad-skip-button-modern',
    '.ytp-ad-skip-button-slot button',
    'button[id^="skip-button"]'
  ].join(',');

  let enabled = true;
  let lastClick = 0;

  chrome.storage.sync.get({ enabled: true }, (data) => {
    enabled = data.enabled;
    if (enabled) trySkip();
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'sync' && changes.enabled) {
      enabled = changes.enabled.newValue;
      if (enabled) trySkip();
    }
  });

  function isVisible(el) {
    if (!el || !el.isConnected) return false;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
      return false;
    }
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function trySkip() {
    if (!enabled) return;
    const player = document.querySelector('.html5-video-player');
    if (!player || !player.classList.contains('ad-showing')) return;

    for (const btn of document.querySelectorAll(SKIP_SELECTORS)) {
      if (!isVisible(btn) || btn.disabled) continue;
      const now = Date.now();
      if (now - lastClick < 500) return; // evita clics repetidos
      lastClick = now;
      btn.click();
      chrome.storage.local.get({ skipped: 0 }, ({ skipped }) => {
        chrome.storage.local.set({ skipped: skipped + 1 });
      });
      return;
    }
  }

  // Reacciona a cambios del DOM (aparición del botón, cambio de clases del reproductor).
  const observer = new MutationObserver(trySkip);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class', 'style']
  });

  // Respaldo por si algún cambio no dispara el observer.
  setInterval(trySkip, 500);
})();
