#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEPENDENCY_IMPORT_ERROR: ModuleNotFoundError | None = None

try:
    from AppKit import NSWorkspace
    from Quartz import (
        CGDisplayBounds,
        CGEventCreate,
        CGEventCreateMouseEvent,
        CGEventGetLocation,
        CGEventPost,
        CGEventSourceCreate,
        CGMainDisplayID,
        CGWindowListCopyWindowInfo,
        kCGEventLeftMouseDown,
        kCGEventLeftMouseUp,
        kCGEventRightMouseDown,
        kCGEventRightMouseUp,
        kCGEventSourceStateHIDSystemState,
        kCGHIDEventTap,
        kCGMouseButtonLeft,
        kCGMouseButtonRight,
        kCGNullWindowID,
        kCGWindowListExcludeDesktopElements,
        kCGWindowListOptionOnScreenOnly,
        kCGWindowName,
        kCGWindowNumber,
        kCGWindowOwnerName,
    )
    from pynput import keyboard
except ModuleNotFoundError as exc:
    DEPENDENCY_IMPORT_ERROR = exc


CONFIG_PATH = Path("config.json")


def ensure_dependencies() -> None:
    if DEPENDENCY_IMPORT_ERROR is None:
        return

    raise RuntimeError(
        "Missing Python package dependencies. Run: "
        "python3 -m venv .venv && source .venv/bin/activate && "
        "pip install -r requirements.txt"
    ) from DEPENDENCY_IMPORT_ERROR


@dataclass(frozen=True)
class Binding:
    x: float
    y: float
    relative: bool = False
    button: str = "left"
    mode: str = "tap"
    repeat_interval: float = 0.1


@dataclass(frozen=True)
class WindowFilter:
    frontmost_app_contains: str = ""
    window_title_contains: str = ""


@dataclass(frozen=True)
class Config:
    only_when: WindowFilter
    bindings: dict[str, Binding]


def load_config(path: Path) -> Config:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. Copy config.example.json to config.json first."
        )

    raw = json.loads(path.read_text())
    only_when = raw.get("only_when", {})
    bindings = raw.get("bindings", {})

    parsed_bindings: dict[str, Binding] = {}
    for key, value in normalize_bindings(bindings).items():
        normalized_key = key.lower()
        parsed_bindings[normalized_key] = Binding(
            x=float(value["x"]),
            y=float(value["y"]),
            relative=bool(value.get("relative", False)),
            button=str(value.get("button", "left")).lower(),
            mode=str(value.get("mode", "tap")).lower(),
            repeat_interval=float(value.get("repeat_interval", 0.1)),
        )

    return Config(
        only_when=WindowFilter(
            frontmost_app_contains=str(only_when.get("frontmost_app_contains", "")),
            window_title_contains=str(only_when.get("window_title_contains", "")),
        ),
        bindings=parsed_bindings,
    )


def normalize_bindings(bindings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in bindings.items():
        if isinstance(value, dict) and "key" in value and "coord" in value:
            binding_key = str(value["key"])
            coord = value["coord"]
            normalized[binding_key] = {
                "x": coord["x"],
                "y": coord["y"],
                "relative": bool(coord.get("relative", value.get("relative", False))),
                "button": value.get("button", "left"),
                "mode": value.get("mode", "tap"),
                "repeat_interval": value.get("repeat_interval", 0.1),
            }
            continue

        normalized[str(key)] = value
    return normalized


def save_binding(path: Path, key: str, x: float, y: float) -> None:
    if path.exists():
        raw: dict[str, Any] = json.loads(path.read_text())
    else:
        raw = {"only_when": {}, "bindings": {}}

    bindings = raw.setdefault("bindings", {})
    current = bindings.get(key, {})
    current["x"] = round(x)
    current["y"] = round(y)
    current.setdefault("button", "left")
    current.setdefault("mode", "tap")
    bindings[key] = current

    path.write_text(json.dumps(raw, indent=2) + "\n")


def current_mouse_position() -> tuple[float, float]:
    event = CGEventCreate(None)
    point = CGEventGetLocation(event)
    return float(point.x), float(point.y)


def main_display_size() -> tuple[float, float]:
    bounds = CGDisplayBounds(CGMainDisplayID())
    return float(bounds.size.width), float(bounds.size.height)


def resolve_binding_coordinate(binding: Binding) -> tuple[float, float]:
    if not binding.relative:
        return binding.x, binding.y

    width, height = main_display_size()
    return width * binding.x, height * binding.y


def frontmost_app_name() -> str:
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return ""
    return str(app.localizedName() or "")


def frontmost_window_title(app_name: str) -> str:
    options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
    windows = CGWindowListCopyWindowInfo(options, kCGNullWindowID) or []

    for window in windows:
        owner = str(window.get(kCGWindowOwnerName, ""))
        if owner != app_name:
            continue
        title = str(window.get(kCGWindowName, ""))
        if title:
            return title
        if window.get(kCGWindowNumber):
            return ""
    return ""


def active_window_matches(window_filter: WindowFilter) -> bool:
    app_need = window_filter.frontmost_app_contains.strip().lower()
    title_need = window_filter.window_title_contains.strip().lower()

    if not app_need and not title_need:
        return True

    app_name = frontmost_app_name()
    if app_need and app_need not in app_name.lower():
        return False

    if title_need:
        title = frontmost_window_title(app_name)
        if title_need not in title.lower():
            return False

    return True


def mouse_event_parts(button: str) -> tuple[int, int, int]:
    if button == "right":
        return kCGMouseButtonRight, kCGEventRightMouseDown, kCGEventRightMouseUp
    elif button == "left":
        return kCGMouseButtonLeft, kCGEventLeftMouseDown, kCGEventLeftMouseUp

    raise ValueError(f"Unsupported mouse button: {button!r}")


def post_mouse_event(x: float, y: float, event_type: int, mouse_button: int) -> None:
    source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
    event = CGEventCreateMouseEvent(source, event_type, (x, y), mouse_button)
    CGEventPost(kCGHIDEventTap, event)


def mouse_down_at(x: float, y: float, button: str) -> None:
    mouse_button, down_type, _up_type = mouse_event_parts(button)
    post_mouse_event(x, y, down_type, mouse_button)



def mouse_up_at(x: float, y: float, button: str) -> None:
    mouse_button, _down_type, up_type = mouse_event_parts(button)
    post_mouse_event(x, y, up_type, mouse_button)


def click_at(x: float, y: float, button: str) -> None:
    mouse_down_at(x, y, button)
    time.sleep(0.025)
    mouse_up_at(x, y, button)


def key_name(key: keyboard.Key | keyboard.KeyCode) -> str | None:
    if isinstance(key, keyboard.KeyCode) and key.char:
        return key.char.lower()
    return None


def run_listener(config: Config) -> None:
    pressed: set[str] = set()
    repeat_stops: dict[str, threading.Event] = {}
    held_clicks: dict[str, tuple[float, float, str]] = {}
    state_lock = threading.Lock()

    def repeat_clicks(
        name: str,
        binding: Binding,
        x: float,
        y: float,
        stop_event: threading.Event,
    ) -> None:
        while not stop_event.is_set():
            if not active_window_matches(config.only_when):
                break

            click_at(x, y, binding.button)
            print(f"{name.upper()} -> click ({x:.0f}, {y:.0f})")
            stop_event.wait(max(binding.repeat_interval, 0.025))

        with state_lock:
            repeat_stops.pop(name, None)

    def on_press(key: keyboard.Key | keyboard.KeyCode) -> None:
        name = key_name(key)
        if not name:
            return

        with state_lock:
            if name in pressed:
                return
            pressed.add(name)

        binding = config.bindings.get(name)
        if binding is None:
            return

        if not active_window_matches(config.only_when):
            return

        x, y = resolve_binding_coordinate(binding)
        if binding.mode == "hold":
            mouse_down_at(x, y, binding.button)
            with state_lock:
                held_clicks[name] = (x, y, binding.button)
            print(f"{name.upper()} -> hold ({x:.0f}, {y:.0f})")
            return

        if binding.mode == "repeat":
            stop_event = threading.Event()
            with state_lock:
                repeat_stops[name] = stop_event
            thread = threading.Thread(
                target=repeat_clicks,
                args=(name, binding, x, y, stop_event),
                daemon=True,
            )
            thread.start()
            return

        if binding.mode != "tap":
            print(f"{name.upper()} ignored: unsupported mode {binding.mode!r}")
            return

        click_at(x, y, binding.button)
        print(f"{name.upper()} -> click ({x:.0f}, {y:.0f})")

    def on_release(key: keyboard.Key | keyboard.KeyCode) -> None:
        name = key_name(key)
        if not name:
            return

        with state_lock:
            pressed.discard(name)
            held_click = held_clicks.pop(name, None)
            repeat_stop = repeat_stops.get(name)

        if repeat_stop is not None:
            repeat_stop.set()

        if held_click is not None:
            x, y, button = held_click
            mouse_up_at(x, y, button)
            print(f"{name.upper()} -> release ({x:.0f}, {y:.0f})")

    def release_all_held() -> None:
        with state_lock:
            active_held = list(held_clicks.values())
            held_clicks.clear()
            active_repeats = list(repeat_stops.values())
            repeat_stops.clear()

        for stop_event in active_repeats:
            stop_event.set()

        for x, y, button in active_held:
            mouse_up_at(x, y, button)

    print("GameClicker is running. Press Ctrl+C here to stop.")
    print(f"Loaded bindings: {', '.join(sorted(config.bindings))}")
    try:
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()
    finally:
        release_all_held()


def show_position() -> None:
    print("Move the pointer. Press Ctrl+C to stop.")
    while True:
        x, y = current_mouse_position()
        print(f"\r x={x:.0f} y={y:.0f}", end="", flush=True)
        time.sleep(0.05)


def print_window() -> None:
    app_name = frontmost_app_name()
    title = frontmost_window_title(app_name)
    print(f"frontmost_app={app_name!r}")
    print(f"window_title={title!r}")


def calibrate(path: Path, key: str, delay: float) -> None:
    normalized_key = key.lower()
    print(f"Move the pointer to the target for {normalized_key.upper()}.")
    print(f"Capturing in {delay:g} seconds...")
    time.sleep(delay)
    x, y = current_mouse_position()
    save_binding(path, normalized_key, x, y)
    print(f"Saved {normalized_key.upper()} -> ({x:.0f}, {y:.0f}) in {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bind keyboard keys to fixed-coordinate mouse clicks."
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        type=Path,
        help="Path to the JSON config file. Defaults to config.json.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to the JSON config file. Overrides the positional config file.",
    )
    parser.add_argument(
        "--app",
        help="Only click when the frontmost app name contains this text.",
    )
    parser.add_argument(
        "--window",
        help="Only click when the frontmost window title contains this text.",
    )
    parser.add_argument(
        "--show-position",
        action="store_true",
        help="Continuously print the current mouse coordinate.",
    )
    parser.add_argument(
        "--print-window",
        action="store_true",
        help="Print the focused app name and window title.",
    )
    parser.add_argument(
        "--calibrate",
        metavar="KEY",
        help="Save the current mouse coordinate to a key binding after --delay seconds.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3,
        help="Delay in seconds for --calibrate.",
    )
    return parser.parse_args()


def selected_config_path(args: argparse.Namespace) -> Path:
    return args.config or args.config_file or CONFIG_PATH


def with_cli_filters(config: Config, app: str | None, window: str | None) -> Config:
    if app is None and window is None:
        return config

    return Config(
        only_when=WindowFilter(
            frontmost_app_contains=(
                config.only_when.frontmost_app_contains if app is None else app
            ),
            window_title_contains=(
                config.only_when.window_title_contains if window is None else window
            ),
        ),
        bindings=config.bindings,
    )


def main() -> int:
    args = parse_args()

    try:
        if args.show_position:
            ensure_dependencies()
            show_position()
            return 0

        if args.print_window:
            ensure_dependencies()
            print_window()
            return 0

        if args.calibrate:
            ensure_dependencies()
            calibrate(selected_config_path(args), args.calibrate, args.delay)
            return 0

        ensure_dependencies()
        config = with_cli_filters(
            load_config(selected_config_path(args)),
            args.app,
            args.window,
        )
        run_listener(config)
        return 0
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
