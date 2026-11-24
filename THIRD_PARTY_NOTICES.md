# Third-party notices

vitraj's own code is under the MIT license (see `LICENSE`). The built app
(for example `vitraj.dmg`) also contains the third-party software below.
Each part keeps its own license.

## Qt and Qt for Python (PySide6, Shiboken6)

The app uses Qt 6 and PySide6 6.12.0 under the **GNU Lesser General Public
License v3 (LGPL-3.0)**.

- Copyright (C) The Qt Company Ltd. and other contributors.
- License text: https://www.gnu.org/licenses/lgpl-3.0.html
- Source code: https://code.qt.io/cgit/pyside/pyside-setup.git (PySide6,
  Shiboken6) and https://code.qt.io/cgit/qt/ (Qt). vitraj uses these
  libraries without changes.
- The app keeps the Qt and PySide6 libraries as separate files
  (`vitraj.app/Contents/Frameworks/PySide6/`). You can replace them with
  other compatible versions. If you change a file inside the app, its code
  signature becomes invalid; sign the app again (for example
  `codesign --force --deep --sign - vitraj.app`).

## Other components

| Component | License |
|-----------|---------|
| Python | PSF License |
| PyMuPDF / MuPDF (PDF preview) | AGPL-3.0 or commercial (Artifex). Note: this makes the built app AGPL-3.0 as a whole. |
| Pillow | MIT-CMU (HPND) |
| Sparkle (macOS updates) | MIT |
| pyobjc | MIT |
| Send2Trash | BSD-3-Clause |
| osxtrash | MIT |
| requests | Apache-2.0 |
| certifi | MPL-2.0 |
| charset-normalizer, urllib3 | MIT |
| idna | BSD-3-Clause |
| tinycss | BSD |
