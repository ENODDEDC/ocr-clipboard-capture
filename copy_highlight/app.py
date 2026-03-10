from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

import pyperclip
import pytesseract
from PIL import Image, ImageDraw, ImageGrab, ImageOps, ImageFilter
from pynput import keyboard
import pystray


SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

DEFAULT_APP_NAME = "ClipOCR"
DEFAULT_HOTKEY = "<ctrl>+<alt>+h"
DEFAULT_LANG = "eng"

_LOG_DIR: Optional[Path] = None


def _app_name() -> str:
    return (
        (os.environ.get("COPY_HIGHLIGHT_APP_NAME") or DEFAULT_APP_NAME).strip()
        or DEFAULT_APP_NAME
    )


def _set_dpi_awareness() -> None:
    # Fix coordinate mismatches on Windows when Display scaling != 100%.
    # Must run before creating any UI (Tk) or capturing screen regions.
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return

    # Prefer per-monitor v2 awareness when available.
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass

    # Fallback: system DPI aware.
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


@dataclass(frozen=True)
class BBox:
    left: int
    top: int
    right: int
    bottom: int

    def normalized(self) -> "BBox":
        left = min(self.left, self.right)
        right = max(self.left, self.right)
        top = min(self.top, self.bottom)
        bottom = max(self.top, self.bottom)
        return BBox(left=left, top=top, right=right, bottom=bottom)

    def is_too_small(self) -> bool:
        b = self.normalized()
        return (b.right - b.left) < 5 or (b.bottom - b.top) < 5


def _virtual_screen_rect() -> tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    x = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
    y = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
    w = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
    h = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    return x, y, w, h


def _find_tesseract_exe() -> Optional[str]:
    env = os.environ.get("TESSERACT_CMD")
    if env and os.path.isfile(env):
        return env

    which = shutil.which("tesseract")
    if which:
        return which

    # Bundled portable layout (for zero-install releases):
    #   ClipOCR.exe
    #   tesseract\tesseract.exe
    try:
        exe_dir = Path(sys.executable).resolve().parent
        bundled = exe_dir / "tesseract" / "tesseract.exe"
        if bundled.is_file():
            return str(bundled)
    except Exception:
        pass

    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _ensure_tesseract_configured() -> None:
    exe = _find_tesseract_exe()
    if not exe:
        raise RuntimeError(
            "Tesseract not found. Install Tesseract OCR, or set TESSERACT_CMD to your tesseract.exe path."
        )
    pytesseract.pytesseract.tesseract_cmd = exe


def _debug_enabled() -> bool:
    return (os.environ.get("COPY_HIGHLIGHT_DEBUG") or "").strip() not in {"", "0", "false", "False"}


def _debug_save(img: Image.Image, name: str) -> None:
    if not _debug_enabled():
        return
    if not _LOG_DIR:
        return
    try:
        path = _LOG_DIR / f"{name}.png"
        img.save(path)
        logging.info("Saved debug image: %s", path)
    except Exception:
        logging.exception("Failed to save debug image")


def _otsu_threshold(gray: Image.Image) -> int:
    hist = gray.histogram()
    total = sum(hist)
    if total <= 0:
        return 128

    sum_total = 0
    for i, h in enumerate(hist):
        sum_total += i * h

    sum_b = 0
    w_b = 0
    max_var = -1.0
    threshold = 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = float(w_b) * float(w_f) * (m_b - m_f) * (m_b - m_f)
        if var_between > max_var:
            max_var = var_between
            threshold = t
    return threshold


def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
    scale_str = (os.environ.get("COPY_HIGHLIGHT_SCALE") or "").strip()
    try:
        scale = int(scale_str) if scale_str else 3
    except ValueError:
        scale = 3

    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.Resampling.LANCZOS)

    gray = ImageOps.autocontrast(img.convert("L"))
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    gray = gray.filter(ImageFilter.UnsharpMask(radius=2, percent=160, threshold=3))

    mean = sum(gray.getdata()) / float(gray.width * gray.height)
    if mean < 110:
        gray = ImageOps.invert(gray)

    thr = _otsu_threshold(gray)
    bw = gray.point(lambda p, t=thr: 255 if p > t else 0, mode="1").convert("L")
    return bw


def _data_to_text(data: dict) -> str:
    # Reconstruct lines from image_to_data output.
    words: list[tuple[int, int, int, int, str]] = []
    n = len(data.get("text", []))
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        try:
            block = int(data.get("block_num", [0])[i])
            par = int(data.get("par_num", [0])[i])
            line = int(data.get("line_num", [0])[i])
        except Exception:
            block, par, line = 0, 0, 0
        words.append((block, par, line, i, txt))

    if not words:
        return ""

    words.sort()
    out_lines: list[str] = []
    current_key = (words[0][0], words[0][1], words[0][2])
    current_words: list[str] = []
    for block, par, line, _idx, txt in words:
        key = (block, par, line)
        if key != current_key:
            out_lines.append(" ".join(current_words).strip())
            current_words = []
            current_key = key
        current_words.append(txt)
    if current_words:
        out_lines.append(" ".join(current_words).strip())
    return "\n".join([l for l in out_lines if l])


def _mean_confidence(data: dict) -> float:
    confs = []
    for c in data.get("conf", []):
        try:
            v = float(c)
        except Exception:
            continue
        if v >= 0:
            confs.append(v)
    if not confs:
        return -1.0
    return sum(confs) / len(confs)


def _ocr_image(img: Image.Image) -> str:
    _ensure_tesseract_configured()
    lang = (os.environ.get("COPY_HIGHLIGHT_LANG") or DEFAULT_LANG).strip() or DEFAULT_LANG

    pre = _preprocess_for_ocr(img)
    _debug_save(pre, "last_capture_preprocessed")

    # Try a few page segmentation modes and pick the best confidence.
    # psm 6: assume a block of text; psm 11: sparse text; psm 7: single line.
    candidates = [6, 11, 7]
    best_text = ""
    best_score = (-1.0, 0)
    for psm in candidates:
        config = f"--oem 3 --psm {psm} -c preserve_interword_spaces=1"
        data = pytesseract.image_to_data(
            pre, lang=lang, config=config, output_type=pytesseract.Output.DICT
        )
        text = _data_to_text(data).strip()
        conf = _mean_confidence(data)
        score = (conf, len(text))
        logging.info("OCR candidate psm=%s conf=%.1f chars=%s", psm, conf, len(text))
        if score > best_score and text:
            best_score = score
            best_text = text

    return best_text.strip()


def _copy_to_clipboard(text: str) -> None:
    pyperclip.copy(text)


def _create_tray_icon_image() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # High-contrast icon that remains recognizable at small tray sizes.
    d.ellipse(
        (4, 4, size - 4, size - 4),
        fill=(20, 22, 26, 255),
        outline=(0, 229, 255, 255),
        width=3,
    )

    back = (18, 22, 42, 46)
    front = (22, 16, 46, 40)
    d.rounded_rectangle(back, radius=4, fill=(255, 255, 255, 200))
    d.rounded_rectangle(front, radius=4, fill=(255, 255, 255, 255))
    d.rectangle((26, 32, 42, 35), fill=(0, 229, 255, 255))
    return img


def _load_hotkey() -> str:
    # Avoid common app shortcuts (e.g. DevTools Inspect: Ctrl+Shift+C).
    return (os.environ.get("COPY_HIGHLIGHT_HOTKEY") or DEFAULT_HOTKEY).strip()


def _hotkey_human(hotkey: str) -> str:
    parts = []
    for p in hotkey.replace(" ", "").split("+"):
        if p in {"<ctrl>", "<control>"}:
            parts.append("Ctrl")
        elif p == "<shift>":
            parts.append("Shift")
        elif p == "<alt>":
            parts.append("Alt")
        elif p in {"<cmd>", "<win>"}:
            parts.append("Win")
        else:
            parts.append(p.strip("<>").upper())
    return "+".join([x for x in parts if x])


class RegionSelector:
    def __init__(self) -> None:
        self._result: Optional[BBox] = None

    def select(self) -> Optional[BBox]:
        import tkinter as tk

        vx, vy, vw, vh = _virtual_screen_rect()

        root = tk.Tk()
        root.withdraw()

        overlay = tk.Toplevel(root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", float(os.environ.get("COPY_HIGHLIGHT_OVERLAY_ALPHA", "0.30")))
        overlay.configure(bg="black")
        overlay.geometry(f"{vw}x{vh}+{vx}+{vy}")

        canvas = tk.Canvas(overlay, cursor="cross", bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        start_x = 0
        start_y = 0
        rect_id = None
        hint_id = canvas.create_text(
            16,
            14,
            anchor="nw",
            fill="white",
            text="Drag to select text - Release to copy - Esc to cancel",
            font=("Segoe UI", 11),
        )

        def cancel(_: object | None = None) -> None:
            self._result = None
            overlay.destroy()
            root.quit()

        def on_press(event: tk.Event) -> None:  # type: ignore[no-untyped-def]
            nonlocal start_x, start_y, rect_id
            start_x, start_y = int(event.x), int(event.y)
            if rect_id is not None:
                canvas.delete(rect_id)
            rect_id = canvas.create_rectangle(
                start_x,
                start_y,
                start_x,
                start_y,
                outline="#00E5FF",
                width=3,
                fill="#00E5FF",
                stipple="gray25",
            )
            canvas.tag_raise(hint_id)

        def on_move(event: tk.Event) -> None:  # type: ignore[no-untyped-def]
            if rect_id is None:
                return
            canvas.coords(rect_id, start_x, start_y, int(event.x), int(event.y))
            canvas.tag_raise(hint_id)

        def on_release(event: tk.Event) -> None:  # type: ignore[no-untyped-def]
            nonlocal rect_id
            end_x, end_y = int(event.x), int(event.y)
            box = BBox(
                left=vx + start_x,
                top=vy + start_y,
                right=vx + end_x,
                bottom=vy + end_y,
            ).normalized()
            if box.is_too_small():
                cancel()
                return
            self._result = box
            overlay.destroy()
            root.quit()

        overlay.bind("<Escape>", cancel)
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_move)
        canvas.bind("<ButtonRelease-1>", on_release)

        root.mainloop()
        try:
            root.destroy()
        except Exception:
            pass
        return self._result


class CopyHighlightApp:
    def __init__(self) -> None:
        self._events: "queue.Queue[str]" = queue.Queue()
        self._stop = threading.Event()
        self._tray_icon: Optional[pystray.Icon] = None
        self._tesseract_warned = False
        self._hotkey = _load_hotkey()

    def start(self) -> None:
        self._start_hotkey_listener()
        self._start_tray_icon()
        self._start_startup_notification()

    def _start_startup_notification(self) -> None:
        def run() -> None:
            time.sleep(1.0)
            self._notify(
                f"Running. Press {_hotkey_human(self._hotkey)}, then drag to copy text."
            )

        t = threading.Thread(target=run, name="startup-notify", daemon=True)
        t.start()

    def _start_hotkey_listener(self) -> None:
        def run_listener() -> None:
            with keyboard.GlobalHotKeys(
                {self._hotkey: lambda: self._events.put("capture")}
            ) as h:
                while not self._stop.is_set():
                    time.sleep(0.05)
                h.stop()

        t = threading.Thread(target=run_listener, name="hotkeys", daemon=True)
        t.start()

    def _start_tray_icon(self) -> None:
        def on_capture(icon: pystray.Icon, item: pystray.MenuItem) -> None:  # noqa: ARG001
            self._events.put("capture")

        def on_quit(icon: pystray.Icon, item: pystray.MenuItem) -> None:  # noqa: ARG001
            self._events.put("quit")

        menu = pystray.Menu(
            pystray.MenuItem(f"Capture ({_hotkey_human(self._hotkey)})", on_capture),
            pystray.MenuItem("Quit", on_quit),
        )
        app_name = _app_name()
        self._tray_icon = pystray.Icon(
            app_name,
            _create_tray_icon_image(),
            app_name,
            menu,
        )

        t = threading.Thread(target=self._tray_icon.run, name="tray", daemon=True)
        t.start()

    def run_forever(self) -> int:
        while not self._stop.is_set():
            try:
                ev = self._events.get(timeout=0.2)
            except queue.Empty:
                continue

            if ev == "quit":
                self._stop.set()
                break
            if ev == "capture":
                self._capture_once()

        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        return 0

    def _notify(self, message: str, title: str | None = None) -> None:
        icon = self._tray_icon
        if not icon:
            return
        notify = getattr(icon, "notify", None)
        if not callable(notify):
            return
        try:
            notify(message, title or _app_name())
        except Exception:
            pass

    def _capture_once(self) -> None:
        selector = RegionSelector()
        bbox = selector.select()
        if not bbox:
            return

        try:
            img = ImageGrab.grab(
                bbox=(bbox.left, bbox.top, bbox.right, bbox.bottom),
                all_screens=True,
            )
        except TypeError:
            img = ImageGrab.grab(bbox=(bbox.left, bbox.top, bbox.right, bbox.bottom))
        _debug_save(img, "last_capture_raw")

        try:
            text = _ocr_image(img)
        except RuntimeError as e:
            logging.warning("OCR unavailable: %s", e)
            if not self._tesseract_warned:
                self._tesseract_warned = True
                self._notify(str(e))
            return
        except Exception:
            logging.exception("OCR failed")
            return

        if not text:
            self._notify("No text detected. Try zooming in and capturing a tighter region.")
            return
        _copy_to_clipboard(text)
        self._notify("Copied to clipboard.")


def main() -> int:
    _set_dpi_awareness()
    log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CopyHighlight"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        global _LOG_DIR
        _LOG_DIR = log_dir
        logging.basicConfig(
            filename=str(log_dir / "copy_highlight.log"),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
    except Exception:
        logging.basicConfig(level=logging.INFO)

    app = CopyHighlightApp()
    app.start()
    return app.run_forever()
