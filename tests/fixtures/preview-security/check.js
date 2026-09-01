document.querySelector('#module').textContent = 'Module: PASS';
// Test access to the storage API only. Never enumerate or read stored values.
try {
  void window.localStorage;
  document.querySelector('#storage').textContent = 'Storage: FAIL (origin not isolated)';
} catch {
  document.querySelector('#storage').textContent = 'Storage: PASS (opaque origin)';
}
try {
  await fetch('/api/health');
  document.querySelector('#network').textContent = 'Network: FAIL (API reachable)';
} catch {
  document.querySelector('#network').textContent = 'Network: PASS (blocked by CSP)';
}
document.querySelector('#test').addEventListener('click', () => {
  document.querySelector('#click').textContent = 'Interaction: PASS';
});
