import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding='utf-8')
from tools.system_ops import open_app, close_app

targets = ['cmd', 'powershell', 'terminal', 'notepad', 'calculator']
print("==================================================")
print("VERIFIED APP LAUNCHER & WINDOW TITLES TEST")
print("==================================================")
for target in targets:
    res = open_app(target)
    print(f"[{target.upper()}]: {res}")
    # Close gracefully
    if target in ('notepad', 'calculator'):
        close_app(target)
print("==================================================")

