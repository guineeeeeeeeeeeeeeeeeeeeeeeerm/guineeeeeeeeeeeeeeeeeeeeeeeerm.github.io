// Closes the language menu when the reader clicks outside it or presses Escape.
document.addEventListener("click", (event) => {
  document.querySelectorAll("details.lang-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.removeAttribute("open");
  });
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  document.querySelectorAll("details.lang-menu[open]").forEach((menu) => menu.removeAttribute("open"));
});
