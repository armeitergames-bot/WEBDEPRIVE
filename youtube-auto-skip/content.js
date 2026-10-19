// Salta los anuncios de vídeo de YouTube y YouTube Music que no se pudieron quitar
// con remove-ads.js:
// 1. Mientras dura el anuncio lo silencia y lo reproduce a 16x (sin saltar al final,
//    porque eso deja el anuncio congelado y rompe los anuncios incrustados en el vídeo).
// 2. En cuanto aparece "Saltar anuncio" lo pulsa; si YouTube ignora el clic
//    normal, hace un clic real con chrome.debugger.
// 3. Si el anuncio termina pero se queda en pantalla, vuelve a intentar el clic real.
// 4. Al acabar el anuncio devuelve la velocidad y el sonido que tenía el usuario.
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

  // Elementos que YouTube solo dibuja mientras hay un anuncio de verdad.
  const AD_UI_SELECTORS = [
    '.video-ads.ytp-ad-module > *',
    '.ytp-ad-player-overlay',
    '.ytp-ad-player-overlay-layout',
    '.ytp-ad-preview-container',
    '.ytp-ad-text',
    '.ytp-ad-badge',
    '.ytp-ad-simple-ad-badge',
    '.ytp-ad-duration-remaining',
    '.ytp-ad-persistent-progress-bar-container'
  ].join(',');

  const AD_RATE = 16;
  // Nadie escucha una canción o un vídeo a más de 4x (YouTube permite como mucho 2x
  // y 4x con algunas extensiones): cualquier velocidad mayor la pusimos nosotros.
  const MAX_USER_RATE = 4;
  // Si un "anuncio" dura más que esto acelerado, no era un anuncio: soltarlo.
  const MAX_AD_MS = 20000;

  const settings = { enabled: true, remove: true, trustedClick: true };

  let inAd = false;
  let contentRate = 1;   // velocidad que eligió el usuario para el vídeo/canción
  let mutedByUs = false;
  let lastClick = 0;
  let lastTrustedClick = 0;
  let endedSince = 0;
  let adStartedAt = 0;
  let ignoreAd = false;  // falsa alarma: no tocar hasta que YouTube quite ad-showing

  // Si la extensión se recarga, el script viejo se queda sin acceso a chrome.*:
  // estas llamadas lanzarían errores en bucle.
  function safe(fn) {
    try { return fn(); } catch (e) { return undefined; }
  }

  function sendToBackground(msg) {
    safe(() => chrome.runtime.sendMessage(msg).catch(() => {}));
  }

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
    schedule();
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'sync') return;
    for (const key of Object.keys(settings)) {
      if (changes[key]) settings[key] = changes[key].newValue;
    }
    mirrorToPage();
    schedule();
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
    sendToBackground({
      type: 'trusted-click',
      x: r.left + r.width / 2,
      y: r.top + r.height / 2
    });
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
    safe(() => chrome.storage.local.get({ skipped: 0 }, ({ skipped }) => {
      safe(() => chrome.storage.local.set({ skipped: skipped + 1 }));
    }));
  }

  function restoreRate(video) {
    if (contentRate > MAX_USER_RATE) contentRate = 1;
    if (video && video.playbackRate !== contentRate) video.playbackRate = contentRate;
    // Avisar también al reproductor para que no guarde la velocidad del anuncio.
    window.postMessage({ source: 'yt-auto-skip', type: 'restore-rate', rate: contentRate }, '*');
  }

  function startAd() {
    inAd = true;
    endedSince = 0;
    adStartedAt = Date.now();
    countSkip();
  }

  function endAd(video) {
    inAd = false;
    endedSince = 0;
    if (video && mutedByUs) video.muted = false;
    mutedByUs = false;
    restoreRate(video);
    sendToBackground({ type: 'ad-finished' });
  }

  function tick() {
    document.documentElement.classList.toggle('yt-auto-skip-on', settings.enabled);

    const player = document.getElementById('movie_player') ||
      document.querySelector('.html5-video-player');
    const video = player && player.querySelector('video');
    // Solo es anuncio si el reproductor tiene ad-showing Y se ve la interfaz del
    // anuncio. En YouTube Music la clase ad-showing puede quedarse puesta mientras
    // suena la canción, y entonces la aceleraríamos.
    const adShowing = !!player && player.classList.contains('ad-showing') &&
      !!player.querySelector(AD_UI_SELECTORS);
    if (!adShowing) ignoreAd = false;

    if (!settings.enabled) {
      if (inAd) endAd(video);
      return;
    }

    closeOverlays();
    if (!video) return;

    if (!adShowing || ignoreAd) {
      if (inAd) endAd(video);
      if (video.playbackRate > MAX_USER_RATE) {
        // Fuera de un anuncio la canción/vídeo nunca debe ir acelerada así:
        // YouTube se quedó con la velocidad del anuncio. Devolver la normal.
        restoreRate(video);
      } else {
        // Recordar la velocidad que usa el usuario (puede cambiarla cuando quiera).
        contentRate = video.playbackRate;
      }
      return;
    }

    if (!inAd) startAd();

    if (Date.now() - adStartedAt > MAX_AD_MS) {
      // Demasiado largo para ser un anuncio: soltar y dejar sonar normal.
      ignoreAd = true;
      endAd(video);
      return;
    }

    if (!video.muted) {
      video.muted = true;
      mutedByUs = true;
    }
    if (video.playbackRate !== AD_RATE) video.playbackRate = AD_RATE;
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

  // YouTube cambia el DOM cientos de veces por segundo: agrupar los cambios
  // en una sola comprobación por fotograma.
  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      tick();
    });
  }

  function start() {
    const observer = new MutationObserver(schedule);
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class', 'src']
    });
    // Respaldo: requestAnimationFrame no corre con la pestaña en segundo plano
    // (por ejemplo, YouTube Music sonando en otra pestaña).
    setInterval(tick, 250);
    tick();
  }

  if (document.documentElement) start();
  else document.addEventListener('DOMContentLoaded', start, { once: true });
})();
