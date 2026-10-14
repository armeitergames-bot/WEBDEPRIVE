# Pac-Man Doodle Pro Bot 🟡👻

Extensión de Chrome/Edge/Brave que hace que el **doodle de Pac-Man de Google**
(el del 30 aniversario, 2010) se juegue solo, como un profesional.

## Cómo instalarla

1. Descarga esta carpeta `pacman-bot/` (o clona el repo).
2. Abre `chrome://extensions` (en Edge: `edge://extensions`).
3. Activa **Modo de desarrollador** (arriba a la derecha).
4. Pulsa **Cargar descomprimida** y elige la carpeta `pacman-bot/`.
5. **Forma más fácil:** pulsa el icono de la extensión (el Pac-Man amarillo en la
   barra de Chrome; si no se ve, búscalo en el icono de la pieza de puzzle 🧩 y
   fíjalo). Se abre una copia del doodle incluida en la extensión y el bot
   empieza a jugar solo.
6. También intenta conectarse al doodle en Google, por ejemplo
   https://www.google.com/logos/2010/pacman10-i.html. Si ya lo tenías abierto,
   **recarga la página**: el bot tiene que cargarse antes que el juego. Si ahí
   aparece el aviso rojo **"PAC-BOT: no conectado"**, usa el icono de la extensión.

Abajo a la derecha aparece un recuadro amarillo **PAC-BOT**:

| Tecla / acción | Qué hace |
| --- | --- |
| `B` o clic en el recuadro | Encender / apagar el bot (puedes retomar tú el control) |
| `R` | Auto-reinicio: cuando hay Game Over, mete otra moneda solo |

No hace falta tocar las flechas: el bot mueve a Pac-Man directamente. Si lo
apagas con `B`, juegas tú con las flechas.

Requiere Chrome 111 o más nuevo.

## Cómo funciona el "cerebro"

No es un bot que mira la pantalla: lee el estado interno del juego y **simula el
futuro**.

1. **Conexión con el juego** (`src/hook.js`). El doodle guarda todo en una
   variable privada. La extensión se carga antes que el juego y pone una trampa
   en `Object.prototype`, así que cuando el juego define `g.insertCoin` el bot
   captura el objeto `g`. Después envuelve `g.moveActors` para decidir justo
   antes de cada tick del juego.
2. **Simulador exacto** (`src/brain.js`). Es una copia línea por línea de la
   lógica original (`pacman10-hp.js`): cómo apunta cada fantasma (Blinky
   persigue, Pinky se adelanta 4 casillas, Inky usa el vector de Blinky, Clyde
   huye de cerca), velocidades por nivel, "Cruise Elroy", túneles, temporizadores
   de dispersión y persecución, la salida de la casa de los fantasmas y hasta el
   generador aleatorio del modo azul (copiamos su semilla). El juego es
   determinista, así que el bot sabe exactamente dónde va a estar cada fantasma.
3. **Búsqueda en árbol**. En cada casilla el bot prueba todas las rutas posibles
   en los próximos ~3,3 segundos (dar la vuelta, cada salida de cada cruce, hasta
   8 cruces de profundidad) y elige la mejor.
4. **Evaluación tipo jugador profesional**:
   - morir es lo peor de todo (con un margen de seguridad extra);
   - "región segura" tipo Voronoi: castiga terminar en zonas donde los fantasmas
     llegan antes que tú (evita quedar acorralado más allá de lo simulado);
   - guarda las pastillas de poder hasta que hay fantasmas cerca y luego se los
     come en cadena (200 → 400 → 800 → 1600);
   - va a por la fruta si le da tiempo;
   - siempre se acerca al punto más cercano para limpiar el nivel rápido.

## Pruebas (opcional, para desarrolladores)

`tools/` contiene un banco de pruebas que corre el doodle en Chromium headless
con el tiempo acelerado, usando la copia pública
[macek/google_pacman](https://github.com/macek/google_pacman):

```bash
git clone https://github.com/macek/google_pacman /tmp/google_pacman
node tools/harness.js /tmp/google_pacman 120   # juega 120 s reales a máxima velocidad
node tools/fidelity.js /tmp/google_pacman      # compara simulador vs. juego real
```

Necesita `playwright` instalado (`npm i -g playwright`).
