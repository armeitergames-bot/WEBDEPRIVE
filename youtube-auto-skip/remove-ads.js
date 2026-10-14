// Se ejecuta dentro de la página de YouTube (world: MAIN) antes que sus scripts.
// Borra los datos de anuncios de la respuesta del reproductor para que
// YouTube ni siquiera cargue los anuncios. Es lo mismo que hace uBlock Origin.
// No funciona con los anuncios incrustados en el propio vídeo (SSAP);
// para esos está content.js, que los salta.
(() => {
  try {
    if (localStorage.getItem('yt-auto-skip:enabled') === '0' ||
        localStorage.getItem('yt-auto-skip:remove') === '0') return;
  } catch (e) { /* sin localStorage: seguir con el valor por defecto */ }

  const AD_KEYS = ['adPlacements', 'adSlots', 'playerAds'];

  function clean(data) {
    if (!data || typeof data !== 'object') return data;
    for (const key of AD_KEYS) {
      if (key in data) delete data[key];
    }
    if (data.playerResponse) clean(data.playerResponse);
    return data;
  }

  function looksLikePlayerData(data) {
    return data && typeof data === 'object' &&
      ('playerResponse' in data || AD_KEYS.some((k) => k in data));
  }

  // 1. Respuesta incrustada en el HTML de la página (var ytInitialPlayerResponse = {...}).
  let initial;
  try {
    Object.defineProperty(window, 'ytInitialPlayerResponse', {
      configurable: true,
      get: () => initial,
      set: (value) => { initial = clean(value); }
    });
  } catch (e) { /* ya definida */ }

  // 2. Respuestas que se cargan al cambiar de vídeo (fetch a /youtubei/v1/player).
  const originalJson = Response.prototype.json;
  Response.prototype.json = async function () {
    const data = await originalJson.call(this);
    try {
      if (/\/youtubei\/v1\/(player|next)/.test(this.url)) clean(data);
    } catch (e) { /* ignorar */ }
    return data;
  };

  // 3. Por si YouTube parsea el texto a mano.
  const originalParse = JSON.parse;
  JSON.parse = function (...args) {
    const data = originalParse.apply(this, args);
    try {
      if (looksLikePlayerData(data)) clean(data);
    } catch (e) { /* ignorar */ }
    return data;
  };
})();
