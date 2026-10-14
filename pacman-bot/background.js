// Al pulsar el icono de la extensión, abre el doodle incluido (con el bot).
chrome.action.onClicked.addListener(function () {
  chrome.tabs.create({ url: chrome.runtime.getURL('game/index.html') });
});
