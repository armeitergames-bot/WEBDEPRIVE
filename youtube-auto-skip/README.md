# YouTube Auto Skip Ads

Extensión para Chrome/Edge/Brave (Manifest V3), para YouTube y YouTube Music, que pulsa automáticamente el botón
**"Saltar anuncio"** de YouTube en cuanto termina el tiempo de espera del anuncio.

## Instalación

1. Descarga esta carpeta (`youtube-auto-skip`).
2. Abre `chrome://extensions` (o `edge://extensions`).
3. Activa el **Modo de desarrollador**.
4. Pulsa **Cargar descomprimida** y selecciona la carpeta `youtube-auto-skip`.
5. Abre YouTube: cuando un anuncio se pueda saltar, se saltará solo.

## Uso

Haz clic en el icono de la extensión para ver el contador y estas opciones:

- **Activada**: enciende o apaga todo.
- **Quitar anuncios por completo**: evita que YouTube cargue los anuncios (recarga la
  página para aplicar). Si YouTube muestra un aviso de bloqueador de anuncios, desactívala.
- **Clic real en "Saltar"**: YouTube ignora los clics automáticos normales, así que la
  extensión hace un clic real con el permiso de depuración. Chrome muestra un aviso
  amarillo ("... ha empezado a depurar este navegador") mientras dura el anuncio.

## Cómo funciona

1. **Quitar los anuncios** (`remove-ads.js`): se ejecuta dentro de la página antes que
   YouTube y borra `adPlacements`, `adSlots` y `playerAds` de la respuesta del
   reproductor, igual que hace uBlock Origin. Así el anuncio ni siquiera se carga.
2. **Saltar los que se cuelen** (`content.js`): algunos anuncios van incrustados en el
   propio vídeo (SSAP) y no se pueden quitar. Cuando el reproductor muestra un anuncio
   (clase `ad-showing`), la extensión:
   - lo silencia y lo reproduce a 16x (no lo adelanta al final, porque eso deja el
     anuncio congelado y con los anuncios incrustados saltaría al final del vídeo);
   - pulsa "Saltar anuncio" en cuanto aparece y, si YouTube ignora el clic, hace un
     clic real (`background.js`, `chrome.debugger`);
   - si el anuncio termina pero se queda en pantalla, vuelve a intentar el clic real;
   - al terminar devuelve el sonido y la velocidad que tenías, también en la API del
     reproductor (`page-bridge.js`), para que YouTube Music no se quede con la
     velocidad del anuncio y acelere la canción.
3. **Anuncios superpuestos y banners**: se cierran o se ocultan (`hide-ads.css`).

Si YouTube cambia el nombre de las clases, basta con añadir el nuevo selector a
`SKIP_SELECTORS` en `content.js` o a `hide-ads.css`.
