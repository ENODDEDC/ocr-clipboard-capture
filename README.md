# ClipOCR (Windows)

A small background app: press a hotkey, **drag-highlight a screen region**, OCR the text, and **copy it to your clipboard**.

## What it does

- Works on PDFs/images where normal copying is blocked (because it OCRs what’s on your screen).
- Hotkey: **Ctrl + Alt + H**
- Runs in the **system tray** (right-click the tray icon to quit).

## Install

0) Install **Python 3.10+**.

1) Install **Tesseract OCR** (required for OCR).
   - Default install path the app looks for:
     - `C:\Program Files\Tesseract-OCR\tesseract.exe`
   - If installed somewhere else, set:
     - `setx TESSERACT_CMD "C:\Path\To\tesseract.exe"`

2) Install Python deps:

```powershell
python -m pip install -r requirements.txt
```

## Run

```powershell
python -m copy_highlight
```

Tip: to run without a console window:

```powershell
pythonw -m copy_highlight
```

## Build an EXE (optional)

This creates a portable folder with `CopyHighlight.exe` (no Python needed on the target PC).

```powershell
.\build_exe.ps1
```

Output:

- `dist\ClipOCR\ClipOCR.exe`

Important: this is a **one-folder** build. Don’t move/copy only the `.exe`—keep the whole `ClipOCR` folder (it contains `_internal\python314.dll` and other files).

## Make a “zero-install” release zip (bundles Tesseract)

If you want users to run the app without installing Tesseract, you can bundle your local Tesseract into the release zip:

```powershell
.\package_release.ps1 -BundleTesseract
```

Output:

- `ClipOCR-win64.zip`

Users just extract the zip and run:

- `ClipOCR\ClipOCR.exe`

## Use

1) Open the PDF/image on your screen.
2) Press **Ctrl + Alt + H**.
3) Drag a rectangle around the text you want.
4) Release mouse → text is copied to clipboard.

### Change the hotkey

Set an env var before starting:

```powershell
$env:COPY_HIGHLIGHT_HOTKEY = '<ctrl>+<alt>+h'
pythonw -m copy_highlight
```

## Notes / limitations

- OCR accuracy depends on image quality/zoom and font clarity.
- If OCR returns empty text, try zooming in and capturing a tighter region.
- If accuracy is still poor, try these:
  - Zoom the PDF to **150–250%** before capturing.
  - Capture only the text (avoid thick borders/lines when possible).
  - Enable debug images/logs:
    - `setx COPY_HIGHLIGHT_DEBUG 1`
    - The preprocessed image is saved to `%LOCALAPPDATA%\CopyHighlight\last_capture_preprocessed.png`
- The EXE uses **Tesseract OCR** (either installed system-wide or bundled via `.\package_release.ps1 -BundleTesseract`).
