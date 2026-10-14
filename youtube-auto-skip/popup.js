const defaults = { enabled: true, remove: true, trustedClick: true };
const count = document.getElementById('count');

chrome.storage.sync.get(defaults, (settings) => {
  for (const key of Object.keys(defaults)) {
    const checkbox = document.getElementById(key);
    checkbox.checked = settings[key];
    checkbox.addEventListener('change', () => {
      chrome.storage.sync.set({ [key]: checkbox.checked });
    });
  }
});

chrome.storage.local.get({ skipped: 0 }, ({ skipped }) => {
  count.textContent = skipped;
});
