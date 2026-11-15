//! Native Rust acceleration engine for PDF Master.
//! Exposes a C-ABI (`cdylib`) loaded by `core/rust_accel.py` via `ctypes`.

use std::slice;

/// Return engine version (100 = 1.0.0) to verify the native Rust DLL is loaded.
#[no_mangle]
pub extern "C" fn rust_accel_version() -> u32 {
    100
}

/// Inspect an RGB/grayscale byte buffer and return 1 if the page is visually blank, 0 otherwise.
///
/// # Safety
/// `samples` must point to a valid byte buffer of at least `len` bytes.
#[no_mangle]
pub unsafe extern "C" fn rust_is_page_blank(
    samples: *const u8,
    len: usize,
    white_threshold: u8,
    max_dark_ratio: f64,
) -> i32 {
    if samples.is_null() || len == 0 {
        return 1;
    }
    let buf = slice::from_raw_parts(samples, len);
    let max_dark = ((len as f64) * max_dark_ratio).ceil() as usize;
    let mut dark_count: usize = 0;

    for &b in buf {
        if b < white_threshold {
            dark_count += 1;
            if dark_count > max_dark {
                return 0;
            }
        }
    }
    1
}

/// Compare two RGB page buffers (`pixel_count * 3` bytes each) in a single pass,
/// write a highlighted visual diff RGB image into `out_buf`, and return the number
/// of pixels whose channel difference exceeded `threshold`.
///
/// # Safety
/// `buf_a`, `buf_b`, and `out_buf` must each point to valid memory of at least `pixel_count * 3` bytes.
#[no_mangle]
pub unsafe extern "C" fn rust_visual_diff_rgb(
    buf_a: *const u8,
    buf_b: *const u8,
    out_buf: *mut u8,
    pixel_count: usize,
    threshold: u8,
) -> usize {
    if buf_a.is_null() || buf_b.is_null() || out_buf.is_null() || pixel_count == 0 {
        return 0;
    }
    let byte_len = pixel_count.saturating_mul(3);
    let a = slice::from_raw_parts(buf_a, byte_len);
    let b = slice::from_raw_parts(buf_b, byte_len);
    let out = slice::from_raw_parts_mut(out_buf, byte_len);

    let mut diff_pixels: usize = 0;
    let mut idx = 0;
    while idx + 2 < byte_len {
        let r1 = a[idx];
        let g1 = a[idx + 1];
        let b1 = a[idx + 2];

        let r2 = b[idx];
        let g2 = b[idx + 1];
        let b2 = b[idx + 2];

        let dr = r1.abs_diff(r2);
        let dg = g1.abs_diff(g2);
        let db = b1.abs_diff(b2);
        let max_d = dr.max(dg).max(db);

        if max_d > threshold {
            diff_pixels += 1;
            // Highlight changed pixel in vivid PDF Master red while keeping underlying contrast
            out[idx] = 229;
            out[idx + 1] = g2 >> 1;
            out[idx + 2] = b2 >> 1;
        } else {
            // Softly blend unchanged pixel so red highlights stand out clearly
            out[idx] = ((r2 as u16 * 3 + 255) >> 2) as u8;
            out[idx + 1] = ((g2 as u16 * 3 + 255) >> 2) as u8;
            out[idx + 2] = ((b2 as u16 * 3 + 255) >> 2) as u8;
        }
        idx += 3;
    }
    diff_pixels
}

/// Convert an RGB buffer (`pixel_count * 3` bytes) into a 1-channel perceptual grayscale
/// buffer (`pixel_count` bytes) using ITU-R BT.601 integer weights: `(77*R + 150*G + 29*B) >> 8`.
///
/// # Safety
/// `rgb_buf` must be at least `pixel_count * 3` bytes and `out_gray` at least `pixel_count` bytes.
#[no_mangle]
pub unsafe extern "C" fn rust_rgb_to_grayscale(
    rgb_buf: *const u8,
    out_gray: *mut u8,
    pixel_count: usize,
) {
    if rgb_buf.is_null() || out_gray.is_null() || pixel_count == 0 {
        return;
    }
    let src = slice::from_raw_parts(rgb_buf, pixel_count.saturating_mul(3));
    let dst = slice::from_raw_parts_mut(out_gray, pixel_count);

    for i in 0..pixel_count {
        let base = i * 3;
        let r = src[base] as u32;
        let g = src[base + 1] as u32;
        let b = src[base + 2] as u32;
        dst[i] = ((77 * r + 150 * g + 29 * b) >> 8) as u8;
    }
}

/// Scale the alpha channel of an RGBA buffer (`pixel_count * 4` bytes) in-place.
/// `opacity_256` is in `[0, 256]` where `256` = 100% opacity.
///
/// # Safety
/// `rgba_buf` must point to a valid mutable buffer of at least `pixel_count * 4` bytes.
#[no_mangle]
pub unsafe extern "C" fn rust_scale_rgba_alpha(
    rgba_buf: *mut u8,
    pixel_count: usize,
    opacity_256: u32,
) {
    if rgba_buf.is_null() || pixel_count == 0 {
        return;
    }
    let scale = opacity_256.min(256);
    let buf = slice::from_raw_parts_mut(rgba_buf, pixel_count.saturating_mul(4));
    let mut idx = 3;
    while idx < buf.len() {
        buf[idx] = (((buf[idx] as u32) * scale) >> 8) as u8;
        idx += 4;
    }
}

/// Compute a fast 64-bit FNV-1a hash of a byte buffer (for fast page/stream deduplication).
///
/// # Safety
/// `data` must point to a valid byte buffer of at least `len` bytes.
#[no_mangle]
pub unsafe extern "C" fn rust_fnv1a_64(data: *const u8, len: usize) -> u64 {
    if data.is_null() || len == 0 {
        return 0xcbf29ce484222325;
    }
    let buf = slice::from_raw_parts(data, len);
    let mut hash: u64 = 0xcbf29ce484222325;
    for &b in buf {
        hash ^= b as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    hash
}
