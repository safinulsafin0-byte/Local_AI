import subprocess
import re
from pathlib import Path

def test_exec(command, cwd="D:\\personal-ai-full"):
    # If user ran `cd` or `chdir` or a drive letter like `C:`:
    # We can detect and support drive switch like `C:` directly, or let PowerShell handle it!
    # In PowerShell, running `C:` or `D:` changes drive just like in cmd if Set-Location is used, or PowerShell syntax:
    # "Set-Location C:\"
    clean_cmd = command.strip()
    
    # Check if bare drive letter like "C:" or "D:"
    if re.match(r"^[a-zA-Z]:$", clean_cmd):
        drive = clean_cmd.upper() + "\\"
        if Path(drive).exists():
            return {
                "ok": True,
                "exit_code": 0,
                "output": "",
                "cwd": drive,
                "command": command
            }
        else:
            return {
                "ok": False,
                "exit_code": 1,
                "output": f"The system cannot find the drive specified: {clean_cmd}",
                "cwd": cwd,
                "command": command
            }

    # Handle cls / clear
    if clean_cmd.lower() in ("cls", "clear"):
        return {
            "ok": True,
            "exit_code": 0,
            "output": "",
            "clear": True,
            "cwd": cwd,
            "command": command
        }

    # Handle bare 'cd' or 'chdir' or 'pwd' (like in Windows CMD: displays current directory)
    if clean_cmd.lower() in ("cd", "chdir", "pwd"):
        return {
            "ok": True,
            "exit_code": 0,
            "output": cwd,
            "cwd": cwd,
            "command": command
        }

    # Wrap with PWD reporting
    wrapper = f"$ErrorActionPreference = 'Continue'; {clean_cmd}\nWrite-Output \"`n__JARVIS_CWD__:$($PWD.Path)\""
    
    res = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", wrapper],
        capture_output=True,
        text=True,
        cwd=cwd
    )
    
    stdout = res.stdout
    stderr = res.stderr
    
    new_cwd = cwd
    m = re.search(r"__JARVIS_CWD__:(.+?)(?:\r?\n|$)", stdout)
    if m:
        candidate_cwd = m.group(1).strip()
        if candidate_cwd and Path(candidate_cwd).exists():
            new_cwd = candidate_cwd
        stdout = re.sub(r"__JARVIS_CWD__:.+?(?:\r?\n|$)", "", stdout).strip()

    combined = stdout + ("\n" + stderr if stderr else "")
    return {
        "ok": res.returncode == 0,
        "exit_code": res.returncode,
        "output": combined.strip(),
        "cwd": new_cwd,
        "command": command
    }

if __name__ == "__main__":
    print("1. Testing 'dir' in D:\\personal-ai-full:")
    r1 = test_exec("dir", "D:\\personal-ai-full")
    print("New cwd:", r1["cwd"])
    print("Output lines:", len(r1["output"].splitlines()))

    print("\n2. Testing 'cd C:\\' from D:\\personal-ai-full:")
    r2 = test_exec("cd C:\\", "D:\\personal-ai-full")
    print("New cwd:", r2["cwd"])
    print("Output:", r2["output"])

    print("\n3. Testing bare 'cd' in C:\\:")
    r3 = test_exec("cd", r2["cwd"])
    print("Bare cd output:", r3["output"])

    print("\n4. Testing 'python -c \"print(\\'hello python\\')\"':")
    r4 = test_exec('python -c "print(\'hello python\')"', "D:\\personal-ai-full")
    print("Python output:", r4["output"])

    print("\n5. Testing 'whoami':")
    r5 = test_exec("whoami", "D:\\personal-ai-full")
    print("Whoami output:", r5["output"])

    print("\n6. Testing 'cls':")
    r6 = test_exec("cls", "D:\\personal-ai-full")
    print("Cls output:", r6)
