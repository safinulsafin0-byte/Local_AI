import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')

token = 'auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA'
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

msg = 'create a file name "Demo.txt" in "D:\\personal-ai-full" and write " Ok jarvis working perfectly"'
payload = {'message': msg, 'mode': 'agent', 'stream': False}
r = requests.post('http://127.0.0.1:8765/api/v1/chat', headers=headers, json=payload, timeout=20)
print('API Response:', r.json().get('response'))

from pathlib import Path
p = Path("D:/personal-ai-full/Demo.txt")
print("Verified on disk exists?", p.is_file(), "Content:", repr(p.read_text(encoding='utf-8')))

