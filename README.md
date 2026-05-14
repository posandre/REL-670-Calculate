# REL-670-Calculate

REL-670-Calculate is a Windows desktop application for engineering calculations of
relay protection settings for ABB/Hitachi Energy RET670 style workflows. The current
scope focuses on distance protection stages, Power Swing Blocking (PSD/PSB), load
encroachment cutouts (RLD), R-X diagrams, and calculation reports.

## Main Capabilities

- Enter distance protection stage settings in a table.
- Configure protection mode, CT/VT values, sensitivity factor, rejection factor, and
  load modes.
- Calculate PSD and RLD settings from selected distance stages.
- Plot phase-phase and phase-ground R-X diagrams.
- Plot PSD/RLD overlay zones and distance protection zones.
- Export charts to graphical formats supported by Matplotlib, including PNG, SVG,
  and PDF.
- Export PSD settings and PSD engineering reports to Word (`.docx`).
- Store projects in SQLite and manage multiple saved projects.
- Switch interface language between Ukrainian and English.

## Calculation Flow

1. Fill in the distance protection stages.
2. Select the protection type:
   - protection against all fault types;
   - protection against phase-to-phase faults.
3. Fill in protection settings and load modes.
4. Run one of the calculation commands:
   - `Calculate all`;
   - `Calculate PSD`;
   - `Calculate PHS` (currently a placeholder and requires a prior PSD calculation).
5. Review diagrams, PSD settings, journal entries, and the PSD report.
6. Export charts or Word reports if required.

After a successful calculation, input data is locked. Use `Clear results` to confirm
clearing all calculation outputs and unlock the inputs for editing.

## Project Structure

```text
src/app/
  core/            Application configuration
  database/        SQLite/SQLAlchemy persistence
  diagrams/        Matplotlib diagram rendering and export
  localization/    Translation files and translator
  models/          Project and electrical data models
  services/        Calculation orchestration
  services/calculations/
                   Engineering formulas and reusable calculation modules
  ui/              PySide6 windows, dialogs, widgets, and styles
  utils/           Serialization and Word export helpers
tests/             Pytest suite for calculations, validation, and persistence
resources/         Application resources such as the Windows icon
```

## Development Setup

Use Python 3.11 or newer.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

Run the application:

```powershell
python -m app.main
```

Run tests:

```powershell
pytest
```

Run formatting and checks:

```powershell
black src tests
ruff check src tests
mypy src
```

## Building Windows EXE

The application can be packaged with PyInstaller:

```powershell
pyinstaller --clean --noconfirm --onefile --windowed `
  --name REL-670-Calculate `
  --icon resources\app_icon.ico `
  --paths src `
  --add-data "src\app\localization\translations;app\localization\translations" `
  --add-data "src\app\ui\styles\app.qss;app\ui\styles" `
  src\app\main.py
```

The resulting executable is created in `dist/`.

## Engineering Notes

Calculation formulas are kept in dedicated modules under
`src/app/services/calculations`. Formulas that still require verification against
RET670 documentation are marked with TODO comments near the implementation.
