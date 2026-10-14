# YouTube Auto Skip Ads

Extensión para Chrome/Edge/Brave (Manifest V3) que pulsa automáticamente el botón
**"Saltar anuncio"** de YouTube en cuanto termina el tiempo de espera del anuncio.

## Instalación

1. Descarga esta carpeta (`youtube-auto-skip`).
2. Abre `chrome://extensions` (o `edge://extensions`).
3. Activa el **Modo de desarrollador**.
4. Pulsa **Cargar descomprimida** y selecciona la carpeta `youtube-auto-skip`.
5. Abre YouTube: cuando un anuncio se pueda saltar, se saltará solo.

## Uso

Haz clic en el icono de la extensión para activarla/desactivarla y ver cuántos
anuncios se han saltado.

## Cómo funciona

`content.js` vigila el reproductor de YouTube. Mientras se muestra un anuncio
(clase `ad-showing`), busca el botón de saltar y lo pulsa en cuanto está visible,
es decir, cuando acaba la cuenta atrás. Los anuncios que no se pueden saltar se
reproducen con normalidad.

Si YouTube cambia el nombre de las clases del botón, basta con añadir el nuevo
selector a `SKIP_SELECTORS` en `content.js`.
