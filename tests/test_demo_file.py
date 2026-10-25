import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intent.engine import IntentEngine
from tools import file_ops

msg = 'create a file name "Demo.txt" in "D:\\personal-ai-full" and write " Ok jarvis working perfectly"'
ie = IntentEngine()
res = ie.parse(msg, use_llm=False)
print("Intent:", res.intent, res.parameters)
if res.intent == "filesystem" and res.parameters.get("action") == "create_file":
    r = file_ops.create_file(res.parameters["path"], res.parameters["content"])
    print("File op result:", r)
    
demo_p = Path("D:/personal-ai-full/Demo.txt")
print("Demo.txt exists?", demo_p.is_file())
if demo_p.is_file():
    print("Content:", repr(demo_p.read_text(encoding="utf-8")))

