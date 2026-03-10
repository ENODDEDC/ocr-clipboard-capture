# Copy Highlight (Windows)

A small background app: press a hotkey, **drag-highlight a screen region**, OCR the text, and **copy it to your clipboard**.

## What it does

- Works on PDFs/images where normal copying is blocked (because it OCRs what’s on your screen).
- Hotkey: **Ctrl + Alt + H**
- Runs in the **system tray** (right-click the tray icon to quit).

## Install

0) Install **Python 3.10+**.

1) Install **Tesseract OCR** (required).
   - Default install path the app looks for:
     - `C:\Program Files\Tesseract-OCR\tesseract.exe`

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
