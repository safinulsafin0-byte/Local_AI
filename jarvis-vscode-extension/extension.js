/**
 * JARVIS AI Copilot — VS Code Extension
 * Complete local engineering copilot & PC bridge.
 */

const vscode = require("vscode");
const http = require("http");
const https = require("https");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

let statusBarItem;
let guardianStatusBarItem;
let voiceStatusBarItem;
let notifiedAlertIds = new Set();
let outputChannel;
let isBackendOnline = false;
let providerInstance = null;

function getApiUrl() {
    const config = vscode.workspace.getConfiguration("jarvis");
    return config.get("apiUrl", "http://127.0.0.1:8765/api/v1");
}

function getBackendBase() {
    const url = getApiUrl();
    return url.replace("/api/v1", "");
}

function getAuthToken() {
    const config = vscode.workspace.getConfiguration("jarvis");
    let token = config.get("token") || "";
    if (!token) {
        try {
            const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || path.dirname(__dirname);
            const envPaths = [path.join(root, ".env"), path.join(path.dirname(__dirname), ".env")];
            for (const ep of envPaths) {
                if (fs.existsSync(ep)) {
                    const content = fs.readFileSync(ep, "utf8");
                    const match = content.match(/JARVIS_TOKEN\s*=\s*(.+)/);
                    if (match) {
                        token = match[1].trim().replace(/^["']|["']$/g, "");
                        break;
                    }
                }
            }
        } catch (e) {}
    }
    return token;
}

function getNonce() {
    let text = "";
    const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    for (let i = 0; i < 32; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
}

// ── HTTP Helper ──────────────────────────────────────────────────────────────

function makeRequest(endpoint, method = "GET", body = null, timeoutMs = 25000) {
    return new Promise((resolve, reject) => {
        const fullUrl = new URL(getApiUrl() + endpoint);
        const isHttps = fullUrl.protocol === "https:";
        const client = isHttps ? https : http;

        const token = getAuthToken();
        const headers = {
            "Content-Type": "application/json",
        };
        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }

        const options = {
            hostname: fullUrl.hostname,
            port: fullUrl.port || (isHttps ? 443 : 80),
            path: fullUrl.pathname + fullUrl.search,
            method: method,
            headers: headers,
            timeout: timeoutMs,
        };

        const req = client.request(options, (res) => {
            let data = "";
            res.on("data", (chunk) => { data += chunk; });
            res.on("end", () => {
                try {
                    const parsed = JSON.parse(data);
                    resolve({ status: res.statusCode, data: parsed });
                } catch (e) {
                    resolve({ status: res.statusCode, text: data });
                }
            });
        });

        req.on("error", (err) => { reject(err); });
        req.on("timeout", () => {
            req.destroy();
            reject(new Error("Request timed out"));
        });

        if (body) {
            req.write(JSON.stringify(body));
        }
        req.end();
    });
}

// ── Health Checker & Auto-Reconnect ──────────────────────────────────────────
let healthTimer = null;
let reconnectDelay = 3000;
const minReconnectDelay = 3000;
const maxReconnectDelay = 20000;

function scheduleNextHealthCheck(delay) {
    if (healthTimer) clearTimeout(healthTimer);
    healthTimer = setTimeout(checkHealth, delay);
}

async function checkHealth() {
    try {
        const res = await makeRequest("/health", "GET", null, 3500);
        if (res.status === 200 && res.data && res.data.ok) {
            const wasOffline = !isBackendOnline;
            isBackendOnline = true;
            reconnectDelay = minReconnectDelay;
            const model = res.data.model || "qwen2.5:7b";
            statusBarItem.text = `$(hubot) JARVIS: ${model}`;
            statusBarItem.tooltip = `JARVIS is online and ready. Model: ${model}`;
            statusBarItem.backgroundColor = undefined;
            if (wasOffline) {
                vscode.window.showInformationMessage(`JARVIS backend reconnected! Model: ${model}`);
            }
            if (providerInstance && providerInstance._view) {
                providerInstance._view.webview.postMessage({ type: "statusUpdate", online: true, model: model });
            }
            updateGuardianStatus();
            updateVoiceStatus();
            scheduleNextHealthCheck(10000);
        } else {
            setOffline();
        }
    } catch (e) {
        setOffline();
    }
}

async function updateVoiceStatus() {
    if (!voiceStatusBarItem) return;
    try {
        const res = await makeRequest("/voice/mode");
        if (res.status === 200 && res.data && res.data.ok) {
            const isAlways = (res.data.mode === "always" || res.data.mode === "push");
            voiceStatusBarItem.text = isAlways ? "$(mic) JARVIS Voice: ON" : "$(mute) JARVIS Voice: OFF";
            voiceStatusBarItem.tooltip = isAlways ? "JARVIS Voice: ON (Always listening) · Click to toggle (Ctrl+Alt+M)" : "JARVIS Voice: OFF · Click to toggle (Ctrl+Alt+M)";
            if (providerInstance && providerInstance._view) {
                providerInstance._view.webview.postMessage({ type: "voiceState", state: isAlways ? "listening" : "off" });
            }
        }
    } catch {
        voiceStatusBarItem.text = `$(mute) JARVIS Voice: –`;
    }
}

async function updateGuardianStatus() {
    if (!guardianStatusBarItem) return;
    try {
        const res = await makeRequest("/guardian/status");
        if (res.status === 200 && res.data && res.data.ok) {
            const unread = res.data.unread_alerts || 0;
            if (unread > 0) {
                guardianStatusBarItem.text = `$(shield) Guardian: ${unread} alert${unread > 1 ? 's' : ''}`;
                guardianStatusBarItem.backgroundColor = new vscode.ThemeColor("statusBarItem.errorBackground");
                guardianStatusBarItem.tooltip = `JARVIS Guardian: ${unread} active suspicious alert(s). Click to review.`;
            } else {
                guardianStatusBarItem.text = `$(shield) Guardian: OK`;
                guardianStatusBarItem.backgroundColor = undefined;
                guardianStatusBarItem.tooltip = `JARVIS Guardian: Active · Footprint: ${res.data.guardian_cpu_pct}% CPU`;
            }

            // Check high-severity alerts for warning toast
            const alertsRes = await makeRequest("/guardian/alerts?limit=5");
            if (alertsRes.status === 200 && alertsRes.data?.alerts) {
                for (const a of alertsRes.data.alerts) {
                    if (a.severity === "high" && !notifiedAlertIds.has(a.id)) {
                        notifiedAlertIds.add(a.id);
                        vscode.window.showWarningMessage(
                            `🛡️ JARVIS Security Warning: ${a.title} — ${a.reason}`,
                            "Review Alerts"
                        ).then(choice => {
                            if (choice === "Review Alerts") {
                                vscode.commands.executeCommand("jarvis.showGuardianAlerts");
                            }
                        });
                    }
                }
            }
        }
    } catch {
        guardianStatusBarItem.text = `$(shield) Guardian: –`;
        guardianStatusBarItem.backgroundColor = undefined;
    }
}

function setOffline() {
    isBackendOnline = false;
    statusBarItem.text = `$(circle-slash) JARVIS: Offline`;
    statusBarItem.tooltip = `JARVIS backend is offline. Auto-retrying... Click to launch.`;
    statusBarItem.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
    if (guardianStatusBarItem) {
        guardianStatusBarItem.text = `$(shield) Guardian: –`;
        guardianStatusBarItem.backgroundColor = undefined;
    }
    if (voiceStatusBarItem) {
        voiceStatusBarItem.text = `$(mute) JARVIS Voice: Offline`;
    }
    if (providerInstance && providerInstance._view) {
        providerInstance._view.webview.postMessage({ type: "statusUpdate", online: false });
    }
    reconnectDelay = Math.min(reconnectDelay * 1.5, maxReconnectDelay);
    scheduleNextHealthCheck(reconnectDelay);
}

// ── Webview Provider ─────────────────────────────────────────────────────────

class JarvisChatViewProvider {
    constructor(extensionUri) {
        this._extensionUri = extensionUri;
        this._view = null;
    }

    resolveWebviewView(webviewView, context, _token) {
        this._view = webviewView;
        providerInstance = this;
        this._abortController = null;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri],
        };

        webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);

        webviewView.webview.onDidReceiveMessage(async (data) => {
            switch (data.type) {
                case "sendMessage":
                    if (this._activeRequest) {
                        try { this._activeRequest.destroy(); } catch (e) {}
                        this._activeRequest = null;
                    }
                    await this._handleChat(data.message, data.mode, data.turn_id, data.file_path);
                    break;
                case "pickAttachment": {
                    const uris = await vscode.window.showOpenDialog({
                        canSelectMany: false,
                        openLabel: "Attach File"
                    });
                    if (uris && uris[0]) {
                        const fp = uris[0].fsPath;
                        if (this._view) {
                            this._view.webview.postMessage({
                                type: "attachmentReady",
                                filePath: fp,
                                name: path.basename(fp)
                            });
                        }
                    }
                    break;
                }
                case "stop":
                    if (this._activeRequest) {
                        try { this._activeRequest.destroy(); } catch (e) {}
                        this._activeRequest = null;
                    }
                    if (this._view) {
                        this._view.webview.postMessage({ type: "streamDone", turn_id: data.turn_id });
                    }
                    break;

                case "copy":
                    await vscode.env.clipboard.writeText(data.text);
                    vscode.window.showInformationMessage("Copied to clipboard!");
                    break;
                case "insertAtCursor":
                    this._insertAtCursor(data.text);
                    break;
                case "applyToFile":
                    this._applyToFile(data.text);
                    break;
                case "openDiff":
                    await this._openDiff(data.text);
                    break;
                case "runInTerminal":
                    this._runInTerminal(data.text);
                    break;
                case "voiceListen":
                    try {
                        if (this._view) {
                            this._view.webview.postMessage({ type: "voiceStatus", status: "listening" });
                        }
                        if (outputChannel) outputChannel.appendLine("[voice] Recording microphone input...");
                        const vRes = await makeRequest("/voice/listen", "POST", { timeout: 30, silence_timeout: 1.2 });
                        if (vRes.status === 200 && vRes.data && vRes.data.text) {
                            if (outputChannel) outputChannel.appendLine(`[voice] Transcribed (${vRes.data.language}): ${vRes.data.text}`);
                            if (this._view) {
                                this._view.webview.postMessage({ type: "voiceTranscript", text: vRes.data.text });
                            }
                        } else {
                            if (this._view) {
                                this._view.webview.postMessage({ type: "voiceStatus", status: "idle" });
                            }
                        }
                    } catch (e) {
                        if (outputChannel) outputChannel.appendLine(`[voice error] ${e.message}`);
                        if (this._view) {
                            this._view.webview.postMessage({ type: "voiceStatus", status: "idle" });
                        }
                    }
                    break;
                case "voiceStop":
                    if (this._view) {
                        this._view.webview.postMessage({ type: "voiceStatus", status: "idle" });
                    }
                    break;
                case "toggleVoice":
                    vscode.commands.executeCommand("jarvis.toggleVoice");
                    break;
                case "openSettings":
                    vscode.commands.executeCommand("workbench.action.openSettings", "jarvis");
                    break;
                case "initError":
                    if (outputChannel) outputChannel.appendLine(`[webview init error] ${data.error}`);
                    break;
                case "startBackend":
                    vscode.commands.executeCommand("jarvis.startBackend");
                    break;
                case "cancelAction":
                    try {
                        await makeRequest("/system/action/cancel", "POST", { action_id: data.action_id });
                        vscode.window.showInformationMessage("Scheduled action cancelled.");
                    } catch (e) {
                        vscode.window.showErrorMessage("Failed to cancel action: " + e.message);
                    }
                    break;
                case "confirmAction":
                    try {
                        const res = await makeRequest("/system/action/confirm", "POST", { action_id: data.action_id });
                        if (res.status === 200 && res.data && res.data.ok) {
                            vscode.window.showInformationMessage("Action executed.");
                        } else {
                            vscode.window.showWarningMessage("Failed to execute: " + (res.data?.error || "unknown"));
                        }
                    } catch (e) {
                        vscode.window.showErrorMessage("Failed to confirm action: " + e.message);
                    }
                    break;
            }
        });
    }

    _insertAtCursor(text) {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage("No active editor to insert code.");
            return;
        }
        editor.edit((editBuilder) => {
            editBuilder.insert(editor.selection.active, text);
        });
    }

    _applyToFile(text) {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage("No active editor to replace code.");
            return;
        }
        editor.edit((editBuilder) => {
            if (!editor.selection.isEmpty) {
                editBuilder.replace(editor.selection, text);
            } else {
                const fullRange = new vscode.Range(
                    editor.document.positionAt(0),
                    editor.document.positionAt(editor.document.getText().length)
                );
                editBuilder.replace(fullRange, text);
            }
        });
    }

    async _openDiff(newContent) {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage("Open a file first to view diff.");
            return;
        }
        const tempUri = vscode.Uri.file(path.join(os.tmpdir(), "jarvis_diff_" + path.basename(editor.document.fileName)));
        await vscode.workspace.fs.writeFile(tempUri, Buffer.from(newContent, "utf8"));
        await vscode.commands.executeCommand(
            "vscode.diff",
            editor.document.uri,
            tempUri,
            `${path.basename(editor.document.fileName)}: Current ↔ JARVIS Proposal`
        );
    }

    _runInTerminal(text) {
        let terminal = vscode.window.activeTerminal;
        if (!terminal) {
            terminal = vscode.window.createTerminal("JARVIS");
        }
        terminal.show();
        terminal.sendText(text);
    }

    async _handleChat(message, mode = "chat", turn_id = null, file_path = null) {
        if (!this._view) return;

        // Context variables resolution
        let contextText = file_path ? "" : await resolveContextVariables(message);
        const editor = vscode.window.activeTextEditor;
        if (!file_path && editor && !contextText.includes("[Context:")) {
            const fileName = path.basename(editor.document.fileName);
            const selection = editor.document.getText(editor.selection);
            if (selection) {
                contextText += `\n[Context: File ${fileName} Selection:\n\`\`\`\n${selection}\n\`\`\`]\n`;
            } else {
                const fullText = editor.document.getText();
                contextText += `\n[Context: File ${fileName}:\n\`\`\`\n${fullText.slice(0, 4000)}\n\`\`\`]\n`;
            }
        }

        const fullUrl = new URL(getApiUrl() + "/chat");
        const isHttps = fullUrl.protocol === "https:";
        const client = isHttps ? https : http;

        const token = getAuthToken();
        const headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        };
        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }

        const bodyData = JSON.stringify({
            message: message,
            mode: mode,
            context: contextText,
            turn_id: turn_id,
            file_path: file_path || null,
            stream: true,
        });

        const options = {
            hostname: fullUrl.hostname,
            port: fullUrl.port || (isHttps ? 443 : 80),
            path: fullUrl.pathname + fullUrl.search,
            method: "POST",
            headers: headers,
        };

        const postMsg = (obj) => {
            if (this._view) {
                if (turn_id) obj.turn_id = turn_id;
                this._view.webview.postMessage(obj);
            }
        };

        const startTime = Date.now();
        let firstTokenMs = null;

        return new Promise((resolve) => {
            const req = client.request(options, (res) => {
                if (res.statusCode === 401) {
                    if (outputChannel) {
                        outputChannel.appendLine(`[send] len=${message.length} url=${fullUrl.toString()} status=401 first_token=${Date.now() - startTime}ms`);
                    }
                    postMsg({
                        type: "streamError",
                        error: "Invalid token or unauthorized (401). Please configure your token in settings.",
                        showSettings: true,
                    });
                    resolve();
                    return;
                }

                if (res.statusCode !== 200) {
                    let errBody = "";
                    res.on("data", c => errBody += c);
                    res.on("end", () => {
                        if (outputChannel) {
                            outputChannel.appendLine(`[send] len=${message.length} url=${fullUrl.toString()} status=${res.statusCode} first_token=${Date.now() - startTime}ms`);
                        }
                        postMsg({
                            type: "streamError",
                            error: `Server returned status ${res.statusCode}: ${errBody}`,
                            showSettings: res.statusCode === 401,
                        });
                        resolve();
                    });
                    return;
                }

                let buffer = "";
                res.on("data", (chunk) => {
                    buffer += chunk.toString();
                    const lines = buffer.split("\n");
                    buffer = lines.pop(); // keep last incomplete line

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (!trimmed || trimmed.startsWith(":")) continue;
                        if (trimmed.startsWith("data: ")) {
                            const raw = trimmed.slice(6).trim();
                            if (raw === "[DONE]") {
                                postMsg({ type: "streamDone" });
                                continue;
                            }
                            try {
                                const parsed = JSON.parse(raw);
                                if (parsed.type === "weather_card" || parsed.type === "news_card" || parsed.type === "search_card" || parsed.type === "pc_status_card" || parsed.type === "action_countdown" || parsed.type === "screenshot_card") {
                                    postMsg({ type: parsed.type, data: parsed.data });
                                } else if (parsed.token || parsed.text) {
                                    if (firstTokenMs === null) firstTokenMs = Date.now() - startTime;
                                    const t = parsed.token || parsed.text;
                                    postMsg({ type: "streamToken", text: t, token: t });
                                } else if (parsed.tool) {
                                    postMsg({ type: "streamTool", tool: parsed.tool, input: parsed.input });
                                } else if (parsed.tool_result) {
                                    postMsg({ type: "streamToolResult", result: parsed.tool_result });
                                } else if (parsed.response || parsed.reply) {
                                    if (firstTokenMs === null) firstTokenMs = Date.now() - startTime;
                                    const replyText = parsed.response || parsed.reply;
                                    postMsg({ type: "streamToken", text: replyText, token: replyText });
                                } else if (parsed.error) {
                                    postMsg({ type: "streamError", error: parsed.error });
                                }
                            } catch (e) {
                                if (firstTokenMs === null) firstTokenMs = Date.now() - startTime;
                                postMsg({ type: "streamToken", text: raw, token: raw });
                            }
                        }
                    }
                });

                res.on("end", () => {
                    const latency = firstTokenMs !== null ? firstTokenMs : (Date.now() - startTime);
                    if (outputChannel) {
                        outputChannel.appendLine(`[send] len=${message.length} url=${fullUrl.toString()} status=200 first_token=${latency}ms`);
                    }
                    postMsg({ type: "streamDone" });
                    resolve();
                });
            });

            this._activeRequest = req;

            req.on("error", (err) => {
                if (outputChannel) {
                    outputChannel.appendLine(`[error] ${err.stack || err.message}`);
                }
                setOffline();
                postMsg({
                    type: "streamError",
                    error: `Backend not reachable at ${getApiUrl()} (${err.code || err.message})`,
                    showSettings: true,
                    isBackendDown: true,
                    turn_id: turn_id,
                });
                postMsg({ type: "streamDone", turn_id: turn_id });
                resolve();
            });

            req.setTimeout(120000, () => {
                try { req.destroy(); } catch (e) {}
                postMsg({
                    type: "streamError",
                    error: "Request timed out after 120 seconds.",
                    turn_id: turn_id,
                });
                postMsg({ type: "streamDone", turn_id: turn_id });
                resolve();
            });

            req.write(bodyData);
            req.end();
        });
    }

    _getNonce() {
        return getNonce();
    }

    _getHtmlForWebview(webview) {
        const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(this._extensionUri, "media", "main.js"));
        const nonce = getNonce();

        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}'; connect-src http://127.0.0.1:8765; img-src ${webview.cspSource} data: http://127.0.0.1:8765 http://localhost:8765;">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  :root {
    --bg: var(--vscode-editor-background);
    --fg: var(--vscode-editor-foreground);
    --input-bg: var(--vscode-input-background);
    --input-fg: var(--vscode-input-foreground);
    --btn-bg: var(--vscode-button-background);
    --btn-fg: var(--vscode-button-foreground);
    --border: var(--vscode-widget-border, #333);
    --accent: #00d4ff;
    --green: #00e676;
    --red: #f44336;
    --muted: var(--vscode-descriptionForeground, #888);
  }
  body {
    background: var(--bg);
    color: var(--fg);
    font-family: var(--vscode-font-family);
    font-size: var(--vscode-font-size);
    margin: 0; padding: 10px;
    display: flex; flex-direction: column; height: 100vh; box-sizing: border-box;
  }
  #header {
    display: flex; justify-content: space-between; align-items: center;
    border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 8px;
    gap: 8px;
  }
  .title { font-weight: bold; font-size: 1.05em; display: flex; align-items: center; gap: 6px; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); display: inline-block; }
  .status-dot.offline { background: var(--red); }
  select {
    background: var(--input-bg); color: var(--input-fg);
    border: 1px solid var(--border); border-radius: 3px; padding: 3px 6px;
    font-size: 11px; outline: none;
  }
  #messages {
    flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; padding-right: 4px;
  }
  .msg { padding: 8px 10px; border-radius: 6px; word-break: break-word; font-size: 13px; line-height: 1.5; }
  .msg.user {
    background: linear-gradient(135deg, #5E4BF5, #4A38E0);
    color: #FFFFFF !important; align-self: flex-end; max-width: 88%;
    border-radius: 14px 14px 4px 14px;
    box-shadow: 2px 2px 8px rgba(0,0,0,0.25), inset 1px 1px 2px rgba(255,255,255,0.3);
  }
  .msg.user * { color: #FFFFFF !important; }
  .msg.assistant {
    background: var(--vscode-sideBar-background, var(--vscode-editor-inactiveSelectionBackground, #252526));
    color: var(--fg) !important;
    align-self: flex-start; max-width: 96%; width: calc(100% - 10px);
    border-radius: 14px 14px 14px 4px;
    border: 1px solid var(--border);
    box-shadow: 2px 2px 8px rgba(0,0,0,0.2), inset 1px 1px 2px rgba(255,255,255,0.05);
  }
  .msg.assistant * { color: inherit; }
  .lang-badge {
    display: inline-flex; align-items: center; justify-content: center;
    padding: 1px 6px; border-radius: 9999px; font-size: 10px; font-weight: 700;
    margin-left: 6px; letter-spacing: 0.5px;
  }
  .lang-badge.bn { background: rgba(5,150,105,0.2); color: #10B981; }
  .lang-badge.en { background: rgba(37,99,235,0.2); color: #60A5FA; }
  .timeline-step {
    padding: 4px 8px; border-left: 2px solid var(--accent); margin: 4px 0;
    font-size: 11px; color: var(--accent); background: rgba(0,212,255,0.05); border-radius: 0 4px 4px 0;
  }
  .timeline-step.done { border-left-color: var(--green); color: var(--green); }
  pre {
    background: var(--vscode-textCodeBlock-background, #1e1e1e);
    border: 1px solid var(--border); border-radius: 4px; padding: 8px; overflow-x: auto; position: relative;
    font-family: var(--vscode-editor-font-family, monospace); font-size: 12px;
  }
  .code-actions {
    display: flex; gap: 4px; margin-top: 6px; justify-content: flex-end; flex-wrap: wrap;
  }
  .code-btn {
    font-size: 11px; padding: 2px 7px; cursor: pointer;
    background: var(--btn-bg); color: var(--btn-fg); border: none; border-radius: 3px;
    transition: opacity 0.15s;
  }
  .code-btn:hover { opacity: 0.85; }
  .context-chips {
    display: flex; gap: 4px; margin-bottom: 6px; flex-wrap: wrap;
  }
  .chip {
    font-size: 10px; padding: 2px 6px; border-radius: 10px;
    background: rgba(255,255,255,0.07); border: 1px solid var(--border);
    color: var(--muted); cursor: pointer;
  }
  .chip:hover { border-color: var(--accent); color: var(--fg); }
  #input-box {
    display: flex; flex-direction: column; gap: 6px; margin-top: 8px;
    border: 1px solid var(--border); border-radius: 6px; padding: 6px;
    background: var(--input-bg);
  }
  textarea {
    width: 100%; background: transparent; color: var(--input-fg);
    border: none; outline: none; padding: 2px;
    font-family: inherit; font-size: 13px; resize: none; min-height: 48px; max-height: 160px;
  }
  .input-footer {
    display: flex; justify-content: space-between; align-items: center;
  }
  .slash-hint { font-size: 11px; color: var(--muted); }
  .mic-btn {
    background: transparent; border: 1px solid var(--border); border-radius: 4px;
    padding: 3px 8px; cursor: pointer; font-size: 13px; color: var(--fg);
    transition: all 0.2s ease;
  }
  .mic-btn:hover { border-color: var(--accent); }
  .mic-btn.off { opacity: 0.6; color: var(--muted); border-color: var(--border); }
  .mic-btn.listening { color: var(--green); border-color: var(--green); box-shadow: 0 0 8px rgba(0,230,118,0.4); }
  .mic-btn.hearing { color: var(--red); border-color: var(--red); box-shadow: 0 0 12px rgba(244,67,54,0.85); animation: mic-pulse 0.8s infinite alternate; }
  .mic-btn.thinking { color: var(--accent); border-color: var(--accent); }
  .mic-btn.speaking { color: #3b82f6; border-color: #3b82f6; box-shadow: 0 0 8px rgba(59,130,246,0.6); }
  .lang-badge {
    display: inline-flex; align-items: center; justify-content: center;
    padding: 1px 5px; border-radius: 4px; font-size: 10px; font-weight: 700;
    margin-top: 6px; letter-spacing: 0.5px; text-transform: uppercase;
  }
  .lang-badge.bn { background: rgba(0, 230, 118, 0.15); color: #00e676; border: 1px solid rgba(0, 230, 118, 0.3); }
  .lang-badge.en { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
  @keyframes mic-pulse {
    from { transform: scale(1); }
    to { transform: scale(1.1); }
  }
  button.send {
    background: var(--btn-bg); color: var(--btn-fg); border: none; border-radius: 4px;
    padding: 4px 14px; cursor: pointer; font-weight: 600; font-size: 12px;
  }
  button.stop {
    background: var(--red); color: #fff; border: none; border-radius: 4px;
    padding: 4px 14px; cursor: pointer; font-weight: 600; font-size: 12px;
  }
  .attach-btn {
    background: transparent; border: 1px solid var(--border); color: var(--text);
    border-radius: 4px; padding: 3px 8px; cursor: pointer; font-size: 13px;
  }
  .attach-btn:hover { background: var(--bg3); }
  .attach-wrap { margin-bottom: 6px; }
  .attach-pill {
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--bg2); border: 1px solid var(--accent); border-radius: 12px;
    padding: 2px 10px; font-size: 11px; color: var(--text);
  }
  .attach-pill .remove-attach { cursor: pointer; color: var(--red); font-weight: bold; margin-left: 4px; }
  .caret { display: inline-block; width: 6px; height: 14px; background: var(--accent); vertical-align: middle; animation: blink 0.8s infinite; }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

  /* Professional Rich Cards */
  .weather-card, .news-card, .search-sources-card, .pc-status-card {
    margin: 8px 0; padding: 10px 12px; background: rgba(255,255,255,0.03);
    border: 1px solid var(--border); border-radius: 6px; font-size: 12px;
  }
  .weather-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .weather-city { font-weight: bold; color: var(--fg); }
  .weather-temp { font-size: 20px; font-weight: bold; color: var(--accent); }
  .weather-metrics { display: flex; gap: 10px; font-size: 11px; color: var(--muted); margin-bottom: 8px; }
  .weather-forecast { display: flex; gap: 4px; overflow-x: auto; }
  .forecast-day { background: rgba(0,0,0,0.2); padding: 4px 6px; border-radius: 4px; text-align: center; font-size: 10px; min-width: 48px; }
  .news-card-title, .pc-status-title { font-weight: bold; color: var(--accent); margin-bottom: 6px; }
  .news-item { padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
  .news-source-badge { font-size: 9px; padding: 1px 4px; background: rgba(255,255,255,0.1); border-radius: 3px; color: var(--muted); }
  .news-link { color: var(--fg); text-decoration: none; font-weight: 500; }
  .news-link:hover { color: var(--accent); text-decoration: underline; }
  .sources-title { font-weight: bold; font-size: 11px; color: var(--muted); margin-bottom: 4px; }
  .source-chips { display: flex; flex-wrap: wrap; gap: 4px; }
  .source-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 6px; border-radius: 10px; background: rgba(255,255,255,0.05); border: 1px solid var(--border); color: var(--fg); text-decoration: none; font-size: 10px; }
  .chip-domain { color: var(--accent); font-weight: bold; }
  .pc-bars { display: flex; flex-direction: column; gap: 6px; }
  .metric-label { display: flex; justify-content: space-between; font-size: 10px; color: var(--muted); }
  .prog-bar { width: 100%; height: 5px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden; margin-top: 2px; }
  .prog-fill { height: 100%; background: var(--accent); border-radius: 3px; }
</style>
</head>
<body>
  <div id="header">
    <div class="title"><span class="status-dot" id="statusDot"></span> JARVIS Copilot</div>
    <select id="mode">
      <option value="chat">💬 Chat</option>
      <option value="code">💻 Code</option>
      <option value="agent">🤖 Agent</option>
    </select>
  </div>
  <div id="messages">
    <div class="msg assistant">Hello! I am JARVIS. How can I assist you with your code, tests, or PC automation today?</div>
  </div>
  <div class="context-chips">
    <span class="chip" data-ctx="#file">#file</span>
    <span class="chip" data-ctx="#selection">#selection</span>
    <span class="chip" data-ctx="#codebase">#codebase</span>
    <span class="chip" data-ctx="#problems">#problems</span>
    <span class="chip" data-ctx="#terminal">#terminal</span>
  </div>
  <div id="attachWrap" class="attach-wrap"></div>
  <div id="input-box">
    <textarea id="prompt" placeholder="Ask JARVIS, type / for commands, or # for context..."></textarea>
    <div class="input-footer">
      <span class="slash-hint">/explain · /fix · /tests · /review</span>
      <div style="display: flex; gap: 6px; align-items: center;">
        <button id="attachBtn" class="attach-btn" title="Attach File or Image">📎</button>
        <button id="micBtn" class="mic-btn" title="Voice Input (Ctrl+Alt+V)">🎤</button>
        <button class="send" id="sendBtn">Send</button>
      </div>
    </div>
  </div>
<script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
    }
}

// ── Inline Completions Provider ──────────────────────────────────────────────

class JarvisInlineCompletionProvider {
    async provideInlineCompletionItems(document, position, context, token) {
        const config = vscode.workspace.getConfiguration("jarvis");
        if (!config.get("enableInlineCompletion", true)) return;

        // Extract prefix and suffix
        const lineText = document.lineAt(position.line).text;
        const prefixRange = new vscode.Range(new vscode.Position(Math.max(0, position.line - 20), 0), position);
        const prefix = document.getText(prefixRange);
        const suffixRange = new vscode.Range(position, new vscode.Position(Math.min(document.lineCount - 1, position.line + 10), 0));
        const suffix = document.getText(suffixRange);

        if (prefix.trim().length < 3) return;

        try {
            const res = await makeRequest("/complete", "POST", {
                prefix: prefix,
                suffix: suffix,
                language: document.languageId,
                max_tokens: 64,
            });

            if (res.data && res.data.ok && res.data.completion) {
                let comp = res.data.completion;
                return [new vscode.InlineCompletionItem(comp, new vscode.Range(position, position))];
            }
        } catch (e) {
            // Silently ignore completion failures
        }
    }
}

// ── Context Variables Resolver (#file, #selection, #codebase, #problems, #terminal)
async function resolveContextVariables(prompt) {
    let contextText = "";
    const editor = vscode.window.activeTextEditor;

    // #selection
    if (prompt.includes("#selection") || (!prompt.includes("#") && editor && !editor.selection.isEmpty)) {
        if (editor && !editor.selection.isEmpty) {
            const sel = editor.document.getText(editor.selection);
            contextText += `\n[Context: #selection from ${path.basename(editor.document.fileName)}]\n\`\`\`\n${sel}\n\`\`\`\n`;
        }
    }

    // #file
    if (prompt.includes("#file")) {
        if (editor) {
            const fileText = editor.document.getText();
            contextText += `\n[Context: #file ${editor.document.fileName}]\n\`\`\`\n${fileText.slice(0, 5000)}\n\`\`\`\n`;
        }
    }

    // #problems
    if (prompt.includes("#problems") || prompt.includes("/fix")) {
        const diags = vscode.languages.getDiagnostics();
        const problems = [];
        for (const [uri, fileDiags] of diags) {
            for (const d of fileDiags) {
                if (d.severity <= vscode.DiagnosticSeverity.Warning) {
                    problems.push(`${path.basename(uri.fsPath)}:${d.range.start.line + 1}: ${d.message}`);
                }
            }
        }
        if (problems.length > 0) {
            contextText += `\n[Context: #problems]\n${problems.slice(0, 10).join("\n")}\n`;
        }
    }

    // #codebase
    if (prompt.includes("#codebase")) {
        try {
            const files = await vscode.workspace.findFiles("**/*", "**/node_modules/**", 30);
            const fileList = files.map(f => vscode.workspace.asRelativePath(f)).join("\n");
            contextText += `\n[Context: #codebase file tree]\n${fileList}\n`;
        } catch (e) {}
    }

    // #terminal
    if (prompt.includes("#terminal")) {
        const terminal = vscode.window.activeTerminal;
        if (terminal) {
            contextText += `\n[Context: #terminal name: ${terminal.name}]\n`;
        }
    }

    return contextText;
}

// ── Multi-File Edits with Per-File Diff Accept / Reject ───────────────────────
async function handleMultiFileEdits(responseText) {
    const fileBlockRegex = /(?:FILE|File|FilePath):\s*([^\r\n]+)\r?\n```[a-zA-Z0-9_-]*\r?\n([\s\S]*?)```/g;
    let match;
    const edits = [];
    while ((match = fileBlockRegex.exec(responseText)) !== null) {
        edits.push({ filePath: match[1].trim(), content: match[2] });
    }

    if (edits.length === 0) return false;

    for (const edit of edits) {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders) continue;
        const targetUri = vscode.Uri.joinPath(workspaceFolders[0].uri, edit.filePath);

        const tempUri = vscode.Uri.file(path.join(os.tmpdir(), "jarvis_" + path.basename(edit.filePath)));
        await vscode.workspace.fs.writeFile(tempUri, Buffer.from(edit.content, "utf8"));

        const exists = fs.existsSync(targetUri.fsPath);
        if (exists) {
            await vscode.commands.executeCommand(
                "vscode.diff",
                targetUri,
                tempUri,
                `${path.basename(edit.filePath)}: Current ↔ JARVIS Proposal`
            );
        }

        const choice = await vscode.window.showInformationMessage(
            `Apply edits to ${edit.filePath}?`,
            "Accept",
            "Reject"
        );

        if (choice === "Accept") {
            await vscode.workspace.fs.writeFile(targetUri, Buffer.from(edit.content, "utf8"));
            vscode.window.showInformationMessage(`Applied edits to ${edit.filePath}`);
        }
    }
    return true;
}

// ── Code Actions Provider (Fix, Explain, Tests) ──────────────────────────────
class JarvisCodeActionProvider {
    provideCodeActions(document, range, context, token) {
        const actions = [];

        if (context.diagnostics && context.diagnostics.length > 0) {
            const fixAction = new vscode.CodeAction("Fix with JARVIS", vscode.CodeActionKind.QuickFix);
            fixAction.command = {
                command: "jarvis.fixCode",
                title: "Fix with JARVIS",
                arguments: [document, range, context.diagnostics]
            };
            fixAction.isPreferred = true;
            actions.push(fixAction);
        }

        if (!range.isEmpty) {
            const explainAction = new vscode.CodeAction("Explain with JARVIS", vscode.CodeActionKind.Refactor);
            explainAction.command = {
                command: "jarvis.explainCode",
                title: "Explain with JARVIS",
                arguments: [document, range]
            };
            actions.push(explainAction);

            const testAction = new vscode.CodeAction("Generate Unit Tests with JARVIS", vscode.CodeActionKind.Refactor);
            testAction.command = {
                command: "jarvis.generateTests",
                title: "Generate Unit Tests with JARVIS",
                arguments: [document, range]
            };
            actions.push(testAction);
        }

        return actions;
    }
}

// ── Chat Participant @jarvis ──────────────────────────────────────────────────
function registerChatParticipant(context) {
    if (typeof vscode.chat?.createChatParticipant !== "function") {
        outputChannel.appendLine("VS Code chat participant API not available in this VS Code host.");
        return;
    }

    const participant = vscode.chat.createChatParticipant("jarvis.chatParticipant", async (request, chatContext, stream, token) => {
        stream.progress("JARVIS is analyzing request...");

        let command = request.command;
        let userPrompt = request.prompt;

        let systemInstruction = "";
        let mode = "chat";

        if (command === "explain") {
            systemInstruction = "Explain the code clearly, breaking down architecture, logic, and patterns.";
            mode = "code";
        } else if (command === "fix") {
            systemInstruction = "Diagnose the error or bug and provide the corrected code with root-cause analysis.";
            mode = "code";
        } else if (command === "tests") {
            systemInstruction = "Generate comprehensive, robust unit tests with edge cases and mock assertions.";
            mode = "code";
        } else if (command === "doc") {
            systemInstruction = "Generate professional docstrings, API reference, and clean documentation.";
            mode = "code";
        } else if (command === "optimize") {
            systemInstruction = "Analyze performance, time/space complexity, and provide an optimized implementation.";
            mode = "code";
        } else if (command === "refactor") {
            systemInstruction = "Refactor the code for clean architecture, SOLID principles, and eliminate code smells.";
            mode = "code";
        } else if (command === "commit") {
            systemInstruction = "Generate a concise Conventional Commit message based on the changes provided.";
            mode = "code";
        } else if (command === "review") {
            systemInstruction = "Perform a thorough code review checking for bugs, security vulnerabilities, edge cases, and style.";
            mode = "code";
        }

        if (userPrompt.toLowerCase().startsWith("agent ") || userPrompt.toLowerCase().includes("terminal") || userPrompt.toLowerCase().includes("create file")) {
            mode = "agent";
        }

        const contextStr = await resolveContextVariables(userPrompt);
        const finalPrompt = (systemInstruction ? `[Instruction: ${systemInstruction}]\n` : "") +
                            (contextStr ? `${contextStr}\n` : "") +
                            `User Query: ${userPrompt}`;

        return new Promise((resolve) => {
            const url = new URL(getApiUrl() + "/chat");
            const isHttps = url.protocol === "https:";
            const client = isHttps ? https : http;

            const postData = JSON.stringify({
                message: finalPrompt,
                mode: mode,
                stream: true
            });

            const req = client.request({
                hostname: url.hostname,
                port: url.port || (isHttps ? 443 : 80),
                path: url.pathname + url.search,
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Content-Length": Buffer.byteLength(postData)
                }
            }, (res) => {
                let accumulated = "";
                let buffer = "";

                res.on("data", (chunk) => {
                    if (token.isCancellationRequested) {
                        req.destroy();
                        stream.markdown("\n\n*(Generation stopped by user)*");
                        resolve();
                        return;
                    }

                    buffer += chunk.toString();
                    const lines = buffer.split("\n");
                    buffer = lines.pop();

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (trimmed.startsWith("data:")) {
                            const jsonStr = trimmed.slice(5).trim();
                            if (!jsonStr) continue;
                            try {
                                const evt = JSON.parse(jsonStr);
                                if (evt.type === "token") {
                                    stream.markdown(evt.text);
                                    accumulated += evt.text;
                                } else if (evt.type === "tool_start") {
                                    stream.progress(`Running tool: ${evt.tool}...`);
                                } else if (evt.type === "tool_result") {
                                    stream.progress(`Completed tool: ${evt.tool}`);
                                } else if (evt.type === "done") {
                                    accumulated = evt.full || accumulated;
                                }
                            } catch (e) {}
                        }
                    }
                });

                res.on("end", async () => {
                    if (accumulated.includes("FILE:") || accumulated.includes("FilePath:")) {
                        await handleMultiFileEdits(accumulated);
                    }
                    resolve();
                });
            });

            token.onCancellationRequested(() => {
                req.destroy();
                stream.markdown("\n\n*(Operation stopped by user)*");
                resolve();
            });

            req.on("error", (err) => {
                stream.markdown(`\n❌ Error communicating with JARVIS backend: ${err.message}`);
                resolve();
            });

            req.write(postData);
            req.end();
        });
    });

    context.subscriptions.push(participant);
}

// ── Extension Activation ─────────────────────────────────────────────────────

function activate(context) {
    outputChannel = vscode.window.createOutputChannel("JARVIS");
    outputChannel.appendLine("JARVIS AI Copilot extension activating...");

    // Status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = "jarvis.showStatus";
    context.subscriptions.push(statusBarItem);
    statusBarItem.show();

    // Guardian status bar item
    guardianStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 99);
    guardianStatusBarItem.command = "jarvis.showGuardianAlerts";
    guardianStatusBarItem.text = "$(shield) Guardian: OK";
    guardianStatusBarItem.tooltip = "JARVIS Guardian Security Monitor: Active · Click to view alerts";
    context.subscriptions.push(guardianStatusBarItem);
    guardianStatusBarItem.show();

    // Voice mode status bar item
    voiceStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 98);
    voiceStatusBarItem.command = "jarvis.toggleVoice";
    voiceStatusBarItem.text = "$(mic) JARVIS Voice: ON";
    voiceStatusBarItem.tooltip = "Click to toggle JARVIS Voice (Ctrl+Alt+M / Ctrl+Alt+V)";
    context.subscriptions.push(voiceStatusBarItem);
    voiceStatusBarItem.show();

    // Initial health & Guardian status check
    checkHealth();
    context.subscriptions.push({ dispose: () => { if (healthTimer) clearTimeout(healthTimer); } });

    // Webview View Provider
    const provider = new JarvisChatViewProvider(context.extensionUri);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider("jarvis.chat", provider)
    );

    // Inline Completions Provider
    context.subscriptions.push(
        vscode.languages.registerInlineCompletionItemProvider(
            { pattern: "**" },
            new JarvisInlineCompletionProvider()
        )
    );

    // Command: Open Chat
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.openChat", () => {
            vscode.commands.executeCommand("workbench.view.extension.jarvis");
        })
    );

    // Command: Explain File / Selection
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.explainFile", async (uri) => {
            let targetPath = uri ? uri.fsPath : vscode.window.activeTextEditor?.document.fileName;
            if (!targetPath) {
                vscode.window.showWarningMessage("No file selected.");
                return;
            }
            await vscode.commands.executeCommand("workbench.view.extension.jarvis");
            if (provider._view) {
                provider._view.webview.postMessage({
                    type: "setAttachmentAndPrompt",
                    filePath: targetPath,
                    name: path.basename(targetPath),
                    prompt: "Explain this document / file."
                });
            }
        })
    );

    // Command: Voice Input (Ctrl+Alt+V)
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.voiceInput", async () => {
            if (provider._view) {
                provider._view.webview.postMessage({ type: "voiceStatus", status: "listening" });
            }
            vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: "JARVIS: Listening to microphone...",
                cancellable: true,
            }, async () => {
                try {
                    const res = await makeRequest("/voice/listen", "POST", { timeout: 30, silence_timeout: 1.2 });
                    if (res.status === 200 && res.data && res.data.text) {
                        const transcript = res.data.text;
                        vscode.window.showInformationMessage(`JARVIS Voice: "${transcript}"`);
                        if (provider._view) {
                            provider._view.webview.postMessage({ type: "voiceTranscript", text: transcript });
                        }
                    } else if (provider._view) {
                        provider._view.webview.postMessage({ type: "voiceStatus", status: "idle" });
                    }
                } catch (e) {
                    vscode.window.showErrorMessage(`Voice Error: ${e.message}`);
                    if (provider._view) {
                        provider._view.webview.postMessage({ type: "voiceStatus", status: "idle" });
                    }
                }
            });
        })
    );

    // Command: Toggle Voice (Ctrl+Alt+V / Ctrl+Alt+M)
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.toggleVoice", async () => {
            try {
                const statusRes = await makeRequest("/voice/mode");
                const currentMode = statusRes.data?.mode || "always";
                const newMode = (currentMode === "always" || currentMode === "push") ? "off" : "always";
                const res = await makeRequest("/voice/mode", "POST", { mode: newMode });
                if (res.status === 200 && res.data && res.data.ok) {
                    const isNowOn = res.data.mode === "always";
                    voiceStatusBarItem.text = isNowOn ? "$(mic) JARVIS Voice: ON" : "$(mute) JARVIS Voice: OFF";
                    voiceStatusBarItem.tooltip = isNowOn ? "JARVIS Voice: ON (Always listening) · Click to toggle (Ctrl+Alt+M)" : "JARVIS Voice: OFF · Click to toggle (Ctrl+Alt+M)";
                    vscode.window.showInformationMessage(`JARVIS Voice: ${isNowOn ? "ON (Always listening)" : "OFF (Muted)"}`);
                    if (provider._view) {
                        provider._view.webview.postMessage({ type: "voiceState", state: isNowOn ? "listening" : "off" });
                    }
                }
            } catch (e) {
                vscode.window.showErrorMessage(`Failed to toggle voice: ${e.message}`);
            }
        })
    );

    // Command: Select Voice Settings
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.selectVoiceMode", async () => {
            const choice = await vscode.window.showQuickPick([
                { label: "$(mic) Toggle Voice ON / OFF", description: "Quickly toggle always-listening mic", action: "toggle" },
                { label: "$(settings-gear) Voice Settings (Popover)", description: "Select device, language, sensitivity", action: "settings" },
                { label: "$(globe) Set Language: Auto (BN/EN)", description: "Auto-detect Bengali or English", action: "lang_auto" },
                { label: "$(globe) Set Language: Bangla Only (বাংলা)", description: "Lock recognition to Bangla", action: "lang_bn" },
                { label: "$(globe) Set Language: English Only", description: "Lock recognition to English", action: "lang_en" }
            ], { placeHolder: "JARVIS Voice Controls" });

            if (choice) {
                if (choice.action === "toggle") {
                    vscode.commands.executeCommand("jarvis.toggleVoice");
                } else if (choice.action?.startsWith("lang_")) {
                    const lang = choice.action.replace("lang_", "");
                    try {
                        await makeRequest("/voice/settings", "POST", { language: lang });
                        vscode.window.showInformationMessage(`JARVIS Voice recognition language set to: ${lang}`);
                    } catch (e) {
                        vscode.window.showErrorMessage(`Failed to update voice language: ${e.message}`);
                    }
                } else {
                    vscode.commands.executeCommand("jarvis.openChat");
                }
            }
        })
    );

    // Command: Start Backend
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.startBackend", () => {
            const batPath = path.join(path.dirname(__dirname), "start_jarvis.bat");
            if (fs.existsSync(batPath)) {
                vscode.window.showInformationMessage("Starting JARVIS Backend Server...");
                spawn("cmd.exe", ["/c", "start", "", batPath], { detached: true, stdio: "ignore" }).unref();
                setTimeout(checkHealth, 5000);
            } else {
                vscode.window.showErrorMessage(`start_jarvis.bat not found at ${batPath}`);
            }
        })
    );

    // Command: Check Status
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.showStatus", async () => {
            await checkHealth();
            if (isBackendOnline) {
                vscode.window.showInformationMessage(`JARVIS is online and connected (${getApiUrl()})`);
            } else {
                const choice = await vscode.window.showWarningMessage(
                    "JARVIS backend is offline.",
                    "Start JARVIS",
                    "Settings"
                );
                if (choice === "Start JARVIS") {
                    vscode.commands.executeCommand("jarvis.startBackend");
                } else if (choice === "Settings") {
                    vscode.commands.executeCommand("workbench.action.openSettings", "jarvis");
                }
            }
        })
    );

    // Command: Inline Chat (Ctrl+I)
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.inlineChat", async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showWarningMessage("Open a file to use Inline Edit.");
                return;
            }

            const selection = editor.document.getText(editor.selection);
            const instruction = await vscode.window.showInputBox({
                prompt: "What would you like JARVIS to do?",
                placeHolder: "e.g., Add type annotations, optimize this loop, handle errors...",
            });

            if (!instruction) return;

            vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: "JARVIS: Generating code edits...",
                cancellable: false,
            }, async () => {
                try {
                    const res = await makeRequest("/edit", "POST", {
                        instruction: instruction,
                        selection: selection || editor.document.getText(),
                        file_path: editor.document.fileName,
                    });

                    if (res.data && res.data.ok && res.data.edited) {
                        editor.edit((editBuilder) => {
                            if (!editor.selection.isEmpty) {
                                editBuilder.replace(editor.selection, res.data.edited);
                            } else {
                                const fullRange = new vscode.Range(
                                    editor.document.positionAt(0),
                                    editor.document.positionAt(editor.document.getText().length)
                                );
                                editBuilder.replace(fullRange, res.data.edited);
                            }
                        });
                        vscode.window.showInformationMessage("JARVIS: Edits applied!");
                    } else {
                        vscode.window.showErrorMessage(res.data?.error || "Edit failed");
                    }
                } catch (e) {
                    vscode.window.showErrorMessage(`JARVIS Edit Error: ${e.message}`);
                }
            });
        })
    );

    // Command: Explain Code
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.explainCode", () => {
            const editor = vscode.window.activeTextEditor;
            const code = editor ? editor.document.getText(editor.selection) : "";
            vscode.commands.executeCommand("jarvis.openChat");
            if (provider._view) {
                provider._view.webview.postMessage({
                    type: "sendMessage",
                    message: `Explain this code:\n\`\`\`\n${code}\n\`\`\``,
                    mode: "code",
                });
            }
        })
    );

    // Command: Fix Code
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.fixCode", () => {
            const editor = vscode.window.activeTextEditor;
            const code = editor ? editor.document.getText(editor.selection) : "";
            vscode.commands.executeCommand("jarvis.openChat");
            if (provider._view) {
                provider._view.webview.postMessage({
                    type: "sendMessage",
                    message: `Find and fix any bugs in this code:\n\`\`\`\n${code}\n\`\`\``,
                    mode: "code",
                });
            }
        })
    );

    // Command: Generate Tests
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.generateTests", () => {
            const editor = vscode.window.activeTextEditor;
            const code = editor ? editor.document.getText(editor.selection) : "";
            vscode.commands.executeCommand("jarvis.openChat");
            if (provider._view) {
                provider._view.webview.postMessage({
                    type: "sendMessage",
                    message: `Generate comprehensive unit tests for this code:\n\`\`\`\n${code}\n\`\`\``,
                    mode: "code",
                });
            }
        })
    );

    // Command: Generate Commit Message
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.generateCommitMessage", async () => {
            try {
                const gitExtension = vscode.extensions.getExtension("vscode.git");
                if (!gitExtension) {
                    vscode.window.showWarningMessage("Git extension not found.");
                    return;
                }
                const git = gitExtension.exports.getAPI(1);
                const repo = git.repositories[0];
                if (!repo) {
                    vscode.window.showWarningMessage("No git repository open.");
                    return;
                }

                const diff = await repo.diff(true) || await repo.diff(false);
                if (!diff || !diff.trim()) {
                    vscode.window.showWarningMessage("No git changes detected to commit.");
                    return;
                }

                vscode.window.withProgress({
                    location: vscode.ProgressLocation.Notification,
                    title: "JARVIS: Generating commit message...",
                }, async () => {
                    const res = await makeRequest("/chat", "POST", {
                        message: `Generate a concise Conventional Commit message for this diff. Output ONLY the commit message:\n\n${diff.slice(0, 3000)}`,
                        mode: "code",
                        stream: false,
                    });
                    const msg = res.data?.response || res.data?.reply || "";
                    if (msg) {
                        repo.inputBox.value = msg.trim().replace(/^["']|["']$/g, "");
                        vscode.window.showInformationMessage("Commit message generated!");
                    }
                });
            } catch (e) {
                vscode.window.showErrorMessage(`Git error: ${e.message}`);
            }
        })
    );

    // Register Chat Participant @jarvis
    registerChatParticipant(context);

    // Register Code Actions Provider (Fix, Explain, Tests)
    context.subscriptions.push(
        vscode.languages.registerCodeActionsProvider(
            { pattern: "**" },
            new JarvisCodeActionProvider(),
            { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix, vscode.CodeActionKind.Refactor] }
        )
    );

    // Register Multi-File Diff Command
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.applyMultiFileDiff", async (text) => {
            await handleMultiFileEdits(text || "");
        })
    );

    // Register Guardian Alerts QuickPick Command
    context.subscriptions.push(
        vscode.commands.registerCommand("jarvis.showGuardianAlerts", async () => {
            try {
                const res = await makeRequest("/guardian/alerts?limit=15");
                const alerts = res.data?.alerts || [];
                if (!alerts.length) {
                    vscode.window.showInformationMessage("🛡️ JARVIS Guardian: No suspicious activity alerts. All normal!");
                    return;
                }
                const items = alerts.map(a => ({
                    label: `[${(a.severity || 'low').toUpperCase()}] ${a.title}`,
                    description: a.reason,
                    detail: a.details?.path ? `Path: ${a.details.path}` : (a.details?.pid ? `PID: ${a.details.pid}` : a.timestamp),
                    alert: a
                }));
                const selected = await vscode.window.showQuickPick(items, {
                    placeHolder: "JARVIS Guardian Alerts — Select an alert to view actions"
                });
                if (selected) {
                    const a = selected.alert;
                    const actionOptions = ["Ignore Alert"];
                    if (a.details?.pid) actionOptions.unshift("Kill Process");
                    const choice = await vscode.window.showWarningMessage(
                        `[${(a.severity || 'low').toUpperCase()}] ${a.title}: ${a.reason}`,
                        ...actionOptions
                    );
                    if (choice === "Ignore Alert") {
                        await makeRequest(`/guardian/alerts/${a.id}/ignore`, "POST");
                        vscode.window.showInformationMessage(`Ignored alert: ${a.title}`);
                        updateGuardianStatus();
                    } else if (choice === "Kill Process") {
                        const killRes = await makeRequest(`/guardian/alerts/${a.id}/kill`, "POST");
                        if (killRes.data?.ok) {
                            vscode.window.showInformationMessage(`Process (PID ${a.details.pid}) terminated.`);
                        } else {
                            vscode.window.showErrorMessage(`Failed to kill process: ${killRes.data?.error || killRes.data?.detail}`);
                        }
                        updateGuardianStatus();
                    }
                }
            } catch (e) {
                vscode.window.showErrorMessage(`Failed to fetch Guardian alerts: ${e.message}`);
            }
        })
    );

    outputChannel.appendLine("JARVIS extension activated successfully.");
}

function deactivate() {
    if (statusBarItem) statusBarItem.dispose();
    if (guardianStatusBarItem) guardianStatusBarItem.dispose();
}

module.exports = {
    activate,
    deactivate,
};