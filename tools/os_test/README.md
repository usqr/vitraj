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
| `click_test.py` | The driver. It needs `pyobjc-framework-Quartz` and `pyobjc-framework-ApplicationServices`. |
| `SortProbe/` | A probe plugin. It writes the window layout to a JSON file every 200 ms. |
| `requirements.txt` | The dependencies of the driver. |
| `test_click_test.py` | Unit tests for the helpers of the driver. They need no GUI. |

The probe plugin writes the layout of the window: the panes, the folder URLs,
the header and row rectangles, the open popups, and the double-click time of
the app. It writes no file contents. But it writes the name of each file in the
two panes and all popup texts. Thus do not install the plugin for normal use,
and do not share the state file.

## Steps

### 1. Build a copy of the app

```bash
source venv/bin/activate   # build.py freeze calls pyinstaller from the PATH
python build.py freeze
```

### 2. Make an isolated home

```bash
SCRATCH=$(mktemp -d)
PLUGINS="$SCRATCH/home/Library/Application Support/vitraj/Plugins"
mkdir -p "$PLUGINS/Third-party" "$PLUGINS/User/Settings"
cp -r tools/os_test/SortProbe "$PLUGINS/Third-party/"
echo '[{"show_hidden_files": false, "show_parent_dir_entry": true},
  {"show_hidden_files": false, "show_parent_dir_entry": true}]' \
  > "$PLUGINS/User/Settings/Panes (Mac).json"
mkdir "$SCRATCH/home/alpha" "$SCRATCH/home/beta" "$SCRATCH/home/zeta"
touch "$SCRATCH/home/a.txt" "$SCRATCH/home/m.txt" "$SCRATCH/home/z.txt"
```

The test folders and files are necessary. Without them, a click on the Name
header does not change the row order.

`Panes (Mac).json` turns on the `..` entry in the two panes. It is off by
default. Without it, the driver stops at the `..` step.

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

1. It waits for the state file (maximum `--wait` seconds, default 120). A state
   file with a probe error stops the driver.
2. It makes sure that the process name contains `vitraj` (frozen app) or
   `python` (source run).
3. It closes the popups:
   - `Overlay` with a "No" button: "No".
   - The alert with "extra configuration": "Cancel".
   - Other popups: the driver stops with an error.
4. It clicks the Name header `--clicks` times in each pane.
5. It clicks the `..` row in each pane. If a pane has no visible `..` row, the
   driver stops. It does not click another row, because that row can be a
   folder.
6. After each click, it waits for a state that the probe wrote at least 0.6 s
   after the click. It also waits for the result of the click:
   - After a popup button: the popup is closed.
   - After a header: no special result. If the row order does not change, the
     driver writes a warning.
   - After the `..` row: the cursor is on the `..` row. A plain click moves the
     cursor. It does not select the row.

   If the result does not occur in 20 s, the driver stops. It never clicks
   again at the position of an old state.
7. After each click, it makes sure that no pane changed its folder.

Before each click, the driver makes sure that a click at the click point goes
to vitraj. It uses the Accessibility hit test for this check. If a system
dialog or a notification is above vitraj, the check fails. The list of windows
is not a correct source: on macOS 26, a transparent Dock window covers the full
primary screen and does not take clicks.

The driver never makes two clicks near the same point within 1.5 times the
double-click time of the app. Two such clicks on a folder open the folder.

The report file (`--report`) contains the steps, each click with its time and
position, and the double-click time.

The driver never clicks "OK". On the configuration alert, OK opens a browser.

## Limits

- macOS only.
- The terminal needs an Accessibility permission. Without it, the CGEvent
  calls do nothing and the hit test fails. The driver then stops with the
  error "The terminal has no Accessibility permission", also with
  `--dry-run`.
- The Qt coordinates and the CGEvent coordinates are in points, with the origin
  at the top left of the primary screen. Retina scaling does not change them.
  The test passed with the window on the primary screen and on a second
  screen above and to the right of the primary screen.
- A real run of the click test is necessary after a change to the probe plugin
  or to the popup texts.

## Cause of the earlier `zeta` problem

In one run of an earlier version of the driver, the left pane opened the empty
folder `zeta` while the popups closed. The earlier driver did not wait for a
new state after a click. Thus it could click the position of a closed popup
again, and the file list was below that position.

A test on 2026-11-24 proved this cause. The test clicked the button of the
license splash screen (removed later), and then clicked the same point 4 more times:

| Gap between the clicks | Result |
|------------------------|--------|
| 0.1 s (shorter than the double-click time of 400 ms) | `zeta` opened in 3 of 3 runs |
| 0.7 s | No folder opened in 2 of 2 runs |

One or two more clicks did not open the folder. Qt does not make a
double-click from a click on the popup and a click on the file list. Two more
clicks that both go to the file list make a double-click.

The current driver waits until the popup is closed. It also keeps 1.5 times
the double-click time between two clicks near the same point. Thus it cannot
make this double-click.

In the first run of vitraj, the `UsageHelper` can take the first double-click
and show a hint in place of opening the folder.
