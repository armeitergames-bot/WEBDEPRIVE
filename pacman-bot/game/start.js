(function () {
  document.getElementById('logo').style.background = 'black';
  document.getElementById('logo-l').style.display = 'block';
  var s = document.createElement('script');
  s.src = 'src/js/pacman10-hp.3.js';
  document.body.appendChild(s);
  document.getElementById('coin').addEventListener('click', function () {
    var G = window.__pacbot && window.__pacbot.G;
    if (!G) return;
    // Siempre partida de 1 jugador: si está en curso, la reiniciamos
    if (G.gameplayMode === 8 || G.gameplayMode === 14) G.insertCoin();
    else if (G.newGame) { try { G.stopAllAudio(); } catch (e) {} G.newGame(); }
    this.blur();
  });
})();
