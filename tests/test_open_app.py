import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding='utf-8')
from tools.system_ops import open_app, close_app

targets = ['cmd', 'powershell', 'terminal', 'notepad', 'calculator']
for target in targets:
    res = open_app(target)
    print(f'open_app("{target}") -> {res}')
    time.sleep(0.5)
    close_app(target)
    time.sleep(0.5)
