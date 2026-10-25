/**
 * JARVIS Stark Edition - Mission Control HUD, 3D CAD, Virtual Room & Task Board Logic
 */

// ── State Store ──────────────────────────────────────────────────────────────
let starkState = {
  cadMesh: null,
  cadRotation: { x: 25, y: 45 },
  cadZoom: 1.0,
  cadWireframe: false,
  facility: null,
  tasksTimer: null,
  currentStlUrl: null
};

// ── 1. HUD & Proactive Briefing ─────────────────────────────────────────────
async function loadStarkBriefing() {
  const el = document.getElementById('stark-briefing-text');
  if (el) el.innerHTML = '<span style="color:var(--stark-cyan)">Compiling real-time system briefing...</span>';
  try {
    const res = await fetch('/api/v1/stark/briefing');
    const data = await res.json();
    if (data.ok && el) {
      el.innerHTML = `<strong>Status:</strong> ${data.briefing_text}`;
      const battEl = document.getElementById('hud-batt-val');
      if (battEl && data.telemetry.battery) {
        battEl.textContent = `${data.telemetry.battery.percent}% (${data.telemetry.battery.status})`;
      }
      const threatEl = document.getElementById('hud-threat-val');
      if (threatEl) {
        threatEl.textContent = data.threat_level;
      }
    }
  } catch (err) {
    if (el) el.textContent = 'Hardware telemetry nominal. Ready for commands.';
  }
}

async function runStarkProtocol(protoName) {
  const logEl = document.getElementById('stark-protocol-log');
  if (logEl) logEl.innerHTML = `<div style="color:var(--stark-gold)">Executing ${protoName} Protocol...</div>`;
  try {
    const res = await fetch('/api/v1/stark/protocols/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: protoName })
    });
    const data = await res.json();
    if (logEl) {
      let html = `<div style="font-weight:bold;color:#00f0ff;margin-bottom:4px">✓ ${data.protocol} Protocol Engaged</div>`;
      (data.steps || []).forEach(s => {
        html += `<div style="font-size:11px;color:${s.ok ? '#22c55e' : '#ef4444'}">• ${s.step}: ${s.summary}</div>`;
      });
      logEl.innerHTML = html;
    }
  } catch (e) {
    if (logEl) logEl.innerHTML = `<div style="color:#ef4444">Protocol execution error: ${e}</div>`;
  }
}

// ── 2. 3D Text-to-CAD Engine & Viewer ──────────────────────────────────────
async function generateCADModel() {
  const input = document.getElementById('cad-prompt-input');
  const query = input ? input.value : 'phone stand';
  const statusEl = document.getElementById('cad-status-text');
  if (statusEl) statusEl.textContent = 'Generating parametric watertight STL mesh...';

  try {
    const res = await fetch('/api/v1/cad/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query })
    });
    const data = await res.json();
    if (data.ok) {
      if (statusEl) {
        const bb = data.bounding_box_mm;
        statusEl.innerHTML = `
          <strong>${data.filename}</strong> (${data.triangles_count} triangles)<br>
          Dimensions: ${bb.width_mm} × ${bb.length_mm} × ${bb.height_mm} mm | Vol: ${data.volume_cm3} cm³<br>
          <a href="/api/v1/cad/file/${data.filename}" download="${data.filename}" style="color:#00f0ff;text-decoration:underline;">Download Binary STL</a>
        `;
      }
      loadSTLFile(`/api/v1/cad/file/${data.filename}`);
    } else {
      if (statusEl) statusEl.textContent = `CAD Error: ${data.error || 'Failed'}`;
    }
  } catch (e) {
    if (statusEl) statusEl.textContent = `Error: ${e}`;
  }
}

async function loadSTLFile(url) {
  starkState.currentStlUrl = url;
  try {
    const res = await fetch(url);
    const buffer = await res.arrayBuffer();
    parseSTLBuffer(buffer);
    drawCADCanvas();
  } catch (e) {
    console.error('Failed to load STL:', e);
  }
}

function parseSTLBuffer(buffer) {
  const dataView = new DataView(buffer);
  const numTriangles = dataView.getUint32(80, true);
  const triangles = [];

  let offset = 84;
  for (let i = 0; i < Math.min(numTriangles, 3000); i++) {
    // Normal (12 bytes)
    offset += 12;
    // 3 vertices (36 bytes)
    const v1 = [dataView.getFloat32(offset, true), dataView.getFloat32(offset + 4, true), dataView.getFloat32(offset + 8, true)];
    offset += 12;
    const v2 = [dataView.getFloat32(offset, true), dataView.getFloat32(offset + 4, true), dataView.getFloat32(offset + 8, true)];
    offset += 12;
    const v3 = [dataView.getFloat32(offset, true), dataView.getFloat32(offset + 4, true), dataView.getFloat32(offset + 8, true)];
    offset += 12;
    // Attribute byte count (2 bytes)
    offset += 2;

    triangles.push([v1, v2, v3]);
  }
  starkState.cadMesh = triangles;
}

function drawCADCanvas() {
  const canvas = document.getElementById('cad-viewport-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;

  ctx.fillStyle = '#050a14';
  ctx.fillRect(0, 0, w, h);

  // Grid
  ctx.strokeStyle = 'rgba(0, 240, 255, 0.1)';
  ctx.lineWidth = 1;
  for (let x = 0; x < w; x += 25) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
  }
  for (let y = 0; y < h; y += 25) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }

  if (!starkState.cadMesh || starkState.cadMesh.length === 0) {
    ctx.fillStyle = 'rgba(0, 240, 255, 0.5)';
    ctx.font = '12px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('3D CAD VIEWPORT - NO MODEL LOADED', w / 2, h / 2);
    return;
  }

  const rotX = (starkState.cadRotation.x * Math.PI) / 180;
  const rotY = (starkState.cadRotation.y * Math.PI) / 180;
  const zoom = starkState.cadZoom * 1.8;

  function project(vertex) {
    // Rotation around Y
    let x1 = vertex[0] * Math.cos(rotY) + vertex[1] * Math.sin(rotY);
    let y1 = -vertex[0] * Math.sin(rotY) + vertex[1] * Math.cos(rotY);
    let z1 = vertex[2];

    // Rotation around X
    let y2 = y1 * Math.cos(rotX) - z1 * Math.sin(rotX);
    let z2 = y1 * Math.sin(rotX) + z1 * Math.cos(rotX);

    return [
      w / 2 + x1 * zoom,
      h / 2 - z2 * zoom,
      y2
    ];
  }

  // Draw triangles
  ctx.lineWidth = 1;
  starkState.cadMesh.forEach((tri, idx) => {
    const p1 = project(tri[0]);
    const p2 = project(tri[1]);
    const p3 = project(tri[2]);

    ctx.beginPath();
    ctx.moveTo(p1[0], p1[1]);
    ctx.lineTo(p2[0], p2[1]);
    ctx.lineTo(p3[0], p3[1]);
    ctx.closePath();

    if (starkState.cadWireframe) {
      ctx.strokeStyle = 'rgba(0, 240, 255, 0.7)';
      ctx.stroke();
    } else {
      const shade = 30 + ((idx % 30) * 4);
      ctx.fillStyle = `rgba(0, ${shade + 100}, ${shade + 160}, 0.85)`;
      ctx.fill();
      ctx.strokeStyle = 'rgba(0, 240, 255, 0.3)';
      ctx.stroke();
    }
  });
}

function rotateCAD(dx, dy) {
  starkState.cadRotation.y += dx;
  starkState.cadRotation.x += dy;
  drawCADCanvas();
}

function toggleCADWireframe() {
  starkState.cadWireframe = !starkState.cadWireframe;
  drawCADCanvas();
}

// ── 3. Virtual Smart Room (Stark Facility) ──────────────────────────────────
async function loadFacilityState() {
  try {
    const res = await fetch('/api/v1/facility/state');
    const data = await res.json();
    if (data.ok) {
      starkState.facility = data;
      renderFacilitySVG(data);
    }
  } catch (e) {
    console.warn('Facility state error:', e);
  }
}

function renderFacilitySVG(fac) {
  const meterEl = document.getElementById('facility-power-val');
  if (meterEl) meterEl.textContent = `${fac.instantaneous_power_kw} kW`;

  const sceneEl = document.getElementById('facility-scene-val');
  if (sceneEl) sceneEl.textContent = fac.active_scene;

  const devs = fac.devices || {};

  // Arc light node
  const arcLightEl = document.getElementById('svg-arc-light');
  if (arcLightEl && devs.arc_light) {
    arcLightEl.setAttribute('fill', devs.arc_light.power ? devs.arc_light.color : '#334155');
    arcLightEl.setAttribute('filter', devs.arc_light.power ? 'url(#glow)' : 'none');
  }

  // Workshop spot node
  const spotEl = document.getElementById('svg-spot-light');
  if (spotEl && devs.workshop_spot) {
    spotEl.setAttribute('fill', devs.workshop_spot.power ? '#ffffff' : '#334155');
  }

  // Door lock node
  const lockEl = document.getElementById('svg-door-lock');
  if (lockEl && devs.door_lock) {
    lockEl.setAttribute('fill', devs.door_lock.locked ? '#ef4444' : '#22c55e');
  }

  // Thermostat text
  const tempEl = document.getElementById('svg-temp-text');
  if (tempEl && devs.thermostat) {
    tempEl.textContent = `${devs.thermostat.current_temp}°C [${devs.thermostat.mode}]`;
  }
}

async function triggerFacilityScene(scene) {
  try {
    const res = await fetch('/api/v1/facility/scene', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene: scene })
    });
    const data = await res.json();
    if (data.ok) {
      loadFacilityState();
    }
  } catch (e) {
    console.error('Scene trigger error:', e);
  }
}

async function toggleDevice(devId) {
  if (!starkState.facility || !starkState.facility.devices[devId]) return;
  const current = starkState.facility.devices[devId];
  const newPower = (devId === 'door_lock') ? !current.locked : !current.power;
  const updates = (devId === 'door_lock') ? { locked: newPower } : { power: newPower };

  try {
    await fetch('/api/v1/facility/device', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: devId, updates: updates })
    });
    loadFacilityState();
  } catch (e) {
    console.error('Device toggle error:', e);
  }
}

// ── 4. Task Board & Swarm Runner ────────────────────────────────────────────
async function loadTaskBoard() {
  try {
    const res = await fetch('/api/v1/tasks/board');
    const data = await res.json();
    if (data.ok) {
      renderTaskBoard(data.tasks);
    }
  } catch (e) {
    console.warn('Tasks board error:', e);
  }
}

function renderTaskBoard(tasks) {
  const container = document.getElementById('task-board-list');
  if (!container) return;
  if (!tasks || tasks.length === 0) {
    container.innerHTML = '<div style="color:var(--text3);font-size:12px;text-align:center;padding:12px">No background tasks running.</div>';
    return;
  }

  container.innerHTML = tasks.map(t => `
    <div class="task-card ${t.status}">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="font-weight:700;font-size:12px;color:#e2f7ff">${t.title}</span>
        <span style="font-size:10px;text-transform:uppercase;color:${t.status==='done'?'#22c55e':t.status==='running'?'#00f0ff':'#eab308'}">${t.status}</span>
      </div>
      <div style="font-size:11px;color:var(--text2);margin-top:2px">${t.status_message || ''}</div>
      <div class="task-progress-bar">
        <div class="task-progress-fill" style="width:${t.progress}%"></div>
      </div>
    </div>
  `).join('');
}

async function launchSwarmDemo() {
  const btn = document.getElementById('swarm-demo-btn');
  if (btn) btn.disabled = true;
  try {
    await fetch('/api/v1/tasks/swarm/demo', { method: 'POST' });
    if (!starkState.tasksTimer) {
      starkState.tasksTimer = setInterval(loadTaskBoard, 800);
    }
    setTimeout(() => {
      if (btn) btn.disabled = false;
    }, 4000);
  } catch (e) {
    if (btn) btn.disabled = false;
  }
}

// ── 5. Scientific Simulation Lab ────────────────────────────────────────────
async function runSim(simType) {
  const logEl = document.getElementById('sim-output-log');
  const canvas = document.getElementById('sim-graph-canvas');
  if (logEl) logEl.innerHTML = `<span style="color:#00f0ff">Calculating ${simType} numerical integration...</span>`;

  try {
    let url = `/api/v1/sim/${simType}`;
    let body = {};
    if (simType === 'projectile') body = { velocity: 60.0, angle: 45.0, drag: 0.02 };
    if (simType === 'beam') body = { length: 2.5, load: 2000.0 };

    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (logEl) {
      logEl.innerHTML = `<strong>Result:</strong> ${data.summary}`;
    }

    if (canvas && (data.trajectory || data.deflection_curve || data.transient_response)) {
      drawSimChart(canvas, data);
    }
  } catch (e) {
    if (logEl) logEl.textContent = `Simulation error: ${e}`;
  }
}

function drawSimChart(canvas, data) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  ctx.fillStyle = '#050a14';
  ctx.fillRect(0, 0, w, h);

  ctx.strokeStyle = 'rgba(0, 240, 255, 0.2)';
  ctx.strokeRect(20, 10, w - 30, h - 30);

  ctx.beginPath();
  ctx.strokeStyle = '#00f0ff';
  ctx.lineWidth = 2;

  if (data.trajectory) {
    const traj = data.trajectory;
    const maxX = traj[traj.length - 1][0] || 1;
    const maxY = data.metrics.max_height_m || 1;
    traj.forEach((pt, i) => {
      const cx = 20 + (pt[0] / maxX) * (w - 40);
      const cy = (h - 20) - (pt[1] / maxY) * (h - 40);
      if (i === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    });
  } else if (data.deflection_curve) {
    const curve = data.deflection_curve;
    const maxDef = data.metrics.max_tip_deflection_mm || 1;
    curve.forEach((pt, i) => {
      const cx = 20 + (i / curve.length) * (w - 40);
      const cy = 20 + (pt.deflection_mm / maxDef) * (h - 50);
      if (i === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    });
  }
  ctx.stroke();
}

// ── Initialization hook ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Setup mouse drag for 3D CAD canvas
  const cadCanvas = document.getElementById('cad-viewport-canvas');
  if (cadCanvas) {
    let isDragging = false;
    let prevMouse = { x: 0, y: 0 };
    cadCanvas.addEventListener('mousedown', (e) => {
      isDragging = true;
      prevMouse = { x: e.clientX, y: e.clientY };
    });
    window.addEventListener('mouseup', () => { isDragging = false; });
    window.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      const dx = e.clientX - prevMouse.x;
      const dy = e.clientY - prevMouse.y;
      rotateCAD(dx * 0.8, dy * 0.8);
      prevMouse = { x: e.clientX, y: e.clientY };
    });
    // Draw initial blank canvas
    drawCADCanvas();
  }
});

