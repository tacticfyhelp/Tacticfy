// Runs before first paint: apply the saved theme and language direction so the page never flashes.
(function () {
  var theme = null, lang = null;
  try { theme = localStorage.getItem("tacticfy.theme"); lang = localStorage.getItem("tacticfy.lang"); } catch (e) { /* storage blocked */ }
  if (!theme) theme = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.classList.toggle("dark", theme === "dark");
  if (lang === "he") { document.documentElement.lang = "he"; document.documentElement.dir = "rtl"; }
})();
