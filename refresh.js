(function () {
  const button = document.getElementById("refresh-button");
  const statusNode = document.getElementById("refresh-status");
  const refreshedNode = document.getElementById("data-refreshed");
  const listNode = document.getElementById("incident-list");
  const emptyNode = document.getElementById("empty-state");
  const endpoint = button ? button.dataset.endpoint : "";

  if (!button || !statusNode || !listNode || !endpoint) return;

  function setStatus(message) {
    statusNode.textContent = message;
  }

  function setLoading(isLoading) {
    button.classList.toggle("is-loading", isLoading);
    button.disabled = isLoading;
  }

  function formatAcres(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "Unknown";
    if (numeric < 1) return String(numeric);
    return Math.round(numeric).toLocaleString();
  }

  function formatContainment(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "Unknown";
    return numeric + "%";
  }

  function formatDate(value) {
    if (!value) return "Unknown";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value.slice(0, 10);
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function formatDateTime(value) {
    const date = value ? new Date(value) : new Date();
    if (Number.isNaN(date.getTime())) return "unknown";
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short"
    });
  }

  function normalize(record) {
    return {
      id: record.UniqueId,
      name: record.Name || "Unnamed incident",
      updated: record.Updated || "",
      started: record.Started || "",
      startedDate: record.StartedDateOnly || (record.Started || "").slice(0, 10),
      county: record.County || "Unknown",
      location: record.Location || "Location unavailable",
      acres: record.AcresBurned,
      containment: record.PercentContained,
      active: Boolean(record.IsActive),
      url: record.Url || "#",
      type: record.Type || ""
    };
  }

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>"']/g, function (char) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char];
    });
  }

  function updateCard(card, incident, refreshedLabel) {
    card.classList.toggle("is-inactive", !incident.active);
    const status = card.querySelector("[data-status]");
    const acres = card.querySelector('[data-field="acres"]');
    const containment = card.querySelector('[data-field="containment"]');
    const refresh = card.querySelector("[data-card-refresh]");
    if (status) status.textContent = incident.active ? "Active" : "No longer active";
    if (acres) acres.textContent = formatAcres(incident.acres);
    if (containment) containment.textContent = formatContainment(incident.containment);
    if (refresh) refresh.textContent = "Live data refreshed " + refreshedLabel;
  }

  function createCard(incident, refreshedLabel) {
    const article = document.createElement("article");
    article.className = "incident-card";
    article.dataset.incidentId = incident.id;
    article.dataset.incidentUrl = incident.url;
    article.innerHTML =
      '<div class="card-topline">' +
        '<p class="eyebrow">' + escapeHtml(incident.county) + '</p>' +
        '<span class="status-pill" data-status>Active</span>' +
      '</div>' +
      '<h3><a href="' + escapeHtml(incident.url) + '">' + escapeHtml(incident.name) + '</a></h3>' +
      '<dl class="metrics">' +
        '<div><dt>Acres</dt><dd data-field="acres">' + formatAcres(incident.acres) + '</dd></div>' +
        '<div><dt>Contained</dt><dd data-field="containment">' + formatContainment(incident.containment) + '</dd></div>' +
        '<div><dt>Started</dt><dd>' + escapeHtml(formatDate(incident.startedDate || incident.started)) + '</dd></div>' +
      '</dl>' +
      '<p class="summary" data-summary>Summary pending next build.</p>' +
      '<p class="location">' + escapeHtml(incident.location) + '</p>' +
      '<p class="card-refresh" data-card-refresh>Live data refreshed ' + escapeHtml(refreshedLabel) + '</p>';
    return article;
  }

  async function fetchLiveIncidents() {
    const response = await fetch(endpoint, { cache: "no-store", mode: "cors" });
    if (!response.ok) {
      throw new Error("CAL FIRE returned HTTP " + response.status);
    }
    const payload = await response.json();
    if (!Array.isArray(payload)) {
      throw new Error("CAL FIRE returned an unexpected response shape.");
    }
    return payload.map(normalize).filter((incident) => incident.type.toLowerCase() === "wildfire");
  }

  async function refresh() {
    setLoading(true);
    try {
      const liveIncidents = await fetchLiveIncidents();
      const refreshedLabel = formatDateTime();
      const liveById = new Map(liveIncidents.map((incident) => [incident.id, incident]));
      const existingCards = Array.from(listNode.querySelectorAll("[data-incident-id]"));

      existingCards.forEach((card) => {
        const live = liveById.get(card.dataset.incidentId);
        if (live) {
          updateCard(card, live, refreshedLabel);
          liveById.delete(card.dataset.incidentId);
        } else {
          card.classList.add("is-inactive");
          const status = card.querySelector("[data-status]");
          const refresh = card.querySelector("[data-card-refresh]");
          if (status) status.textContent = "No longer active";
          if (refresh) refresh.textContent = "Not present in latest live active feed";
        }
      });

      Array.from(liveById.values())
        .sort((a, b) => (Number(b.acres) || 0) - (Number(a.acres) || 0))
        .forEach((incident) => listNode.appendChild(createCard(incident, refreshedLabel)));

      if (emptyNode) emptyNode.hidden = listNode.querySelectorAll("[data-incident-id]").length > 0;
      if (refreshedNode) refreshedNode.textContent = refreshedLabel;
      setStatus("Live CAL FIRE data refreshed in this browser.");
    } catch (error) {
      setStatus("Live refresh failed. This static portfolio site updates live only when the browser can reach CAL FIRE directly.");
      console.error(error);
    } finally {
      button.disabled = false;
      setLoading(false);
    }
  }

  async function checkCors() {
    button.disabled = true;
    try {
      await fetchLiveIncidents();
      button.disabled = false;
      setStatus("Live refresh is available.");
    } catch (error) {
      button.disabled = true;
      button.title = "Browser requests to CAL FIRE appear to be blocked by CORS.";
      setStatus("Live browser refresh is unavailable because CAL FIRE is blocking direct browser requests. The displayed data is from the last deployed build.");
      console.info("Live refresh unavailable", error);
    }
  }

  button.addEventListener("click", refresh);
  checkCors();
})();
