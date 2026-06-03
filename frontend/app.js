/* Balloon Flight Planner - dashboard. Map + reachable-airspace list + LLM answer,
   driven by POST /api/query. Click sets takeoff; the Morning/Evening toggle picks
   the window; the box is the optional flight question. */

const map = L.map("map");
// Start zoomed to the Gros de Vaud (Lausanne -> Yverdon-les-Bains).
map.fitBounds([[46.50, 6.45], [46.82, 7.00]]);
L.tileLayer(
  "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/{z}/{x}/{y}.jpeg",
  { attribution: "© swisstopo", maxZoom: 18 }
).addTo(map);

const overlay = L.layerGroup().addTo(map);
const zoneLayers = {};            // id -> leaflet layer (for list/click -> map)
const notamLayers = {};
let takeoff = null, marker = null, mode = "morning";

const $ = (id) => document.getElementById(id);

function fmtAlt(b) {
  if (!b) return "GND";
  if (b.raw && /GND|SFC/i.test(b.raw)) return "GND";
  if (b.amsl_m != null) return Math.round(b.amsl_m) + " m";
  return b.raw || "—";
}
const band = (lo, up) => `${fmtAlt(lo)}–${fmtAlt(up)} AMSL`;
const dist = (km) => (km === 0 ? "Within zone" : km + " km");

map.on("click", (e) => setTakeoff(e.latlng.lat, e.latlng.lng));

$("toggle").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  mode = b.dataset.mode;
  document.querySelectorAll("#toggle button").forEach((x) => x.classList.toggle("on", x === b));
  if (takeoff) run(false);
});

$("plan").addEventListener("click", () => takeoff && run(true));

const TK_ICON = L.divIcon({ className: "tk", html: '<div class="tk-ring"></div>',
                            iconSize: [20, 20], iconAnchor: [10, 10] });

function setTakeoff(lat, lon) {
  takeoff = { lat, lon };
  if (marker) marker.remove();
  marker = L.marker([lat, lon], { icon: TK_ICON }).addTo(map).bindPopup("Takeoff");
  $("plan").disabled = false;
  run(false);
}

async function run(plan) {
  if (plan) { $("plan").disabled = true; $("plan").textContent = "Planning..."; }
  try {
    const r = await fetch("/api/query", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...takeoff, mode, plan, question: $("question").value || null }),
    }).then((x) => x.json());
    renderMap(r);
    renderList(r.context);
    renderWarning(r.dabs);
    if (plan) renderAnswer(r.llm);
  } catch (err) {
    $("answer").innerHTML = "<span class='hint'>Request failed: " + err + "</span>";
  } finally {
    $("plan").disabled = false; $("plan").textContent = "Plan flight";
  }
}

function zoneStyle(z) {
  const s = z.status || "";
  let color = "#2266cc", fill = 0.12, dash = null;          // controlled default
  if (s.startsWith("ACTIVE")) { color = "#e00000"; fill = 0.32; }
  else if (s.includes("HX")) { color = "#f08000"; fill = 0.18; }
  else if (s.includes("inactive")) { color = "#888888"; fill = 0.05; dash = "4"; }
  else if (["R", "Q"].includes(z.kind)) { color = "#e00000"; fill = 0.22; }
  return { color, weight: 1, fillOpacity: fill, dashArray: dash };
}

function statusTag(s) {
  if (s.startsWith("ACTIVE")) return ["ACTIVE", "t-active"];
  if (s.includes("HX")) return ["HX", "t-hx"];
  if (s.includes("inactive")) return ["INACTIVE", "t-off"];
  return ["PERMANENT", "t-ok"];
}

function renderMap(r) {
  overlay.clearLayers();
  for (const k in zoneLayers) delete zoneLayers[k];
  for (const k in notamLayers) delete notamLayers[k];
  for (const z of r.context.in_reach) {
    const lyr = L.geoJSON(z.geometry, { style: zoneStyle(z) })
      .bindPopup(`<b>${z.name}</b><br>${z.kind} · class ${z.asclass || "—"}<br>${band(z.lower, z.upper)}<br>${z.status}<br>${dist(z.distance_km)}`);
    lyr.addTo(overlay); zoneLayers[z.id] = lyr;
  }
  for (const o of r.context.notam_obstacles) {
    const [lon, lat] = o.centre;
    const c = L.circle([lat, lon], { radius: o.radius_km * 1000, color: "#8e44ad", weight: 1, fillOpacity: 0.15 })
      .bindPopup(`<b>NOTAM</b> (${o.live ? "live" : "inactive"})<br>${band(o.lower, o.upper)}<br>${o.text}`);
    c.addTo(overlay); notamLayers[o.id] = c;
  }
}

function renderList(ctx) {
  const strip = (color, code, nm, tag, tagCls, data, onclick) => {
    const d = document.createElement("div");
    d.className = "strip"; d.style.borderLeftColor = color;
    d.innerHTML = `<div><span class="code">${code}</span> <span class="nm">${nm}</span></div>` +
      `<span class="tag ${tagCls}">${tag}</span><div class="data">${data}</div>`;
    d.onclick = onclick;
    return d;
  };
  const list = $("ctxlist"); list.innerHTML = "";
  for (const z of ctx.in_reach) {
    const [tag, cls] = statusTag(z.status);
    list.appendChild(strip(zoneStyle(z).color, z.kind, z.name, tag, cls,
      `<b>${band(z.lower, z.upper)}</b> · ${dist(z.distance_km)} · class ${z.asclass || "—"}`,
      () => { const l = zoneLayers[z.id]; if (l) { map.fitBounds(l.getBounds(), { maxZoom: 11 }); l.openPopup(); } }));
  }
  for (const o of ctx.notam_obstacles) {
    list.appendChild(strip("#8e44ad", "NOTAM", o.aip || o.applies, o.live ? "LIVE" : "INACTIVE",
      o.live ? "t-active" : "t-off",
      `<b>${band(o.lower, o.upper)}</b> · ${o.text.slice(0, 52)}`,
      () => { const c = notamLayers[o.id]; if (c) { map.setView(c.getLatLng(), 12); c.openPopup(); } }));
  }
}

function renderWarning(dabs) {
  const el = $("warning");
  if (dabs && dabs.warning) { el.style.display = "block"; el.textContent = dabs.warning; }
  else { el.style.display = "none"; }
}

function renderAnswer(llm) {
  if (!llm) return;
  const el = $("answer"); el.classList.remove("hint");
  if (llm.error) {
    el.classList.add("hint"); el.textContent = "LLM unavailable: " + llm.error;
  } else {
    const html = marked.parse(llm.answer)
      .replace(/\[([^\[\]\n]{1,48})\]/g, '<span class="cite">[$1]</span>');
    el.innerHTML = html;
  }
  $("sources").innerHTML = (llm.sources || [])
    .map((s) => `<li><b>${s.name}</b> ${s.type}</li>`).join("");
}
