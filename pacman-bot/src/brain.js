/*
 * Pac-Man Doodle Pro Bot — cerebro
 *
 * Simulador exacto (port 1:1 de la lógica del doodle de Google de 2010,
 * pacman10-hp.js) + búsqueda en árbol sobre las decisiones de Pac-Man.
 *
 * El juego es determinista: los fantasmas siguen reglas fijas de objetivo
 * (Blinky/Pinky/Inky/Clyde), y el modo asustado usa un PRNG lineal cuya
 * semilla podemos copiar. Así que en cada decisión copiamos el estado vivo
 * del juego, simulamos varios segundos hacia el futuro para cada ruta posible
 * y elegimos la que da más puntos sin morir.
 */
(function (root) {
  'use strict';

  // ---------------------------------------------------------------------------
  // Constantes del juego (copiadas del código original)
  // ---------------------------------------------------------------------------
  var DIRS = [1, 4, 2, 8]; // arriba, izquierda, abajo, derecha (orden del juego)
  var L = {
    0: { axis: 0, inc: 0 },
    1: { axis: 0, inc: -1 },
    2: { axis: 0, inc: 1 },
    4: { axis: 1, inc: -1 },
    8: { axis: 1, inc: 1 }
  };
  var OPP = { 0: 0, 1: 2, 2: 1, 4: 8, 8: 4 };
  var DIR_SLOT = { 1: 0, 4: 1, 2: 2, 8: 3 };
  var TUN = [{ x: 2, y: 8 }, { x: 63, y: 8 }];
  var DOOR = [32, 312];
  var FRUIT = [80, 312];
  var PEN_DOTS = [0, 7, 17, 32];
  var PEN_SPEED = 0.8 * 0.4;
  var ROUTINES = {
    1: [{ x: 37.6, y: 7, dir: 1, dest: 6.375, speed: 0.48 }, { x: 37.6, y: 6.375, dir: 2, dest: 7.625, speed: 0.48 }, { x: 37.6, y: 7.625, dir: 1, dest: 7, speed: 0.48 }],
    2: [{ x: 39.5, y: 7, dir: 2, dest: 7.625, speed: 0.48 }, { x: 39.5, y: 7.625, dir: 1, dest: 6.375, speed: 0.48 }, { x: 39.5, y: 6.375, dir: 2, dest: 7, speed: 0.48 }],
    3: [{ x: 41.4, y: 7, dir: 1, dest: 6.375, speed: 0.48 }, { x: 41.4, y: 6.375, dir: 2, dest: 7.625, speed: 0.48 }, { x: 41.4, y: 7.625, dir: 1, dest: 7, speed: 0.48 }],
    4: [{ x: 37.6, y: 7, dir: 8, dest: 39.5, speed: PEN_SPEED }, { x: 39.5, y: 7, dir: 1, dest: 4, speed: PEN_SPEED }],
    5: [{ x: 39.5, y: 7, dir: 1, dest: 4, speed: PEN_SPEED }],
    6: [{ x: 41.4, y: 7, dir: 4, dest: 39.5, speed: PEN_SPEED }, { x: 39.5, y: 7, dir: 1, dest: 4, speed: PEN_SPEED }],
    7: [{ x: 39.5, y: 4, dir: 2, dest: 7, speed: 1.6 }, { x: 39.5, y: 7, dir: 4, dest: 37.625, speed: 1.6 }],
    8: [{ x: 39.5, y: 4, dir: 2, dest: 7, speed: 1.6 }],
    9: [{ x: 39.5, y: 4, dir: 2, dest: 7, speed: 1.6 }, { x: 39.5, y: 7, dir: 8, dest: 41.375, speed: 1.6 }],
    10: [{ x: 37.6, y: 7, dir: 8, dest: 39.5, speed: PEN_SPEED }, { x: 39.5, y: 7, dir: 1, dest: 4, speed: PEN_SPEED }],
    11: [{ x: 39.5, y: 7, dir: 1, dest: 4, speed: PEN_SPEED }],
    12: [{ x: 41.4, y: 7, dir: 4, dest: 39.5, speed: PEN_SPEED }, { x: 39.5, y: 7, dir: 1, dest: 4, speed: PEN_SPEED }]
  };

  // Modos de fantasma
  var M_CHASE = 1, M_SCATTER = 2, M_FRIGHT = 4, M_EYES = 8, M_PEN = 16,
    M_EXIT = 32, M_ENTER = 64, M_REEXIT = 128;

  function isHarmlessMode(m) {
    return m === M_EYES || m === M_PEN || m === M_EXIT || m === M_REEXIT || m === M_ENTER;
  }

  // ---------------------------------------------------------------------------
  // Parámetros de la búsqueda / evaluación
  // ---------------------------------------------------------------------------
  var CFG = {
    horizon: 300,        // ticks simulados hacia el futuro (~3.3 s a 90 ticks/s)
    maxDepth: 8,         // decisiones en cruces dentro del horizonte
    tickBudget: 90000,   // límite de ticks simulados por decisión
    msBudget: 30,        // límite de tiempo real por decisión (ms)
    deathPenalty: 1000000,
    winBonus: 20000,
    dotDistW: 6,         // castigo por casilla hasta el punto más cercano
    reversePenalty: 12,  // evita titubeos
    trapArea: 26,        // casillas "seguras" mínimas al final de la rama
    trapW: 260,
    nearGhostW: 2500
  };

  // ---------------------------------------------------------------------------
  // Estado global del cerebro
  // ---------------------------------------------------------------------------
  var G = null;           // objeto interno del juego (closure "g")
  var MAP = null;         // grafo de casillas precalculado
  var D = 90;             // ticks por segundo de la lógica
  var ticksUsed = 0, deadline = 0;
  var now = typeof performance !== 'undefined' ? function () { return performance.now(); } : Date.now;
  var lastDots = -1, lastDotTime = 0, frustration = 0;
  var W = { dot: 6, trap: 260, near: 2500 }; // pesos efectivos (dependen de la frustración)

  var COLS = 80, ROWS = 24;
  function tIdx(py, px) { return ((py >> 3) + 2) * COLS + ((px >> 3) + 4); }

  function pf(y, x) {
    var row = G.playfield[y];
    return row ? row[x] : undefined;
  }

  function SI(speed) { return G.getSpeedIntervals(speed); }

  // ---------------------------------------------------------------------------
  // Mapa: grafo de casillas para BFS
  // ---------------------------------------------------------------------------
  function buildMap() {
    var nb = new Int16Array(COLS * ROWS * 4).fill(-1);
    var isPath = new Uint8Array(COLS * ROWS);
    var tiles = [];
    var y, x, t;
    for (var ky in G.playfield) {
      y = +ky;
      var row = G.playfield[ky];
      for (var kx in row) {
        x = +kx;
        t = row[kx];
        if (t && t.path) {
          var id = tIdx(y, x);
          if (!isPath[id]) { isPath[id] = 1; tiles.push(id); }
        }
      }
    }
    for (ky in G.playfield) {
      y = +ky;
      row = G.playfield[ky];
      for (kx in row) {
        x = +kx;
        t = row[kx];
        if (!t || !t.path) continue;
        var from = tIdx(y, x);
        for (var s = 0; s < 4; s++) {
          var d = DIRS[s], l = L[d];
          var ny = y + (l.axis === 0 ? l.inc * 8 : 0);
          var nx = x + (l.axis === 1 ? l.inc * 8 : 0);
          var n = pf(ny, nx);
          if (n && n.path) nb[from * 4 + s] = tIdx(ny, nx);
        }
      }
    }
    // Túneles (teletransporte)
    var a = tIdx(TUN[0].y * 8, TUN[0].x * 8), b = tIdx(TUN[1].y * 8, (TUN[1].x - 1) * 8);
    var c = tIdx(TUN[1].y * 8, TUN[1].x * 8), e = tIdx(TUN[0].y * 8, (TUN[0].x + 1) * 8);
    if (isPath[a] && isPath[b]) { nb[a * 4 + 1] = b; nb[b * 4 + 3] = a; }
    if (isPath[c] && isPath[e]) { nb[c * 4 + 3] = e; nb[e * 4 + 1] = c; }
    return {
      playfield: G.playfield,
      nb: nb,
      isPath: isPath,
      tiles: tiles,
      dist: new Int16Array(COLS * ROWS),
      queue: new Int16Array(COLS * ROWS),
      ghostDist: [new Int16Array(COLS * ROWS), new Int16Array(COLS * ROWS), new Int16Array(COLS * ROWS), new Int16Array(COLS * ROWS), new Int16Array(COLS * ROWS), new Int16Array(COLS * ROWS)]
    };
  }

  // BFS en casillas; blockedSlot = dirección prohibida en el primer paso (los
  // fantasmas no pueden dar media vuelta).
  function bfs(start, out, blockedSlot, maxD) {
    var nb = MAP.nb, q = MAP.queue;
    out.fill(32767);
    if (start < 0 || !MAP.isPath[start]) return;
    var h = 0, tl = 0;
    out[start] = 0;
    q[tl++] = start;
    while (h < tl) {
      var cur = q[h++], cd = out[cur];
      if (cd >= maxD) continue;
      var base = cur * 4;
      for (var s = 0; s < 4; s++) {
        if (cur === start && s === blockedSlot) continue;
        var n = nb[base + s];
        if (n >= 0 && out[n] > cd + 1) { out[n] = cd + 1; q[tl++] = n; }
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Snapshot / clon del estado
  // ---------------------------------------------------------------------------
  var A_SCALARS = ['id', 'ghost', 'dir', 'nextDir', 'lastActiveDir', 'mode', 'physicalSpeed',
    'currentSpeed', 'fullSpeed', 'tunnelSpeed', 'dotEatingSpeed', 'reverseDirectionsNext',
    'freeToLeavePen', 'modeChangedWhileInPen', 'eatenInThisFrightMode', 'followingRoutine',
    'routineToFollow', 'routineMoveId', 'proceedToNextRoutineMove', 'targetPlayerId', 'dotCount',
    'speedIntervals'];

  function v2(a) { return a ? [a[0], a[1]] : a; }

  function cloneActor(a) {
    var o = {};
    for (var i = 0; i < A_SCALARS.length; i++) o[A_SCALARS[i]] = a[A_SCALARS[i]];
    o.pos = v2(a.pos);
    o.posDelta = v2(a.posDelta) || [0, 0];
    o.tilePos = v2(a.tilePos);
    o.scatterPos = v2(a.scatterPos);
    // el juego a veces comparte la referencia targetPos === scatterPos (y la
    // muta in situ en el caso de Inky): lo replicamos.
    o.targetPos = a.targetPos === a.scatterPos ? o.scatterPos : v2(a.targetPos);
    o.lastGoodTilePos = v2(a.lastGoodTilePos);
    return o;
  }

  var S_SCALARS = ['pc', 'intervalTime', 'mode', 'modeTime', 'frightModeTime', 'ghostModeTime',
    'ghostModeSwitchPos', 'mainGhostMode', 'lastMainGhostMode', 'levels', 'timing',
    'cruiseElroySpeed', 'dotsRemaining', 'dotsEaten', 'randSeed', 'lostLifeOnThisLevel',
    'alternatePenLeavingScheme', 'alternateDotCount', 'forcePenLeaveTime', 'ghostExitingPenNow',
    'fruitShown', 'fruitTime', 'modeScoreMultiplier', 'tilesChanged', 'ghostBeingEatenId',
    'curPlayerSpeed', 'curDotSpeed', 'reward', 'dead', 'won', 't', 'pending', 'needDecision',
    'energizersLeft', 'firstMoveRev'];

  function snapshot() {
    var S = {
      pc: G.playerCount,
      intervalTime: G.intervalTime,
      mode: G.gameplayMode,
      modeTime: G.gameplayModeTime,
      frightModeTime: G.frightModeTime,
      ghostModeTime: G.ghostModeTime,
      ghostModeSwitchPos: G.ghostModeSwitchPos,
      mainGhostMode: G.mainGhostMode,
      lastMainGhostMode: G.lastMainGhostMode,
      levels: G.levels,
      timing: G.timing,
      cruiseElroySpeed: G.cruiseElroySpeed,
      dotsRemaining: G.dotsRemaining,
      dotsEaten: G.dotsEaten,
      randSeed: G.randSeed,
      lostLifeOnThisLevel: G.lostLifeOnThisLevel,
      alternatePenLeavingScheme: G.alternatePenLeavingScheme,
      alternateDotCount: G.alternateDotCount,
      forcePenLeaveTime: G.forcePenLeaveTime,
      ghostExitingPenNow: G.ghostExitingPenNow,
      fruitShown: G.fruitShown,
      fruitTime: G.fruitTime,
      modeScoreMultiplier: G.modeScoreMultiplier,
      tilesChanged: G.tilesChanged,
      ghostBeingEatenId: G.ghostBeingEatenId,
      curPlayerSpeed: G.currentPlayerSpeed,
      curDotSpeed: G.currentDotEatingSpeed,
      reward: 0, dead: false, won: false, t: 0, pending: 0, needDecision: false,
      energizersLeft: 0, firstMoveRev: false,
      actors: [],
      dots: new Uint8Array(COLS * ROWS)
    };
    for (var i = 0; i < G.actors.length; i++) S.actors.push(cloneActor(G.actors[i]));
    var tiles = MAP.tiles, dots = S.dots;
    for (var ky in G.playfield) {
      var row = G.playfield[ky];
      for (var kx in row) {
        var t = row[kx];
        if (t && t.dot) {
          dots[tIdx(+ky, +kx)] = t.dot;
          if (t.dot === 2) S.energizersLeft++;
        }
      }
    }
    void tiles;
    return S;
  }

  function cloneState(S) {
    var C = { actors: new Array(S.actors.length), dots: S.dots.slice() };
    for (var i = 0; i < S_SCALARS.length; i++) C[S_SCALARS[i]] = S[S_SCALARS[i]];
    for (i = 0; i < S.actors.length; i++) C.actors[i] = cloneActor(S.actors[i]);
    return C;
  }

  // ---------------------------------------------------------------------------
  // Simulación (port fiel del juego)
  // ---------------------------------------------------------------------------
  function rand(S) {
    var b = 4294967296, c = 134775813;
    c = c * S.randSeed + 1;
    return (S.randSeed = c % b) / b;
  }

  function updSpeed(S, a) { // E.prototype.d
    var b;
    switch (a.currentSpeed) {
      case 0: b = a.id === S.pc && (a.mode === 2 || a.mode === 1) ? S.cruiseElroySpeed : a.fullSpeed; break;
      case 1: b = a.dotEatingSpeed; break;
      case 2: b = a.tunnelSpeed; break;
    }
    if (a.physicalSpeed !== b) {
      a.physicalSpeed = b;
      a.speedIntervals = SI(a.physicalSpeed);
    }
  }

  function setSpeed(S, a, c) { a.currentSpeed = c; updSpeed(S, a); }

  function pickTarget(S, a) { // E.prototype.l
    if (a.id >= S.pc) a.targetPlayerId = Math.floor(rand(S) * S.pc);
  }

  function updateCruise(S) {
    var lv = S.levels, b = lv.ghostSpeed * 0.8;
    if (!S.lostLifeOnThisLevel || S.actors[S.pc + 3].mode !== 16) {
      if (S.dotsRemaining < lv.elroyDotsLeftPart2) b = lv.elroySpeedPart2 * 0.8;
      else if (S.dotsRemaining < lv.elroyDotsLeftPart1) b = lv.elroySpeedPart1 * 0.8;
    }
    if (b !== S.cruiseElroySpeed) {
      S.cruiseElroySpeed = b;
      updSpeed(S, S.actors[S.pc]);
    }
  }

  function setMode(S, a, b) { // E.prototype.a
    var c = a.mode, lv = S.levels, pc = S.pc;
    a.mode = b;
    if (a.id === pc + 3 && (b === 16 || c === 16)) updateCruise(S);
    if (c === 32) S.ghostExitingPenNow = false;
    switch (b) {
      case 4:
        a.fullSpeed = lv.ghostFrightSpeed * 0.8; a.tunnelSpeed = lv.ghostTunnelSpeed * 0.8; a.followingRoutine = false; break;
      case 1:
        a.fullSpeed = lv.ghostSpeed * 0.8; a.tunnelSpeed = lv.ghostTunnelSpeed * 0.8; a.followingRoutine = false; break;
      case 2:
        a.targetPos = a.scatterPos; a.fullSpeed = lv.ghostSpeed * 0.8; a.tunnelSpeed = lv.ghostTunnelSpeed * 0.8; a.followingRoutine = false; break;
      case 8:
        a.tunnelSpeed = a.fullSpeed = 1.6; a.targetPos = [DOOR[0], DOOR[1]]; a.freeToLeavePen = a.followingRoutine = false; break;
      case 16:
        pickTarget(S, a); a.followingRoutine = true; a.routineMoveId = -1;
        if (a.id === pc + 1) a.routineToFollow = 2; else if (a.id === pc + 2) a.routineToFollow = 1; else if (a.id === pc + 3) a.routineToFollow = 3;
        break;
      case 32:
        a.followingRoutine = true; a.routineMoveId = -1;
        if (a.id === pc + 1) a.routineToFollow = 5; else if (a.id === pc + 2) a.routineToFollow = 4; else if (a.id === pc + 3) a.routineToFollow = 6;
        S.ghostExitingPenNow = true;
        break;
      case 64:
        a.followingRoutine = true; a.routineMoveId = -1;
        if (a.id === pc || a.id === pc + 1) a.routineToFollow = 8; else if (a.id === pc + 2) a.routineToFollow = 7; else if (a.id === pc + 3) a.routineToFollow = 9;
        break;
      case 128:
        a.followingRoutine = true; a.routineMoveId = -1;
        if (a.id === pc || a.id === pc + 1) a.routineToFollow = 11; else if (a.id === pc + 2) a.routineToFollow = 10; else if (a.id === pc + 3) a.routineToFollow = 12;
        break;
    }
    updSpeed(S, a);
  }

  function switchMain(S, b, c) { // g.switchMainGhostMode
    var lv = S.levels, i, f;
    if (b === 4 && lv.frightTime === 0) {
      for (i = 0; i < S.actors.length; i++) if (S.actors[i].ghost) S.actors[i].reverseDirectionsNext = true;
      return;
    }
    if (b === 4 && S.mainGhostMode !== 4) S.lastMainGhostMode = S.mainGhostMode;
    S.mainGhostMode = b;
    switch (b) {
      case 1: case 2:
        S.curPlayerSpeed = lv.playerSpeed * 0.8; S.curDotSpeed = lv.dotEatingSpeed * 0.8; break;
      case 4:
        S.curPlayerSpeed = lv.playerFrightSpeed * 0.8; S.curDotSpeed = lv.dotEatingFrightSpeed * 0.8;
        S.frightModeTime = lv.frightTotalTime; S.modeScoreMultiplier = 1; break;
    }
    for (i = 0; i < S.actors.length; i++) {
      f = S.actors[i];
      if (f.ghost) {
        if (b !== 64 && !c) f.modeChangedWhileInPen = true;
        if (b === 4) f.eatenInThisFrightMode = false;
        if (!isHarmlessMode(f.mode) || c) {
          if (!c && f.mode !== 4 && f.mode !== b) f.reverseDirectionsNext = true;
          setMode(S, f, b);
        }
      } else {
        f.fullSpeed = S.curPlayerSpeed; f.dotEatingSpeed = S.curDotSpeed; f.tunnelSpeed = S.curPlayerSpeed;
        updSpeed(S, f);
      }
    }
  }

  function finishFright(S) { switchMain(S, S.lastMainGhostMode, false); }

  function resetForce(S) { S.forcePenLeaveTime = S.levels.penForceTime * D; }

  function figureOutPen(S) {
    var A = S.actors, pc = S.pc, lv = S.levels;
    if (S.alternatePenLeavingScheme) {
      S.alternateDotCount++;
      switch (S.alternateDotCount) {
        case PEN_DOTS[1]: A[pc + 1].freeToLeavePen = true; break;
        case PEN_DOTS[2]: A[pc + 2].freeToLeavePen = true; break;
        case PEN_DOTS[3]: if (A[pc + 3].mode === 16) S.alternatePenLeavingScheme = false; break;
      }
    } else if (A[pc + 1].mode === 16 || A[pc + 1].mode === 8) {
      A[pc + 1].dotCount++;
      if (A[pc + 1].dotCount >= lv.penLeavingLimits[1]) A[pc + 1].freeToLeavePen = true;
    } else if (A[pc + 2].mode === 16 || A[pc + 2].mode === 8) {
      A[pc + 2].dotCount++;
      if (A[pc + 2].dotCount >= lv.penLeavingLimits[2]) A[pc + 2].freeToLeavePen = true;
    } else if (A[pc + 3].mode === 16 || A[pc + 3].mode === 8) {
      A[pc + 3].dotCount++;
      if (A[pc + 3].dotCount >= lv.penLeavingLimits[3]) A[pc + 3].freeToLeavePen = true;
    }
  }

  function showFruit(S) {
    S.fruitShown = true;
    S.fruitTime = S.timing[15] + (S.timing[16] - S.timing[15]) * rand(S);
  }

  function disc(S) { return 1 - S.t / 2400; }

  function dotEaten(S, id, b) {
    var k = tIdx(b[0], b[1]), dv = S.dots[k], pac = S.actors[id];
    S.dotsRemaining--;
    S.dotsEaten++;
    setSpeed(S, pac, 1);
    if (dv === 2) {
      if (id === 0) S.reward += energizerValue(S, pac) * disc(S);
      S.energizersLeft--;
      switchMain(S, 4, false);
    } else if (id === 0) {
      S.reward += 10 * disc(S);
    }
    S.dots[k] = 0;
    updateCruise(S);
    resetForce(S);
    figureOutPen(S);
    if (S.dotsEaten === 70 || S.dotsEaten === 170) showFruit(S);
    if (S.dotsRemaining === 0) { S.won = true; S.reward += CFG.winBonus * disc(S); }
  }

  // Un profesional no se come la pastilla de poder si no hay fantasmas cerca.
  function energizerValue(S, pac) {
    var lv = S.levels;
    if (!lv.frightTime) return 50;
    var near = 0, alreadyBlue = 0;
    for (var i = S.pc; i < S.actors.length; i++) {
      var gh = S.actors[i];
      if (gh.mode === M_FRIGHT) { alreadyBlue++; continue; }
      if (gh.mode !== M_CHASE && gh.mode !== M_SCATTER) continue;
      var d = (Math.abs(gh.tilePos[0] - pac.tilePos[0]) + Math.abs(gh.tilePos[1] - pac.tilePos[1])) / 8;
      if (d <= 12) near++;
    }
    var endgame = S.dotsRemaining <= S.energizersLeft + 12;
    if (endgame) return 50;
    if (alreadyBlue) return -250;
    if (near === 0) return -450;
    return 50 + 160 * near;
  }

  function eatFruit(S, id) {
    if (S.fruitShown) {
      S.fruitShown = false;
      S.fruitTime = S.timing[14];
      if (id === 0) S.reward += Math.min(S.levels.fruitScore, 2000) * disc(S);
    }
  }

  function simZ(S, a, b) { // E.prototype.z (requestedDir)
    if (a.dir === OPP[b]) {
      a.dir = b;
      a.posDelta = [0, 0];
      if (a.currentSpeed !== 2) setSpeed(S, a, 0);
      if (a.dir !== 0) a.lastActiveDir = a.dir;
      a.nextDir = 0;
    } else if (a.dir !== b) {
      if (a.dir === 0) {
        var here = pf(a.pos[0], a.pos[1]);
        if (here && here.allowedDir & b) a.dir = b;
      } else {
        var c = pf(a.tilePos[0], a.tilePos[1]);
        if (c && c.allowedDir & b) {
          var dl = L[a.dir], d = [a.pos[0], a.pos[1]], f = 0;
          d[dl.axis] -= dl.inc;
          if (d[0] === a.tilePos[0] && d[1] === a.tilePos[1]) f = 1;
          else {
            d[dl.axis] -= dl.inc;
            if (d[0] === a.tilePos[0] && d[1] === a.tilePos[1]) f = 2;
          }
          if (f) {
            a.dir = b;
            a.pos[0] = a.tilePos[0];
            a.pos[1] = a.tilePos[1];
            var nl = L[a.dir];
            a.pos[nl.axis] += nl.inc * f;
            return;
          }
        }
        a.nextDir = b;
        a.posDelta = [0, 0];
      }
    }
  }

  // Aplica una decisión de Pac-Man exactamente como lo hace el bot en el juego real
  function applyChoice(S, a, k) {
    if (k === -1) { // "seguir" (limpiar giro pendiente)
      a.nextDir = 0; a.posDelta = [0, 0];
    } else if (k === a.dir && a.dir !== 0) {
      a.nextDir = 0; a.posDelta = [0, 0];
    } else {
      simZ(S, a, k);
    }
  }

  function ghostDecide(S, a, b) { // E.prototype.i
    var c = a.tilePos, d = L[a.dir], f = [c[0], c[1]];
    f[d.axis] += d.inc * 8;
    var h = pf(f[0], f[1]);
    if (b && (!h || !h.intersection)) h = pf(c[0], c[1]);
    if (!h || !h.intersection) return;
    switch (a.mode) {
      case 2: case 1: case 8:
        if ((a.dir & h.allowedDir) === 0 && h.allowedDir === OPP[a.dir]) a.nextDir = OPP[a.dir];
        else {
          var best = 99999999999, bd = 0;
          for (var j = 0; j < 4; j++) {
            var k = DIRS[j];
            if (h.allowedDir & k && a.dir !== OPP[k]) {
              var kl = L[k], x = [f[0], f[1]];
              x[kl.axis] += kl.inc;
              var dy = a.targetPos[0] - x[0], dx = a.targetPos[1] - x[1];
              var dist = Math.sqrt(dx * dx + dy * dy);
              if (dist < best) { best = dist; bd = k; }
            }
          }
          if (bd) a.nextDir = bd;
        }
        break;
      case 4:
        if ((a.dir & h.allowedDir) === 0 && h.allowedDir === OPP[a.dir]) a.nextDir = OPP[a.dir];
        else {
          var r, guard = 0;
          do { r = DIRS[Math.floor(rand(S) * 4)]; guard++; }
          while (((r & h.allowedDir) === 0 || r === OPP[a.dir]) && guard < 200);
          a.nextDir = r;
        }
        break;
    }
  }

  function enterTile(S, a, b) { // E.prototype.p
    S.tilesChanged = true;
    if (a.reverseDirectionsNext) {
      a.dir = OPP[a.dir];
      a.nextDir = 0;
      a.reverseDirectionsNext = false;
      ghostDecide(S, a, true);
    }
    var t = pf(b[0], b[1]);
    if (!a.ghost && (!t || !t.path)) {
      a.pos[0] = a.lastGoodTilePos[0];
      a.pos[1] = a.lastGoodTilePos[1];
      b[0] = a.lastGoodTilePos[0];
      b[1] = a.lastGoodTilePos[1];
      a.dir = 0;
      t = pf(b[0], b[1]);
    } else a.lastGoodTilePos = [b[0], b[1]];
    if (t && t.type === 1 && a.mode !== 8) setSpeed(S, a, 2); else setSpeed(S, a, 0);
    if (!a.ghost && S.dots[tIdx(b[0], b[1])]) dotEaten(S, a.id, b);
    a.tilePos[0] = b[0];
    a.tilePos[1] = b[1];
    if (a.id === 0 && !S.noAuto) pacEnteredTile(S, a);
  }

  // Detecta cuándo Pac-Man necesita una decisión (igual que el bot en vivo)
  function pacEnteredTile(S, a) {
    var t = pf(a.tilePos[0], a.tilePos[1]);
    if (!t || !t.intersection || a.dir === 0) return;
    var opts = t.allowedDir & ~OPP[a.dir];
    var n = 0, only = 0;
    for (var j = 0; j < 4; j++) if (opts & DIRS[j]) { n++; only = DIRS[j]; }
    if (n >= 2) S.needDecision = true;
    else if (n === 1 && only !== a.dir) S.pending = only; // curva forzada
  }

  function corner(S, a) { // E.prototype.t
    var b = a.tilePos, c, d;
    switch (a.dir) {
      case 1: c = [b[0], b[1]]; d = [b[0] + 3.6, b[1]]; break;
      case 2: c = [b[0] - 4, b[1]]; d = [b[0], b[1]]; break;
      case 4: c = [b[0], b[1]]; d = [b[0], b[1] + 3.6]; break;
      case 8: c = [b[0], b[1] - 4]; d = [b[0], b[1]]; break;
      default: return;
    }
    if (a.pos[0] >= c[0] && a.pos[0] <= d[0] && a.pos[1] >= c[1] && a.pos[1] <= d[1]) {
      var nl = L[a.nextDir];
      a.posDelta[nl.axis] += nl.inc;
    }
  }

  function tunnelEtc(S, a) { // E.prototype.n
    if (a.pos[0] === TUN[0].y * 8 && a.pos[1] === TUN[0].x * 8) {
      a.pos[0] = TUN[1].y * 8; a.pos[1] = (TUN[1].x - 1) * 8;
    } else if (a.pos[0] === TUN[1].y * 8 && a.pos[1] === TUN[1].x * 8) {
      a.pos[0] = TUN[0].y * 8; a.pos[1] = (TUN[0].x + 1) * 8;
    }
    if (a.mode === 8 && a.pos[0] === DOOR[0] && a.pos[1] === DOOR[1]) setMode(S, a, 64);
    if (!a.ghost && a.pos[0] === FRUIT[0] && (a.pos[1] === FRUIT[1] || a.pos[1] === FRUIT[1] + 8)) eatFruit(S, a.id);
  }

  function atCenter(S, a) { // E.prototype.u
    tunnelEtc(S, a);
    if (a.ghost) ghostDecide(S, a, false);
    var b = pf(a.pos[0], a.pos[1]);
    if (b && b.intersection) {
      if (a.nextDir && a.nextDir & b.allowedDir) {
        if (a.dir !== 0) a.lastActiveDir = a.dir;
        a.dir = a.nextDir;
        a.nextDir = 0;
        if (!a.ghost) {
          a.pos[0] += a.posDelta[0];
          a.pos[1] += a.posDelta[1];
          a.posDelta = [0, 0];
        }
      } else if ((a.dir & b.allowedDir) === 0) {
        if (a.dir !== 0) a.lastActiveDir = a.dir;
        a.nextDir = a.dir = 0;
        setSpeed(S, a, 0);
      }
    }
  }

  function afterStep(S, a) { // E.prototype.o
    var b = a.pos[0] / 8, c = a.pos[1] / 8;
    var d = [Math.round(b) * 8, Math.round(c) * 8];
    if (d[0] !== a.tilePos[0] || d[1] !== a.tilePos[1]) enterTile(S, a, d);
    else if (a.pos[0] === Math.floor(b) * 8 && a.pos[1] === Math.floor(c) * 8) atCenter(S, a);
    if (!a.ghost && a.nextDir) {
      var t = pf(d[0], d[1]);
      if (t && t.intersection && a.nextDir & t.allowedDir) corner(S, a);
    }
  }

  function step(S, a) { // E.prototype.e
    if (a.dir && a.speedIntervals[S.intervalTime]) {
      var b = L[a.dir];
      a.pos[b.axis] += b.inc;
      afterStep(S, a);
    }
  }

  function routineNext(S, a) { // E.prototype.v
    a.routineMoveId++;
    var R = ROUTINES[a.routineToFollow];
    if (!R) return;
    if (a.routineMoveId === R.length) {
      if (a.mode === 16 && a.freeToLeavePen && !S.ghostExitingPenNow) {
        setMode(S, a, a.eatenInThisFrightMode ? 128 : 32);
        return;
      } else if (a.mode === 32 || a.mode === 128) {
        a.pos = [DOOR[0], DOOR[1] + 4];
        a.dir = a.modeChangedWhileInPen ? 8 : 4;
        var m = S.mainGhostMode;
        if (a.mode === 128 && m === 4) m = S.lastMainGhostMode;
        setMode(S, a, m);
        return;
      } else if (a.mode === 64) {
        if (a.id === S.pc || a.freeToLeavePen) setMode(S, a, 128);
        else { a.eatenInThisFrightMode = true; setMode(S, a, 16); }
        return;
      } else a.routineMoveId = 0;
    }
    var mv = R[a.routineMoveId];
    a.pos[0] = mv.y * 8;
    a.pos[1] = mv.x * 8;
    a.dir = mv.dir;
    a.physicalSpeed = 0;
    a.speedIntervals = SI(mv.speed);
    a.proceedToNextRoutineMove = false;
  }

  function routineMove(S, a) { // E.prototype.m
    var R = ROUTINES[a.routineToFollow], b = R && R[a.routineMoveId];
    if (b && a.speedIntervals[S.intervalTime]) {
      var c = L[a.dir];
      a.pos[c.axis] += c.inc;
      if (a.dir === 1 || a.dir === 4) {
        if (a.pos[c.axis] < b.dest * 8) { a.pos[c.axis] = b.dest * 8; a.proceedToNextRoutineMove = true; }
      } else if (a.dir === 2 || a.dir === 8) {
        if (a.pos[c.axis] > b.dest * 8) { a.pos[c.axis] = b.dest * 8; a.proceedToNextRoutineMove = true; }
      }
    }
  }

  function routineTick(S, a) { // E.prototype.j
    if (a.routineMoveId === -1 || a.proceedToNextRoutineMove) routineNext(S, a);
    routineMove(S, a);
  }

  function moveActor(S, a) { // E.prototype.move
    if (S.mode === 0 || (a.ghost && S.mode === 1 && (a.mode === 8 || a.mode === 64))) {
      if (a.followingRoutine) {
        routineTick(S, a);
        if (a.mode === 64) routineTick(S, a);
      } else {
        step(S, a);
        if (a.mode === 8) step(S, a);
      }
    }
  }

  function updateTargets(S) { // E.prototype.B para cada fantasma
    var pc = S.pc, A = S.actors;
    for (var i = pc; i < pc + 4; i++) {
      var a = A[i], b, c;
      if (a.id === pc && S.dotsRemaining < S.levels.elroyDotsLeftPart1 && a.mode === 2 &&
        (!S.lostLifeOnThisLevel || A[pc + 3].mode !== 16)) {
        b = A[a.targetPlayerId];
        a.targetPos = [b.tilePos[0], b.tilePos[1]];
      } else if (a.ghost && a.mode === 1) {
        b = A[a.targetPlayerId];
        if (a.id === pc) {
          a.targetPos = [b.tilePos[0], b.tilePos[1]];
        } else if (a.id === pc + 1) {
          a.targetPos = [b.tilePos[0], b.tilePos[1]];
          c = L[b.dir];
          a.targetPos[c.axis] += 32 * c.inc;
          if (b.dir === 1) a.targetPos[1] -= 32;
        } else if (a.id === pc + 2) {
          var bl = A[pc], f = [b.tilePos[0], b.tilePos[1]];
          c = L[b.dir];
          f[c.axis] += 16 * c.inc;
          if (b.dir === 1) f[1] -= 16;
          a.targetPos[0] = f[0] * 2 - bl.tilePos[0];
          a.targetPos[1] = f[1] * 2 - bl.tilePos[1];
        } else if (a.id === pc + 3) {
          var dy = b.tilePos[0] - a.tilePos[0], dx = b.tilePos[1] - a.tilePos[1];
          a.targetPos = Math.sqrt(dx * dx + dy * dy) > 64 ? [b.tilePos[0], b.tilePos[1]] : a.scatterPos;
        }
      }
    }
  }

  function detectCollisions(S) {
    S.tilesChanged = false;
    var pc = S.pc, A = S.actors;
    for (var b = pc; b < pc + 4; b++) {
      for (var c = 0; c < pc; c++) {
        if (A[b].tilePos[0] === A[c].tilePos[0] && A[b].tilePos[1] === A[c].tilePos[1]) {
          if (A[b].mode === 4) {
            // fantasma comido
            if (c === 0) S.reward += (200 * S.modeScoreMultiplier + 150) * disc(S);
            S.modeScoreMultiplier *= 2;
            S.ghostBeingEatenId = b;
            S.mode = 1;
            S.modeTime = S.timing[2];
            return;
          } else if (!isHarmlessMode(A[b].mode)) {
            if (c === 0) killPac(S);
            else S.won = true; // el jugador 2 murió: fin de la rama
            return;
          }
        }
      }
    }
  }

  function killPac(S) {
    S.dead = true;
    S.reward -= CFG.deathPenalty * (1 - S.t / (CFG.horizon * 4));
  }

  // Margen de seguridad extra: si un fantasma peligroso se solapa en píxeles
  // con Pac-Man (aunque el juego no lo cuente como choque), lo tratamos como muerte.
  function paranoidCheck(S) {
    var p = S.actors[0], pc = S.pc;
    for (var b = pc; b < pc + 4; b++) {
      var gh = S.actors[b];
      if (gh.mode !== M_CHASE && gh.mode !== M_SCATTER) continue;
      var dy = Math.abs(gh.pos[0] - p.pos[0]), dx = Math.abs(gh.pos[1] - p.pos[1]);
      if ((dy < 1 && dx < 7) || (dx < 1 && dy < 7)) { killPac(S); return; }
    }
  }

  function handleTimers(S) {
    var lv = S.levels;
    if (S.mode === 0) {
      if (S.forcePenLeaveTime) {
        S.forcePenLeaveTime--;
        if (S.forcePenLeaveTime <= 0) {
          for (var b = 1; b <= 3; b++) {
            if (S.actors[S.pc + b].mode === 16) { S.actors[S.pc + b].freeToLeavePen = true; break; }
          }
          resetForce(S);
        }
      }
      if (S.fruitTime) {
        S.fruitTime--;
        if (S.fruitTime <= 0) S.fruitShown = false;
      }
      if (S.frightModeTime) {
        S.frightModeTime--;
        if (S.frightModeTime <= 0) { S.frightModeTime = 0; finishFright(S); }
      } else if (S.ghostModeTime > 0) {
        S.ghostModeTime--;
        if (S.ghostModeTime <= 0) {
          S.ghostModeTime = 0;
          S.ghostModeSwitchPos++;
          if (lv.ghostModeSwitchTimes[S.ghostModeSwitchPos]) {
            S.ghostModeTime = lv.ghostModeSwitchTimes[S.ghostModeSwitchPos] * D;
            if (S.mainGhostMode === 2) switchMain(S, 1, false);
            else if (S.mainGhostMode === 1) switchMain(S, 2, false);
          }
        }
      }
    }
    if (S.mode === 1 && S.modeTime) {
      S.modeTime--;
      if (S.modeTime <= 0) {
        S.modeTime = 0;
        S.mode = 0;
        setMode(S, S.actors[S.ghostBeingEatenId], 8);
        var any = false;
        for (var i = S.pc; i < S.pc + 4; i++) {
          var a = S.actors[i];
          if (a.mode === 4 || ((a.mode === 16 || a.mode === 128) && !a.eatenInThisFrightMode)) { any = true; break; }
        }
        if (!any) finishFright(S);
      }
    }
  }

  function simTick(S) {
    ticksUsed++;
    var A = S.actors;
    if (S.pending && S.mode === 0) {
      applyChoice(S, A[0], S.pending);
      S.pending = 0;
    }
    for (var i = 0; i < A.length; i++) moveActor(S, A[i]);
    if (S.mode === 0 && S.tilesChanged) {
      detectCollisions(S);
      if (S.dead) return;
      updateTargets(S);
    }
    if (S.mode === 0) paranoidCheck(S);
    S.intervalTime = (S.intervalTime + 1) % D;
    handleTimers(S);
    S.t++;
    if (A[0].dir === 0 && S.mode === 0 && !S.pending) S.needDecision = true;
  }

  // ---------------------------------------------------------------------------
  // Evaluación de hojas
  // ---------------------------------------------------------------------------
  function evaluate(S) {
    if (S.dead || S.won) return S.reward;
    var p = S.actors[0], pc = S.pc;
    var pacIdx = tIdx(p.tilePos[0], p.tilePos[1]);
    var pd = MAP.dist;
    bfs(pacIdx, pd, -1, 400);
    var v = S.reward;

    // Distancia al punto más cercano
    var tiles = MAP.tiles, dots = S.dots, nearest = 32767, i, t;
    for (i = 0; i < tiles.length; i++) {
      t = tiles[i];
      if (dots[t] && pd[t] < nearest) nearest = pd[t];
    }
    if (nearest < 32767) v -= nearest * W.dot;

    var pacSpeed = Math.max(0.3, p.fullSpeed || 0.64); // px por tick
    var pacTileT = 8 / pacSpeed;

    // Fantasmas: presas (asustados) y amenazas
    var nThreat = 0, preyBonus = 0;
    for (var gi = pc; gi < pc + 4; gi++) {
      var gh = S.actors[gi];
      var gIdx = tIdx(gh.tilePos[0], gh.tilePos[1]);
      if (gh.mode === M_FRIGHT) {
        var reachT = pd[gIdx] * pacTileT * 1.15;
        if (reachT < S.frightModeTime - 20) {
          var val = 200 * S.modeScoreMultiplier * (1 - reachT / (S.frightModeTime + 1));
          if (val > preyBonus) preyBonus = val;
          continue;
        }
        // se le acabará el susto antes de alcanzarlo -> amenaza retrasada
      }
      var delay = 0, src = gIdx, blocked = gh.dir ? DIR_SLOT[OPP[gh.dir]] : -1;
      if (gh.mode === M_FRIGHT) delay = S.frightModeTime;
      else if (gh.mode === M_EXIT || gh.mode === M_REEXIT) { delay = 50; src = tIdx(DOOR[0], DOOR[1]); blocked = -1; }
      else if (gh.mode === M_PEN) {
        if (!gh.freeToLeavePen) continue;
        delay = 110; src = tIdx(DOOR[0], DOOR[1]); blocked = -1;
      } else if (gh.mode === M_EYES || gh.mode === M_ENTER) continue;
      var gd = MAP.ghostDist[nThreat];
      bfs(src, gd, blocked, 60);
      var gs = Math.max(0.3, gh.mode === M_FRIGHT ? S.levels.ghostSpeed * 0.8 : gh.fullSpeed);
      if (gi === pc) gs = Math.max(gs, S.cruiseElroySpeed || 0);
      gd.delay = delay;
      gd.tileT = 8 / gs;
      nThreat++;
    }
    v += preyBonus;

    if (nThreat > 0) {
      // Región segura tipo Voronoi: casillas a las que Pac-Man llega antes que
      // cualquier fantasma peligroso.
      var safe = 0, closest = 32767;
      for (i = 0; i < tiles.length; i++) {
        t = tiles[i];
        if (pd[t] > 60) continue;
        var pt = pd[t] * pacTileT, ok = true;
        for (var k = 0; k < nThreat; k++) {
          var g2 = MAP.ghostDist[k];
          var gt = g2[t] * g2.tileT + g2.delay;
          if (gt <= pt + 10) { ok = false; break; }
        }
        if (ok) safe++;
      }
      for (k = 0; k < nThreat; k++) {
        g2 = MAP.ghostDist[k];
        var tt = g2[pacIdx] * g2.tileT + g2.delay;
        if (tt < closest) closest = tt;
      }
      if (safe < CFG.trapArea) v -= (CFG.trapArea - safe) * W.trap;
      if (closest < 60) v -= W.near * (1 - closest / 60);
    }

    // Fruta
    if (S.fruitShown) {
      var fd = pd[tIdx(FRUIT[0], FRUIT[1])];
      if (fd < 32767 && fd * pacTileT < S.fruitTime) v += Math.min(S.levels.fruitScore, 2000) * 0.3 * (1 - fd / 60);
    }
    return v;
  }

  // ---------------------------------------------------------------------------
  // Búsqueda
  // ---------------------------------------------------------------------------
  function runUntilDecision(S) {
    while (true) {
      if (S.dead || S.won || S.t >= CFG.horizon) return false;
      if (S.mode === 0 && S.needDecision && !S.pending) { S.needDecision = false; return true; }
      S.needDecision = false;
      simTick(S);
      if (S.dead || S.won) return false;
    }
  }

  function decisionOptions(S) {
    var a = S.actors[0], opts = [];
    if (a.dir === 0) {
      var here = pf(a.pos[0], a.pos[1]) || pf(a.tilePos[0], a.tilePos[1]);
      if (here) for (var j = 0; j < 4; j++) if (here.allowedDir & DIRS[j]) opts.push(DIRS[j]);
      return opts;
    }
    var t = pf(a.tilePos[0], a.tilePos[1]);
    if (!t) return [a.dir];
    var allowed = t.allowedDir & ~OPP[a.dir];
    for (j = 0; j < 4; j++) if (allowed & DIRS[j]) opts.push(DIRS[j]);
    return opts;
  }

  function dfs(S, depth) {
    if (!runUntilDecision(S)) return evaluate(S);
    if (depth >= CFG.maxDepth || ticksUsed > CFG.tickBudget || now() > deadline) return evaluate(S);
    var opts = decisionOptions(S);
    if (!opts.length) return evaluate(S);
    var best = -Infinity;
    for (var i = 0; i < opts.length; i++) {
      var C = i === opts.length - 1 ? S : cloneState(S);
      C.pending = opts[i];
      var v = dfs(C, depth + 1);
      if (v > best) best = v;
    }
    return best;
  }

  function dotField(S) {
    var out = new Int16Array(COLS * ROWS).fill(32767), q = MAP.queue, nb = MAP.nb;
    var h = 0, tl = 0, tiles = MAP.tiles;
    for (var i = 0; i < tiles.length; i++) if (S.dots[tiles[i]]) { out[tiles[i]] = 0; q[tl++] = tiles[i]; }
    while (h < tl) {
      var cur = q[h++], cd = out[cur];
      for (var s = 0; s < 4; s++) {
        var n = nb[cur * 4 + s];
        if (n >= 0 && out[n] > cd + 1) { out[n] = cd + 1; q[tl++] = n; }
      }
    }
    return out;
  }

  // ¿Pac-Man está entrando a un cruce y todavía no pasa el centro?
  function pendingJunction(a) {
    if (a.dir === 0) return false;
    var t = pf(a.tilePos[0], a.tilePos[1]);
    if (!t || !t.intersection) return false;
    var l = L[a.dir];
    return (a.tilePos[l.axis] - a.pos[l.axis]) * l.inc > 0;
  }

  // Decide la jugada para el estado vivo. Devuelve {kind, dir, scores}
  function plan() {
    if (!MAP || MAP.playfield !== G.playfield) MAP = buildMap();
    D = SI(1).length || 90;
    ticksUsed = 0;
    deadline = now() + CFG.msBudget;
    // Presión: si lleva mucho sin comer (fantasmas acampando junto a los
    // últimos puntos), acepta más riesgo calculado y busca más lejos.
    if (G.dotsRemaining !== lastDots) { lastDots = G.dotsRemaining; lastDotTime = G.globalTime; }
    frustration = Math.max(0, G.globalTime - lastDotTime - 180);
    var f = Math.min(1, frustration / 1800);
    W.dot = CFG.dotDistW * (1 + 8 * f);
    W.trap = CFG.trapW * (1 - 0.85 * f);
    W.near = CFG.nearGhostW * (1 - 0.85 * f);
    var S0 = snapshot();
    var pac = S0.actors[0];
    var options = [];
    if (pac.dir === 0) {
      var here = pf(pac.pos[0], pac.pos[1]) || pf(pac.tilePos[0], pac.tilePos[1]);
      if (here) for (var j = 0; j < 4; j++) if (here.allowedDir & DIRS[j]) options.push({ kind: 'dir', dir: DIRS[j] });
    } else {
      options.push({ kind: 'rev', dir: OPP[pac.dir] });
      if (pendingJunction(pac)) {
        var t = pf(pac.tilePos[0], pac.tilePos[1]);
        var allowed = t.allowedDir & ~OPP[pac.dir];
        for (j = 0; j < 4; j++) if (allowed & DIRS[j]) options.push({ kind: 'dir', dir: DIRS[j] });
      } else {
        options.push({ kind: 'cont', dir: -1 });
      }
    }
    if (!options.length) return null;
    // Campo de distancias a los puntos (BFS multi-origen) para el modo remate
    var field = null;
    if (f > 0) {
      field = dotField(S0);
    }
    var best = null;
    for (var i = 0; i < options.length; i++) {
      var o = options[i];
      var C = cloneState(S0);
      applyChoice(C, C.actors[0], o.dir);
      C.needDecision = false;
      o.score = dfs(C, 0);
      if (o.kind === 'rev') o.score -= CFG.reversePenalty;
      if (field) {
        var dd = o.dir === -1 ? pac.dir : o.dir;
        var nIdx = MAP.nb[tIdx(pac.tilePos[0], pac.tilePos[1]) * 4 + DIR_SLOT[dd]];
        if (nIdx >= 0 && field[nIdx] < 32767) o.score -= f * 400 * field[nIdx];
        else o.score -= f * 400 * 60;
      }
      if (!best || o.score > best.score) best = o;
    }
    best.options = options;
    best.ticks = ticksUsed;
    return best;
  }

  root.PacBrain = {
    setGame: function (g) { G = g; MAP = null; },
    plan: plan,
    applyChoice: function (actor, k) {
      if (k === -1) { if (actor.nextDir) { actor.nextDir = 0; actor.posDelta = [0, 0]; } }
      else if (k === actor.dir && actor.dir !== 0) { actor.nextDir = 0; actor.posDelta = [0, 0]; }
      else actor.requestedDir = k;
    },
    pendingJunction: pendingJunction,
    CFG: CFG,
    _sim: { snapshot: snapshot, cloneState: cloneState, simTick: simTick, applyChoice: applyChoice,
      buildMap: function () { MAP = buildMap(); D = SI(1).length || 90; } }
  };
})(typeof window !== 'undefined' ? window : this);
