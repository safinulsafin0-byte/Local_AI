import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from intent.fast_rules import match_fast_rules

sys.stdout.reconfigure(encoding='utf-8')

tests = [
    'run python --version',
    'create a file name "Demo.txt" in "D:\\personal-ai-full" and write " Ok jarvis working perfectly"',
    'create file D:\\jarvis_test\\sample.txt with content hello',
    'create folder D:\\jarvis_test',
    'delete file D:\\jarvis_test\\sample.txt',
    'read file D:\\jarvis_test\\sample.txt',
    'list files in D:\\jarvis_test',
    'volume set to 50%',
    'set volume to 50%',
    'volume 30',
    'volume tirish koro',
    'ভলিউম ৩০ করো',
    'what is the volume',
    'take a screenshot',
    'bitcoin price',
    'latest python version',
    'prime minister of bangladesh',
]

for t in tests:
    res = match_fast_rules(t)
    print(f"PASS: {t} -> {res['intent']} ({res.get('parameters')})" if res else f"FAIL: {t}")
