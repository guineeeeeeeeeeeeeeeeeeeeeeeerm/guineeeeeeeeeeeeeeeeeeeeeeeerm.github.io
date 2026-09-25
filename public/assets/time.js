(() => {
  const pad = (value, width = 2) => String(value).padStart(width, "0");
  const localTime = (date) => {
    // Numeric local getters keep the result fixed-format across Intl.DateTimeFormat locales.
    const year = date.getFullYear();
    if (year < 1 || year > 9999) return null;
    return `${pad(year, 4)}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
      + ` ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };
  document.querySelectorAll("time[datetime]").forEach((element) => {
    const date = new Date(element.dateTime);
    const utcTitle = element.getAttribute("title");
    if (utcTitle) element.title = utcTitle;
    if (!Number.isNaN(date.getTime())) {
      const localized = localTime(date);
      if (localized !== null) element.textContent = localized;
    }
  });
  const post = document.querySelector("article.post");
  const toggle = document.querySelector(".patch-view-toggle");
  const dataElement = document.querySelector("#patch-data");
  if (!post || !toggle || !dataElement) return;
  const regions = [...post.querySelectorAll(".patch-region")];
  const addHistoryEvents = (region) => {
    const history = region.querySelector(".patch-history");
    if (!history) return;
    if (region.dataset.patchEventsBound === "true") return;
    region.dataset.patchEventsBound = "true";
    region.addEventListener("mouseenter", () => {
      if (post.classList.contains("patch-view-on")) history.hidden = false;
    });
    region.addEventListener("mouseleave", () => {
      history.hidden = true;
    });
  };
  const setPatchView = (enabled) => {
    post.classList.toggle("patch-view-on", enabled);
    toggle.setAttribute("aria-pressed", String(enabled));
    regions.forEach((region) => {
      addHistoryEvents(region);
      if (!enabled) {
        const history = region.querySelector(".patch-history");
        if (history) history.hidden = true;
      }
    });
  };
  setPatchView(false);
  toggle.addEventListener("click", () => {
    setPatchView(toggle.getAttribute("aria-pressed") !== "true");
  });
})();
