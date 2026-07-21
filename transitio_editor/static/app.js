/* transitio editor frontend: a thin client over the /api endpoints. */
"use strict";

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

const status = (message) => {
  document.getElementById("status").textContent = message || "";
};

async function api(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail || detail;
    } catch (error) {
      /* not JSON */
    }
    throw new Error(`${method} ${path}: ${detail}`);
  }
  return response.json();
}

const map = new maplibregl.Map({
  container: "map",
  style: {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors",
      },
    },
    layers: [{ id: "osm", type: "raster", source: "osm" }],
  },
  center: [24.94, 60.17],
  zoom: 11,
});
map.addControl(new maplibregl.NavigationControl());

let mode = "select";
let snapAvailable = false;
let drawnPoints = []; // [lat, lon]
let previewCoords = []; // [lon, lat] for the preview line
let movingStop = null;
const tripStops = [];

function setMode(next) {
  mode = next;
  for (const id of ["select", "add-stop", "draw"]) {
    document
      .getElementById(`mode-${id}`)
      .classList.toggle("active", `mode-${id}` === `mode-${next}`);
  }
  document
    .getElementById("draw-actions")
    .classList.toggle("hidden", next !== "draw");
  document
    .getElementById("snap-row")
    .classList.toggle("hidden", next !== "draw" || !snapAvailable);
  if (next !== "draw") resetDraw();
  map.getCanvas().style.cursor = next === "select" ? "" : "crosshair";
}
document.getElementById("mode-select").onclick = () => setMode("select");
document.getElementById("mode-add-stop").onclick = () => setMode("add-stop");
document.getElementById("mode-draw").onclick = () => setMode("draw");

function resetDraw() {
  drawnPoints = [];
  previewCoords = [];
  renderPreview();
}

function renderPreview() {
  const source = map.getSource("preview");
  if (source) {
    source.setData({
      type: "Feature",
      geometry: { type: "LineString", coordinates: previewCoords },
    });
  }
}

async function refreshSummary() {
  const summary = await api("GET", "/api/feed");
  snapAvailable = Boolean(summary.snapAvailable);
  const rows = Object.entries(summary.tables)
    .map(([name, count]) => `<tr><td>${esc(name)}</td><td>${esc(count)}</td></tr>`)
    .join("");
  document.getElementById("summary").innerHTML =
    `<div>${esc(summary.source || "new feed")}</div><table>${rows}</table>`;
}

async function refreshLayers(fit) {
  const [stops, shapes] = await Promise.all([
    api("GET", "/api/stops"),
    api("GET", "/api/shapes"),
  ]);
  map.getSource("stops").setData(stops);
  map.getSource("shapes").setData(shapes);
  if (fit && stops.features.length) {
    const bounds = new maplibregl.LngLatBounds();
    for (const feature of stops.features) {
      bounds.extend(feature.geometry.coordinates);
    }
    map.fitBounds(bounds, { padding: 60, maxZoom: 15 });
  }
}

function inspectStop(properties) {
  const inspector = document.getElementById("inspector");
  inspector.classList.remove("hidden");
  // Feed fields are untrusted; build the panel through the DOM, never
  // through markup interpolation.
  inspector.replaceChildren();
  const title = document.createElement("b");
  title.textContent = `stop ${properties.stop_id}`;
  const label = document.createElement("label");
  label.textContent = "name ";
  const nameInput = document.createElement("input");
  nameInput.id = "inspect-name";
  nameInput.value = properties.stop_name || "";
  label.append(nameInput);
  const saveButton = document.createElement("button");
  saveButton.id = "inspect-save";
  saveButton.textContent = "Update";
  const moveButton = document.createElement("button");
  moveButton.id = "inspect-move";
  moveButton.textContent = "Move (click map)";
  inspector.append(title, label, saveButton, moveButton);
  document.getElementById("inspect-save").onclick = async () => {
    await api("PATCH", `/api/stops/${encodeURIComponent(properties.stop_id)}`, {
      stop_name: document.getElementById("inspect-name").value,
    });
    await refreshAll(false);
  };
  document.getElementById("inspect-move").onclick = () => {
    movingStop = properties.stop_id;
    map.getCanvas().style.cursor = "crosshair";
    status(`click the new location of ${movingStop}`);
  };
}

async function handleMapClick(event) {
  const { lng, lat } = event.lngLat;
  try {
    if (movingStop) {
      await api("PATCH", `/api/stops/${encodeURIComponent(movingStop)}`, {
        stop_lat: lat,
        stop_lon: lng,
      });
      movingStop = null;
      status("");
      await refreshAll(false);
      return;
    }
    if (mode === "add-stop") {
      const stopId = prompt("stop_id?");
      if (!stopId) return;
      const name = prompt("stop name?", stopId) || stopId;
      await api("POST", "/api/stops", {
        stop_id: stopId,
        stop_name: name,
        stop_lat: lat,
        stop_lon: lng,
      });
      await refreshAll(false);
      return;
    }
    if (mode === "draw") {
      drawnPoints.push([lat, lng]);
      const snapOn =
        snapAvailable && document.getElementById("snap-toggle").checked;
      if (snapOn && drawnPoints.length >= 2) {
        const feature = await api("POST", "/api/shapes/snap", {
          waypoints: drawnPoints,
        });
        previewCoords = feature.geometry.coordinates;
      } else {
        previewCoords = drawnPoints.map(([a, b]) => [b, a]);
      }
      renderPreview();
    }
  } catch (error) {
    status(error.message);
  }
}

async function finishShape() {
  if (previewCoords.length < 2) {
    status("draw at least two points first");
    return;
  }
  const shapeId = prompt("shape_id?");
  if (!shapeId) return;
  try {
    await api("POST", "/api/shapes", {
      shape_id: shapeId,
      points: previewCoords.map(([lon, lat]) => [lat, lon]),
    });
    resetDraw();
    setMode("select");
    await refreshAll(false);
  } catch (error) {
    status(error.message);
  }
}
document.getElementById("finish-shape").onclick = finishShape;
document.getElementById("cancel-shape").onclick = () => {
  resetDraw();
  setMode("select");
};

function wireForm(id, path, transform) {
  document.getElementById(id).onsubmit = async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.target).entries());
    try {
      await api("POST", path, transform ? transform(data) : data);
      event.target.reset();
      status("");
      await refreshAll(false);
    } catch (error) {
      status(error.message);
    }
  };
}
wireForm("agency-form", "/api/agencies");
wireForm("service-form", "/api/services");
wireForm("route-form", "/api/routes", (data) => ({
  ...data,
  route_type: Number(data.route_type),
  agency_id: data.agency_id || null,
}));
wireForm("trip-form", "/api/trips/frequency", (data) => ({
  ...data,
  headway: Number(data.headway),
  shape_id: data.shape_id || null,
  stops: tripStops.map((entry) => [entry.stopId, entry.offset]),
}));
document.getElementById("clear-trip-stops").onclick = () => {
  tripStops.length = 0;
  renderTripStops();
};

function renderTripStops() {
  const list = document.getElementById("trip-stops");
  list.replaceChildren();
  tripStops.forEach((entry, index) => {
    const item = document.createElement("li");
    item.textContent = `${entry.stopId} +`;
    const offset = document.createElement("input");
    offset.type = "number";
    offset.value = entry.offset;
    offset.style.width = "70px";
    offset.onchange = () => {
      tripStops[index].offset = Number(offset.value) || 0;
    };
    item.append(offset, "s");
    list.append(item);
  });
}

document.getElementById("save").onclick = async () => {
  const result = document.getElementById("save-result");
  result.textContent = "saving…";
  try {
    const saved = await api("POST", "/api/save", {});
    const counts = saved.report.notices.reduce((acc, notice) => {
      acc[notice.severity] = (acc[notice.severity] || 0) + 1;
      return acc;
    }, {});
    const outcome = document.createElement("span");
    outcome.className = saved.clean ? "clean" : "dirty";
    outcome.textContent = saved.clean
      ? "saved — no errors"
      : `saved with ${counts.ERROR || 0} errors, ${counts.WARNING || 0} warnings`;
    result.replaceChildren(outcome);
    await refreshSummary();
  } catch (error) {
    const outcome = document.createElement("span");
    outcome.className = "dirty";
    outcome.textContent = error.message;
    result.replaceChildren(outcome);
  }
};

map.on("load", async () => {
  map.addSource("stops", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
  map.addSource("shapes", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
  map.addSource("preview", {
    type: "geojson",
    data: { type: "Feature", geometry: { type: "LineString", coordinates: [] } },
  });
  map.addLayer({
    id: "shapes",
    type: "line",
    source: "shapes",
    paint: { "line-color": "#35507a", "line-width": 3, "line-opacity": 0.8 },
  });
  map.addLayer({
    id: "preview",
    type: "line",
    source: "preview",
    paint: {
      "line-color": "#c0392b",
      "line-width": 3,
      "line-dasharray": [2, 1],
    },
  });
  map.addLayer({
    id: "stops",
    type: "circle",
    source: "stops",
    paint: {
      "circle-radius": 6,
      "circle-color": "#e67e22",
      "circle-stroke-color": "#fff",
      "circle-stroke-width": 1.5,
    },
  });

  map.on("click", "stops", (event) => {
    if (movingStop) return; // fall through to the map handler
    const properties = event.features[0].properties;
    if (mode === "select") {
      const open = document.querySelector("#trip-form");
      if (open && open.closest("details").open) {
        tripStops.push({
          stopId: properties.stop_id,
          offset: tripStops.length * 120,
        });
        renderTripStops();
      } else {
        inspectStop(properties);
      }
      event.preventDefault();
    }
  });
  map.on("click", (event) => {
    if (event.defaultPrevented) return;
    handleMapClick(event);
  });

  try {
    await refreshSummary();
    await refreshLayers(true);
  } catch (error) {
    status(error.message);
  }
});

async function refreshAll(fit) {
  await refreshSummary();
  await refreshLayers(fit);
}
