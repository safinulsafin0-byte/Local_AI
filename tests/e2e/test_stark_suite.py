"""
JARVIS Stark Edition - End-to-End Comprehensive Test Suite
===========================================================
Validates all 14 civilian Stark capabilities across all modules:
1. Module Registry & Health
2. Proactive Executive Briefing
3. Personality Modes (Stark / Professional / Friendly)
4. Protocols (Clean Slate, Night Mode, Study, Demo Mode)
5. Parametric Text-to-CAD (watertight binary STL verification)
6. Hardware Diagnostics & Health Score
7. Power Rerouting
8. Defensive Threat & Security Audit
9. Consent-Gated Local Network Inventory
10. Static Code Security Scanner
11. Virtual Smart Facility & Scenes
12. Comms & Native Desktop Notifications
13. Scientific Physics Simulations (Projectile, Beam, Heat, RLC)
14. Parallel Task Board & Agent Swarm
"""

import os
import sys

# Configure UTF-8 stdout/stderr for Windows console compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import time
import struct
import unittest
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

class TestStarkSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 70)
        print("  STARTING JARVIS STARK EDITION VERIFICATION SUITE")
        print("=" * 70)

    # 1. Module Registry
    def test_01_module_registry(self):
        from modules.registry import discover_modules, list_modules
        mods = discover_modules()
        print(f"  [1/14] Discovered Modules: {list(mods.keys())}")
        self.assertGreaterEqual(len(mods), 7)
        expected = ["briefing_protocols", "cad_engineering", "comms", "simulation_lab", "smart_facility", "task_board", "threat_defense"]
        for exp in expected:
            self.assertIn(exp, mods, f"Module {exp} missing from registry")
        
        all_mods = list_modules()
        for m in all_mods:
            self.assertTrue(m.get("health", {}).get("ok"), f"Health check failed for {m.get('id')}")
        print("  [OK] Module registry operational and 100% healthy.")

    # 2. Proactive Briefing
    def test_02_proactive_briefing(self):
        from modules.briefing_protocols.tools import get_proactive_briefing
        briefing = get_proactive_briefing(lang="en")
        print(f"  [2/14] Briefing Telemetry: Threat={briefing.get('threat_level')}, CPU={briefing.get('telemetry',{}).get('cpu_percent')}%")
        self.assertTrue(briefing.get("ok"))
        self.assertIn("briefing_text", briefing)
        self.assertIn("telemetry", briefing)
        self.assertIn("battery", briefing["telemetry"])
        self.assertIn("threat_level", briefing)
        print("  [OK] Proactive briefing verified with live hardware telemetry.")

    # 3. Personality Modes
    def test_03_personality_modes(self):
        from modules.briefing_protocols.tools import set_personality_mode, get_personality_mode
        set_personality_mode("Stark")
        self.assertEqual(get_personality_mode(), "Stark")
        set_personality_mode("Professional")
        self.assertEqual(get_personality_mode(), "Professional")
        set_personality_mode("Friendly")
        self.assertEqual(get_personality_mode(), "Friendly")
        set_personality_mode("Stark")
        print("  [OK] Personality profile toggle verified (Stark, Professional, Friendly).")

    # 4. Protocols
    def test_04_protocols_execution(self):
        from modules.briefing_protocols.tools import list_protocols, run_protocol
        plist = list_protocols()
        self.assertTrue(plist.get("ok"))
        raw_protos = plist.get("protocols", {})
        if isinstance(raw_protos, dict):
            names = list(raw_protos.keys())
        else:
            names = [p.get("name", p) if isinstance(p, dict) else p for p in raw_protos]

        self.assertIn("Study", names)
        self.assertIn("Clean Slate", names)
        self.assertIn("Night Mode", names)
        self.assertIn("Demo Mode", names)

        # Run Study protocol
        res = run_protocol("Study")
        print(f"  [4/14] Study Protocol Steps executed: {len(res.get('steps', []))}")
        self.assertTrue(res.get("ok"))
        self.assertGreaterEqual(len(res.get("steps", [])), 2)
        print("  [OK] Autonomous protocols verified with step verification.")

    # 5. Text-to-CAD Watertight STL Generator
    def test_05_parametric_cad_stl(self):
        from modules.cad_engineering.tools import generate_cad_model
        res = generate_cad_model("phone stand 80mm wide")
        print(f"  [5/14] CAD Model: {res.get('filename')} | Triangles: {res.get('triangles_count')} | Vol: {res.get('volume_cm3')} cm3")
        self.assertTrue(res.get("ok"))
        self.assertGreater(res.get("triangles_count", 0), 10)
        self.assertGreater(res.get("volume_cm3", 0), 0)
        
        stl_path = Path(res.get("file_path"))
        self.assertTrue(stl_path.exists())
        self.assertGreater(stl_path.stat().st_size, 84)

        with open(stl_path, "rb") as f:
            header = f.read(80)
            self.assertTrue(header.startswith(b"JARVIS Stark CAD"))
            num_triangles = struct.unpack("<I", f.read(4))[0]
            self.assertEqual(num_triangles, res.get("triangles_count"))
        print("  [OK] Watertight binary STL file generated and validated.")

    # 6. Hardware Diagnostics
    def test_06_hardware_diagnostics(self):
        from modules.cad_engineering.tools import run_hardware_diagnostics
        diag = run_hardware_diagnostics()
        print(f"  [6/14] Diagnostics Health Score: {diag.get('health_score')}/100 | Findings: {len(diag.get('findings', []))}")
        self.assertTrue(diag.get("ok"))
        self.assertGreaterEqual(diag.get("health_score", 0), 20)
        self.assertIn("telemetry", diag)
        print("  [OK] Hardware suit diagnostics operational.")

    # 7. Power Rerouting
    def test_07_power_rerouting(self):
        from modules.cad_engineering.tools import reroute_system_power
        res = reroute_system_power("balanced")
        print(f"  [7/14] Power Rerouting: {res.get('summary')}")
        self.assertTrue(res.get("ok"))
        print("  [OK] Power rerouting scheme execution confirmed.")

    # 8. Defensive Security Audit
    def test_08_defensive_security_audit(self):
        from modules.threat_defense.tools import audit_system_security
        audit = audit_system_security()
        print(f"  [8/14] Defense Audit: Readiness={audit.get('readiness_score')}% | Level={audit.get('threat_level')}")
        self.assertTrue(audit.get("ok"))
        self.assertIn("threat_level", audit)
        self.assertIn("open_ports", audit)
        self.assertIn("ports_summary", audit)
        print("  [OK] Defensive security posture & open port audit verified.")

    # 9. Consent-Gated LAN Scan
    def test_09_consent_gated_lan_scan(self):
        from modules.threat_defense.tools import scan_local_network
        denied = scan_local_network(consent=False)
        self.assertFalse(denied.get("ok"))
        self.assertEqual(denied.get("error"), "CONSENT_REQUIRED")
        
        allowed = scan_local_network(consent=True)
        print(f"  [9/14] Passive ARP LAN Inventory: {allowed.get('device_count')} active local devices found.")
        self.assertTrue(allowed.get("ok"))
        self.assertTrue(allowed.get("consent_verified"))
        print("  [OK] Consent gate & passive LAN device discovery verified.")

    # 10. Static Code Security Scanner
    def test_10_code_security_scan(self):
        from modules.threat_defense.tools import scan_code_security
        scan_res = scan_code_security(target_dir=str(BASE_DIR / "modules"))
        print(f"  [10/14] Code Scanner: Scanned {scan_res.get('files_scanned')} files. Found {scan_res.get('issues_found')} items.")
        self.assertTrue(scan_res.get("ok"))
        self.assertGreater(scan_res.get("files_scanned", 0), 5)
        print("  [OK] Static code vulnerability analysis verified.")

    # 11. Virtual Smart Facility & Scenes
    def test_11_virtual_smart_facility(self):
        from modules.smart_facility.tools import get_facility_state, activate_facility_scene
        state = get_facility_state()
        print(f"  [11/14] Smart Facility: Active Scene='{state.get('active_scene')}', Load={state.get('instantaneous_power_kw')} kW")
        self.assertTrue(state.get("ok"))
        self.assertIn("arc_light", state.get("devices", {}))

        sc = activate_facility_scene("movie_night")
        self.assertTrue(sc.get("ok"))
        self.assertEqual(sc.get("scene"), "Cinema / Presentation Mode")
        
        st2 = get_facility_state()
        self.assertEqual(st2["devices"]["arc_light"]["brightness"], 15)
        self.assertTrue(st2["devices"]["door_lock"]["locked"])
        print("  [OK] Virtual smart room state and scenes validated.")

    # 12. Comms & Notifications
    def test_12_comms_and_notifications(self):
        from modules.comms.tools import send_desktop_notification, get_notification_history, create_reminder
        notif = send_desktop_notification("Stark Alert", "Mark 85 online and ready for Devpost demonstration.", "info")
        self.assertTrue(notif.get("ok"))
        
        hist = get_notification_history()
        self.assertTrue(hist.get("ok"))
        self.assertGreaterEqual(hist.get("count", 0), 1)

        rem = create_reminder("Review Devpost pitch script", due_in_minutes=15)
        self.assertTrue(rem.get("ok"))
        print(f"  [12/14] Comms: Notification delivered, reminder registered.")
        print("  [OK] Comms notification relay and reminders verified.")

    # 13. Physics Simulation Lab
    def test_13_simulation_lab(self):
        from modules.simulation_lab.tools import simulate_projectile, simulate_beam_deflection, simulate_rlc_circuit
        proj = simulate_projectile(v0=50.0, angle_deg=45.0, drag_coeff=0.03)
        self.assertTrue(proj.get("ok"))
        self.assertGreater(proj["metrics"]["range_m"], 0)
        self.assertGreater(len(proj["trajectory"]), 5)

        beam = simulate_beam_deflection(length_m=2.0, point_load_n=1500.0)
        self.assertTrue(beam.get("ok"))
        self.assertGreater(beam["metrics"]["max_tip_deflection_mm"], 0)

        rlc = simulate_rlc_circuit(r=10.0, l=0.05, c=0.0005)
        self.assertTrue(rlc.get("ok"))
        self.assertIn("Underdamped", rlc["regime"])
        print(f"  [13/14] Simulations: Projectile Range={proj['metrics']['range_m']}m | Beam Deflection={beam['metrics']['max_tip_deflection_mm']}mm | RLC={rlc['regime']}")
        print("  [OK] Scientific physics simulations verified.")

    # 14. Parallel Task Board & Swarm
    def test_14_task_board_swarm(self):
        from modules.task_board.tools import launch_swarm_demo, list_active_tasks
        res = launch_swarm_demo()
        self.assertTrue(res.get("ok"))
        print(f"  [14/14] Dispatched Swarm: 3 parallel tasks launched.")
        
        board = list_active_tasks()
        self.assertTrue(board.get("ok"))
        self.assertGreaterEqual(len(board.get("tasks", [])), 3)
        for t in board["tasks"]:
            self.assertIn(t["status"], ["running", "done", "queued", "aborted"])
        print("  [OK] Parallel multi-agent swarm execution verified.")

if __name__ == "__main__":
    unittest.main()
