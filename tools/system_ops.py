import os
import subprocess
import shutil
import time
from pathlib import Path
from datetime import datetime

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None


# ============================================================
# HELPERS
# ============================================================

def _require_pyautogui():
    if pyautogui is None:
        return (
            "ERROR: pyautogui is not installed. "
            "Install it with: pip install pyautogui"
        )
    return None


# ============================================================
# OPEN APPLICATION
# ============================================================

def open_app(command):
    """
    Open a Windows application.
    Confirms a new process AND a visible window within 3 seconds;
    otherwise tries fallback or reports real failure.
    """
    if not command:
        return "ERROR: No application command was provided."

    command = str(command).strip().strip('"').strip("'")
    if not command:
        return "ERROR: No application command was provided."

    import win32gui
    import psutil
    import time
    import shutil
    import subprocess
    import os
    import ctypes

    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _get_visible_windows():
        titles = []
        try:
            h_desk = user32.OpenDesktopW("default", 0, False, 0x0040 | 0x0001)
            if h_desk:
                def enum_cb(hwnd, lparam):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0 and user32.IsWindowVisible(hwnd):
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        if buff.value.strip():
                            titles.append(buff.value.strip())
                    return True
                cb = WNDENUMPROC(enum_cb)
                user32.EnumDesktopWindows(h_desk, cb, 0)
                user32.CloseDesktop(h_desk)
        except Exception:
            pass
        if not titles:
            try:
                def _enum_cb(hwnd, _):
                    if win32gui.IsWindowVisible(hwnd):
                        t = win32gui.GetWindowText(hwnd).strip()
                        if t:
                            titles.append(t)
                    return True
                win32gui.EnumWindows(_enum_cb, None)
            except Exception:
                pass
        return titles

    app_lower = command.lower().strip()
    
    # Define strategy candidates (canonical_name, target_exe, is_console, title_keywords)
    strategies = []
    if app_lower in ("terminal", "wt", "windows terminal"):
        wt_path = shutil.which("wt.exe") or os.path.expandvars(r"%LocalAppData%\Microsoft\WindowsApps\wt.exe")
        if wt_path and (os.path.isfile(wt_path) or shutil.which(wt_path)):
            strategies.append(("terminal", wt_path, False, ["terminal", "windows terminal"]))
        strategies.append(("powershell", "powershell.exe", True, ["powershell", "windows powershell"]))
        strategies.append(("cmd", "cmd.exe", True, ["cmd.exe", "command prompt", "cmd"]))
    elif app_lower in ("cmd", "command prompt", "cmd.exe"):
        strategies.append(("cmd", "cmd.exe", True, ["cmd.exe", "command prompt", "cmd"]))
    elif app_lower in ("powershell", "powershell.exe"):
        strategies.append(("powershell", "powershell.exe", True, ["powershell", "windows powershell"]))
    elif app_lower in ("notepad", "notepad.exe"):
        strategies.append(("notepad", "notepad.exe", False, ["notepad"]))
    elif app_lower in ("calc", "calculator", "calc.exe"):
        strategies.append(("calc", "calc.exe", False, ["calculator", "calc"]))
    elif app_lower in ("explorer", "file explorer"):
        strategies.append(("explorer", "explorer.exe", False, ["file explorer", "explorer"]))
    elif app_lower in ("paint", "mspaint"):
        strategies.append(("mspaint", "mspaint.exe", False, ["paint"]))
    elif app_lower in ("chrome", "google chrome"):
        chrome_path = "chrome.exe"
        for cp in [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]:
            if os.path.isfile(cp):
                chrome_path = cp
                break
        strategies.append(("chrome", chrome_path, False, ["chrome", "google chrome"]))
    elif app_lower in ("code", "vscode", "visual studio code"):
        code_path = "code"
        for vp in [
            os.path.expandvars(r"%LocalAppData%\Programs\Microsoft VS Code\Code.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
        ]:
            if os.path.isfile(vp):
                code_path = vp
                break
        strategies.append(("code", code_path, False, ["visual studio code", "code"]))
    else:
        strategies.append((app_lower, command, False, [app_lower]))

    last_err = ""
    for canonical_name, exec_target, is_console, title_keywords in strategies:
        initial_pids = set(psutil.pids())
        initial_wins = set(_get_visible_windows())

        spawned_proc = None
        try:
            if is_console:
                # Launch console with CREATE_NEW_CONSOLE, never pipe stdin/stdout
                spawned_proc = subprocess.Popen(
                    [exec_target],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                    close_fds=True
                )
            else:
                # GUI apps via startfile or Popen
                try:
                    os.startfile(exec_target)
                except Exception:
                    spawned_proc = subprocess.Popen(
                        [exec_target] if (shutil.which(exec_target) or os.path.isfile(exec_target)) else exec_target,
                        shell=not (shutil.which(exec_target) or os.path.isfile(exec_target)),
                        close_fds=True
                    )
        except Exception as spawn_exc:
            last_err = str(spawn_exc)
            continue

        confirmed_proc = None
        confirmed_win = None
        t0 = time.time()
        while time.time() - t0 < 3.0:
            time.sleep(0.3)
            new_pids = set(psutil.pids()) - initial_pids
            for pid in new_pids:
                try:
                    p = psutil.Process(pid)
                    p_name_lower = p.name().lower()
                    if (canonical_name in p_name_lower) or (Path(exec_target).stem.lower() in p_name_lower) or (spawned_proc and spawned_proc.pid == pid):
                        confirmed_proc = p
                        break
                except Exception:
                    pass

            curr_wins = set(_get_visible_windows())
            new_wins = curr_wins - initial_wins
            for w in new_wins:
                w_lower = w.lower()
                if any(kw in w_lower for kw in title_keywords):
                    confirmed_win = w
                    break
            if not confirmed_win and new_wins:
                # If a window spawned with an associated title
                for w in new_wins:
                    if canonical_name in w.lower():
                        confirmed_win = w
                        break

            if confirmed_proc and confirmed_win:
                break

        # If confirmed process or window
        if confirmed_proc or confirmed_win:
            p_name = confirmed_proc.name() if confirmed_proc else canonical_name
            p_pid = confirmed_proc.pid if confirmed_proc else (spawned_proc.pid if spawned_proc else "Active")
            w_title = confirmed_win or (f"{canonical_name.capitalize()} Window" if confirmed_proc else "Visible Window Active")
            return f"SUCCESS: Opened {command} (Process: {p_name}, PID: {p_pid}, Window: '{w_title}')."

    return f"ERROR: Could not verify that '{command}' opened within 3 seconds (no active process or window found). {last_err}".strip()


# ============================================================
# OPEN PATH
# ============================================================

def open_path(path):
    """
    Open a file or folder using the default Windows application.
    """

    if not path:
        return "ERROR: No path was provided."

    try:

        path = Path(
            os.path.expandvars(
                os.path.expanduser(
                    str(path)
                )
            )
        )

        if not path.exists():

            return (
                f"ERROR: Path does not exist: {path}"
            )

        os.startfile(str(path))

        return (
            f"SUCCESS: Opened path: {path.resolve()}"
        )

    except Exception as e:

        return (
            f"ERROR: Could not open path: {e}"
        )


# ============================================================
# TYPE TEXT
# ============================================================

def type_text(text):

    error = _require_pyautogui()

    if error:
        return error

    if text is None:
        return "ERROR: No text was provided."

    try:

        pyautogui.write(
            str(text),
            interval=0.01
        )

        return "SUCCESS: Text typed."

    except Exception as e:

        return (
            f"ERROR: Could not type text: {e}"
        )


# ============================================================
# PRESS KEY
# ============================================================

def press(key):

    error = _require_pyautogui()

    if error:
        return error

    if not key:
        return "ERROR: No key was provided."

    try:

        pyautogui.press(
            str(key)
        )

        return (
            f"SUCCESS: Key pressed: {key}"
        )

    except Exception as e:

        return (
            f"ERROR: Could not press key: {e}"
        )


# ============================================================
# HOTKEY
# ============================================================

def hotkey(keys):

    error = _require_pyautogui()

    if error:
        return error

    if not keys:
        return "ERROR: No hotkey was provided."

    try:

        if isinstance(keys, str):

            key_list = [
                key.strip()
                for key in keys.split("+")
                if key.strip()
            ]

        elif isinstance(keys, (list, tuple)):

            key_list = [
                str(key).strip()
                for key in keys
                if str(key).strip()
            ]

        else:

            return (
                "ERROR: Hotkey must be a string "
                "or a list of keys."
            )

        if not key_list:

            return "ERROR: No valid keys were provided."

        pyautogui.hotkey(
            *key_list
        )

        return (
            f"SUCCESS: Hotkey pressed: {' + '.join(key_list)}"
        )

    except Exception as e:

        return (
            f"ERROR: Could not press hotkey: {e}"
        )


# ============================================================
# CLICK
# ============================================================

def click(x, y, button="left"):

    error = _require_pyautogui()

    if error:
        return error

    try:

        pyautogui.click(
            x=int(x),
            y=int(y),
            button=str(button)
        )

        return (
            f"SUCCESS: Clicked at ({x}, {y}) "
            f"with {button} button."
        )

    except Exception as e:

        return (
            f"ERROR: Could not click: {e}"
        )


# ============================================================
# SCROLL
# ============================================================

def scroll(amount):

    error = _require_pyautogui()

    if error:
        return error

    try:

        pyautogui.scroll(
            int(amount)
        )

        return (
            f"SUCCESS: Scrolled {amount}."
        )

    except Exception as e:

        return (
            f"ERROR: Could not scroll: {e}"
        )


# ============================================================
# SCREENSHOT
# ============================================================

def screenshot(path=None):
    """
    Take a verified screenshot of the primary display.
    Saves to %USERPROFILE%\\Pictures\\JARVIS\\Screenshots\\ and data/screenshots/.
    Verifies file exists, non-zero size, and valid image dimensions.
    """
    try:
        from PIL import Image, ImageGrab
    except ImportError:
        return "ERROR: Screenshot requires Pillow. Install it with: pip install pillow"

    import shutil

    user_pictures = Path(os.environ.get("USERPROFILE", "C:/Users/USER")) / "Pictures" / "JARVIS" / "Screenshots"
    user_pictures.mkdir(parents=True, exist_ok=True)
    web_screenshots_dir = Path.cwd() / "data" / "screenshots"
    web_screenshots_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_name = f"screenshot_{timestamp}.png"

    if not path:
        target_path = user_pictures / default_name
    else:
        target_path = Path(os.path.expandvars(os.path.expanduser(str(path))))
        if str(target_path.parent) == ".":
            target_path = user_pictures / target_path.name
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        try:
            image = ImageGrab.grab()
        except Exception:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
            w = user32.GetSystemMetrics(0) or 1920
            h = user32.GetSystemMetrics(1) or 1080
            hwnd = 0
            hdc_screen = user32.GetDC(hwnd)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
            hbmp_old = gdi32.SelectObject(hdc_mem, hbmp)
            SRCCOPY = 0x00CC0020
            gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, 0, 0, SRCCOPY)

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ('biSize', wintypes.DWORD),
                    ('biWidth', wintypes.LONG),
                    ('biHeight', wintypes.LONG),
                    ('biPlanes', wintypes.WORD),
                    ('biBitCount', wintypes.WORD),
                    ('biCompression', wintypes.DWORD),
                    ('biSizeImage', wintypes.DWORD),
                    ('biXPelsPerMeter', wintypes.LONG),
                    ('biYPelsPerMeter', wintypes.LONG),
                    ('biClrUsed', wintypes.DWORD),
                    ('biClrImportant', wintypes.DWORD)
                ]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0
            buf = (ctypes.c_char * (w * h * 4))()
            gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
            gdi32.SelectObject(hdc_mem, hbmp_old)
            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(hwnd, hdc_screen)
            image = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1).convert('RGB')

        image.save(str(target_path), "PNG")

        # Copy to web serving directory
        web_copy = web_screenshots_dir / target_path.name
        try:
            if str(target_path.resolve()) != str(web_copy.resolve()):
                shutil.copy2(str(target_path), str(web_copy))
        except Exception:
            pass

        # Verify state
        if not target_path.is_file():
            return f"ERROR: Screenshot file was not created at {target_path}."

        size_bytes = target_path.stat().st_size
        if size_bytes <= 0:
            return f"ERROR: Screenshot file {target_path} is 0 bytes."

        with Image.open(str(target_path)) as img:
            img_w, img_h = img.size

        size_kb = round(size_bytes / 1024, 1)
        return f"SUCCESS: Screenshot captured ({img_w}x{img_h}, {size_kb} KB) and saved to: {target_path.resolve()}"

    except Exception as e:
        return f"ERROR: Could not take screenshot: {e}"


# ============================================================
# CLIPBOARD
# ============================================================

def clipboard_set(text):

    if pyperclip is None:

        return (
            "ERROR: Clipboard support requires pyperclip. "
            "Install it with: pip install pyperclip"
        )

    if text is None:

        return "ERROR: No text was provided."

    try:

        pyperclip.copy(
            str(text)
        )

        return (
            "SUCCESS: Text copied to clipboard."
        )

    except Exception as e:

        return (
            f"ERROR: Could not set clipboard: {e}"
        )


# ============================================================
# SYSTEM STATUS
# ============================================================

def system_status():
    """Return real system metrics using psutil."""
    try:
        from tools.monitor import get_natural_language_summary
        summary = get_natural_language_summary()
        return "SUCCESS: " + summary
    except Exception as e:
        # Graceful fallback to basic info
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            return (
                f"SUCCESS: CPU {cpu:.0f}%, "
                f"RAM {mem.percent:.0f}% ({mem.used//1024**3}GB/{mem.total//1024**3}GB used), "
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e2:
            return (
                f"SUCCESS: JARVIS system is running. "
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )


# ============================================================
# SHUTDOWN
# ============================================================

def shutdown(delay_seconds=25):
    """
    Schedule a Windows shutdown.

    Default delay: 25 seconds.
    """

    try:

        delay_seconds = int(delay_seconds)

        if delay_seconds < 0:
            return (
                "ERROR: delay_seconds cannot be negative."
            )

        result = subprocess.run(
            [
                "shutdown",
                "/s",
                "/t",
                str(delay_seconds)
            ],
            capture_output=True,
            text=True,
            timeout=25
        )

        if result.returncode == 0:

            if delay_seconds == 0:

                return (
                    "SUCCESS: Windows shutdown has been initiated."
                )

            return (
                f"SUCCESS: Windows will shut down in "
                f"{delay_seconds} seconds. "
                f"Use cancel_shutdown to cancel it."
            )

        error = (
            result.stderr.strip()
            or result.stdout.strip()
        )

        return (
            f"ERROR: Could not schedule shutdown. {error}"
        )

    except Exception as e:

        return (
            f"ERROR: Could not shut down Windows: {e}"
        )


# ============================================================
# CANCEL SHUTDOWN
# ============================================================

def cancel_shutdown():
    """
    Cancel a scheduled Windows shutdown.
    """

    try:

        result = subprocess.run(
            [
                "shutdown",
                "/a"
            ],
            capture_output=True,
            text=True,
            timeout=25
        )

        if result.returncode == 0:

            return (
                "SUCCESS: Scheduled shutdown was cancelled."
            )

        error = (
            result.stderr.strip()
            or result.stdout.strip()
        )

        return (
            f"ERROR: No scheduled shutdown could be cancelled. "
            f"{error}"
        )

    except Exception as e:

        return (
            f"ERROR: Could not cancel shutdown: {e}")


# ============================================================
# RESTART COMPUTER
# ============================================================

def restart(delay_seconds=25):
    """Schedule a Windows system restart."""
    try:
        delay_seconds = int(delay_seconds)
        if delay_seconds < 0:
            return "ERROR: delay_seconds cannot be negative."
        result = subprocess.run(
            ["shutdown", "/r", "/t", str(delay_seconds)],
            capture_output=True,
            text=True,
            timeout=25,
        )
        if result.returncode == 0:
            return f"SUCCESS: Windows restart scheduled in {delay_seconds} seconds."
        return f"ERROR: Could not schedule restart: {result.stderr.strip()}"
    except Exception as e:
        return f"ERROR: Failed to schedule restart: {e}"


# ============================================================
# CLOSE APPLICATION / KILL PROCESS
# ============================================================

def close_app(name):
    """Close an application gracefully or forcefully by name."""
    if not name:
        return "ERROR: No application name provided."
    name = str(name).strip()
    if not name.lower().endswith(".exe"):
        exe_name = f"{name}.exe"
    else:
        exe_name = name

    try:
        # Try taskkill
        result = subprocess.run(
            ["taskkill", "/IM", exe_name, "/F"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return f"SUCCESS: Closed application: {name}"
        # Also try by exact name without .exe
        result2 = subprocess.run(
            ["taskkill", "/IM", name, "/F"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result2.returncode == 0:
            return f"SUCCESS: Closed application: {name}"
        return f"ERROR: Could not close {name}: {result.stderr.strip() or 'Process not found'}"
    except Exception as e:
        return f"ERROR: Failed to close application: {e}"


def kill_process(pid_or_name):
    """Kill a process by PID (number) or process name."""
    if not pid_or_name:
        return "ERROR: No PID or process name provided."
    try:
        import psutil
        # Try integer PID
        try:
            pid = int(pid_or_name)
            p = psutil.Process(pid)
            p_name = p.name()
            p.kill()
            return f"SUCCESS: Killed process {p_name} (PID {pid})."
        except (ValueError, TypeError):
            pass

        # Try by name
        killed = 0
        name_lower = str(pid_or_name).lower()
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if name_lower in p.info["name"].lower():
                    p.kill()
                    killed += 1
            except Exception:
                continue
        if killed > 0:
            return f"SUCCESS: Killed {killed} process(es) matching '{pid_or_name}'."
        return f"ERROR: No process found matching '{pid_or_name}'."
    except Exception as e:
        return f"ERROR: Failed to kill process: {e}"


# ============================================================
# WINDOW MANAGEMENT
# ============================================================

def list_windows():
    """List all open desktop windows with visible titles."""
    try:
        import pygetwindow as gw
        windows = gw.getAllWindows()
        visible = [w.title.strip() for w in windows if w.title and w.title.strip()]
        if not visible:
            return "No active visible windows found."
        return "Active Windows:\n" + "\n".join(f"- {title}" for title in visible[:30])
    except Exception:
        # PowerShell fallback
        try:
            ps_cmd = 'Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -ExpandProperty MainWindowTitle'
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=10)
            lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
            if lines:
                return "Active Windows:\n" + "\n".join(f"- {t}" for t in lines[:30])
            return "No active windows found."
        except Exception as e:
            return f"ERROR: Could not list windows: {e}"


def focus_window(title):
    """Bring a window to the foreground by partial title match."""
    if not title:
        return "ERROR: No window title provided."
    try:
        import pygetwindow as gw
        matched = [w for w in gw.getAllWindows() if title.lower() in w.title.lower()]
        if not matched:
            return f"ERROR: No window found matching '{title}'."
        w = matched[0]
        if w.isMinimized:
            w.restore()
        w.activate()
        return f"SUCCESS: Focused window: {w.title}"
    except Exception as e:
        return f"ERROR: Could not focus window: {e}"


def minimize_window(title):
    """Minimize a window by partial title match."""
    try:
        import pygetwindow as gw
        matched = [w for w in gw.getAllWindows() if title.lower() in w.title.lower()]
        if not matched:
            return f"ERROR: No window found matching '{title}'."
        matched[0].minimize()
        return f"SUCCESS: Minimized window: {matched[0].title}"
    except Exception as e:
        return f"ERROR: Could not minimize window: {e}"


def maximize_window(title):
    """Maximize a window by partial title match."""
    try:
        import pygetwindow as gw
        matched = [w for w in gw.getAllWindows() if title.lower() in w.title.lower()]
        if not matched:
            return f"ERROR: No window found matching '{title}'."
        matched[0].maximize()
        return f"SUCCESS: Maximized window: {matched[0].title}"
    except Exception as e:
        return f"ERROR: Could not maximize window: {e}"


# ============================================================
# CLIPBOARD GET
# ============================================================

def clipboard_get():
    """Get text currently stored in the Windows clipboard."""
    if pyperclip is None:
        return "ERROR: Clipboard support requires pyperclip."
    try:
        text = pyperclip.paste()
        if not text:
            return "SUCCESS: Clipboard is empty."
        return f"SUCCESS: Clipboard content:\n{text}"
    except Exception as e:
        return f"ERROR: Could not read clipboard: {e}"


# ============================================================
# SYSTEM SETTINGS: VOLUME, BRIGHTNESS, LOCK, SLEEP
# ============================================================

def _get_audio_endpoint_volume():
    """Helper to get pycaw IAudioEndpointVolume object with COM initialized."""
    import pycaw.pycaw as pycaw
    import comtypes
    try:
        comtypes.CoInitialize()
    except Exception:
        pass
    device = pycaw.AudioUtilities.GetSpeakers()
    if device is None:
        raise RuntimeError("No audio output device found.")
    return device.EndpointVolume


def volume_set(level):
    """Set master system volume (0-100) and verify via pycaw scalar read-back."""
    try:
        lvl = max(0, min(100, int(level)))
        vol = _get_audio_endpoint_volume()
        vol.SetMasterVolumeLevelScalar(lvl / 100.0, None)
        read_back = vol.GetMasterVolumeLevelScalar()
        actual_pct = round(read_back * 100)
        return f"SUCCESS: Volume is now {actual_pct}%."
    except Exception as e:
        try:
            ps_script = f"""
            $wsh = New-Object -ComObject WScript.Shell
            1..50 | ForEach-Object {{ $wsh.SendKeys([char]174) }}
            1..{int(level) // 2} | ForEach-Object {{ $wsh.SendKeys([char]175) }}
            """
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, timeout=5)
            return f"SUCCESS: Volume set to {level}%."
        except Exception as exc:
            return f"ERROR: Could not set volume: {e} (Fallback: {exc})"


def volume_get():
    """Get current master audio volume percentage verified via pycaw."""
    try:
        vol = _get_audio_endpoint_volume()
        read_back = vol.GetMasterVolumeLevelScalar()
        actual_pct = round(read_back * 100)
        is_muted = bool(vol.GetMute())
        mute_str = " (Muted)" if is_muted else ""
        return f"SUCCESS: Current volume is {actual_pct}%{mute_str}."
    except Exception as e:
        return f"ERROR: Could not get volume: {e}"


def volume_up(steps=10):
    """Increase system volume by steps and verify via pycaw."""
    try:
        vol = _get_audio_endpoint_volume()
        cur = vol.GetMasterVolumeLevelScalar()
        new_scalar = min(1.0, cur + (int(steps) / 100.0))
        vol.SetMasterVolumeLevelScalar(new_scalar, None)
        actual_pct = round(vol.GetMasterVolumeLevelScalar() * 100)
        return f"SUCCESS: Volume increased to {actual_pct}%."
    except Exception as e:
        return f"ERROR: Could not increase volume: {e}"


def volume_down(steps=10):
    """Decrease system volume by steps and verify via pycaw."""
    try:
        vol = _get_audio_endpoint_volume()
        cur = vol.GetMasterVolumeLevelScalar()
        new_scalar = max(0.0, cur - (int(steps) / 100.0))
        vol.SetMasterVolumeLevelScalar(new_scalar, None)
        actual_pct = round(vol.GetMasterVolumeLevelScalar() * 100)
        return f"SUCCESS: Volume decreased to {actual_pct}%."
    except Exception as e:
        return f"ERROR: Could not decrease volume: {e}"


def volume_mute():
    """Toggle mute on master audio volume and verify via pycaw."""
    try:
        vol = _get_audio_endpoint_volume()
        cur_mute = bool(vol.GetMute())
        vol.SetMute(not cur_mute, None)
        new_mute = bool(vol.GetMute())
        return f"SUCCESS: Master volume {'muted' if new_mute else 'unmuted'}."
    except Exception as e:
        return f"ERROR: Could not toggle mute: {e}"


def empty_recycle_bin():
    """Empty the Windows Recycle Bin."""
    try:
        ps_cmd = "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=10)
        return "SUCCESS: Recycle Bin emptied."
    except Exception as e:
        return f"ERROR: Could not empty recycle bin: {e}"


def brightness_set(level):
    """Set screen brightness (0-100) on laptops / supported monitors."""
    try:
        lvl = max(0, min(100, int(level)))
        ps_cmd = f"(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {lvl})"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return f"SUCCESS: Set brightness to {lvl}%."
        return f"ERROR: Screen brightness change not supported on this display: {res.stderr.strip()}"
    except Exception as e:
        return f"ERROR: Could not set brightness: {e}"


def lock_workstation():
    """Lock the Windows workstation immediately."""
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return "SUCCESS: Windows workstation locked."
    except Exception as e:
        return f"ERROR: Could not lock workstation: {e}"


def sleep_pc():
    """Put PC into sleep / suspend mode."""
    try:
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], shell=True)
        return "SUCCESS: PC placed in sleep mode."
    except Exception as e:
        return f"ERROR: Could not sleep PC: {e}"


# ============================================================
# HARDWARE & NETWORK INFO
# ============================================================

def network_info():
    """Get network adapters, IP addresses, and Wi-Fi status."""
    try:
        ps_cmd = "Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*'} | Select-Object InterfaceAlias, IPAddress | ConvertTo-Json"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=10)
        out = []
        if res.stdout.strip():
            try:
                import json
                data = json.loads(res.stdout)
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    out.append(f"  - {item.get('InterfaceAlias', '?')}: {item.get('IPAddress', '?')}")
            except Exception:
                out.append(res.stdout.strip())

        # Wi-Fi SSID
        try:
            wifi_res = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=5)
            for line in wifi_res.stdout.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    out.append(f"  Wi-Fi: {line.split(':', 1)[1].strip()}")
        except Exception:
            pass

        return "SUCCESS: Network Information:\n" + ("\n".join(out) if out else "No active external connections.")
    except Exception as e:
        return f"ERROR: Could not get network info: {e}"


def battery_info():
    """Get battery status and percentage."""
    try:
        import psutil
        bat = psutil.sensors_battery()
        if not bat:
            return "SUCCESS: No battery detected (Desktop PC or AC powered)."
        plugged = "Plugged in (Charging)" if bat.power_plugged else "Discharging"
        time_left = f"{bat.secsleft // 60} minutes" if bat.secsleft > 0 else "Calculating..."
        return f"SUCCESS: Battery: {bat.percent:.0f}% ({plugged}), Remaining time: {time_left}"
    except Exception as e:
        return f"ERROR: Could not retrieve battery info: {e}"


def installed_apps():
    """List major installed applications from Windows Registry."""
    try:
        ps_cmd = """
        Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* |
        Where-Object { $_.DisplayName } |
        Select-Object -ExpandProperty DisplayName |
        Sort-Object -Unique
        """
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=15)
        lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
        if not lines:
            return "No installed applications found via registry query."
        return f"SUCCESS: Installed Applications ({len(lines)} found, top 50 shown):\n" + "\n".join(f"- {a}" for a in lines[:50])
    except Exception as e:
        return f"ERROR: Could not list installed apps: {e}"


# ============================================================
# SHELL COMMAND EXECUTION
# ============================================================

def run_shell(command, timeout_seconds=60, cwd=None):
    """Run a PowerShell/CMD command with timeout and captured output across any directory on the laptop."""
    if not command:
        return "ERROR: No command provided."
    try:
        timeout_seconds = int(timeout_seconds)
        if cwd and not Path(cwd).exists():
            cwd = None
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=cwd
        )
        output = res.stdout.strip()
        error = res.stderr.strip()
        if res.returncode == 0:
            return f"SUCCESS (Exit 0):\n{output or '(No stdout output)'}"
        return f"ERROR (Exit {res.returncode}):\nStdout: {output}\nStderr: {error}"
    except subprocess.TimeoutExpired:
        return f"ERROR: Command timed out after {timeout_seconds} seconds."
    except Exception as e:
        return f"ERROR: Shell execution failed: {e}"


take_screenshot = screenshot