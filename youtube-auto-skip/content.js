// Salta los anuncios de vídeo de YouTube:
// 1. Pulsa "Saltar anuncio" si el botón está disponible.
// 2. Si no se puede (anuncio no saltable o YouTube ignora el clic),
//    silencia el anuncio y lo adelanta hasta el final.
// También cierra los anuncios superpuestos (banners sobre el vídeo).
(() => {
  const SKIP_SELECTORS = [
    '.ytp-skip-ad-button',
    '.ytp-ad-skip-button',
    '.ytp-ad-skip-button-modern',
    '.ytp-ad-skip-button-slot button',
    'button[id^="skip-button"]'
  ].join(',');

  const OVERLAY_CLOSE_SELECTORS = [
    '.ytp-ad-overlay-close-button',
    '.ytp-ad-overlay-close-container'
  ].join(',');

  let enabled = true;
  let currentAdVideo = null; // vídeo del anuncio que ya contamos
  let mutedByUs = false;

  chrome.storage.sync.get({ enabled: true }, (data) => {
    enabled = data.enabled;
    tick();
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'sync' && changes.enabled) {
      enabled = changes.enabled.newValue;
      tick();
    }
  });

  function isVisible(el) {
    if (!el || !el.isConnected) return false;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function clickSkipButton() {
    for (const btn of document.querySelectorAll(SKIP_SELECTORS)) {
      if (isVisible(btn) && !btn.disabled) {
        btn.click();
        return true;
      }
    }
    return false;
  }

  function closeOverlays() {
    for (const btn of document.querySelectorAll(OVERLAY_CLOSE_SELECTORS)) {
      if (isVisible(btn)) btn.click();
    }
  }

  function countSkip() {
    chrome.storage.local.get({ skipped: 0 }, ({ skipped }) => {
      chrome.storage.local.set({ skipped: skipped + 1 });
    });
  }

  function tick() {
    document.documentElement.classList.toggle('yt-auto-skip-on', enabled);
    if (!enabled) return;
    closeOverlays();

    const player = document.querySelector('#movie_player.html5-video-player, .html5-video-player');
    const video = player && player.querySelector('video');
    if (!player || !video) return;

    if (player.classList.contains('ad-showing')) {
      if (currentAdVideo !== video.src) {
        currentAdVideo = video.src;
        countSkip();
      }

      clickSkipButton();

      // Adelantar el anuncio hasta el final.
      if (!video.muted) {
        video.muted = true;
        mutedByUs = true;
      }
      if (Number.isFinite(video.duration) && video.duration > 0 &&
          video.currentTime < video.duration - 0.1) {
        video.currentTime = video.duration;
      }
      if (video.paused) video.play().catch(() => {});
    } else {
      currentAdVideo = null;
      if (mutedByUs) {
        video.muted = false;
        mutedByUs = false;
      }
    }
  }

  // Reacciona a cambios del DOM (aparición del anuncio, cambio de clases del reproductor).
  const observer = new MutationObserver(tick);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class', 'src']
  });

  // Respaldo por si algún cambio no dispara el observer.
  setInterval(tick, 300);
})();
