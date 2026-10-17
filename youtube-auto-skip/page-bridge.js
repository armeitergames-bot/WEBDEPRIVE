// Se ejecuta dentro de la página (world: MAIN) para poder usar la API del reproductor,
// que content.js no puede ver. Sirve para devolver la velocidad normal después de un
// anuncio: si solo se cambia el <video>, YouTube (sobre todo YouTube Music) guarda la
// velocidad del anuncio como la del usuario y la vuelve a poner en la canción.
(() => {
  window.addEventListener('message', (event) => {
    const msg = event.data;
    if (event.source !== window || !msg || msg.source !== 'yt-auto-skip') return;
    if (msg.type !== 'restore-rate' || typeof msg.rate !== 'number') return;
    const player = document.getElementById('movie_player') ||
      document.querySelector('.html5-video-player');
    try {
      if (player && typeof player.setPlaybackRate === 'function') {
        player.setPlaybackRate(msg.rate);
      }
    } catch (e) { /* ignorar */ }
  });
})();
