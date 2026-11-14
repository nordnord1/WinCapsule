"""Keyboard layout switcher (EN QWERTY <-> UA ЙЦУКЕН) and a robust UA<->EN translator."""

from __future__ import annotations

import itertools
import re
import threading

import requests
from PySide6.QtCore import QObject, Signal

from core.i18n import tr

EN_CHARS = (
    "`qwertyuiop[]asdfghjkl;'zxcvbnm,./"
    "~QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?"
)
UA_CHARS = (
    "'йцукенгшщзхїфівапролджєячсмитьбю."
    "₴ЙЦУКЕНГШЩЗХЇФІВАПРОЛДЖЄЯЧСМИТЬБЮ,"
)

_EN_TO_UA = str.maketrans(EN_CHARS, UA_CHARS)
_UA_TO_EN = str.maketrans(UA_CHARS, EN_CHARS)

_LATIN_VOWELS = set("aeiouy")
_CYR_VOWELS = set("аеєиіїоуюяыэё")

TRANSLATOR_SOURCE_LANGS: tuple[str, ...] = ("auto", "uk", "en", "ru", "es", "fr", "pl")
TRANSLATOR_TARGET_LANGS: tuple[str, ...] = ("uk", "en", "ru", "es", "fr", "pl")

LANG_NAMES = {
    "auto": "Auto",
    "uk": "Українська",
    "en": "English",
    "ru": "Російська",
    "pl": "Польська",
    "de": "Німецька",
    "fr": "Французька",
    "es": "Іспанська",
    "it": "Італійська",
    "be": "Білоруська",
}


def lang_display_name(code: str) -> str:
    """Return localized display name for a language code."""
    key = f"lang_{code}"
    val = tr(key)
    if val != key:
        return val
    return LANG_NAMES.get(code, code.upper())


def _script_counts(text: str) -> tuple[int, int]:
    latin = sum(1 for c in text if "a" <= c.lower() <= "z")
    cyr = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    return latin, cyr


def fix_keyboard_layout(text: str) -> str:
    """
    Convert text typed in the wrong layout:
    EN->UA ('ghbdsn' -> 'привіт') or UA->EN ('руддщ' -> 'hello'),
    picking the direction from the dominant script.
    """
    if not text:
        return ""
    latin, cyr = _script_counts(text)
    if latin >= cyr:
        return text.translate(_EN_TO_UA)
    return text.translate(_UA_TO_EN)


def looks_like_wrong_layout(text: str) -> str | None:
    """
    Heuristic: return the fixed text if `text` looks like it was typed in the
    wrong keyboard layout (e.g. 'ghbdsn' or 'руддщ'), else None.
    """
    words = re.findall(r"[^\s\d]+", text.strip())
    letters = "".join(words)
    if len(letters) < 4:
        return None
    latin, cyr = _script_counts(letters)
    low = letters.lower()
    if latin > cyr:
        vowels = sum(1 for c in low if c in _LATIN_VOWELS)
        odd = sum(1 for c in low if c in "[];',.`")
        ratio = vowels / max(1, latin)
        if ratio < 0.2 or odd >= 2:
            fixed = fix_keyboard_layout(text)
            return fixed if fixed != text else None
    elif cyr > latin:
        vowels = sum(1 for c in low if c in _CYR_VOWELS)
        ratio = vowels / max(1, cyr)
        if ratio < 0.22:
            fixed = fix_keyboard_layout(text)
            return fixed if fixed != text else None
    return None


def detect_direction(text: str) -> tuple[str, str]:
    """Primary-script guess: Cyrillic -> ('uk','en'), otherwise ('en','uk')."""
    latin, cyr = _script_counts(text)
    if cyr > latin:
        return ("uk", "en")
    return ("en", "uk")


def _chunk_text(text: str, limit: int = 3800) -> list[str]:
    """Split long text on paragraph / sentence boundaries without breaking words."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    buf = ""
    for piece in re.split(r"(?<=[\.\!\?\n])", text):
        if len(buf) + len(piece) > limit and buf:
            chunks.append(buf)
            buf = ""
        while len(piece) > limit:
            chunks.append(piece[:limit])
            piece = piece[limit:]
        buf += piece
    if buf:
        chunks.append(buf)
    return chunks


def _google_translate(text: str, tl: str, sl: str = "auto") -> tuple[str, str]:
    resp = requests.post(
        "https://translate.googleapis.com/translate_a/single",
        params={
            "client": "gtx",
            "sl": sl,
            "tl": tl,
            "dt": "t",
            "dj": "1",
            "ie": "UTF-8",
            "oe": "UTF-8",
        },
        data={"q": text},
        timeout=8,
    )
    resp.raise_for_status()
    data = resp.json()
    result = "".join(s.get("trans", "") for s in data.get("sentences", []) if isinstance(s, dict))
    return result, str(data.get("src") or sl)


def _mymemory_translate(text: str, sl: str, tl: str) -> str:
    resp = requests.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text[:480], "langpair": f"{sl}|{tl}"},
        timeout=8,
    )
    resp.raise_for_status()
    return str(resp.json().get("responseData", {}).get("translatedText", "")).strip()


def translate_text(
    text: str,
    direction: str = "auto",
    src_lang: str | None = None,
    tgt_lang: str | None = None,
) -> tuple[str, str, str]:
    """
    Blocking translation. Returns (translated_text, detected_src, target).
    Supports explicit src_lang/tgt_lang or direction tokens like 'auto', 'uk_en', 'auto_es'.
    """
    clean = text.replace("\r\n", "\n").strip()
    if not clean:
        return "", "", ""

    if src_lang is not None and tgt_lang is not None:
        sl = src_lang
        tl = tgt_lang
    elif direction == "uk_en":
        sl, tl = "uk", "en"
    elif direction == "en_uk":
        sl, tl = "en", "uk"
    elif "_" in direction:
        parts_dir = direction.split("_", 1)
        sl, tl = parts_dir[0] or "auto", parts_dir[1] or "en"
    else:
        sl = "auto"
        tl = detect_direction(clean)[1]

    try:
        parts: list[str] = []
        detected_src = sl
        for chunk in _chunk_text(clean):
            out, detected_src = _google_translate(chunk, tl, sl=sl)
            parts.append(out)
        result = "".join(parts).strip()

        # Auto mode: if Google says the text already is in the target language, flip.
        if sl == "auto" and detected_src == tl:
            tl = "uk" if tl == "en" else "en"
            parts = [_google_translate(chunk, tl, sl="auto")[0] for chunk in _chunk_text(clean)]
            result = "".join(parts).strip()
        if result:
            return result, detected_src, tl
    except Exception:
        pass

    # Fallback provider
    fb_sl = sl if sl != "auto" else ("uk" if tl == "en" else "en")
    result = _mymemory_translate(clean, fb_sl, tl)
    if not result:
        raise RuntimeError("empty translation")
    return result, fb_sl, tl


class TranslatorService(QObject):
    """Asynchronous multilingual translator with stale-request protection."""

    translation_ready = Signal(int, str, str, str)  # request_id, text, src, tgt
    translation_error = Signal(int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ids = itertools.count(1)
        self.latest_id = 0

    def translate(
        self,
        text: str,
        direction: str = "auto",
        src_lang: str | None = None,
        tgt_lang: str | None = None,
    ) -> int:
        cleaned = text.strip()
        if not cleaned:
            return 0
        req_id = next(self._ids)
        self.latest_id = req_id
        threading.Thread(
            target=self._worker,
            args=(req_id, cleaned, direction, src_lang, tgt_lang),
            daemon=True,
        ).start()
        return req_id

    def _worker(
        self,
        req_id: int,
        text: str,
        direction: str,
        src_lang: str | None,
        tgt_lang: str | None,
    ) -> None:
        try:
            result, src, tgt = translate_text(text, direction, src_lang=src_lang, tgt_lang=tgt_lang)
            self.translation_ready.emit(req_id, result, src, tgt)
        except Exception:
            self.translation_error.emit(req_id, tr("tr_err_net"))
