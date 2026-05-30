from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("PI_TV_CONFIG", BASE_DIR / "config.json"))

DEFAULT_CONFIG: dict[str, Any] = {
    "port": 8080,
    "pin": "",
    "dry_run": "auto",
    "browser_command": "surf",
    "browser_args": ["-F"],
    "browser_process_names": ["surf", "cog", "chromium", "chromium-browser", "firefox-esr"],
    "default_browser_url": "https://lite.duckduckgo.com/lite/",
    "launcher_url": "http://localhost:8080/tv",
    "apps": [
        {
            "id": "youtube",
            "label": "YouTube",
            "url": "https://www.youtube.com/tv",
            "theme": "red",
        },
        {
            "id": "moviehub",
            "label": "Moviehub",
            "url": "https://openmovies.hostingfrompurva.xyz",
            "theme": "violet",
        },
        {
            "id": "browser",
            "label": "Browser",
            "url": "https://lite.duckduckgo.com/lite/",
            "theme": "blue",
        },
    ],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("pi-tv-launcher")

app = Flask(__name__)

LAST_EVENT: dict[str, Any] = {
    "command": "",
    "ok": True,
    "error": "",
    "updated_at": "",
}


def load_config() -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            loaded = json.load(file)
        if isinstance(loaded, dict):
            config.update(loaded)
    return config


CONFIG = load_config()


def dry_run_enabled() -> bool:
    env_value = os.environ.get("PI_TV_DRY_RUN")
    if env_value is not None:
        value = env_value
    else:
        value = CONFIG.get("dry_run", "auto")

    if isinstance(value, bool):
        return value
    if str(value).lower() in {"1", "true", "yes", "on"}:
        return True
    if str(value).lower() in {"0", "false", "no", "off"}:
        return False
    return platform.system() != "Linux" or not os.environ.get("DISPLAY")


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def safe_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def configured_apps() -> list[dict[str, str]]:
    apps = CONFIG.get("apps", [])
    if not isinstance(apps, list):
        return []

    clean_apps = []
    for item in apps:
        if not isinstance(item, dict):
            continue
        app_id = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        url = str(item.get("url") or "").strip()
        theme = str(item.get("theme") or "slate").strip()
        if app_id and label and safe_url(url):
            clean_apps.append({"id": app_id, "label": label, "url": url, "theme": theme})
    return clean_apps


def find_app(app_id: str) -> dict[str, str] | None:
    for item in configured_apps():
        if item["id"] == app_id:
            return item
    return None


def remember_event(command: str, result: dict[str, Any]) -> None:
    LAST_EVENT.update(
        {
            "command": command,
            "ok": bool(result.get("ok")),
            "error": str(result.get("error") or ""),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def require_pin() -> tuple[bool, str]:
    configured_pin = str(CONFIG.get("pin") or "")
    if not configured_pin:
        return True, ""

    supplied_pin = ""
    if request.is_json:
        supplied_pin = str((request.get_json(silent=True) or {}).get("pin") or "")
    supplied_pin = supplied_pin or request.headers.get("X-Pi-TV-PIN", "")

    if supplied_pin != configured_pin:
        return False, "Invalid or missing PIN"
    return True, ""


def command_label(args: list[str]) -> str:
    return " ".join(args)


def run_checked(args: list[str], timeout: int = 8, check: bool = True) -> dict[str, Any]:
    command = args[0]
    if dry_run_enabled():
        log.info("Dry run command: %s", args)
        return {
            "ok": True,
            "dry_run": True,
            "error": "",
            "returncode": 0,
            "stdout": f"Dry run: {command_label(args)}",
            "stderr": "",
        }

    if not command_exists(command):
        log.warning("Missing command: %s", command)
        return {"ok": False, "error": f"Command not found: {command}"}

    try:
        result = subprocess.run(
            args,
            check=check,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": result.returncode == 0,
            "error": "" if result.returncode == 0 else result.stderr.strip() or f"{command} exited with {result.returncode}",
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.CalledProcessError as exc:
        log.warning("Command failed: %s", args, exc_info=True)
        return {
            "ok": False,
            "error": exc.stderr.strip() or str(exc),
            "returncode": exc.returncode,
        }
    except subprocess.TimeoutExpired:
        log.warning("Command timed out: %s", args)
        return {"ok": False, "error": f"Command timed out: {command}"}
    except OSError as exc:
        log.warning("Command could not run: %s", args, exc_info=True)
        return {"ok": False, "error": str(exc)}


def run_best_effort(args: list[str], timeout: int = 5) -> dict[str, Any]:
    result = run_checked(args, timeout=timeout, check=False)
    result["ok"] = True
    return result


def start_background(args: list[str]) -> dict[str, Any]:
    command = args[0]
    if dry_run_enabled():
        log.info("Dry run background command: %s", args)
        return {"ok": True, "dry_run": True}

    if not command_exists(command):
        log.warning("Missing command: %s", command)
        return {"ok": False, "error": f"Command not found: {command}"}

    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"ok": True}
    except OSError as exc:
        log.warning("Background command could not run: %s", args, exc_info=True)
        return {"ok": False, "error": str(exc)}


def kill_browser() -> None:
    for process_name in CONFIG.get("browser_process_names", []):
        name = str(process_name).strip()
        if name:
            run_best_effort(["pkill", "-f", name], timeout=3)


def browser_args(url: str) -> list[str]:
    command = str(CONFIG.get("browser_command") or "surf")
    args = CONFIG.get("browser_args", [])
    if not isinstance(args, list):
        args = []
    return [command, *[str(item) for item in args], url]


def open_browser(url: str) -> dict[str, Any]:
    if not safe_url(url):
        return {"ok": False, "error": "Only http:// and https:// URLs are allowed"}
    kill_browser()
    return start_background(browser_args(url))


def open_home() -> dict[str, Any]:
    launcher_url = str(CONFIG.get("launcher_url") or f"http://localhost:{CONFIG.get('port', 8080)}/tv")
    return open_browser(launcher_url)


def keypress(key: str) -> dict[str, Any]:
    return run_checked(["xdotool", "key", key])


def mouse_move(dx: int, dy: int) -> dict[str, Any]:
    return run_checked(["xdotool", "mousemove_relative", "--", str(dx), str(dy)])


def perform_command(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    app_shortcut = find_app(command)
    if app_shortcut:
        return open_browser(app_shortcut["url"])

    actions = {
        "home": open_home,
        "browser": lambda: open_browser(str(CONFIG.get("default_browser_url"))),
        "close_browser": lambda: (kill_browser() or {"ok": True}),
        "back": lambda: keypress("Alt+Left"),
        "forward": lambda: keypress("Alt+Right"),
        "refresh": lambda: keypress("F5"),
        "escape": lambda: keypress("Escape"),
        "nav_up": lambda: keypress("Up"),
        "nav_down": lambda: keypress("Down"),
        "nav_left": lambda: keypress("Left"),
        "nav_right": lambda: keypress("Right"),
        "select": lambda: keypress("Return"),
        "tab": lambda: keypress("Tab"),
        "shift_tab": lambda: keypress("Shift+Tab"),
        "page_up": lambda: keypress("Page_Up"),
        "page_down": lambda: keypress("Page_Down"),
        "click": lambda: run_checked(["xdotool", "click", "1"]),
        "right_click": lambda: run_checked(["xdotool", "click", "3"]),
        "mouse_up": lambda: mouse_move(0, -80),
        "mouse_down": lambda: mouse_move(0, 80),
        "mouse_left": lambda: mouse_move(-80, 0),
        "mouse_right": lambda: mouse_move(80, 0),
        "volume_up": lambda: run_checked(["amixer", "set", "Master", "5%+"]),
        "volume_down": lambda: run_checked(["amixer", "set", "Master", "5%-"]),
        "mute": lambda: run_checked(["amixer", "set", "Master", "toggle"]),
        "reboot": lambda: run_checked(["sudo", "systemctl", "reboot"], timeout=3, check=False),
    }

    if command == "open_url":
        url = str(payload.get("url") or "").strip()
        return open_browser(url)

    action = actions.get(command)
    if action is None:
        return {"ok": False, "error": f"Unknown command: {command}"}
    return action()


def process_running(pattern: str) -> bool:
    if dry_run_enabled():
        return False

    result = run_best_effort(["pgrep", "-f", pattern], timeout=3)
    return bool(result.get("ok") and result.get("stdout"))


def browser_running() -> bool:
    return any(process_running(str(name)) for name in CONFIG.get("browser_process_names", []))


@app.get("/")
def index():
    return render_template("tv.html", apps=configured_apps())


@app.get("/tv")
def tv():
    return render_template("tv.html", apps=configured_apps())


@app.get("/remote")
def remote():
    return render_template(
        "remote.html",
        apps=configured_apps(),
        pin_enabled=bool(CONFIG.get("pin")),
    )


@app.post("/api/cmd")
def api_cmd():
    ok, error = require_pin()
    if not ok:
        return jsonify({"ok": False, "error": error}), 401

    payload = request.get_json(silent=True) or {}
    command = str(payload.get("cmd") or "").strip()
    if not command:
        return jsonify({"ok": False, "error": "Missing cmd"}), 400

    result = perform_command(command, payload)
    remember_event(command, result)
    status = 200 if result.get("ok") else 400
    log.info("Command %s result: %s", command, result.get("ok"))
    return jsonify(result), status


@app.post("/api/type")
def api_type():
    ok, error = require_pin()
    if not ok:
        return jsonify({"ok": False, "error": error}), 401

    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or "")
    if not text:
        return jsonify({"ok": False, "error": "Missing text"}), 400
    if len(text) > 1000:
        return jsonify({"ok": False, "error": "Text is too long"}), 400

    result = run_checked(["xdotool", "type", "--clearmodifiers", "--", text], timeout=15)
    remember_event("type", result)
    return jsonify(result), 200 if result.get("ok") else 400


@app.get("/api/status")
def api_status():
    return jsonify(
        {
            "ok": True,
            "browser_running": browser_running(),
            "browser_command": str(CONFIG.get("browser_command") or ""),
            "dry_run": dry_run_enabled(),
            "pin_enabled": bool(CONFIG.get("pin")),
            "port": int(CONFIG.get("port", 8080)),
            "apps": configured_apps(),
            "last_event": LAST_EVENT,
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or CONFIG.get("port", 8080))
    app.run(host="0.0.0.0", port=port)
