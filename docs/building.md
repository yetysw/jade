# Building

At the end of this page you have run jade from source and built the installer. Windows is the only target that ships today.

## Prerequisites

Python 3.12 or later, the Flutter SDK (stable channel, Windows desktop enabled), and Inno Setup 6 for the installer. The Dart SDK constraint is `^3.12.2`.

## Run from source

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env       # then fill in the values
jade check
jade serve                   # http://127.0.0.1:8765 with UI_PORT=8765
```

In another terminal:

```bash
cd flutter_app
flutter run -d windows
```

The app finds a running `jade serve` as a fallback. Install the `ocr` extra with `pip install .[ocr]` for local OCR, and `.[dev]` for PyInstaller and pytest.

## Build the installer

```bash
cd flutter_app && flutter build windows --release
cd ..
python -m PyInstaller jade.spec --noconfirm
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\jade.iss
```

The output is `dist\installer\Jade-Setup-<version>.exe`. For a protected installer, add `/DSetupPassword=<password>` to the `ISCC` call. `/DBackendDir=<path>` points to another PyInstaller output folder. The password is never stored in the repository.

## Tests

```bash
python -m pytest             # tests in tests/unit
cd flutter_app && flutter analyze
```

## Layout

```
flutter_app/   native Windows interface
ragagent/      backend: web/app.py (API and orchestration), ingest/, rag.py,
               hybrid.py, router.py, store.py, llm.py, websearch.py, memory.py,
               chat_store.py, ntfs.py, security.py, audit.py, filegen.py, updater.py,
               licensing.py, models_fetch.py, config.py, cli.py
licsrv/        licence server (internal)
installer/     Inno Setup script and the scheduled update task
tests/unit/    backend tests
```

## Stack

| Layer | Technology |
|---|---|
| Interface | Flutter, `http`, `flutter_markdown` |
| Backend | Python 3.12+, FastAPI 0.139.0, Uvicorn 0.49.0 |
| Index | ChromaDB 1.5.9, fastembed 0.8.0 (ONNX, CPU), rank-bm25 |
| Parsing | python-docx, openpyxl, xlrd, pypdf, pypdfium2, extract-msg, odfpy |
| File creation | python-docx, python-pptx, openpyxl, reportlab |
| Outbound client | httpx 0.28.1 |
| Licences | PyJWT with Ed25519 |
| Packaging | PyInstaller, Inno Setup 6 |

Contributions: see [CONTRIBUTING.md](https://github.com/yetysw/jade/blob/main/CONTRIBUTING.md).
