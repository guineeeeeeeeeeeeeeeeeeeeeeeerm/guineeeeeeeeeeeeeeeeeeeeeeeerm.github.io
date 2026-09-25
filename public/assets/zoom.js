(function () {
  const closeOverlay = (overlay) => overlay.remove();

  document.querySelectorAll(".image-zoom").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const image = link.querySelector("img");
      if (!image) return;

      document.querySelector(".zoom-overlay")?.remove();
      const overlay = document.createElement("div");
      overlay.className = "zoom-overlay";
      const original = document.createElement("img");
      original.src = link.href;
      original.alt = image.alt;
      overlay.append(original);
      overlay.addEventListener("click", () => closeOverlay(overlay));
      document.body.append(overlay);
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      document.querySelector(".zoom-overlay")?.remove();
    }
  });
})();
