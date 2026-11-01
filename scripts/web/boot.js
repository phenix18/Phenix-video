"use strict";
buildNav();
$("burger").onclick = () => document.body.classList.toggle("nav-open");
$("scrim").onclick = () => document.body.classList.remove("nav-open");
$("theme").onclick = () => setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
document.addEventListener("keydown", (e) => { if (e.key === "Escape") document.body.classList.remove("nav-open"); });
refreshHealth().then(() => refreshAccounts());
loadHistory();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
const first = (location.hash || "").slice(1);
go(PAGES[first] && first !== "job" ? first : "home");
setInterval(async () => {
  await loadHistory();
  const r = S.jobs.find((j) => j.status === "running" || j.status === "queued");
  setPill(r && S.page !== "job" ? r.id : null);
}, 3000);
