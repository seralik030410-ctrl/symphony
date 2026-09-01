// Runs before styles/React so a saved dark preference does not flash a light canvas.
(() => {
  let preference = "system";
  try { preference = localStorage.getItem("symphony.theme") || "system"; } catch { /* storage is optional */ }
  const dark = preference === "dark" || (preference !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#14171b" : "#f3f5f7");
})();
