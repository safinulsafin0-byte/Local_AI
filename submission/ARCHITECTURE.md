# JARVIS Stark Edition - System Architecture

JARVIS is a local-first, privacy-respecting AI assistant running on Windows with an autonomous modular capability framework, deterministic verified tool execution, and an international showcase civilian defense interface.

```mermaid
flowchart TD
    subgraph UI ["Client Layer (Two Clients, One Protocol)"]
        WebUI["Web HUD & Command Center\n(web/index.html + Three.js + SVG)"]
        VSCode["VS Code Copilot Extension\n(jarvis-ai-copilot)"]
    end

    subgraph Backend ["FastAPI Core (127.0.0.1:8765)"]
        Auth["Bearer Token Auth\n(Secrets compare_digest)"]
        Router["Dynamic Router & Module Registry\n(modules/registry.py)"]
        AgentLoop["Deterministic Intent Engine & ReAct Loop\n(intent/engine.py + fast_rules.py)"]
        SSE["Streaming SSE & WebSocket Engine\n(/api/v1/chat + /ws/events)"]
    end

    subgraph Modules ["Modular Stark Capability Bay"]
        M1["Briefing & Protocols\n(briefing_protocols)"]
        M2["3D Engineering Bay\n(cad_engineering)"]
        M3["Threat Defense & Audit\n(threat_defense)"]
        M4["Virtual Smart Facility\n(smart_facility)"]
        M5["Comms & Alerts\n(comms)"]
        M6["Simulation Lab\n(simulation_lab)"]
        M7["Swarm Task Board\n(task_board)"]
    end

    subgraph Hardware ["Local Hardware & Models (Zero-Cloud Option)"]
        LLM["Ollama Local LLM\n(qwen2.5:7b / qwen2.5-coder:7b)"]
        Voice["Faster-Whisper STT\n(Microphone Input)"]
        OS["Windows 11 Subsystem\n(psutil, powercfg, win32gui, DISM, ARP)"]
    end

    WebUI -->|HTTP / SSE / WS| Auth
    VSCode -->|HTTP / SSE| Auth
    Auth --> Router
    Router --> AgentLoop
    AgentLoop --> Modules
    AgentLoop --> LLM
    M1 & M2 & M3 & M4 & M5 & M6 & M7 --> OS
    AgentLoop --> SSE
    SSE --> WebUI
    SSE --> VSCode
```

## Architectural Tenets

1. **Local-First & Offline Capable**:
   Core intelligence, file operations, hardware telemetry, 3D CAD modeling, threat audits, simulations, and smart room automation execute 100% locally on a standard 16 GB laptop without internet connection.
2. **Zero False Positives**:
   A tool result is marked success only when the real physical or operating system state confirms it (e.g. file size on disk, active power scheme GUID, volume scalar).
3. **Defensive Civilian Scope**:
   All security capabilities are strictly defensive (Windows Defender audit, firewall status, BitLocker, passive ARP table discovery with explicit user consent). Zero offensive probing or weapon systems.
4. **Plug-and-Play Dynamic Modules**:
   Modules live in `modules/` with self-describing `manifest.json` files, lazy-loaded routers, isolated tools, and health endpoints.

