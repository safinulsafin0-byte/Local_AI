# JARVIS Stark Edition - Security & Defensive Policy

## 1. Civilian Scope & Responsible AI Design
JARVIS is designed strictly for civilian productivity, hardware telemetry, educational simulation, and peaceful automation:
- **No weapons, targeting systems, or destructive capabilities.**
- **No unauthorized network penetration or offensive hacking.**
- All device discovery features are strictly passive (inspecting the Windows ARP table) and require explicit user consent (`consent=True`) before running.
- Destructive filesystem or process kill actions require user confirmation or run under a visible 10-second cancellation countdown.

## 2. Local-First & Zero Cloud Leakage
- **127.0.0.1 Binding**: The backend FastAPI server binds strictly to `127.0.0.1` and does not expose ports to external WAN networks.
- **Token Protection**: All API endpoints and WebSocket streams require bearer token authentication (auto-generated in `.env` using cryptographically secure `secrets.token_urlsafe(32)`).
- **Local LLM**: Primary inference runs through Ollama on `127.0.0.1:11434` with open weights (`qwen2.5:7b`). No user prompts or documents are transmitted to external servers.

## 3. Untrusted Data Sanitization
- Content originating from external web pages, documents, files, PDFs, and command execution is marked as **UNTRUSTED DATA**.
- Text extracts are passed inside sanitized context delimiters and will never execute as privileged commands.

## 4. Defensive Readiness & Audit Score
The S.H.I.E.L.D. threat defense module performs read-only checks of:
- Windows Defender Real-Time Protection (`Get-MpComputerStatus`)
- Windows Firewall Profiles (`Get-NetFirewallProfile`)
- Active listening ports mapped to local process PIDs (`psutil.net_connections`)
- Static code vulnerability analysis for dangerous function calls (`eval`, `exec`, `shell=True`)

