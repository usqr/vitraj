# OS click test

The script closes the startup popups of vitraj and clicks the file lists with
the real mouse events of macOS. After each click, it checks two conditions:

- The window below the click point belongs to vitraj.
- No pane changed its folder.

Use this test when a change can break the start of the app: popups, overlays,
sorting by a click on a header, or the `..` entry.

## Files

| Path | Purpose |
|------|---------|
| `click_test.py` | The driver. It needs `pyobjc-framework-Quartz`. |
| `SortProbe/` | A probe plugin. It writes the window layout to a JSON file every 200 ms. |
| `requirements.txt` | The dependency of the driver. |

The probe plugin writes only the layout of the window: the panes, the folder
URLs, the header and row rectangles, and the open popups. It writes no file
contents. Do not install it for normal use.

## Steps

### 1. Build a copy of the app

```bash
python build.py freeze
```

### 2. Make an isolated home

```bash
SCRATCH=$(mktemp -d)
PLUGINS="$SCRATCH/home/Library/Application Support/vitraj/Plugins/Third-party"
mkdir -p "$PLUGINS"
cp -r tools/os_test/SortProbe "$PLUGINS/"
```

### 3. Start the copy, not `/Applications/vitraj.app`

```bash
HOME="$SCRATCH/home" VITRAJ_OS_TEST_STATE="$SCRATCH/state.json" \
  target/vitraj.app/Contents/MacOS/vitraj &
```

### 4. Run the driver

```bash
./venv/bin/pip install -r tools/os_test/requirements.txt
./venv/bin/python tools/os_test/click_test.py \
  --state "$SCRATCH/state.json" --report "$SCRATCH/report.json"
```

Add `--dry-run` to print the click points and to click nothing. Add
`--clicks N` to change the number of clicks on each Name header.

## What the driver does

1. It waits for the state file (maximum `--wait` seconds, default 120).
2. It makes sure that the process name contains `vitraj` (frozen app) or
   `python` (source run).
3. It closes the popups:
   - `SplashScreen`: the button named in "press button X".
   - `Overlay` with a "No" button: "No".
   - The alert with "extra configuration": "Cancel".
   - Other popups: the driver stops with an error.
4. It clicks the Name header `--clicks` times in each pane.
5. It clicks the `..` row in each pane.
6. After each click, it waits for a new state. It then checks the pane URLs.
   A click on a header can change the sort order. A click on a row can change
   the selection. Neither click can change the folder.

The driver never clicks "OK". On the configuration alert, OK opens a browser.

## Limits

- macOS only.
- The terminal needs an Accessibility permission. Without it, the CGEvent
  calls do nothing.
- The Qt coordinates and the CGEvent coordinates are equal on the primary
  screen. Put the vitraj window on the primary screen.
- The `SplashScreen` path occurs only in an unlicensed or expired run.
- A real run of the click test is necessary after a change to the probe plugin
  or to the popup texts.

## Known issue

In one run, the left pane opened the empty folder `zeta` while the popups
closed. It did not occur again in 3 runs. The driver stops on such a change.
