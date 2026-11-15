"""Screen region text recognition (OCR) with Windows WinRT offline + cloud fallback."""

from __future__ import annotations

import asyncio
import itertools
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import requests
from PySide6.QtCore import QBuffer, QIODevice, QObject, Qt, Signal
from PySide6.QtGui import QImage

from core.i18n import tr

try:
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import (
        BitmapAlphaMode,
        BitmapPixelFormat,
        SoftwareBitmap,
    )
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter

    WINRT_OCR_AVAILABLE = True
except ImportError:  # pragma: no cover
    WINRT_OCR_AVAILABLE = False
    Language = None
    SoftwareBitmap = None
    BitmapPixelFormat = None
    BitmapAlphaMode = None
    OcrEngine = None
    DataWriter = None


_LANG_TAG_MAP = {
    "uk": "uk-UA",
    "en": "en-US",
    "ru": "ru-RU",
    "es": "es-ES",
    "fr": "fr-FR",
    "pl": "pl-PL",
}

_TESS_LANG_MAP = {
    "uk": "ukr+eng",
    "ru": "rus+eng",
    "en": "eng",
    "es": "spa+eng",
    "fr": "fra+eng",
    "pl": "pol+eng",
    "auto": "eng+ukr+rus",
}


def _prepare_ocr_image(image: QImage) -> QImage:
    """Ensure RGBA8888 format and upscale small UI text crops for sharper OCR."""
    if image.isNull():
        return image
    prepared = image
    if prepared.width() < 480 or prepared.height() < 120:
        scale = 2 if max(prepared.width(), prepared.height()) < 900 else 1
        if scale > 1:
            prepared = prepared.scaled(
                prepared.width() * scale,
                prepared.height() * scale,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    if prepared.format() != QImage.Format.Format_RGBA8888:
        prepared = prepared.convertToFormat(QImage.Format.Format_RGBA8888)
    return prepared


def _encode_png_bytes(image: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


def _ocr_via_winrt(
    rgba_bytes: bytes,
    width: int,
    height: int,
    lang_hint: str = "auto",
) -> str | None:
    if not WINRT_OCR_AVAILABLE or not rgba_bytes or width <= 0 or height <= 0:
        return None
    try:
        avail = list(OcrEngine.available_recognizer_languages)
        if not avail:
            return None

        engine = None
        wanted_tag = _LANG_TAG_MAP.get(lang_hint, "")
        if wanted_tag:
            for lang in avail:
                if lang.language_tag.lower().startswith(lang_hint):
                    engine = OcrEngine.try_create_from_language(lang)
                    if engine is not None:
                        break
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            engine = OcrEngine.try_create_from_language(avail[0])
        if engine is None:
            return None

        dw = DataWriter()
        dw.write_bytes(rgba_bytes)
        ibuf = dw.detach_buffer()
        bmp = SoftwareBitmap.create_copy_from_buffer(
            ibuf,
            BitmapPixelFormat.RGBA8,
            width,
            height,
            BitmapAlphaMode.PREMULTIPLIED,
        )
        result = asyncio.run(engine.recognize_async(bmp))
        lines = [line.text.strip() for line in result.lines if line.text and line.text.strip()]
        if lines:
            return "\n".join(lines)
        return (result.text or "").strip()
    except Exception:
        return None


def _find_tesseract() -> str | None:
    exe = shutil.which("tesseract")
    if exe:
        return exe
    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def _ocr_via_tesseract(png_bytes: bytes, lang_hint: str = "auto") -> str | None:
    exe = _find_tesseract()
    if not exe or not png_bytes:
        return None
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tf.write(png_bytes)
            tmp_path = tf.name
        lang_arg = _TESS_LANG_MAP.get(lang_hint, "eng")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            [exe, tmp_path, "stdout", "-l", lang_arg, "--psm", "6"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=creationflags,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
        # Retry with English only if a traineddata pack is missing
        if lang_arg != "eng":
            proc2 = subprocess.run(
                [exe, tmp_path, "stdout", "-l", "eng", "--psm", "6"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=creationflags,
            )
            if proc2.returncode == 0:
                return proc2.stdout.strip()
    except Exception:
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass
    return None


def _ocr_via_cloud(png_bytes: bytes) -> str:
    resp = requests.post(
        "https://api.ocr.space/parse/image",
        files={"file": ("capture.png", png_bytes, "image/png")},
        data={"apikey": "helloworld", "OCREngine": "2", "scale": "true"},
        timeout=14,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("IsErroredOnProcessing"):
        raise RuntimeError(str(payload.get("ErrorMessage") or "ocr error"))
    parsed = payload.get("ParsedResults") or []
    texts = [str(r.get("ParsedText", "")).strip() for r in parsed if isinstance(r, dict)]
    return "\n".join(t for t in texts if t).strip()


def recognize_bytes(
    rgba_bytes: bytes,
    width: int,
    height: int,
    png_bytes: bytes,
    lang_hint: str = "auto",
) -> str:
    """Run offline WinRT -> local Tesseract -> OCR.space cloud recognition."""
    txt = _ocr_via_winrt(rgba_bytes, width, height, lang_hint=lang_hint)
    if txt is not None:
        return txt

    txt_tess = _ocr_via_tesseract(png_bytes, lang_hint=lang_hint)
    if txt_tess is not None:
        return txt_tess

    return _ocr_via_cloud(png_bytes)


class OcrService(QObject):
    """Asynchronous screen capture OCR service with stale-request protection."""

    ocr_ready = Signal(int, str, str)  # request_id, recognized_text, action ("copy"|"translate")
    ocr_error = Signal(int, str)  # request_id, error_message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ids = itertools.count(1)
        self.latest_id = 0

    def recognize_image(
        self,
        image: QImage,
        action: str = "translate",
        lang_hint: str = "auto",
    ) -> int:
        prepared = _prepare_ocr_image(image)
        if prepared.isNull():
            return 0
        req_id = next(self._ids)
        self.latest_id = req_id

        width = prepared.width()
        height = prepared.height()
        rgba_bytes = bytes(prepared.constBits())
        png_bytes = _encode_png_bytes(prepared)

        threading.Thread(
            target=self._worker,
            args=(req_id, rgba_bytes, width, height, png_bytes, action, lang_hint),
            daemon=True,
        ).start()
        return req_id

    def _worker(
        self,
        req_id: int,
        rgba_bytes: bytes,
        width: int,
        height: int,
        png_bytes: bytes,
        action: str,
        lang_hint: str,
    ) -> None:
        try:
            text = recognize_bytes(rgba_bytes, width, height, png_bytes, lang_hint=lang_hint)
            self.ocr_ready.emit(req_id, text, action)
        except Exception:
            self.ocr_error.emit(req_id, tr("ocr_err"))
