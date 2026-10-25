const vscode = acquireVsCodeApi();

let msgs = null;
let promptInput = null;
let sendBtn = null;
let modeSelect = null;
let statusDot = null;
let micBtn = null;

let isGenerating = false;
let isListening = false;
let activeTurnId = null;
let activeAssistantDiv = null;
let activeTokenAccum = '';
let currentAttachedFilePath = null;
let attachWrap = null;
let attachBtn = null;

function renderAttachPill(name) {
  if (!attachWrap) return;
  if (!name) {
    attachWrap.innerHTML = '';
    return;
  }
  attachWrap.innerHTML = '<div class="attach-pill">📎 <span>' + name + '</span> <span class="remove-attach" title="Remove attachment">✕</span></div>';
  const removeBtn = attachWrap.querySelector('.remove-attach');
  if (removeBtn) {
    removeBtn.addEventListener('click', () => {
      currentAttachedFilePath = null;
      renderAttachPill(null);
    });
  }
}

function insertContext(ctx) {
  if (!promptInput) return;
  promptInput.value += (promptInput.value ? ' ' : '') + ctx + ' ';
  promptInput.focus();
}

function formatTextChunk(str) {
  let res = str.replace(/\n/g, '<br>');
  // Format markdown images: ![alt](url)
  res = res.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (m, alt, url) => {
    let fullUrl = url;
    if (fullUrl.startsWith('/')) {
      fullUrl = 'http://127.0.0.1:8765' + fullUrl;
    }
    return '<img src="' + fullUrl + '" alt="' + (alt || '') + '" style="max-width:100%;border-radius:6px;margin:8px 0;display:block;box-shadow:0 2px 8px rgba(0,0,0,0.3);">';
  });
  return res;
}

function renderMarkdown(text) {
  if (!text) return '';
  const raw = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const parts = raw.split('```');
  if (parts.length > 1) {
    let res = '';
    for (let i = 0; i < parts.length; i++) {
      if (i % 2 === 1) {
        const code = parts[i].trim();
        const esc = encodeURIComponent(code);
        res += '<pre><code>' + code + '</code><div class="code-actions">' +
          '<button class="code-btn" data-action="copy" data-code="' + esc + '">📋 Copy</button>' +
          '<button class="code-btn" data-action="insert" data-code="' + esc + '">Insert</button>' +
          '<button class="code-btn" data-action="apply" data-code="' + esc + '">Apply</button>' +
          '<button class="code-btn" data-action="diff" data-code="' + esc + '">Diff</button>' +
          '<button class="code-btn" data-action="run" data-code="' + esc + '">Run</button>' +
          '</div></pre>';
      } else {
        res += formatTextChunk(parts[i]);
      }
    }
    return res;
  }
  return formatTextChunk(raw);
}

function send() {
  if (isGenerating) {
    vscode.postMessage({ type: 'stop', turn_id: activeTurnId });
    setGenerating(false);
    return;
  }

  const text = promptInput ? promptInput.value.trim() : '';
  if (!text) return;
  promptInput.value = '';

  const turnId = 'turn_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
  activeTurnId = turnId;

  if (msgs) {
    const userDiv = document.createElement('div');
    userDiv.className = 'msg user';
    userDiv.textContent = text;
    msgs.appendChild(userDiv);

    const assistantDiv = document.createElement('div');
    assistantDiv.className = 'msg assistant';
    assistantDiv.dataset.turnId = turnId;
    assistantDiv.innerHTML = '<span class="caret"></span>';
    msgs.appendChild(assistantDiv);
    msgs.scrollTop = msgs.scrollHeight;

    activeAssistantDiv = assistantDiv;
  }
  activeTokenAccum = '';
  setGenerating(true);

  const mode = modeSelect ? modeSelect.value : 'chat';
  const sentFilePath = currentAttachedFilePath;
  currentAttachedFilePath = null;
  renderAttachPill(null);

  vscode.postMessage({
    type: 'sendMessage',
    message: text,
    text: text,
    mode: mode,
    turn_id: turnId,
    file_path: sentFilePath
  });
}

function setGenerating(state) {
  isGenerating = state;
  if (sendBtn) {
    if (state) {
      sendBtn.textContent = 'Stop';
      sendBtn.className = 'stop';
    } else {
      sendBtn.textContent = 'Send';
      sendBtn.className = 'send';
    }
  }
  if (!state) {
    const carets = document.querySelectorAll('.caret');
    carets.forEach(c => c.remove());
  }
}

function toggleMic() {
  vscode.postMessage({ type: 'toggleVoice' });
}

function setVoiceVisualState(state) {
  if (!micBtn) return;
  micBtn.className = 'mic-btn ' + (state || 'off');
  if (state === 'off') {
    micBtn.title = 'JARVIS Voice: OFF (Click to turn ON, Ctrl+Alt+V)';
    micBtn.textContent = '🎤';
  } else if (state === 'listening') {
    micBtn.title = 'JARVIS Voice: Listening (Click to mute, Ctrl+Alt+M)';
    micBtn.textContent = '🎙️';
  } else if (state === 'hearing') {
    micBtn.title = 'Hearing speech...';
    micBtn.textContent = '🔴';
  } else if (state === 'thinking') {
    micBtn.title = 'Processing speech...';
    micBtn.textContent = '⏳';
  } else if (state === 'speaking') {
    micBtn.title = 'JARVIS is speaking...';
    micBtn.textContent = '🔊';
  }
}

// ── DOM Initialization with Safe try/catch ─────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  try {
    msgs = document.getElementById('messages');
    promptInput = document.getElementById('prompt');
    sendBtn = document.getElementById('sendBtn');
    modeSelect = document.getElementById('mode');
    statusDot = document.getElementById('statusDot');
    micBtn = document.getElementById('micBtn');
    attachWrap = document.getElementById('attachWrap');
    attachBtn = document.getElementById('attachBtn');

    if (sendBtn) {
      sendBtn.addEventListener('click', send);
    }
    if (attachBtn) {
      attachBtn.addEventListener('click', () => {
        vscode.postMessage({ type: 'pickAttachment' });
      });
    }
    if (promptInput) {
      promptInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          send();
        }
      });
    }
    if (micBtn) {
      micBtn.addEventListener('click', toggleMic);
    }

    // Event delegation for chips, code buttons, and settings buttons
    document.addEventListener('click', (e) => {
      const chip = e.target.closest('.chip');
      if (chip && chip.dataset.ctx) {
        insertContext(chip.dataset.ctx);
        return;
      }

      const btn = e.target.closest('button[data-action]');
      if (btn) {
        const action = btn.dataset.action;
        const code = btn.dataset.code ? decodeURIComponent(btn.dataset.code) : '';
        if (action === 'copy') {
          vscode.postMessage({ type: 'copy', text: code });
        } else if (action === 'insert') {
          vscode.postMessage({ type: 'insertAtCursor', text: code });
        } else if (action === 'apply') {
          vscode.postMessage({ type: 'applyToFile', text: code });
        } else if (action === 'diff') {
          vscode.postMessage({ type: 'openDiff', text: code });
        } else if (action === 'run') {
          vscode.postMessage({ type: 'runInTerminal', text: code });
        } else if (action === 'openSettings') {
          vscode.postMessage({ type: 'openSettings' });
        } else if (action === 'startBackend') {
          vscode.postMessage({ type: 'startBackend' });
        } else if (action === 'cancelAction') {
          const actId = btn.dataset.actionId;
          const cardId = btn.dataset.cardId;
          const card = document.getElementById(cardId);
          if (card) {
            card.dataset.cancelled = "true";
            card.innerHTML = '<div style="color:var(--green);text-align:center;padding:8px;">✓ Action Cancelled Successfully</div>';
          }
          vscode.postMessage({ type: 'cancelAction', action_id: actId });
        } else if (action === 'confirmAction') {
          const actId = btn.dataset.actionId;
          const cardId = btn.dataset.cardId;
          const card = document.getElementById(cardId);
          if (card) {
            card.dataset.cancelled = "true";
            card.innerHTML = '<div style="color:var(--orange);text-align:center;padding:8px;">⏳ Executing action...</div>';
          }
          vscode.postMessage({ type: 'confirmAction', action_id: actId });
        }
      }
    });
  } catch (err) {
    vscode.postMessage({ type: 'initError', error: err.stack || err.message });
  }
});

// ── Window Message Dispatcher ──────────────────────────────────────────
window.addEventListener('message', (event) => {
  const message = event.data;
  if (!message) return;

  // Discard older turns if turn_id doesn't match, but always clear generating state on completion/error
  if (message.turn_id && message.turn_id !== activeTurnId) {
    if (message.type === 'streamDone' || message.type === 'streamError') {
      setGenerating(false);
    }
    return;
  }

  const targetDiv = (message.turn_id && document.querySelector('.msg.assistant[data-turn-id="' + message.turn_id + '"]')) || activeAssistantDiv;

  if (message.type === 'streamToken') {
    activeTokenAccum += (message.token || message.text || '');
    if (targetDiv) {
      targetDiv.innerHTML = renderMarkdown(activeTokenAccum) + '<span class="caret"></span>';
      if (msgs) msgs.scrollTop = msgs.scrollHeight;
    }
  } else if (message.type === 'streamTool') {
    if (targetDiv) {
      const step = document.createElement('div');
      step.className = 'timeline-step';
      step.textContent = '⚙ ' + message.tool + (message.input ? ': ' + JSON.stringify(message.input).slice(0, 40) : '');
      targetDiv.insertBefore(step, targetDiv.firstChild);
    }
  } else if (message.type === 'streamToolResult') {
    const step = targetDiv && targetDiv.querySelector('.timeline-step:last-of-type');
    if (step) {
      step.classList.add('done');
      step.textContent += ' ✓';
    }
  } else if (message.type === 'weather_card') {
    if (targetDiv) renderWeatherCard(targetDiv, message.data);
  } else if (message.type === 'news_card') {
    if (targetDiv) renderNewsCard(targetDiv, message.data);
  } else if (message.type === 'search_card') {
    if (targetDiv) renderSearchCard(targetDiv, message.data);
  } else if (message.type === 'pc_status_card') {
    if (targetDiv) renderPcStatusCard(targetDiv, message.data);
  } else if (message.type === 'action_countdown') {
    if (targetDiv) renderActionCountdownCard(targetDiv, message.data);
  } else if (message.type === 'screenshot_card') {
    if (targetDiv) renderScreenshotCard(targetDiv, message.data);
  } else if (message.type === 'streamDone') {
    setGenerating(false);
    if (targetDiv) {
      const isBn = message.lang === 'BN' || /[\u0980-\u09FF]/.test(activeTokenAccum);
      const badge = '<div style="margin-top:6px;"><span class="lang-badge ' + (isBn ? 'bn' : 'en') + '">' + (isBn ? 'BN' : 'EN') + '</span></div>';
      targetDiv.innerHTML = renderMarkdown(activeTokenAccum) + badge;
    }
  } else if (message.type === 'streamError') {
    setGenerating(false);
    if (targetDiv) {
      targetDiv.innerHTML = '<span style="color:var(--red)">' + message.error + '</span>';
      let actionsHtml = '<div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">';
      if (message.isBackendDown) {
        actionsHtml += '<button class="code-btn" data-action="startBackend">🚀 Start JARVIS Backend</button>';
      }
      if (message.showSettings) {
        actionsHtml += '<button class="code-btn" data-action="openSettings">⚙ Open Settings</button>';
      }
      actionsHtml += '</div>';
      targetDiv.innerHTML += actionsHtml;
    }
  } else if (message.type === 'voiceState') {
    setVoiceVisualState(message.state);
  } else if (message.type === 'voiceStatus') {
    if (message.status === 'listening') {
      setVoiceVisualState('listening');
    } else if (message.status === 'processing') {
      setVoiceVisualState('thinking');
    } else if (message.status === 'idle') {
      setVoiceVisualState('off');
    }
  } else if (message.type === 'voiceTranscript') {
    setVoiceVisualState('listening');
    if (promptInput) {
      promptInput.value = message.text;
      send();
    }
  } else if (message.type === 'statusUpdate') {
    if (statusDot) {
      if (message.online) {
        statusDot.className = 'status-dot';
        statusDot.title = 'Online: ' + (message.model || '');
      } else {
        statusDot.className = 'status-dot offline';
        statusDot.title = 'Offline';
      }
    }
  } else if (message.type === 'attachmentReady') {
    currentAttachedFilePath = message.filePath;
    renderAttachPill(message.name);
  } else if (message.type === 'setAttachmentAndPrompt') {
    currentAttachedFilePath = message.filePath;
    renderAttachPill(message.name);
    if (promptInput) {
      promptInput.value = message.prompt || 'Explain this file';
      send();
    }
  }
});

function renderWeatherCard(container, data) {
  if (!container || !data || !data.current) return;
  const curr = data.current;
  const daily = data.daily || [];
  let html = '<div class="weather-card"><div class="weather-header"><div><div class="weather-city">' +
    (data.location || 'Weather') + '</div><div style="font-size:11px;color:var(--muted)">' + (curr.condition || '') +
    '</div></div><div class="weather-temp">' + (curr.icon || '☀️') + ' ' + Math.round(curr.temperature) + '°C</div></div>' +
    '<div class="weather-metrics"><span>Feels: ' + Math.round(curr.feels_like) + '°C</span><span>Humidity: ' + curr.humidity + '%</span><span>Wind: ' + curr.wind_speed + ' km/h</span></div>';
  if (daily.length > 0) {
    html += '<div class="weather-forecast">';
    daily.forEach(d => {
      const dt = (d.date || '').split('-').slice(1).join('/');
      html += '<div class="forecast-day"><div>' + dt + '</div><div>' + (d.icon || '☀️') + '</div><div>' + Math.round(d.max_temp) + '°/' + Math.round(d.min_temp) + '°</div></div>';
    });
    html += '</div>';
  }
  html += '</div>';
  container.insertAdjacentHTML('beforeend', html);
}

function renderNewsCard(container, data) {
  if (!container || !data || !data.articles) return;
  let html = '<div class="news-card"><div class="news-card-title">📰 Headlines (' + (data.topic || 'World') + ')</div>';
  data.articles.forEach(a => {
    html += '<div class="news-item"><span class="news-source-badge">' + (a.source || '') + '</span> ' +
      '<a class="news-link" href="' + (a.link || '#') + '">' + (a.title || '') + '</a></div>';
  });
  html += '</div>';
  container.insertAdjacentHTML('beforeend', html);
}

function renderSearchCard(container, data) {
  if (!container || !data || !data.sources || !data.sources.length) return;
  let html = '<div class="search-sources-card"><div class="sources-title">🌐 Sources:</div><div class="source-chips">';
  data.sources.forEach(s => {
    html += '<a class="source-chip" href="' + (s.url || '#') + '"><span class="chip-domain">' + (s.domain || 'link') + '</span> <span>' + (s.title || '').substring(0, 24) + '...</span></a>';
  });
  html += '</div></div>';
  container.insertAdjacentHTML('beforeend', html);
}

function renderPcStatusCard(container, data) {
  if (!container || !data) return;
  const cpu = data.cpu_percent || 0;
  const ram = data.ram_percent || 0;
  let html = '<div class="pc-status-card"><div class="pc-status-title">💻 System Health</div><div class="pc-bars">' +
    '<div class="metric-row"><div class="metric-label"><span>CPU Usage:</span> <b>' + cpu + '%</b></div><div class="prog-bar"><div class="prog-fill" style="width:' + cpu + '%"></div></div></div>' +
    '<div class="metric-row"><div class="metric-label"><span>RAM Usage:</span> <b>' + ram + '%</b></div><div class="prog-bar"><div class="prog-fill" style="width:' + ram + '%"></div></div></div>' +
    '</div></div>';
  container.insertAdjacentHTML('beforeend', html);
}

function renderActionCountdownCard(container, data) {
  if (!container || !data) return;
  const actionId = data.action_id || ('act_' + Date.now());
  const label = data.label || 'System Action';
  let remaining = data.countdown || 10;
  const cardId = 'card_' + actionId;

  let html = '<div class="action-countdown-card" id="' + cardId + '" style="margin:10px 0;padding:12px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:6px;">' +
    '<div style="color:var(--red);font-weight:600;font-size:13px;margin-bottom:6px;">⚠️ ' + label + '</div>' +
    '<div style="font-size:11px;color:var(--muted);text-align:center;">This action will execute automatically in:</div>' +
    '<div id="timer_' + actionId + '" style="font-size:22px;font-weight:700;color:var(--red);text-align:center;margin:6px 0;">' + remaining + 's</div>' +
    '<div style="display:flex;gap:6px;justify-content:center;margin-top:8px;">' +
    '<button class="code-btn" data-action="cancelAction" data-action-id="' + actionId + '" data-card-id="' + cardId + '" style="background:var(--red);color:#fff;border:none;padding:4px 12px;cursor:pointer;">🛑 Cancel</button>' +
    '<button class="code-btn" data-action="confirmAction" data-action-id="' + actionId + '" data-card-id="' + cardId + '" style="padding:4px 10px;cursor:pointer;">Confirm Now</button>' +
    '</div></div>';
  container.insertAdjacentHTML('beforeend', html);

  const interval = setInterval(() => {
    remaining--;
    const card = document.getElementById(cardId);
    if (!card || card.dataset.cancelled) {
      clearInterval(interval);
      return;
    }
    const tEl = document.getElementById('timer_' + actionId);
    if (tEl) tEl.textContent = remaining + 's';
    if (remaining <= 0) {
      clearInterval(interval);
      if (card && !card.dataset.cancelled) {
        card.innerHTML = '<div style="color:var(--orange);text-align:center;padding:8px;">⏳ Executing action...</div>';
      }
    }
  }, 1000);
}

function renderScreenshotCard(container, data) {
  if (!container || !data || !data.url) return;
  const url = data.url.startsWith('http') ? data.url : ('http://127.0.0.1:8765' + data.url);
  let html = '<div class="screenshot-card" style="margin:10px 0;padding:8px;background:var(--card-bg, rgba(255,255,255,0.03));border:1px solid var(--border);border-radius:6px;">' +
    '<div style="font-size:11px;font-weight:600;margin-bottom:6px;">📸 Screenshot Captured</div>' +
    '<img src="' + url + '" alt="Screenshot" style="width:100%;border-radius:4px;" />' +
    '</div>';
  container.insertAdjacentHTML('beforeend', html);
}

