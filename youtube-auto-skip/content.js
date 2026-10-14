// Salta los anuncios de vídeo de YouTube que no se pudieron quitar con remove-ads.js:
// 1. Mientras dura el anuncio lo silencia y lo reproduce a 16x (sin saltar al final,
//    porque eso deja el anuncio congelado y rompe los anuncios incrustados en el vídeo).
// 2. En cuanto aparece "Saltar anuncio" lo pulsa; si YouTube ignora el clic
//    normal, hace un clic real con chrome.debugger.
// 3. Si el anuncio termina pero se queda en pantalla, vuelve a intentar el clic real.
// También cierra los anuncios superpuestos y oculta los banners (hide-ads.css).
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

  const settings = { enabled: true, remove: true, trustedClick: true };

  let inAd = false;
  let savedRate = 1;
  let mutedByUs = false;
  let lastClick = 0;
  let lastTrustedClick = 0;
  let endedSince = 0;

  function mirrorToPage() {
    // remove-ads.js corre en la página y no puede leer chrome.storage: le pasamos los ajustes.
    try {
      localStorage.setItem('yt-auto-skip:enabled', settings.enabled ? '1' : '0');
      localStorage.setItem('yt-auto-skip:remove', settings.remove ? '1' : '0');
    } catch (e) { /* ignorar */ }
  }

  chrome.storage.sync.get(settings, (data) => {
    Object.assign(settings, data);
    mirrorToPage();
    tick();
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'sync') return;
    for (const key of Object.keys(settings)) {
      if (changes[key]) settings[key] = changes[key].newValue;
    }
    mirrorToPage();
    tick();
  });

  function isVisible(el) {
    if (!el || !el.isConnected) return false;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function findSkipButton() {
    for (const btn of document.querySelectorAll(SKIP_SELECTORS)) {
      if (isVisible(btn) && !btn.disabled) return btn;
    }
    return null;
  }

  function trustedClick(el) {
    if (!settings.trustedClick) return;
    const now = Date.now();
    if (now - lastTrustedClick < 1000) return;
    lastTrustedClick = now;
    const r = el.getBoundingClientRect();
    chrome.runtime.sendMessage({
      type: 'trusted-click',
      x: r.left + r.width / 2,
      y: r.top + r.height / 2
    }).catch(() => {});
  }

  function trySkip(force) {
    const btn = findSkipButton();
    if (!btn) return;
    const now = Date.now();
    if (now - lastClick < 400 && !force) return;
    lastClick = now;
    btn.click();
    // Si a los 400 ms el botón sigue ahí, YouTube ignoró el clic: hacer uno real.
    setTimeout(() => {
      const still = findSkipButton();
      if (still && inAd) trustedClick(still);
    }, 400);
    if (force) trustedClick(btn);
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

  function startAd(video) {
    inAd = true;
    endedSince = 0;
    savedRate = video.playbackRate || 1;
    countSkip();
  }

  function endAd(video) {
    inAd = false;
    endedSince = 0;
    if (video) {
      video.playbackRate = savedRate;
      if (mutedByUs) video.muted = false;
    }
    mutedByUs = false;
    chrome.runtime.sendMessage({ type: 'ad-finished' }).catch(() => {});
  }

  function tick() {
    document.documentElement.classList.toggle('yt-auto-skip-on', settings.enabled);

    const player = document.querySelector('#movie_player.html5-video-player, .html5-video-player');
    const video = player && player.querySelector('video');
    const adShowing = !!player && player.classList.contains('ad-showing');

    if (!settings.enabled) {
      if (inAd) endAd(video);
      return;
    }

    closeOverlays();
    if (!video) return;

    if (!adShowing) {
      if (inAd) endAd(video);
      return;
    }

    if (!inAd) startAd(video);

    if (!video.muted) {
      video.muted = true;
      mutedByUs = true;
    }
    if (video.playbackRate !== 16) video.playbackRate = 16;
    if (video.paused && !video.ended) video.play().catch(() => {});

    trySkip(false);

    // Anuncio terminado pero sigue en pantalla: forzar el clic real.
    const atEnd = video.ended ||
      (Number.isFinite(video.duration) && video.duration > 0 &&
       video.currentTime >= video.duration - 0.3);
    if (atEnd) {
      if (!endedSince) endedSince = Date.now();
      else if (Date.now() - endedSince > 1500) trySkip(true);
    } else {
      endedSince = 0;
    }
  }

  function start() {
    const observer = new MutationObserver(tick);
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class', 'src']
    });
    setInterval(tick, 250);
    tick();
  }

  if (document.documentElement) start();
  else document.addEventListener('DOMContentLoaded', start, { once: true });
})();
