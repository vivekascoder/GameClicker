# GameClicker

GameClicker maps keyboard keys to mouse clicks at fixed screen coordinates. It is built for macOS and can restrict clicks to a specific foreground app or window title.

## Requirements

- macOS
- Python 3.10+
- Terminal, iTerm, or your launcher allowed in macOS Accessibility settings

## Install

```bash
git clone https://github.com/vivekascoder/GameClicker.git
cd GameClicker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
```

Grant permissions to the terminal app that runs the script:

- `System Settings -> Privacy & Security -> Accessibility`
- `System Settings -> Privacy & Security -> Input Monitoring`

If window detection does not work, also grant:

- `System Settings -> Privacy & Security -> Screen Recording`

## Configure

Print the current pointer position:

```bash
python game_clicker.py --show-position
```

Move the pointer to the click target, note the `x` and `y` values, then edit `config.json`.

You can also capture a coordinate after a delay:

```bash
python game_clicker.py --calibrate w --delay 3
python game_clicker.py --calibrate s --delay 3
```

Restrict clicks to a foreground app or window by editing `only_when`:

```json
{
  "only_when": {
    "frontmost_app_contains": "Your Game App",
    "window_title_contains": "Your Window Title"
  }
}
```

Leave either value empty to ignore that check. To inspect the currently focused app and window:

```bash
python game_clicker.py --print-window
```

## Run

```bash
python game_clicker.py
```

Press the configured keys while the target window is focused. Press `Ctrl+C` in the terminal to stop.

## Hill Climb Racing Example

The included `hillclimbracing.json` binds:

- `D` to a left-click hold at 90% screen width and 90% screen height
- `A` to a left-click hold at 10% screen width and 90% screen height

Run it with:

```bash
python game_clicker.py hillclimbracing.json
```

Override the app or window filter from the command line:

```bash
python game_clicker.py hillclimbracing.json --app "Hill Climb"
python game_clicker.py hillclimbracing.json --window "Hill Climb"
```

## Binding Modes

Each binding supports a `mode`:

- `tap`: click once per key press
- `hold`: mouse down on key press, mouse up on key release
- `repeat`: keep tapping while the key is held

Repeat mode uses `repeat_interval` in seconds:

```json
{
  "key": "d",
  "coord": { "x": 0.9, "y": 0.9, "relative": true },
  "button": "left",
  "mode": "repeat",
  "repeat_interval": 0.08
}
```

## Files

- `game_clicker.py`: the command-line tool
- `config.example.json`: starter local config
- `hillclimbracing.json`: ready-to-run example config
- `index.html`: static landing page for hosted documentation
