"""Native Rust PDF acceleration bridge (`pdf_rust_accel.dll`) loaded via `ctypes`.
Provides ultra-fast SIMD/native pixel scanning, visual PDF comparison diffing,
ITU-R BT.601 grayscale conversion, RGBA watermark alpha scaling, and FNV-1a 64-bit hashing,
with automatic fallback if the DLL is absent."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import ctypes
import os
import sys
from typing import Optional

_LIB: Optional[ctypes.CDLL] = None
_LOADED = False


def _find_dll() -> Optional[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    meipass = getattr(sys, "_MEIPASS", None)
    candidates = [
        os.path.join(here, "pdf_rust_accel.dll"),
        os.path.join(root, "rust_accel", "target", "release", "pdf_rust_accel.dll"),
    ]
    if meipass:
        candidates.insert(0, os.path.join(meipass, "core", "pdf_rust_accel.dll"))
        candidates.insert(1, os.path.join(meipass, "pdf_rust_accel.dll"))
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def _get_lib() -> Optional[ctypes.CDLL]:
    global _LIB, _LOADED
    if _LOADED:
        return _LIB
    _LOADED = True
    dll_path = _find_dll()
    if not dll_path:
        return None
    try:
        lib = ctypes.CDLL(dll_path)
        lib.rust_accel_version.argtypes = []
        lib.rust_accel_version.restype = ctypes.c_uint32

        lib.rust_is_page_blank.argtypes = [
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_uint8,
            ctypes.c_double,
        ]
        lib.rust_is_page_blank.restype = ctypes.c_int32

        lib.rust_visual_diff_rgb.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_uint8,
        ]
        lib.rust_visual_diff_rgb.restype = ctypes.c_size_t

        lib.rust_rgb_to_grayscale.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        lib.rust_rgb_to_grayscale.restype = None

        lib.rust_scale_rgba_alpha.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_uint32,
        ]
        lib.rust_scale_rgba_alpha.restype = None

        lib.rust_fnv1a_64.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        lib.rust_fnv1a_64.restype = ctypes.c_uint64

        if lib.rust_accel_version() >= 100:
            _LIB = lib
    except Exception:
        _LIB = None
    return _LIB


def rust_available() -> bool:
    """Return True if the compiled Rust native library (`pdf_rust_accel.dll`) is active."""
    return _get_lib() is not None


def rust_version() -> str:
    lib = _get_lib()
    if not lib:
        return "fallback"
    v = int(lib.rust_accel_version())
    return f"{v // 100}.{(v // 10) % 10}.{v % 10}"


def is_buffer_blank(samples: bytes, white_threshold: int = 245, max_dark_ratio: float = 0.002) -> bool:
    """Check whether a rendered page sample buffer is visually blank using Rust."""
    if not samples:
        return True
    lib = _get_lib()
    if lib is not None:
        res = lib.rust_is_page_blank(samples, len(samples), white_threshold, float(max_dark_ratio))
        return bool(res == 1)
    # Fallback
    step = max(1, len(samples) // 30000)
    sampled = samples[::step]
    non_white = sum(1 for b in sampled if b < white_threshold)
    return (non_white / max(1, len(sampled))) <= max_dark_ratio


def visual_diff_rgb(
    buf_a: bytes,
    buf_b: bytes,
    pixel_count: int,
    threshold: int = 18,
) -> tuple[bytes, int]:
    """Compare two RGB buffers of `pixel_count` pixels and return `(diff_rgb_bytes, changed_pixels)`."""
    byte_len = pixel_count * 3
    if len(buf_a) < byte_len or len(buf_b) < byte_len or pixel_count <= 0:
        return b"", 0
    lib = _get_lib()
    if lib is not None:
        out_arr = (ctypes.c_uint8 * byte_len)()
        changed = int(lib.rust_visual_diff_rgb(buf_a, buf_b, out_arr, pixel_count, int(threshold)))
        return bytes(out_arr), changed

    # Fallback via PIL
    from PIL import Image, ImageChops

    im1 = Image.frombytes("RGB", (pixel_count, 1), buf_a[:byte_len])
    im2 = Image.frombytes("RGB", (pixel_count, 1), buf_b[:byte_len])
    diff_gray = ImageChops.difference(im1, im2).convert("L")
    mask = diff_gray.point(lambda v: 255 if v > threshold else 0)
    changed = sum(1 for v in mask.getdata() if v > 0)
    red_layer = Image.new("RGB", (pixel_count, 1), (229, 50, 45))
    blended = Image.blend(im2, Image.new("RGB", (pixel_count, 1), (255, 255, 255)), 0.25)
    blended.paste(red_layer, mask=mask)
    return blended.tobytes(), changed


def rgb_to_grayscale_bytes(rgb_bytes: bytes, pixel_count: int) -> bytes:
    """Convert `pixel_count` RGB pixels (`3 * pixel_count` bytes) into 1-channel grayscale bytes."""
    if pixel_count <= 0 or len(rgb_bytes) < pixel_count * 3:
        return b""
    lib = _get_lib()
    if lib is not None:
        out_arr = (ctypes.c_uint8 * pixel_count)()
        lib.rust_rgb_to_grayscale(rgb_bytes, out_arr, pixel_count)
        return bytes(out_arr)

    from PIL import Image

    im = Image.frombytes("RGB", (pixel_count, 1), rgb_bytes[: pixel_count * 3]).convert("L")
    return im.tobytes()


def scale_rgba_alpha(rgba_bytes: bytes, pixel_count: int, opacity: float) -> bytes:
    """Scale the alpha channel of `rgba_bytes` (`4 * pixel_count` bytes) by `opacity` in `[0.0, 1.0]`."""
    byte_len = pixel_count * 4
    if pixel_count <= 0 or len(rgba_bytes) < byte_len:
        return rgba_bytes
    scale_256 = max(0, min(256, int(round(opacity * 256))))
    lib = _get_lib()
    if lib is not None:
        buf = (ctypes.c_uint8 * byte_len).from_buffer_copy(rgba_bytes[:byte_len])
        lib.rust_scale_rgba_alpha(buf, pixel_count, scale_256)
        return bytes(buf)

    arr = bytearray(rgba_bytes[:byte_len])
    for i in range(3, byte_len, 4):
        arr[i] = (arr[i] * scale_256) >> 8
    return bytes(arr)


def fnv1a_64(data: bytes) -> int:
    """Compute a fast 64-bit FNV-1a fingerprint using Rust."""
    lib = _get_lib()
    if lib is not None:
        return int(lib.rust_fnv1a_64(data, len(data)))
    h = 0xCBF29CE484222325
    for b in data:
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h
