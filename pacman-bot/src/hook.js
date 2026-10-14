/*
 * Pac-Man Doodle Pro Bot — conexión con el juego
 *
 * Se ejecuta en el "MAIN world" de la página, antes que el script del doodle.
 * El juego guarda todo su estado en una variable privada (closure "g"), así que
 * ponemos una trampa en Object.prototype: cuando el juego hace
 * `g.insertCoin = function...` el setter recibe `this === g` y lo capturamos.
 */
(function () {
  'use strict';
  if (window.__pacbot) return;

  var bot = window.__pacbot = {
    G: null,
    enabled: true,
    autoRestart: false,
    lastTile: '',
    lastMode: -1,
    sinceplan: 0,
    stats: { plans: 0, ms: 0, maxMs: 0, lastTicks: 0 },
    lastChoice: null
  };

  function looksLikeGame(o) {
    return o && typeof o === 'object' && typeof o.getDistance === 'function' &&
      typeof o.rand === 'function' && typeof o.keyPressed === 'function';
  }

  function capture(o) {
    if (bot.G === o) return;
    bot.G = o;
    window.PacBrain && window.PacBrain.setGame(o);
    log('juego detectado');
  }

  // Trampa en Object.prototype para las propiedades que el juego asigna a "g".
  ['insertCoin', 'moveActors'].forEach(function (name) {
    try {
      Object.defineProperty(Object.prototype, name, {
        configurable: true,
        enumerable: false,
        get: function () { return undefined; },
        set: function (val) {
          // Crea la propiedad propia como si no hubiera trampa
          try {
            Object.defineProperty(this, name, { value: val, writable: true, enumerable: true, configurable: true });
          } catch (e) { return; }
          if (looksLikeGame(this)) {
            capture(this);
            if (name === 'moveActors') ensureWrapped();
          }
        }
      });
    } catch (e) { /* nada */ }
  });

  function log(m) { try { console.log('%c[PacBot] ' + m, 'color:#fc0'); } catch (e) { /* nada */ } }

  // ---------------------------------------------------------------------------
  // Envoltura de g.moveActors: corre antes de mover a los actores en cada tick
  // ---------------------------------------------------------------------------
  function ensureWrapped() {
    var G = bot.G;
    if (!G || typeof G.moveActors !== 'function' || G.moveActors.__pacbot) return;
    var orig = G.moveActors;
    var wrapped = function () {
      try { onTick(G); } catch (e) { if (!bot._errLogged) { bot._errLogged = true; console.error('[PacBot]', e); } }
      return orig.apply(this, arguments);
    };
    wrapped.__pacbot = true;
    G.moveActors = wrapped;
    log('bot conectado. Tecla B = encender/apagar, R = auto-reinicio');
  }

  function onTick(G) {
    if (!bot.enabled || !window.PacBrain) return;
    if (G.gameplayMode !== 0 || !G.actors || !G.actors[0]) {
      bot.lastTile = '';
      bot.lastMode = G.gameplayMode;
      return;
    }
    var pac = G.actors[0];
    var tile = pac.tilePos[0] + ',' + pac.tilePos[1];
    bot.sinceplan++;
    var ghostSig = G.mainGhostMode + ':' + G.actors.map(function (a) { return a.mode; }).join('');
    var need = tile !== bot.lastTile || pac.dir === 0 || ghostSig !== bot.lastSig ||
      bot.sinceplan > 30;
    if (!need) return;
    bot.lastTile = tile;
    bot.lastSig = ghostSig;
    bot.sinceplan = 0;
    var t0 = performance.now();
    var choice = window.PacBrain.plan();
    var ms = performance.now() - t0;
    bot.stats.plans++;
    bot.stats.ms += ms;
    if (ms > bot.stats.maxMs) bot.stats.maxMs = ms;
    if (!choice) return;
    bot.stats.lastTicks = choice.ticks;
    bot.lastChoice = choice;
    window.PacBrain.applyChoice(pac, choice.dir);
  }

  // Auto-reinicio tras "Game Over"
  setInterval(function () {
    ensureWrapped();
    var G = bot.G;
    if (!G) return;
    if (bot.autoRestart && bot.enabled && G.gameplayMode === 8 && !bot._restarting) {
      bot._restarting = true;
      setTimeout(function () {
        bot._restarting = false;
        try { if (G.gameplayMode === 8 || G.gameplayMode === 14) G.insertCoin(); } catch (e) { /* nada */ }
      }, 2500);
    }
    updateHud();
  }, 250);

  // ---------------------------------------------------------------------------
  // HUD
  // ---------------------------------------------------------------------------
  var hud = null;
  function updateHud() {
    var G = bot.G;
    if (!document.body) return;
    if (!G || !G.canvasEl) {
      // Diagnóstico: hay un Pac-Man en la página pero no pudimos conectarnos
      if (document.getElementById('pcm-c') || (window.google && window.google.pacman)) {
        ensureHudEl('#ff6b6b');
        hud.innerHTML = '<b>PAC-BOT: no conectado</b><br>Recarga la página (F5).<br>' +
          'Si sigue así, pulsa el icono de la extensión<br>para abrir el Pac-Man incluido.';
        if (!bot._diagLogged) {
          bot._diagLogged = true;
          log('juego visible pero sin conexión. google.pacman=' +
            (window.google && window.google.pacman ? Object.keys(window.google.pacman).join(',') : 'no'));
        }
      }
      return;
    }
    ensureHudEl('#ffd200');
    var score = G.score ? G.score[0] : 0;
    var avg = bot.stats.plans ? (bot.stats.ms / bot.stats.plans).toFixed(1) : '-';
    hud.innerHTML = '<b>PAC-BOT ' + (bot.enabled ? 'ON' : 'OFF') + '</b>' +
      (bot.autoRestart ? ' · auto-restart' : '') +
      '<br>nivel ' + (G.level || 0) + ' · score ' + score + ' · vidas ' + (G.lives != null ? G.lives : '-') +
      '<br>plan ' + avg + ' ms (máx ' + bot.stats.maxMs.toFixed(0) + ')';
  }

  function ensureHudEl(color) {
    if (!hud || !hud.isConnected) {
      hud = document.createElement('div');
      hud.id = 'pacbot-hud';
      hud.style.cssText = 'position:fixed;right:8px;bottom:8px;z-index:2147483647;' +
        'font:12px/1.35 monospace;background:rgba(0,0,0,.82);color:#ffd200;padding:6px 9px;' +
        'border:1px solid #ffd200;border-radius:6px;cursor:pointer;user-select:none;max-width:260px';
      hud.title = 'Clic o tecla B: encender/apagar bot · R: auto-reinicio';
      hud.addEventListener('click', function () { toggle(); });
      document.body.appendChild(hud);
    }
    hud.style.color = color;
    hud.style.borderColor = color;
  }

  function toggle() {
    bot.enabled = !bot.enabled;
    if (!bot.enabled && bot.G && bot.G.actors && bot.G.actors[0]) bot.G.actors[0].nextDir = 0;
    updateHud();
  }

  window.addEventListener('keydown', function (e) {
    if (e.target && /input|textarea/i.test(e.target.tagName)) return;
    if (e.keyCode === 66) { toggle(); }                         // B
    else if (e.keyCode === 82) { bot.autoRestart = !bot.autoRestart; updateHud(); } // R
  }, true);
})();
