const checkbox = document.getElementById('enabled');
const count = document.getElementById('count');

chrome.storage.sync.get({ enabled: true }, ({ enabled }) => {
  checkbox.checked = enabled;
});
chrome.storage.local.get({ skipped: 0 }, ({ skipped }) => {
  count.textContent = skipped;
});

checkbox.addEventListener('change', () => {
  chrome.storage.sync.set({ enabled: checkbox.checked });
});
