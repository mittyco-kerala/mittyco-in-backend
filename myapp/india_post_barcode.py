"""Helpers for India Post S10 article identifiers and allocated serials."""

import re


_S10_WEIGHTS = (8, 6, 4, 2, 3, 5, 9, 7)


def s10_check_digit(serial):
    """Return the UPU S10 check digit for an eight-digit serial number."""
    serial_text = str(serial)
    if not serial_text.isdigit() or len(serial_text) > 8:
        raise ValueError("An S10 serial must contain at most eight digits.")
    serial_text = serial_text.zfill(8)
    remainder = sum(
        int(digit) * weight
        for digit, weight in zip(serial_text, _S10_WEIGHTS)
    ) % 11
    result = 11 - remainder
    if result == 10:
        return "0"
    if result == 11:
        return "5"
    return str(result)


def make_s10_barcode(prefix, serial):
    """Build a 13-character S10 barcode from its DOP prefix and serial."""
    prefix = str(prefix or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", prefix):
        raise ValueError("An India Post barcode prefix must contain two letters.")
    serial_text = str(serial)
    if not serial_text.isdigit() or len(serial_text) > 8:
        raise ValueError("An India Post allocated serial must contain at most eight digits.")
    serial_text = serial_text.zfill(8)
    return f"{prefix}{serial_text}{s10_check_digit(serial_text)}IN"


def is_valid_s10_barcode(barcode):
    """Check the S10 shape and check digit of an India Post article ID."""
    match = re.fullmatch(r"[A-Z]{2}(\d{8})(\d)IN", str(barcode or ""))
    return bool(match and match.group(2) == s10_check_digit(match.group(1)))


def barcode_serial_candidates(barcode):
    """Return possible serials, including legacy zero-padded local IDs."""
    match = re.fullmatch(r"[A-Z]{2}(\d{9})IN", str(barcode or ""))
    if not match:
        return set()
    numeric = match.group(1)
    candidates = {int(numeric[:8])}
    if numeric.startswith("0"):
        candidates.add(int(numeric))
    elif not is_valid_s10_barcode(barcode):
        candidates.add(int(numeric))
    return candidates
