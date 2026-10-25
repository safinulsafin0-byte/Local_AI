from config import REQUIRE_CONFIRMATION_FOR
from tools import file_ops, system_ops


# ============================================================
# TOOL DESCRIPTIONS
# ============================================================

TOOL_DESCRIPTIONS = """
You are controlling a Windows computer.

AVAILABLE TOOLS:

FILESYSTEM:
filesystem.list_dir(path)
filesystem.read_file(path)
filesystem.create_file(path, content)
filesystem.create_folder(path)
filesystem.write_file(path, content)
filesystem.rename(path, new_name)
filesystem.move(path, destination)
filesystem.copy(path, destination)
filesystem.delete_file(path)
filesystem.delete_folder(path)
filesystem.search_files(root, pattern)

SYSTEM:
system.open_app(command)
system.open_path(path)
system.type_text(text)
system.press(key)
system.hotkey(keys)
system.click(x, y, button)
system.scroll(amount)
system.screenshot(path)
system.clipboard_set(text)
system.system_status()
system.shutdown()
system.cancel_shutdown()

BROWSER:
browser.open(url)
browser.back()
browser.forward()
browser.scroll(amount)
browser.click_text(text)
browser.type(selector, text)
browser.search(query)
browser.page_text()

BROWSER VIDEO CONTROL:
browser.play_video()
browser.pause_video()
browser.toggle_play_pause()
browser.mute_video()
browser.unmute_video()


IMPORTANT BROWSER RULES:

- If the user says "open YouTube", use:
  browser.open(url="https://www.youtube.com")

- If the user says "open Google", use:
  browser.open(url="https://www.google.com")

- If the user says "open Facebook", use:
  browser.open(url="https://www.facebook.com")

- If the user says "open Gmail", use:
  browser.open(url="https://mail.google.com")

- If the user says "open Chrome", use:
  system.open_app(command="chrome")

- Website requests should use browser.open, NOT system.open_app.

VIDEO CONTROL RULES:

- If the user says "pause the video", use:
  browser.pause_video()

- If the user says "pause video", use:
  browser.pause_video()

- If the user says "play the video", use:
  browser.play_video()

- If the user says "resume the video", use:
  browser.play_video()

- If the user says "continue the video", use:
  browser.play_video()

- If the user says "toggle video", use:
  browser.toggle_play_pause()

- If the user says "play or pause the video", use:
  browser.toggle_play_pause()

- If the user says "mute the video", use:
  browser.mute_video()

- If the user says "unmute the video", use:
  browser.unmute_video()

- NEVER use browser.open() with a javascript: URL.

- NEVER use browser.open() with:
  javascript:
  data:
  file:

- NEVER generate JavaScript URLs such as:
  javascript:void(document.getElementsByTagName('video')[0].pause())

- Video actions must use the dedicated browser video tools.

- After a tool executes, trust the actual tool result.
- NEVER claim an action succeeded if the tool returned ERROR.
- NEVER invent a successful result.
"""


# ============================================================
# WEBSITE ALIASES
# ============================================================

WEBSITE_ALIASES = {
    "youtube": "https://www.youtube.com",
    "youtube.com": "https://www.youtube.com",

    "google": "https://www.google.com",
    "google.com": "https://www.google.com",

    "facebook": "https://www.facebook.com",
    "facebook.com": "https://www.facebook.com",

    "gmail": "https://mail.google.com",
    "gmail.com": "https://mail.google.com",

    "github": "https://github.com",
    "github.com": "https://github.com",

    "reddit": "https://www.reddit.com",
    "reddit.com": "https://www.reddit.com",

    "instagram": "https://www.instagram.com",
    "instagram.com": "https://www.instagram.com",

    "twitter": "https://twitter.com",
    "twitter.com": "https://twitter.com",

    "x": "https://x.com",
    "x.com": "https://x.com",
}


# ============================================================
# TOOL NAME ALIASES
# ============================================================

TOOL_ALIASES = {

    # -------------------------
    # SYSTEM
    # -------------------------

    "screenshot": "system.screenshot",
    "open_app": "system.open_app",
    "open_path": "system.open_path",
    "type_text": "system.type_text",
    "press": "system.press",
    "hotkey": "system.hotkey",
    "click": "system.click",
    "scroll": "system.scroll",
    "clipboard_set": "system.clipboard_set",
    "system_status": "system.system_status",
    "shutdown": "system.shutdown",
    "cancel_shutdown": "system.cancel_shutdown",

    # -------------------------
    # BROWSER & WEBSITES
    # -------------------------
    "browser_open": "browser.open",
    "browser.open": "browser.open",
    "open_browser": "browser.open",
    "browser_search": "browser.search",

    # -------------------------
    # YOUTUBE
    # -------------------------
    "youtube_search": "youtube.search",
    "youtube_play": "youtube.play",
    "youtube_pause": "youtube.pause",
    "youtube_seek": "youtube.seek",
    "youtube_mute": "youtube.mute",
    "youtube_next": "youtube.next",

    # -------------------------
    # WEB & SEARCH
    # -------------------------
    "web_search": "web.search",
    "web_research": "web.research",
    "research": "web.research",
    "news": "web.news",
    "web_news": "web.news",
    "weather": "web.weather",

    # -------------------------
    # BROWSER VIDEO
    # -------------------------

    "play_video": "browser.play_video",
    "pause_video": "browser.pause_video",
    "toggle_play_pause": "browser.toggle_play_pause",
    "mute_video": "browser.mute_video",
    "unmute_video": "browser.unmute_video",

    # Common variations from LLM
    "browser.play": "browser.play_video",
    "browser.pause": "browser.pause_video",
    "browser.resume_video": "browser.play_video",
    "browser.resume": "browser.play_video",
    "browser.continue_video": "browser.play_video",
    "browser.toggle_video": "browser.toggle_play_pause",

    # -------------------------
    # IMAGE GENERATION
    # -------------------------
    "image_generate": "image.generate",
    "generate_image": "image.generate",
    "image.generate": "image.generate",
    "image_gen": "image.generate",

    # -------------------------
    # FILESYSTEM
    # -------------------------
    "filesystem_create_file": "filesystem.create_file",
    "filesystem.create.file": "filesystem.create_file",
    "create_file": "filesystem.create_file",
    "create.file": "filesystem.create_file",
    "make_file": "filesystem.create_file",
    "new_file": "filesystem.create_file",
    "file_create": "filesystem.create_file",

    "filesystem_create_folder": "filesystem.create_folder",
    "filesystem.create.folder": "filesystem.create_folder",
    "create_folder": "filesystem.create_folder",
    "create.folder": "filesystem.create_folder",
    "make_folder": "filesystem.create_folder",
    "mkdir": "filesystem.create_folder",

    "filesystem_read_file": "filesystem.read_file",
    "filesystem.read.file": "filesystem.read_file",
    "read_file": "filesystem.read_file",
    "read.file": "filesystem.read_file",
    "cat": "filesystem.read_file",

    "filesystem_write_file": "filesystem.write_file",
    "filesystem.write.file": "filesystem.write_file",
    "write_file": "filesystem.write_file",
    "write.file": "filesystem.write_file",

    "filesystem_append_file": "filesystem.append_file",
    "filesystem.append.file": "filesystem.append_file",
    "append_file": "filesystem.append_file",
    "append.file": "filesystem.append_file",

    "filesystem_delete_file": "filesystem.delete_file",
    "filesystem.delete.file": "filesystem.delete_file",
    "delete_file": "filesystem.delete_file",
    "delete.file": "filesystem.delete_file",
    "remove_file": "filesystem.delete_file",

    "filesystem_delete_folder": "filesystem.delete_folder",
    "filesystem.delete.folder": "filesystem.delete_folder",
    "delete_folder": "filesystem.delete_folder",
    "delete.folder": "filesystem.delete_folder",
    "remove_folder": "filesystem.delete_folder",

    "filesystem_list_dir": "filesystem.list_dir",
    "filesystem.list.dir": "filesystem.list_dir",
    "list_dir": "filesystem.list_dir",
    "list.dir": "filesystem.list_dir",
    "ls": "filesystem.list_dir",
    "dir": "filesystem.list_dir",

    "filesystem_rename": "filesystem.rename",
    "filesystem.rename": "filesystem.rename",
    "rename": "filesystem.rename",

    "filesystem_move": "filesystem.move",
    "filesystem.move": "filesystem.move",
    "move": "filesystem.move",

    "filesystem_copy": "filesystem.copy",
    "filesystem.copy": "filesystem.copy",
    "copy": "filesystem.copy",

    "filesystem_search_files": "filesystem.search_files",
    "filesystem.search.files": "filesystem.search_files",
    "search_files": "filesystem.search_files",
    "search.files": "filesystem.search_files",
    "find_files": "filesystem.search_files",

    "run_command": "system.run_shell",
    "system_run_command": "system.run_shell",
    "system.run_command": "system.run_shell",
    "system_run_shell": "system.run_shell",
    "run_shell": "system.run_shell",
    "terminal_run_command": "system.run_shell",
    "terminal.run_command": "system.run_shell",
    "execute_command": "system.run_shell",
    "run_powershell": "system.run_shell",
    "powershell": "system.run_shell",
}


# ============================================================
# EXECUTE TOOL
# ============================================================

def execute_tool_call(call, user_confirmed=False):

    # --------------------------------------------------------
    # Validate input
    # --------------------------------------------------------

    if not isinstance(call, dict):
        return "ERROR: Invalid tool call. Expected a dictionary."

    tool = call.get("tool", "")
    args = call.get("args", {}) or {}

    if not isinstance(args, dict):
        args = {}

    # --------------------------------------------------------
    # Normalize tool name
    # --------------------------------------------------------

    tool = str(tool).strip()

    if not tool:
        return "ERROR: Empty tool name."

    if tool in TOOL_ALIASES:
        tool = TOOL_ALIASES[tool]
    else:
        # Check if tool is using dots instead of underscores, e.g. filesystem.create.file -> filesystem.create_file
        for ns in ("filesystem", "system", "browser", "youtube", "web", "image", "schedule"):
            prefix = f"{ns}."
            if tool.startswith(prefix):
                action = tool[len(prefix):].replace(".", "_")
                candidate = f"{prefix}{action}"
                tool = candidate
                break

    def _normalize_file_args(a):
        res = dict(a)
        if "path" not in res:
            for k in ("file_path", "filepath", "filename", "file", "target", "dest"):
                if k in res:
                    res["path"] = res.pop(k)
                    break
        if "content" not in res:
            for k in ("text", "body", "data"):
                if k in res:
                    res["content"] = res.pop(k)
                    break
        return res

    def _normalize_shell_args(a):
        res = dict(a)
        if "command" not in res:
            for k in ("cmd", "script", "command_line", "input", "code"):
                if k in res:
                    res["command"] = res.pop(k)
                    break
        return res

    # ========================================================
    # WEBSITE FALLBACK
    # ========================================================

    if tool == "system.open_app":

        command = str(
            args.get("command", "")
        ).strip()

        normalized = (
            command
            .lower()
            .strip()
            .rstrip("/")
        )

        normalized = normalized.strip("\"'")

        if normalized in WEBSITE_ALIASES:

            url = WEBSITE_ALIASES[normalized]

            try:

                from browser.browser_agent import browser_tool

                return browser_tool(
                    "open",
                    url=url
                )

            except Exception as e:

                return (
                    f"ERROR: Could not open website "
                    f"{url}: {e}"
                )

    # ========================================================
    # CONFIRMATION
    # ========================================================

    action = tool.split(".")[-1]

    if (
        action in REQUIRE_CONFIRMATION_FOR
        and not user_confirmed
    ):

        return (
            f"CONFIRMATION_NEEDED: "
            f"{action} with args={args}"
        )

    # ========================================================
    # FILESYSTEM
    # ========================================================
    # FILESYSTEM (with resilient name aliasing)
    # ========================================================

    if tool in ("filesystem.list_dir", "filesystem.list.dir", "list_dir", "filesystem_list_dir"):
        return file_ops.list_dir(**_normalize_file_args(args))

    if tool in ("filesystem.read_file", "filesystem.read.file", "read_file", "filesystem_read_file"):
        return file_ops.read_file(**_normalize_file_args(args))

    if tool in ("filesystem.create_file", "filesystem.create.file", "create_file", "filesystem_create_file"):
        return file_ops.create_file(**_normalize_file_args(args))

    if tool in ("filesystem.create_folder", "filesystem.create.folder", "create_folder", "filesystem_create_folder"):
        return file_ops.create_folder(**_normalize_file_args(args))

    if tool in ("filesystem.write_file", "filesystem.write.file", "write_file", "filesystem_write_file"):
        return file_ops.write_file(**_normalize_file_args(args))

    if tool in ("filesystem.append_file", "filesystem.append.file", "append_file", "filesystem_append_file"):
        return file_ops.append_file(**_normalize_file_args(args))

    if tool in ("filesystem.rename", "rename"):
        return file_ops.rename(**args)

    if tool in ("filesystem.move", "move"):
        return file_ops.move(**args)

    if tool in ("filesystem.copy", "copy"):
        return file_ops.copy(**args)

    if tool in ("filesystem.delete_file", "filesystem.delete.file", "delete_file", "filesystem_delete_file"):
        return file_ops.delete_file(**_normalize_file_args(args))

    if tool in ("filesystem.delete_folder", "filesystem.delete.folder", "delete_folder", "filesystem_delete_folder"):
        return file_ops.delete_folder(**_normalize_file_args(args))

    if tool in ("filesystem.search_files", "search_files"):
        return file_ops.search_files(**args)

    # ========================================================
    # SYSTEM
    # ========================================================

    if tool == "system.open_app":

        return system_ops.open_app(
            **args
        )

    if tool == "system.open_path":

        return system_ops.open_path(
            **args
        )

    if tool == "system.type_text":

        return system_ops.type_text(
            **args
        )

    if tool == "system.press":

        return system_ops.press(
            **args
        )

    if tool == "system.hotkey":

        return system_ops.hotkey(
            **args
        )

    if tool == "system.click":

        return system_ops.click(
            **args
        )

    if tool == "system.scroll":

        return system_ops.scroll(
            **args
        )

    if tool == "system.screenshot":

        return system_ops.screenshot(
            **args
        )

    if tool == "system.clipboard_set":

        return system_ops.clipboard_set(
            **args
        )

    if tool == "system.system_status":

        return system_ops.system_status()

    if tool == "system.shutdown":

        return system_ops.shutdown()

    if tool == "system.cancel_shutdown":

        return system_ops.cancel_shutdown()

    if tool in ("system.run_shell", "run_shell", "run_command", "system.run_command"):
        return system_ops.run_shell(
            **_normalize_shell_args(args)
        )

    # ========================================================
    # CENTRAL TOOL REGISTRY
    # ========================================================

    try:
        from tools.registry import registry
        reg_result = registry.execute(tool, args, confirmed=user_confirmed)
        if not reg_result.startswith("ERROR: Unknown tool"):
            return reg_result
    except Exception as e:
        pass

    # ========================================================
    # BROWSER
    # ========================================================

    if tool.startswith("browser."):

        from browser.browser_agent import browser_tool

        action = tool.split(
            ".",
            1
        )[1]

        try:

            return browser_tool(
                action,
                **args
            )

        except Exception as e:

            return (
                f"ERROR: Browser action "
                f"{action} failed: {e}"
            )


    # ========================================================
    # UNKNOWN TOOL
    # ========================================================

    return (
        f"ERROR: Unknown tool: {tool}"
    )