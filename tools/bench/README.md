# Performance tools

Use these tools to measure a performance change before and after you make it.

## Directory load benchmark

The script `dir_load.py` makes a temporary folder with many files. It loads
the folder into the real model and a table view, then it scrolls through all
of the rows.

```bash
venv/bin/python tools/bench/dir_load.py               # 5,000 files, 200 folders
venv/bin/python tools/bench/dir_load.py --files 20000
venv/bin/python tools/bench/dir_load.py --profile     # also print the top functions
```

The script prints three times:

| Name | Meaning |
|------|---------|
| `first rows` | The time until the first rows show. |
| `all rows` | The time until the worker loads all of the rows. |
| `scroll + repaint` | The time to scroll through all of the rows and paint each page. |

Do each run two or three times. The first run can be slower because the OS
caches the file metadata.

## Stall detector

The stall detector writes a stack trace of the main thread to the log when the
event loop is blocked for longer than a threshold. It is off by default. To
turn it on, set `VITRAJ_STALL_MS` to the threshold in milliseconds:

```bash
VITRAJ_STALL_MS=100 venv/bin/python build.py run
```

Each log entry starts with `Main thread blocked for N ms`. The stack trace
shows the code that held the main thread at the time of the check.
