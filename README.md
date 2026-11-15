# PDF Master – Offline PDF Toolkit

A fast, lightweight, fully offline Windows desktop PDF application built with **Python 3.12**, **PySide6 (Qt Widgets)**, **PyMuPDF (fitz)**, **pikepdf**, and **Pillow**.

- **100% Offline** – No account, no cloud services, no API keys, no telemetry.
- **SQLite File & Operation History** – Local `history.db` database (`%APPDATA%\PDFMaster\history.db`) tracks opened and generated files, page counts, file sizes, tool actions, timestamps, and open counts with instant search & action filtering on the **Recent Files** screen.
- **Non-Destructive** – Original files are preserved by default; all writes are atomic via temporary files.
- **Lightweight** – Page-by-page streaming, 64 MB bounded LRU thumbnail cache, lazy page loading, and background `QThread` workers with progress & cancellation.

---

## Implemented Features (Phase 1, Phase 2 & Phase 3)

| Sidebar Category | Tools Included |
|---|---|
| **Organize PDF** | **Merge PDF**, **Split PDF** (individual pages, custom ranges, every N pages), **Organize PDF** (thumbnail drag & drop reorder, rotate, duplicate, delete), **Remove Pages**, **Extract Pages**, **Rotate PDF** (90°/180°/270°), **Remove Blank Pages**, **Compare PDFs** (visual pixel diff + unified text diff report), **Batch Rename PDFs** |
| **Convert PDF** | **PDF to Image** (JPG, PNG, TIFF at 72/150/200/300/600 DPI, JPG quality, page ranges, batch, live preview), **Image to PDF** (JPG, JPEG, PNG, BMP, multi-page TIFF; A4/Letter/Legal/Original size; portrait/landscape/auto; fit/stretch/original; margins), **PDF to Word (`.docx`)**, **PDF to Excel (`.xlsx`)**, **PDF to PowerPoint (`.pptx`)**, **Office to PDF (`.docx`/`.xlsx`/`.pptx` → `.pdf`)**, **Extract Text (`.txt`)**, **Extract Embedded Images** |
| **Compress PDF** | **Compress PDF** (Low, Recommended, High presets; image optimization & downsampling; structural cleanup via PyMuPDF + pikepdf; displays original size, compressed size, bytes saved, and % saved; never writes a file if larger than original), **Repair PDF**, **Grayscale PDF**, **Flatten PDF** |
| **Edit PDF** | **Edit & Annotate PDF** (Add text boxes, insert images, highlight text, underline text, add rectangle/circle/line shapes, draw freehand ink annotations — with interactive click/drag page preview), **Add Page Numbers**, **Headers & Footers** (`{page}`, `{total}`, `{date}`), **Watermark PDF** (text & image watermarks with opacity, angle, tiling, overlay/underlay), **Crop Pages** (interactive drag-to-crop preview), **Edit PDF Metadata** |
| **PDF Security** | **Protect PDF** (AES-256 user & owner passwords + print/copy/modify/annotate permissions), **Unlock PDF** (with authorized password verification), **Redact Sensitive Content** (permanent text & pixel destruction + interactive region selection + automatic post-save verification by reopening and inspecting the output PDF), **Sign PDF** (visual signature stamp + SHA-256 document digest + optional lock) |
| **OCR Tools** | **OCR PDF** (Tesseract OCR integration: generate searchable PDFs or extract text from scanned pages, language pack selector, batch OCR) |
| **PDF Reader** | Built-in viewer with page navigation, thumbnail sidebar, zoom in/out, fit page, fit width, text search with highlighted matches, single-page & continuous scrolling, view rotation, and Windows system printing |

---

## Running from Source

You can launch `main.py` directly from any Python interpreter or IDE button (`main.py` automatically delegates to `.venv\Scripts\python.exe` if needed):

```powershell
python main.py
```

Or explicitly via the virtual environment:

```powershell
.\.venv\Scripts\python.exe main.py
```

To recreate the virtual environment from scratch:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-optional.txt
```

---

## Running the Test Suite

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- `tests/test_merge.py` – PDF merging, ordering, encrypted/damaged files, cancellation
- `tests/test_split.py` – Split by pages/ranges/every N, extract, organize, remove, rotate
- `tests/test_compress.py` – Compression presets, size reduction verification, non-inflation guarantee
- `tests/test_render.py` – PDF to JPG/PNG/TIFF, 300 & 600 DPI, batch export, memory-bounded page streaming, thumbnail LRU cache
- `tests/test_image_to_pdf.py` – Multi-format images to PDF, page sizes, orientations, aspect ratio, margins
- `tests/test_phase2_phase3.py` – Page numbers, headers/footers, watermarks, annotations, cropping, metadata, AES-256 encryption/unlocking, verified redaction, signing, repair, blank page removal, flattening, grayscale, text/image extraction, PDF comparison, batch rename, PDF ⇄ Word/Excel/PowerPoint, and Tesseract OCR
- `tests/test_gui.py` – End-to-end headless GUI tests across all screens, tools, interactive preview canvas, "Open in Reader" workflow, viewer, search, theme switching, and task cancellation

### Sample Test Files (`samples/`)

Pre-generated sample PDFs and images are included in `samples/` (single-page, multi-page, image-heavy, scanned page, encrypted `secret` PDF, rotated pages, mixed page sizes, corrupt file, and sample JPG/PNG images). To regenerate them at any time:

```powershell
.\.venv\Scripts\python.exe tools\generate_samples.py
```

---

## Building the Standalone Windows Executable & Setup Installer

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

- **Standalone App**: `dist\PDFMaster\PDFMaster.exe` (no Python installation required on target Windows 10/11 machines).
- **Windows GUI Setup Installer**: `dist\PDFMaster-Setup.exe` (and `build\installer\PDFMaster-Setup.exe`), built 100% offline via `tools/build_installer.py` using the Windows .NET compiler (`csc.exe`). Includes an interactive Setup Wizard, custom destination directory, Desktop & Start Menu shortcuts, Windows "Installed Apps" registration, and `Uninstall.exe`.
