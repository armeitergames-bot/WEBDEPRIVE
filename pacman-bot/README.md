# 🟡 PacBot: bot para el Pac-Man de Google

Una extensión de Chrome que **juega sola** al Pac-Man de Google: esquiva a los fantasmas, se come las pastillas grandes cuando la persiguen, caza a los fantasmas asustados y pasa nivel tras nivel. Tiene **modo turbo** para acelerar el juego.

## Cómo instalarla (2 minutos)

1. Descarga el repositorio: botón verde **Code → Download ZIP** y descomprímelo.
2. En Chrome, abre `chrome://extensions`.
3. Activa el **Modo de desarrollador** (arriba a la derecha).
4. Pulsa **Cargar descomprimida** y elige la carpeta **`pacman-bot/extension`**.
5. Listo. Debe salir "PacBot" en la lista.

## Cómo usarla

1. Entra a Google, busca **pacman** y dale a jugar (o abre <https://www.google.com/logos/2010/pacman10-i.html>).
2. Abajo a la derecha aparece el panel **PacBot**.
3. Pulsa **Bot ENCENDIDO** o usa **Alt+B**. Para ocultar o mostrar el panel, usa **Alt+P**.
4. Elige el turbo: 1x, 1.5x, 2x o 3x.
5. Marca **Ver el cerebro del bot** para ver lo que piensa: el camino que va a seguir (verde), las zonas peligrosas (rojo) y los pasillos que ya aprendió.

> Al empezar, el bot pasa unos segundos **calibrando**: mueve a Pac-Man para descubrir quién es quién y cómo es el laberinto. Después juega solo.

## Cómo funciona

El código del juego de Google está ofuscado, así que el bot **no lo lee**. Mira la pantalla como lo haría una persona:

- **Ve el juego:** encuentra los puntos, el tamaño de las casillas, a Pac-Man (el que se come los puntos) y a los fantasmas.
- **Aprende el laberinto:** une los puntos en pasillos y suma por donde ve pasar a los personajes. Si Pac-Man choca con una pared que creía pasillo, lo apunta y no lo vuelve a intentar.
- **Piensa cada movimiento:** calcula cuánto tarda cada fantasma en llegar a cada casilla. Solo va por caminos donde llega antes que ellos y evita meterse en callejones donde lo pueden encerrar.
- **Ataca:** si los fantasmas están asustados y le da tiempo de alcanzarlos, va a por ellos. Las pastillas grandes las guarda para cuando lo están persiguiendo.
- **Turbo:** acelera el reloj de la página para que el juego vaya más rápido.

## Si algo no funciona

Desde donde se programó el bot no se podía abrir Google, así que se probó con un Pac-Man de prueba hecho igual que el de Google (`test/mock-pacman.html`). Si en el juego real falla algo:

1. Pulsa **Diagnóstico** en el panel. Se copia un texto.
2. Pégalo en un issue de este repo o mándaselo a Claude, y se ajusta.

## Para programadores

```bash
cd pacman-bot
npm install          # instala Playwright
npm test             # el bot juega 60 s al Pac-Man de prueba
node test/run.mjs 120 2   # 120 s con turbo 2x
```

En la consola de la página tienes `window.__pacBot` para revisar el estado (`__pacBot.diagnostics()`).
