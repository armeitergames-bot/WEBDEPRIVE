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

- **Anuncios de vídeo** (antes o durante el vídeo): `content.js` detecta cuando el
  reproductor muestra un anuncio (clase `ad-showing`). Pulsa **"Saltar anuncio"** si
  está disponible y, además, silencia el anuncio y lo adelanta hasta el final, así que
  también se saltan los anuncios que no tienen botón de saltar. Al terminar, el sonido
  se restaura.
- **Anuncios superpuestos** sobre el vídeo: se cierran automáticamente.
- **Banners y anuncios patrocinados** de la página: se ocultan con `hide-ads.css`.

Al desactivar la extensión desde su icono, deja de hacer todo lo anterior.

Si YouTube cambia el nombre de las clases, basta con añadir el nuevo selector a
`SKIP_SELECTORS` en `content.js` o a `hide-ads.css`.
