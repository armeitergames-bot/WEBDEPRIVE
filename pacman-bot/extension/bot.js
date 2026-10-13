/*
 * PacBot — bot autónomo para el Pac-Man de Google.
 *
 * Corre en el "mundo principal" de la página (MAIN world) para poder mandar
 * teclas que el juego acepte y para acelerar el tiempo (modo turbo).
 *
 * No depende del código interno (ofuscado) del juego: observa los elementos
 * de la página, descubre solo el laberinto, los puntos, a Pac-Man y a los
 * fantasmas, y decide cada movimiento con búsquedas en el laberinto.
 */
(() => {
  'use strict';
  if (window.__pacBot) return;

  // ---------------------------------------------------------------------------
  // Funciones nativas guardadas antes de cualquier parche
  // ---------------------------------------------------------------------------
  const N = {
    now: performance.now.bind(performance),
    Date: window.Date,
    dateNow: window.Date.now.bind(window.Date),
    setTimeout: window.setTimeout.bind(window),
    clearTimeout: window.clearTimeout.bind(window),
    setInterval: window.setInterval.bind(window),
    clearInterval: window.clearInterval.bind(window),
    raf: window.requestAnimationFrame.bind(window),
  };

  const LIKELY_GAME_PAGE = /pac-?man/i.test(location.href);

  const store = {
    get(k, d) {
      try {
        const v = localStorage.getItem('pacbot:' + k);
        return v == null ? d : JSON.parse(v);
      } catch (e) {
        return d;
      }
    },
    set(k, v) {
      try {
        localStorage.setItem('pacbot:' + k, JSON.stringify(v));
      } catch (e) {}
    },
  };

  // ---------------------------------------------------------------------------
  // Turbo: acelera el reloj del juego
  // ---------------------------------------------------------------------------
  const Turbo = (() => {
    let factor = 1;
    let touched = false;
    let baseReal = N.now();
    let baseVirt = baseReal;
    const perf0 = N.now();
    const date0 = N.dateNow();

    const vNow = () => (touched ? baseVirt + (N.now() - baseReal) * factor : N.now());
    const vDateNow = () => (touched ? date0 + (vNow() - perf0) : N.dateNow());

    function install() {
      performance.now = function () {
        return vNow();
      };

      const ND = N.Date;
      function PDate(...args) {
        if (!new.target) return new ND(vDateNow()).toString();
        if (args.length === 0) return Reflect.construct(ND, [vDateNow()], new.target);
        return Reflect.construct(ND, args, new.target);
      }
      PDate.prototype = ND.prototype;
      Object.setPrototypeOf(PDate, ND);
      PDate.now = vDateNow;
      window.Date = PDate;

      window.setTimeout = function (fn, d, ...a) {
        const delay = factor !== 1 ? (+d || 0) / factor : d;
        return N.setTimeout(fn, delay, ...a);
      };

      // Los intervalos rápidos (bucles de juego) usan un planificador propio
      // para que el turbo se pueda cambiar en caliente.
      const ivs = new Map();
      let seq = 1e9;
      window.setInterval = function (fn, d, ...a) {
        d = +d || 0;
        if (d > 60) return N.setInterval(fn, d, ...a);
        const id = ++seq;
        let next = N.now() + Math.max(1, d / factor);
        const tick = () => {
          if (!ivs.has(id)) return;
          next += Math.max(1, d / factor);
          const now = N.now();
          if (next < now - 250) next = now; // no acumular atrasos enormes
          ivs.set(id, N.setTimeout(tick, Math.max(0, next - now)));
          if (typeof fn === 'function') fn(...a);
          else (0, eval)(String(fn));
        };
        ivs.set(id, N.setTimeout(tick, Math.max(1, d / factor)));
        return id;
      };
      const clear = (nat) =>
        function (id) {
          if (ivs.has(id)) {
            N.clearTimeout(ivs.get(id));
            ivs.delete(id);
          } else nat(id);
        };
      window.clearInterval = clear(N.clearInterval);
      window.clearTimeout = clear(N.clearTimeout);

      window.requestAnimationFrame = function (cb) {
        return N.raf((t) => cb(touched ? vNow() : t));
      };
    }

    return {
      install,
      get factor() {
        return factor;
      },
      set(f) {
        f = Math.max(1, Math.min(4, +f || 1));
        baseVirt = vNow();
        baseReal = N.now();
        factor = f;
        if (f !== 1) touched = true;
      },
    };
  })();

  if (LIKELY_GAME_PAGE) Turbo.install();

  // ---------------------------------------------------------------------------
  // Utilidades
  // ---------------------------------------------------------------------------
  const DIRS = {
    L: { dc: -1, dr: 0, code: 37, key: 'ArrowLeft', rev: 'R' },
    U: { dc: 0, dr: -1, code: 38, key: 'ArrowUp', rev: 'D' },
    R: { dc: 1, dr: 0, code: 39, key: 'ArrowRight', rev: 'L' },
    D: { dc: 0, dr: 1, code: 40, key: 'ArrowDown', rev: 'U' },
  };
  const key = (c, r) => c + ',' + r;
  const unkey = (k) => {
    const i = k.indexOf(',');
    return [+k.slice(0, i), +k.slice(i + 1)];
  };
  const median = (a) => {
    if (!a.length) return 0;
    const s = [...a].sort((x, y) => x - y);
    return s[s.length >> 1];
  };
  function mode(values) {
    const m = new Map();
    let best = null;
    let bestN = 0;
    for (const v of values) {
      const n = (m.get(v) || 0) + 1;
      m.set(v, n);
      if (n > bestN) {
        bestN = n;
        best = v;
      }
    }
    return best;
  }
  // Media circular de residuos en [0, p): sirve para encontrar desfases de sprites
  function circMean(samples, p) {
    let sx = 0;
    let sy = 0;
    for (const s of samples) {
      const a = (s / p) * 2 * Math.PI;
      sx += Math.cos(a);
      sy += Math.sin(a);
    }
    let m = (Math.atan2(sy, sx) / (2 * Math.PI)) * p;
    if (m > p / 2) m -= p;
    if (m <= -p / 2) m += p;
    return m;
  }
  const isVisible = (el) => el.isConnected && el.offsetWidth > 0 && el.offsetHeight > 0;

  // Tiempos de susto (en segundos) por nivel, como en el arcade original
  const HORIZON = 10;
  const FRIGHT_TABLE = [6, 5, 4, 3, 2, 5, 2, 2, 1, 5, 2, 1, 1, 3, 1, 1, 0, 1];

  // ---------------------------------------------------------------------------
  // Estado global
  // ---------------------------------------------------------------------------
  const S = {
    enabled: store.get('enabled', false),
    showBrain: store.get('brain', false),
    root: null,
    rootRect: null,
    ts: 8,
    ox: 0,
    oy: 0,
    calibratedGrid: false,
    dots: [], // {el, x, y, k, big, wasVisible, hiddenSince}
    dotTiles: new Map(), // k -> dot
    everDot: new Set(),
    eaten: new Set(),
    visibleDots: 0,
    level: 1,
    tracks: new Map(), // el -> track
    actorEls: [],
    lastActorScan: 0,
    pac: null,
    offsets: new Map(), // bucket -> {xs:[], ys:[]}
    frightStart: -1e9,
    frightEnded: true,
    normalSigs: new Set(),
    sigOwners: new Map(), // sig -> Set(trackId)
    frightShared: new Set(),
    lastFrightSigSeen: 0,
    mode: '—',
    plan: null,
    danger: null,
    lastKey: null,
    lastKeyAt: 0,
    stuck: { since: 0, k: null, to: null },
    stats: { frames: 0 },
    lastSeenGame: 0,
  };
  let trackSeq = 0;

  // ---------------------------------------------------------------------------
  // Grafo del laberinto (se aprende jugando)
  // ---------------------------------------------------------------------------
  const Graph = {
    adj: new Map(), // k -> Map(k2 -> edge)
    edge(a, b) {
      const m = this.adj.get(a);
      return m ? m.get(b) : undefined;
    },
    add(a, b, type, dir) {
      // type: 'c' confirmado (un actor lo cruzó), 't' tentativo (puntos), 'w' túnel
      const set = (x, y, d) => {
        let m = this.adj.get(x);
        if (!m) this.adj.set(x, (m = new Map()));
        const e = m.get(y);
        if (!e) m.set(y, { type, dir: d, blocked: false });
        else if (type !== 't') {
          e.type = type;
          e.blocked = false;
          if (d) e.dir = d;
        }
      };
      const [ac, ar] = unkey(a);
      const [bc, br] = unkey(b);
      let d1 = dir;
      if (!d1) {
        for (const [n, d] of Object.entries(DIRS)) if (ac + d.dc === bc && ar + d.dr === br) d1 = n;
      }
      if (!d1) return;
      set(a, b, d1);
      set(b, a, DIRS[d1].rev);
    },
    block(a, b) {
      for (const [x, y] of [
        [a, b],
        [b, a],
      ]) {
        const e = this.edge(x, y);
        if (e && e.type !== 'c' && e.type !== 'w') e.blocked = true;
      }
    },
    neighbors(k) {
      const out = [];
      const m = this.adj.get(k);
      if (m) for (const [k2, e] of m) if (!e.blocked) out.push([k2, e]);
      return out;
    },
    has(k) {
      return this.adj.has(k);
    },
    nearest(c, r) {
      const k = key(c, r);
      if (this.has(k)) return k;
      let best = null;
      let bd = 3;
      for (const k2 of this.adj.keys()) {
        const [c2, r2] = unkey(k2);
        const d = Math.abs(c2 - c) + Math.abs(r2 - r);
        if (d < bd) {
          bd = d;
          best = k2;
        }
      }
      return best;
    },
    reset() {
      this.adj.clear();
    },
  };

  // ---------------------------------------------------------------------------
  // Detección del juego
  // ---------------------------------------------------------------------------
  function findGameRoot() {
    let best = null;
    let bestScore = 0;
    for (const el of document.querySelectorAll('*')) {
      if (el.childElementCount < 50) continue;
      let tiny = 0;
      let visTiny = 0;
      for (const ch of el.children) {
        const w = ch.offsetWidth;
        const h = ch.offsetHeight;
        if (w <= 8 && h <= 8) {
          if (w > 0 && h > 0) visTiny++;
          else if (!(ch.style.width || ch.style.height)) continue;
          tiny++;
        }
      }
      if (visTiny >= 20 && tiny >= 50 && tiny > bestScore) {
        bestScore = tiny;
        best = el;
      }
    }
    return best;
  }

  function attachRoot(root) {
    S.root = root;
    S.dots = [];
    S.dotTiles.clear();
    S.eaten.clear();
    S.tracks.clear();
    S.pac = null;
    S.actorEls = [];
    S.offsets.clear();
    Graph.reset();
    S.everDot.clear();
    S.calibratedGrid = false;
    collectDots();
  }

  function rel(el) {
    const r = el.getBoundingClientRect();
    const rr = S.rootRect;
    return { x: r.left - rr.left + r.width / 2, y: r.top - rr.top + r.height / 2, w: r.width, h: r.height };
  }

  function collectDots() {
    S.rootRect = S.root.getBoundingClientRect();
    const found = [];
    for (const ch of S.root.children) {
      if (!isVisible(ch)) continue;
      const g = rel(ch);
      if (g.w <= 8 && g.h <= 8) found.push({ el: ch, ...g });
    }
    if (found.length < 20) return;
    // Los puntos normales son el grupo de tamaño más pequeño que se repite mucho
    // (así no confundimos trozos de pared con puntos).
    const groups = new Map();
    for (const d of found) {
      const a = Math.round(d.w) * 100 + Math.round(d.h);
      if (!groups.has(a)) groups.set(a, []);
      groups.get(a).push(d);
    }
    let dotGroup = null;
    for (const [a, g] of groups) {
      if (g.length < 20) continue;
      if (!dotGroup || g[0].w * g[0].h < dotGroup[0].w * dotGroup[0].h) dotGroup = g;
    }
    if (!dotGroup) return;
    const dotArea = dotGroup[0].w * dotGroup[0].h;
    const all = found.slice();
    found.length = 0;
    found.push(...dotGroup);
    // Tamaño de casilla = separación más común entre puntos
    const diffs = [];
    for (const axis of ['x', 'y']) {
      const vals = [...new Set(found.map((d) => Math.round(d[axis] * 2) / 2))].sort((a, b) => a - b);
      for (let i = 1; i < vals.length; i++) {
        const df = Math.round((vals[i] - vals[i - 1]) * 2) / 2;
        if (df >= 3 && df <= 24) diffs.push(df);
      }
    }
    const ts = mode(diffs) || 8;
    S.ts = ts;
    const resid = (v) => Math.round((((v % ts) + ts) % ts) * 2) / 2;
    S.ox = mode(found.map((d) => resid(d.x)));
    S.oy = mode(found.map((d) => resid(d.y)));
    S.calibratedGrid = true;

    // Energizantes: elementos algo más grandes que un punto pero más pequeños que una casilla
    const bigs = all.filter((d) => d.w * d.h > dotArea * 1.8 && d.w < ts * 0.95 && d.h < ts * 0.95 && Math.abs(d.w - d.h) <= 2);
    if (bigs.length <= 12) found.push(...bigs);
    const known = new Set(S.dots.map((d) => d.el));
    for (const d of found) {
      if (known.has(d.el)) continue;
      const c = Math.round((d.x - S.ox) / ts);
      const r = Math.round((d.y - S.oy) / ts);
      const k = key(c, r);
      const dot = {
        el: d.el,
        x: c * ts + S.ox,
        y: r * ts + S.oy,
        k,
        big: d.w * d.h > dotArea * 1.8,
        wasVisible: true,
        hiddenSince: 0,
      };
      S.dots.push(dot);
      S.dotTiles.set(k, dot);
      S.everDot.add(k);
    }
    rebuildTentativeEdges();
  }

  function rebuildTentativeEdges() {
    for (const k of S.everDot) {
      const [c, r] = unkey(k);
      for (const d of ['R', 'D']) {
        const k2 = key(c + DIRS[d].dc, r + DIRS[d].dr);
        if (S.everDot.has(k2) || Graph.has(k2)) Graph.add(k, k2, 't', d);
      }
      for (const d of ['L', 'U']) {
        const k2 = key(c + DIRS[d].dc, r + DIRS[d].dr);
        if (Graph.has(k2) && !S.everDot.has(k2)) Graph.add(k, k2, 't', d);
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Percepción por cuadro
  // ---------------------------------------------------------------------------
  function tileOf(track, x, y) {
    const off = offsetFor(track);
    const c = Math.round((x - off.x - S.ox) / S.ts);
    const r = Math.round((y - off.y - S.oy) / S.ts);
    return [c, r];
  }

  function bucketOf(track) {
    return Math.round(track.w) + 'x' + Math.round(track.h);
  }

  function offsetFor(track) {
    const b = S.offsets.get(bucketOf(track));
    if (!b) return { x: 0, y: 0, ok: false };
    // Lo más fiable: dónde está el sprite de Pac-Man justo cuando se come un punto
    if (b.ex.length >= 3 && b.ey.length >= 3) return { x: median(b.ex), y: median(b.ey), ok: true };
    const o = b.cached || { x: 0, y: 0, ok: false };
    // Sprites de otro tamaño (fantasmas distintos de Pac-Man): usar la media circular,
    // pero sólo cuando Pac-Man ya está calibrado.
    const pb = S.pac && S.offsets.get(bucketOf(S.pac));
    const pacOk = pb && pb !== b && pb.ex.length >= 3 && pb.ey.length >= 3;
    return { x: o.x, y: o.y, ok: !!(o.ok && b.isGhostOnly && pacOk) };
  }

  function bucket(track) {
    const bk = bucketOf(track);
    let b = S.offsets.get(bk);
    if (!b) S.offsets.set(bk, (b = { xs: [], ys: [], ex: [], ey: [], cached: null, isGhostOnly: true }));
    return b;
  }

  function addOffsetSample(track, axis, v) {
    const b = bucket(track);
    const arr = axis === 'x' ? b.xs : b.ys;
    arr.push(v);
    if (arr.length > 200) arr.shift();
    if (b.xs.length >= 12 && b.ys.length >= 12) {
      b.cached = { x: circMean(b.xs, S.ts), y: circMean(b.ys, S.ts), ok: true };
    } else if (b.xs.length >= 12 || b.ys.length >= 12) {
      b.cached = {
        x: b.xs.length >= 12 ? circMean(b.xs, S.ts) : 0,
        y: b.ys.length >= 12 ? circMean(b.ys, S.ts) : 0,
        ok: false,
      };
    }
  }

  function sigOf(el) {
    let bp = el.style.backgroundPosition;
    let bi = el.style.backgroundImage;
    if (!bp && !bi) {
      const cs = getComputedStyle(el);
      bp = cs.backgroundPosition;
      bi = cs.backgroundImage;
    }
    return (el.className && el.className.baseVal === undefined ? el.className : '') + '|' + bp + '|' + (bi || '').slice(-48);
  }

  function scanActors(now) {
    S.lastActorScan = now;
    const scope = S.root.parentElement || S.root;
    const dotSet = new Set(S.dots.map((d) => d.el));
    const rr = S.rootRect;
    const min = S.ts * 1.2;
    const max = S.ts * 3.6;
    const els = [];
    for (const el of scope.querySelectorAll('*')) {
      if (dotSet.has(el) || el === S.root || el.id === 'pacbot-overlay') continue;
      const w = el.offsetWidth;
      const h = el.offsetHeight;
      if (w < min || h < min || w > max || h > max) continue;
      const r = el.getBoundingClientRect();
      if (r.right < rr.left || r.left > rr.right || r.bottom < rr.top || r.top > rr.bottom) continue;
      els.push(el);
    }
    S.actorEls = els;
  }

  function updateDots(now) {
    // Si el juego reemplazó los elementos de los puntos (nivel nuevo), volver a recogerlos
    let gone = 0;
    for (const d of S.dots) if (!d.el.isConnected) gone++;
    if (S.dots.length && gone > S.dots.length / 2) {
      S.dots = S.dots.filter((d) => d.el.isConnected);
      S.dotTiles.clear();
      for (const d of S.dots) S.dotTiles.set(d.k, d);
      collectDots();
    }
    let vis = 0;
    let visNormal = 0;
    const vanished = [];
    for (const d of S.dots) {
      const v = isVisible(d.el);
      if (v) {
        vis++;
        if (!d.big) visNormal++;
        d.hiddenSince = 0;
      } else if (d.wasVisible || !d.hiddenSince) {
        if (!d.hiddenSince) d.hiddenSince = now;
      }
      if (d.wasVisible && !v) {
        if (!d.big) vanished.push(d);
      }
      // Los energizantes parpadean: sólo cuentan como comidos si siguen ocultos un rato
      if (d.big && !v && d.hiddenSince && now - d.hiddenSince > 900 && !S.eaten.has(d.k)) {
        S.eaten.add(d.k);
      }
      d.wasVisible = v;
    }
    // ¿Nuevo nivel o partida nueva? (aparecen muchos puntos de golpe)
    if (S.visibleDots && visNormal - S.prevVisNormal > 30) {
      if (S.prevVisNormal > 25) S.level = 1; // se rellenó a medias: partida nueva
      else S.level++;
      S.eaten.clear();
      S.frightStart = -1e9;
      S.frightEnded = true;
    }
    S.prevVisNormal = visNormal;
    S.visibleDots = vis;
    return vanished;
  }

  function updateActors(now, dt) {
    const rr = S.rootRect;
    // Agrupar elementos superpuestos (cuerpo + ojos) en un solo actor
    const items = [];
    for (const el of S.actorEls) {
      if (!isVisible(el)) continue;
      const g = rel(el);
      if (g.x < -S.ts || g.y < -S.ts || g.x > rr.width + S.ts || g.y > rr.height + S.ts) continue;
      items.push({ el, ...g, area: g.w * g.h });
    }
    items.sort((a, b) => b.area - a.area);
    const actors = [];
    for (const it of items) {
      const host = actors.find((a) => Math.abs(a.x - it.x) < S.ts * 0.6 && Math.abs(a.y - it.y) < S.ts * 0.6);
      if (host) host.extra.push(it.el);
      else actors.push({ ...it, extra: [] });
    }

    const seen = new Set();
    for (const a of actors) {
      let t = S.tracks.get(a.el);
      if (!t) {
        t = {
          id: ++trackSeq,
          el: a.el,
          x: a.x,
          y: a.y,
          w: a.w,
          h: a.h,
          lastMove: 0,
          speed: 0,
          credits: 0,
          dir: null,
          tile: null,
          prevTile: null,
          sig: '',
          firstSeen: now,
        };
        S.tracks.set(a.el, t);
      }
      seen.add(a.el);
      const dx = a.x - t.x;
      const dy = a.y - t.y;
      const jump = Math.abs(dx) > S.ts * 3 || Math.abs(dy) > S.ts * 3;
      if (!jump && (Math.abs(dx) > 0.3 || Math.abs(dy) > 0.3)) {
        t.lastMove = now;
        const v = Math.hypot(dx, dy) / S.ts / Math.max(dt, 1e-3);
        if (v < 40) t.speed = t.speed ? t.speed * 0.9 + v * 0.1 : v;
        // Calibración del desfase del sprite respecto a la cuadrícula
        if (Math.abs(dx) > 0.3 && Math.abs(dy) < 0.05) addOffsetSample(t, 'y', a.y - S.oy);
        if (Math.abs(dy) > 0.3 && Math.abs(dx) < 0.05) addOffsetSample(t, 'x', a.x - S.ox);
        if (Math.abs(dx) > Math.abs(dy)) t.moveDir = dx > 0 ? 'R' : 'L';
        else t.moveDir = dy > 0 ? 'D' : 'U';
      }
      t.jumped = jump;
      t.x = a.x;
      t.y = a.y;
      t.w = a.w;
      t.h = a.h;
      t.sig = sigOf(a.el) + a.extra.map(sigOf).join('');
      t.seen = now;

      const [c, r] = tileOf(t, a.x, a.y);
      const k = key(c, r);
      if (k !== t.tile) {
        if (t.tile && offsetFor(t).ok && !jump) learnStep(t.tile, k);
        else if (t.tile && jump) learnWrap(t, t.tile, k);
        t.prevTile = t.tile;
        t.tile = k;
        t.tileSince = now;
        if (t.prevTile) {
          const [pc, pr] = unkey(t.prevTile);
          const ddc = Math.sign(c - pc);
          const ddr = Math.sign(r - pr);
          for (const [n, d] of Object.entries(DIRS)) if (d.dc === ddc && d.dr === ddr) t.dir = n;
        }
      }
      t.c = c;
      t.r = r;
    }
    for (const [el, t] of S.tracks) {
      if (!seen.has(el)) {
        t.missing = (t.missing || 0) + 1;
        if (t.missing > 120) S.tracks.delete(el);
      } else t.missing = 0;
    }
  }

  function learnStep(a, b) {
    const [ac, ar] = unkey(a);
    const [bc, br] = unkey(b);
    const dc = bc - ac;
    const dr = br - ar;
    if (Math.abs(dc) + Math.abs(dr) === 1) Graph.add(a, b, 'c');
    else if ((Math.abs(dc) === 2 && dr === 0) || (Math.abs(dr) === 2 && dc === 0)) {
      const m = key(ac + dc / 2, ar + dr / 2);
      Graph.add(a, m, 'c');
      Graph.add(m, b, 'c');
    }
  }

  function learnWrap(t, a, b) {
    // Túnel: salto horizontal grande en la misma fila
    const [ac, ar] = unkey(a);
    const [bc, br] = unkey(b);
    if (ar !== br || Math.abs(ac - bc) < 10) return;
    const dir = ac > bc ? 'R' : 'L';
    if (!Graph.edge(a, b)) {
      let m = Graph.adj.get(a);
      if (!m) Graph.adj.set(a, (m = new Map()));
      m.set(b, { type: 'w', dir, blocked: false });
      let m2 = Graph.adj.get(b);
      if (!m2) Graph.adj.set(b, (m2 = new Map()));
      m2.set(a, { type: 'w', dir: DIRS[dir].rev, blocked: false });
    }
  }

  function identifyPac(vanished, now) {
    const live = [...S.tracks.values()].filter((t) => t.seen === now);
    for (const d of vanished) {
      let best = null;
      let bd = S.ts * 3;
      for (const t of live) {
        const dist = Math.hypot(t.x - d.x, t.y - d.y);
        if (dist < bd) {
          bd = dist;
          best = t;
        }
      }
      if (best) best.credits++;
      if (best && best === S.pac) {
        S.eaten.add(d.k);
        const b = bucket(best);
        b.isGhostOnly = false;
        if (best.moveDir === 'L' || best.moveDir === 'R') b.ey.push(best.y - d.y);
        else if (best.moveDir) b.ex.push(best.x - d.x);
        if (b.ex.length > 30) b.ex.shift();
        if (b.ey.length > 30) b.ey.shift();
      }
    }
    let top = null;
    for (const t of S.tracks.values()) if (!top || t.credits > top.credits) top = t;
    if (top && top.credits >= 3 && (!S.pac || top.credits > S.pac.credits + 3 || !S.tracks.has(S.pac.el))) S.pac = top;
    if (S.pac && !S.tracks.has(S.pac.el)) S.pac = null;
  }

  // ---------------------------------------------------------------------------
  // Estado de los fantasmas (normal / asustado / ojos)
  // ---------------------------------------------------------------------------
  function frightLeft(now) {
    if (S.frightEnded) return 0;
    const est = (FRIGHT_TABLE[Math.min(S.level - 1, FRIGHT_TABLE.length - 1)] ?? 1) * 1000;
    return Math.max(0, S.frightStart + est - gameTime(now));
  }

  // Tiempo del juego (tiene en cuenta el turbo)
  const gameTime = (now) => now * Turbo.factor;

  function updateGhosts(now) {
    const pac = S.pac;
    const ghosts = [];
    for (const t of S.tracks.values()) {
      if (t === pac || t.seen !== now) continue;
      if (now - t.lastMove > 6000 && now - t.firstSeen > 1500) continue; // decorado quieto
      ghosts.push(t);
    }
    // Energizante comido por Pac-Man
    if (pac && pac.tile) {
      const d = S.dotTiles.get(pac.tile);
      if (d && d.big && !S.eaten.has(d.k)) {
        S.eaten.add(d.k);
        S.frightStart = gameTime(now);
        S.frightEnded = false;
        S.frightSeenAny = false;
      }
    }
    const inWindow = !S.frightEnded && gameTime(now) - S.frightStart < 12000;
    const sigCount = new Map();
    for (const g of ghosts) sigCount.set(g.sig, (sigCount.get(g.sig) || 0) + 1);
    let anyFright = false;
    for (const g of ghosts) {
      let owners = S.sigOwners.get(g.sig);
      if (!owners) S.sigOwners.set(g.sig, (owners = new Set()));
      owners.add(g.id);
      if (!inWindow && gameTime(now) - S.frightStart > 14000) S.normalSigs.add(g.sig);
      if (inWindow && !S.normalSigs.has(g.sig) && (owners.size >= 2 || sigCount.get(g.sig) >= 2)) S.frightShared.add(g.sig);
      const special = S.frightShared.has(g.sig) && !S.normalSigs.has(g.sig);
      g.edible = special;
      if (special) anyFright = true;
    }
    if (anyFright) {
      S.lastFrightSigSeen = now;
      S.frightSeenAny = true;
    }
    if (!S.frightEnded && S.frightSeenAny && !anyFright && now - S.lastFrightSigSeen > 400) S.frightEnded = true;
    if (!S.frightEnded && gameTime(now) - S.frightStart > 12000) S.frightEnded = true;
    S.ghosts = ghosts;
  }

  // ---------------------------------------------------------------------------
  // Cerebro: decide hacia dónde ir
  // ---------------------------------------------------------------------------
  function bfs(start, avoidFirst, maxD = 400) {
    const dist = new Map([[start, 0]]);
    const q = [start];
    for (let i = 0; i < q.length; i++) {
      const k = q[i];
      const d = dist.get(k);
      if (d >= maxD) continue;
      for (const [k2] of Graph.neighbors(k)) {
        if (dist.has(k2)) continue;
        if (i === 0 && k2 === avoidFirst) continue;
        dist.set(k2, d + 1);
        q.push(k2);
      }
    }
    return dist;
  }

  function dangerMap(now) {
    // Tiempo (s) que tarda el fantasma peligroso más rápido en llegar a cada casilla
    const T = new Map();
    const pacSpeed = Math.max(S.pac.speed || 0, 6);
    const left = frightLeft(now) / 1000 / Turbo.factor;
    for (const g of S.ghosts) {
      // Asustado con tiempo de sobra: no es peligroso. Si el susto está por acabar, sí.
      if (g.edible && left > 1.0) continue;
      const start = Graph.nearest(g.c, g.r);
      if (!start) continue;
      const startPenalty = start === g.tile ? 0 : 1;
      const v = Math.max(g.speed || 0, pacSpeed * 0.95);
      const dist = bfs(start, g.prevTile && g.dir ? g.prevTile : null);
      for (const [k, d] of dist) {
        const t = (d + startPenalty) / v;
        if (!T.has(k) || T.get(k) > t) T.set(k, t);
      }
      // la casilla por detrás también es peligrosa si está pegada
      if (g.prevTile) {
        const t = 1 / v;
        if (!T.has(g.prevTile) || T.get(g.prevTile) > t) T.set(g.prevTile, t);
      }
    }
    return T;
  }

  function remainingDots() {
    const out = new Map();
    for (const d of S.dots) {
      if (S.eaten.has(d.k)) continue;
      if (!d.big && !isVisible(d.el)) continue;
      out.set(d.k, d);
    }
    return out;
  }

  function decide(now) {
    const pac = S.pac;
    if (!pac || !pac.tile) return null;
    let P = Graph.has(pac.tile) ? pac.tile : Graph.nearest(pac.c, pac.r);
    if (!P) return null;

    // Si Pac-Man ya pasó el centro de su casilla, planear desde la siguiente
    const [pc, pr] = unkey(P);
    const off = offsetFor(pac);
    const fx = (pac.x - off.x - S.ox) / S.ts - pc;
    const fy = (pac.y - off.y - S.oy) / S.ts - pr;
    let from = P;
    if (pac.moveDir && now - pac.lastMove < 150) {
      const d = DIRS[pac.moveDir];
      const along = fx * d.dc + fy * d.dr;
      const nk = key(pc + d.dc, pr + d.dr);
      const e = Graph.edge(P, nk);
      if (along > 0.15 && e && !e.blocked) from = nk;
    }

    const T = dangerMap(now);
    S.danger = T;
    const vP = Math.max(pac.speed || 0, 6);
    const margin = 0.15;
    const dots = remainingDots();
    let normalLeft = 0;
    for (const d of dots.values()) if (!d.big) normalLeft++;
    const left = frightLeft(now) / 1000 / Turbo.factor;

    let nearestThreat = Infinity;
    if (T.has(from)) nearestThreat = T.get(from);
    const hunted = nearestThreat < 2.2;
    const energizerAllowed = hunted || normalLeft <= 6;

    const edibleTiles = new Set();
    if (left > 0.6) for (const g of S.ghosts) if (g.edible) edibleTiles.add(Graph.nearest(g.c, g.r));

    const options = [];
    const firstMoves = Graph.neighbors(from);
    for (const [n, e] of firstMoves) {
      // BFS restringida a casillas a las que llegamos antes que los fantasmas
      const dist = new Map([[n, 1]]);
      const parent = new Map([[n, null]]);
      const q = [n];
      // Más allá del horizonte los fantasmas ya se habrán movido: no vale la pena ser tan pesimista
      const ok = (k, d) => {
        if (d > HORIZON) return true;
        const tg = T.get(k);
        return tg === undefined || d / vP + margin < tg;
      };
      const firstSafe = ok(n, 1);
      let safeCount = 0;
      let dotD = Infinity;
      let dotK = null;
      let eneD = Infinity;
      let eneK = null;
      let ghostD = Infinity;
      let ghostK = null;
      let slack = Infinity;
      if (firstSafe) {
        for (let i = 0; i < q.length; i++) {
          const k = q[i];
          const d = dist.get(k);
          safeCount++;
          const tg = T.get(k);
          if (tg !== undefined && i < 6) slack = Math.min(slack, tg - d / vP);
          const dot = dots.get(k);
          if (dot) {
            if (dot.big) {
              if (d < eneD) {
                eneD = d;
                eneK = k;
              }
            } else if (d < dotD) {
              dotD = d;
              dotK = k;
            }
          }
          if (edibleTiles.has(k) && d / vP < left - 0.3 && d < ghostD) {
            ghostD = d;
            ghostK = k;
          }
          if (d > 60) continue;
          for (const [k2] of Graph.neighbors(k)) {
            if (dist.has(k2) || k2 === from) continue;
            if (!ok(k2, d + 1)) continue;
            dist.set(k2, d + 1);
            parent.set(k2, k);
            q.push(k2);
          }
        }
      }
      let score;
      let goal = null;
      // Distancia al punto más cercano aunque el camino no sea seguro (para no quedarse dando vueltas)
      let anyDotD = Infinity;
      if (firstSafe && !dotK && !ghostK) {
        const all = bfs(n, from);
        for (const [k, d] of all) if (dots.has(k) && d < anyDotD) anyDotD = d;
      }
      if (!firstSafe) {
        const tg = T.get(n) ?? 99;
        score = -5000 + (tg - 1 / vP) * 100;
      } else {
        score = Math.min(safeCount, 80) * 3;
        if (safeCount < 10) score -= 1500 - safeCount * 50;
        if (ghostK) {
          score += 900 - ghostD * 12;
          goal = ghostK;
        } else if (energizerAllowed && eneK && (hunted || eneD <= dotD + 2 || !dotK)) {
          score += 700 - eneD * 6;
          goal = eneK;
        } else if (dotK) {
          score += 500 - dotD * 6;
          goal = dotK;
        } else if (eneK) {
          score += 300 - eneD * 6;
          goal = eneK;
        } else if (Number.isFinite(anyDotD)) {
          score += 100 - anyDotD * 2;
        }
        // Evitar comerse un energizante sin necesidad
        const nd = dots.get(n);
        if (nd && nd.big && !energizerAllowed) score -= 250;
        if (Number.isFinite(slack)) score += Math.min(slack, 2) * 20;
      }
      if (pac.moveDir && e.dir === pac.moveDir) score += 4;
      if (pac.moveDir && e.dir === DIRS[pac.moveDir].rev && !hunted) score -= 6;
      let path = [];
      if (goal) {
        let k = goal;
        while (k) {
          path.push(k);
          k = parent.get(k);
        }
        path.reverse();
      }
      options.push({ n, dir: e.dir, score, safeCount, path });
    }
    if (!options.length) return null;
    options.sort((a, b) => b.score - a.score);
    const best = options[0];
    S.mode = best.score < -1000 ? 'acorralado' : hunted ? 'huyendo' : left > 0.6 && edibleTiles.size ? 'cazando' : 'comiendo';
    S.plan = { from, path: [from, ...best.path], options };

    // Si planeamos desde la casilla siguiente, la tecla es la dirección desde allí
    return { dir: best.dir, from, to: best.n };
  }

  // ---------------------------------------------------------------------------
  // Teclado
  // ---------------------------------------------------------------------------
  function sendKey(type, dir) {
    const d = DIRS[dir];
    const target = S.root || document;
    const ev = new KeyboardEvent(type, { key: d.key, code: d.key, bubbles: true, cancelable: true, view: window });
    Object.defineProperty(ev, 'keyCode', { get: () => d.code });
    Object.defineProperty(ev, 'which', { get: () => d.code });
    Object.defineProperty(ev, 'charCode', { get: () => 0 });
    target.dispatchEvent(ev);
  }

  function steer(dir, now) {
    if (dir !== S.lastKey) {
      if (S.lastKey) sendKey('keyup', S.lastKey);
      sendKey('keydown', dir);
      S.lastKey = dir;
      S.lastKeyAt = now;
    } else if (now - S.lastKeyAt > 120) {
      sendKey('keydown', dir);
      S.lastKeyAt = now;
    }
  }

  function releaseKeys() {
    if (S.lastKey) sendKey('keyup', S.lastKey);
    S.lastKey = null;
  }

  // Si Pac-Man se queda atascado contra una pared que creíamos pasillo, aprenderlo
  function checkStuck(now, move) {
    const pac = S.pac;
    if (!move || !pac) return;
    const othersMoving = (S.ghosts || []).some((g) => now - g.lastMove < 300);
    const st = S.stuck;
    if (now - pac.lastMove > 350 && othersMoving) {
      if (st.k !== pac.tile || st.to !== move.to) {
        st.k = pac.tile;
        st.to = move.to;
        st.since = now;
      } else if (now - st.since > 300) {
        if (move.from === pac.tile) Graph.block(pac.tile, move.to);
        st.since = now;
      }
    } else {
      st.k = null;
    }
  }

  // ---------------------------------------------------------------------------
  // Bucle principal
  // ---------------------------------------------------------------------------
  let lastFrame = N.now();
  let lastSearch = 0;
  function frame() {
    N.raf(frame);
    const now = N.now();
    const dt = (now - lastFrame) / 1000;
    lastFrame = now;
    try {
      if (!S.root || !S.root.isConnected) {
        if (S.root) {
          S.root = null;
          releaseKeys();
        }
        if (now - lastSearch > 1000) {
          lastSearch = now;
          const r = findGameRoot();
          if (r) attachRoot(r);
        }
        UI.update(now);
        return;
      }
      S.lastSeenGame = now;
      S.rootRect = S.root.getBoundingClientRect();
      if (!S.calibratedGrid || (now - (S.lastDotScan || 0) > 3000 && S.dots.length < 40)) {
        S.lastDotScan = now;
        collectDots();
      }
      if (now - S.lastActorScan > 400) scanActors(now);
      const vanished = updateDots(now);
      updateActors(now, dt);
      identifyPac(vanished, now);
      updateGhosts(now);
      S.stats.frames++;

      if (S.enabled) {
        if (!S.pac) {
          // Aún no sabemos quién es Pac-Man: empujarlo para que se mueva
          if (now - (S.nudgeAt || 0) > 900) {
            S.nudgeAt = now;
            S.nudgeDir = S.nudgeDir === 'L' ? 'R' : 'L';
            sendKey('keydown', S.nudgeDir);
          }
          S.mode = 'buscando a Pac-Man';
        } else if (!offsetFor(S.pac).ok) {
          // Calibrando: dejar que Pac-Man coma unos puntos para medir su sprite
          S.mode = 'calibrando';
          if (now - S.pac.lastMove > 200 && now - (S.nudgeAt || 0) > 250) {
            S.nudgeAt = now;
            const opts = Object.keys(DIRS).filter((d) => d !== S.lastKey);
            steer(opts[Math.floor(Math.random() * opts.length)], now);
          } else if (S.lastKey) steer(S.lastKey, now);
        } else {
          const move = decide(now);
          if (move) {
            steer(move.dir, now);
            checkStuck(now, move);
          }
        }
      }
      Overlay.draw(now);
    } catch (err) {
      S.lastError = String((err && err.stack) || err);
    }
    UI.update(now);
  }

  // ---------------------------------------------------------------------------
  // Capa de visualización ("ver cerebro")
  // ---------------------------------------------------------------------------
  const Overlay = {
    cv: null,
    draw() {
      if (!S.showBrain || !S.root) {
        if (this.cv) this.cv.style.display = 'none';
        return;
      }
      if (!this.cv) {
        this.cv = document.createElement('canvas');
        this.cv.id = 'pacbot-overlay';
        Object.assign(this.cv.style, { position: 'fixed', pointerEvents: 'none', zIndex: 2147483646 });
        document.documentElement.appendChild(this.cv);
      }
      const rr = S.rootRect;
      const cv = this.cv;
      cv.style.display = 'block';
      cv.style.left = rr.left + 'px';
      cv.style.top = rr.top + 'px';
      if (cv.width !== Math.ceil(rr.width) || cv.height !== Math.ceil(rr.height)) {
        cv.width = Math.ceil(rr.width);
        cv.height = Math.ceil(rr.height);
      }
      const g = cv.getContext('2d');
      g.clearRect(0, 0, cv.width, cv.height);
      const ts = S.ts;
      const px = (c) => c * ts + S.ox;
      const py = (r) => r * ts + S.oy;
      for (const [k, m] of Graph.adj) {
        const [c, r] = unkey(k);
        const tg = S.danger && S.danger.get(k);
        if (tg !== undefined && tg < 1.5) {
          g.fillStyle = `rgba(255,0,0,${0.45 * (1 - tg / 1.5)})`;
          g.fillRect(px(c) - ts / 2, py(r) - ts / 2, ts, ts);
        }
        for (const [k2, e] of m) {
          if (e.type === 'w') continue;
          const [c2, r2] = unkey(k2);
          g.strokeStyle = e.blocked ? 'rgba(255,0,0,.5)' : e.type === 'c' ? 'rgba(0,200,255,.35)' : 'rgba(255,255,255,.15)';
          g.beginPath();
          g.moveTo(px(c), py(r));
          g.lineTo(px(c2), py(r2));
          g.stroke();
        }
      }
      if (S.plan && S.plan.path.length > 1) {
        g.strokeStyle = '#3f6';
        g.lineWidth = 2;
        g.beginPath();
        S.plan.path.forEach((k, i) => {
          const [c, r] = unkey(k);
          if (i) g.lineTo(px(c), py(r));
          else g.moveTo(px(c), py(r));
        });
        g.stroke();
        g.lineWidth = 1;
      }
      for (const t of [S.pac, ...(S.ghosts || [])]) {
        if (!t) continue;
        g.strokeStyle = t === S.pac ? '#ff0' : t.edible ? '#39f' : '#f33';
        g.strokeRect(t.x - t.w / 2, t.y - t.h / 2, t.w, t.h);
      }
    },
  };

  // ---------------------------------------------------------------------------
  // Panel de control
  // ---------------------------------------------------------------------------
  const UI = {
    host: null,
    shown: false,
    forced: store.get('panel', null),
    lastUpdate: 0,
    build() {
      const host = document.createElement('div');
      host.id = 'pacbot-panel';
      Object.assign(host.style, { position: 'fixed', right: '16px', bottom: '16px', zIndex: 2147483647 });
      const sh = host.attachShadow({ mode: 'open' });
      sh.innerHTML = `
        <style>
          .p{font:13px/1.35 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#eee;background:#111c;backdrop-filter:blur(6px);
             border:2px solid #fc0;border-radius:12px;padding:10px 12px;width:230px;box-shadow:0 6px 24px #0008}
          h1{font-size:15px;margin:0 0 6px;color:#fc0;display:flex;align-items:center;gap:6px}
          h1 span{flex:1}
          .x{cursor:pointer;color:#aaa;font-size:16px;background:none;border:0}
          button.main{width:100%;padding:8px;border:0;border-radius:8px;font-weight:700;font-size:14px;cursor:pointer;margin:4px 0}
          .on{background:#2c5;color:#000}.off{background:#444;color:#eee}
          label{display:flex;align-items:center;gap:6px;margin:4px 0}
          select{background:#222;color:#eee;border:1px solid #555;border-radius:6px;padding:2px 4px}
          .st{font-size:12px;color:#bbb;white-space:pre-line;margin-top:6px}
          .row{display:flex;gap:6px;margin-top:6px}
          .row button{flex:1;padding:5px;border-radius:6px;border:1px solid #555;background:#222;color:#ddd;cursor:pointer;font-size:12px}
          textarea{width:100%;height:120px;margin-top:6px;font:10px monospace;display:none;background:#000;color:#9f9}
        </style>
        <div class="p">
          <h1>🟡 <span>PacBot</span><button class="x" title="Ocultar (Alt+P)">×</button></h1>
          <button class="main off" id="tg">Bot APAGADO</button>
          <label>Turbo <select id="tb"><option value="1">1x normal</option><option value="1.5">1.5x</option><option value="2">2x</option><option value="3">3x</option></select></label>
          <label><input type="checkbox" id="br"> Ver el cerebro del bot</label>
          <div class="st" id="st"></div>
          <div class="row"><button id="dg">Diagnóstico</button></div>
          <textarea id="ta" readonly></textarea>
        </div>`;
      const $ = (id) => sh.getElementById(id);
      $('tg').onclick = () => setEnabled(!S.enabled);
      $('tb').value = String(Turbo.factor);
      $('tb').onchange = (e) => {
        Turbo.set(e.target.value);
        store.set('turbo', +e.target.value);
      };
      if (!LIKELY_GAME_PAGE) $('tb').disabled = true;
      $('br').checked = S.showBrain;
      $('br').onchange = (e) => {
        S.showBrain = e.target.checked;
        store.set('brain', S.showBrain);
      };
      $('dg').onclick = () => {
        const txt = JSON.stringify(diagnostics(), null, 1);
        const ta = $('ta');
        ta.style.display = 'block';
        ta.value = txt;
        ta.select();
        try {
          navigator.clipboard.writeText(txt);
          $('dg').textContent = '¡Copiado!';
          N.setTimeout(() => ($('dg').textContent = 'Diagnóstico'), 1500);
        } catch (e) {}
      };
      sh.querySelector('.x').onclick = () => this.setShown(false, true);
      // Que las teclas dentro del panel no lleguen al juego
      host.addEventListener('keydown', (e) => e.stopPropagation());
      this.host = host;
      this.$ = $;
    },
    setShown(v, user) {
      if (user) {
        this.forced = v;
        store.set('panel', v);
      }
      if (v && !this.host) this.build();
      if (this.host) {
        if (v && !this.host.isConnected) document.documentElement.appendChild(this.host);
        this.host.style.display = v ? 'block' : 'none';
      }
      this.shown = v;
    },
    update(now) {
      const want = this.forced === false ? false : this.forced === true || !!S.root;
      if (want !== this.shown) this.setShown(want);
      if (!this.shown || now - this.lastUpdate < 200) return;
      this.lastUpdate = now;
      const $ = this.$;
      const tg = $('tg');
      tg.className = 'main ' + (S.enabled ? 'on' : 'off');
      tg.textContent = S.enabled ? 'Bot ENCENDIDO (Alt+B)' : 'Bot APAGADO (Alt+B)';
      const ghosts = (S.ghosts || []).length;
      const lines = S.root
        ? [
            `Juego: detectado ✔  · nivel ~${S.level}`,
            `Pac-Man: ${S.pac ? 'localizado ✔' : 'buscando…'}`,
            `Fantasmas: ${ghosts}  · puntos: ${S.visibleDots}`,
            `Laberinto aprendido: ${Graph.adj.size} casillas`,
            `Modo: ${S.enabled ? S.mode : 'en pausa'}`,
          ]
        : ['Juego: no detectado todavía.', 'Abre Google, busca "pacman"', 'y dale a jugar.'];
      if (S.lastError) lines.push('⚠ ' + S.lastError.split('\n')[0].slice(0, 80));
      $('st').textContent = lines.join('\n');
    },
  };

  function setEnabled(v) {
    S.enabled = v;
    store.set('enabled', v);
    if (!v) releaseKeys();
  }

  function diagnostics() {
    const smallSample = [];
    if (S.root) {
      for (const ch of [...S.root.children].slice(0, 12)) {
        smallSample.push({ tag: ch.tagName, id: ch.id, cls: String(ch.className).slice(0, 40), w: ch.offsetWidth, h: ch.offsetHeight, bp: ch.style.backgroundPosition });
      }
    }
    const canvases = [...document.querySelectorAll('canvas')]
      .filter((c) => c.id !== 'pacbot-overlay')
      .map((c) => ({ id: c.id, w: c.width, h: c.height, cls: String(c.className).slice(0, 40) }));
    const pacGlobals = Object.keys(window).filter((k) => /pac|pcm|game/i.test(k)).slice(0, 20);
    const gp = window.google && window.google.pacman ? Object.keys(window.google.pacman).slice(0, 40) : null;
    return {
      v: 1,
      url: location.href.slice(0, 120),
      frame: window.top === window ? 'top' : 'iframe',
      root: S.root ? { tag: S.root.tagName, id: S.root.id, cls: String(S.root.className).slice(0, 40), children: S.root.childElementCount } : null,
      grid: { ts: S.ts, ox: S.ox, oy: S.oy },
      dots: S.dots.length,
      visibleDots: S.visibleDots,
      energizers: S.dots.filter((d) => d.big).length,
      tiles: Graph.adj.size,
      tracks: [...S.tracks.values()].map((t) => ({ id: t.id, x: Math.round(t.x), y: Math.round(t.y), w: t.w, h: t.h, credits: t.credits, speed: +(t.speed || 0).toFixed(1), tile: t.tile, sig: t.sig.slice(0, 60), pac: t === S.pac, edible: !!t.edible })),
      offsets: [...S.offsets].map(([b, o]) => [b, o.cached, o.ex.length, o.ey.length]),
      normalSigs: S.normalSigs.size,
      frightSigs: S.frightShared.size,
      level: S.level,
      mode: S.mode,
      sample: smallSample,
      canvases,
      pacGlobals,
      googlePacman: gp,
      error: S.lastError || null,
    };
  }

  window.addEventListener(
    'keydown',
    (e) => {
      if (!e.isTrusted || !e.altKey) return;
      if (e.code === 'KeyB') {
        setEnabled(!S.enabled);
        e.preventDefault();
      } else if (e.code === 'KeyP') {
        UI.setShown(!UI.shown, true);
        e.preventDefault();
      }
    },
    true
  );

  // API para pruebas y para la consola
  window.__pacBot = {
    setEnabled,
    setTurbo: (f) => Turbo.set(f),
    state: S,
    graph: Graph,
    diagnostics,
  };

  if (LIKELY_GAME_PAGE) Turbo.set(store.get('turbo', 1));
  N.raf(frame);
})();
