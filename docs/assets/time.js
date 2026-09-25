(() => {
  const pad = (value, width = 2) => String(value).padStart(width, "0");
  const localTime = (date) => {
    // Numeric local getters keep the result fixed-format across Intl.DateTimeFormat locales.
    const year = date.getFullYear();
    if (year < 1 || year > 9999) return null;
    return `${pad(year, 4)}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
      + ` ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };
  const utcLabel = (value) => `${value.slice(0, 16).replace("T", " ")} UTC`;
  const localizeTime = (element) => {
    const date = new Date(element.dateTime);
    const utcTitle = element.getAttribute("title");
    if (utcTitle) element.title = utcTitle;
    if (!Number.isNaN(date.getTime())) {
      const localized = localTime(date);
      if (localized !== null) element.textContent = localized;
    }
  };
  document.querySelectorAll("time[datetime]").forEach(localizeTime);
  const post = document.querySelector("article.post");
  const toggle = document.querySelector(".patch-view-toggle");
  const dataElement = document.querySelector("#patch-data");
  if (!post || !toggle || !dataElement) return;
  const regions = [...post.querySelectorAll(".patch-region")];
  const regionData = new Map((JSON.parse(dataElement.textContent || "{}").regions || []).map((region) => [region.id, region]));
  const addHistoryEvents = (region) => {
    let history = region.querySelector(".patch-history");
    if (!history) {
      const info = regionData.get(region.dataset.patchRegion);
      if (!info) return;
      history = document.createElement("span");
      history.className = "patch-history";
      history.hidden = true;
      const heading = document.createElement("strong");
      heading.textContent = "패치 이력";
      history.append(heading);
      const list = document.createElement("ul");
      (info.patches || []).forEach((patch) => {
        const item = document.createElement("li");
        const time = document.createElement("time");
        time.dateTime = patch.at;
        time.title = utcLabel(patch.at);
        time.textContent = utcLabel(patch.at);
        localizeTime(time);
        item.append(time, ` — ${patch.why} — ${patch.op} — 이전 글자: ${patch.previous_text}`);
        list.append(item);
      });
      history.append(list);
      region.append(history);
    }
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
