#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jiar and contributors
"""Render public synthetic illustrations with Python stdlib and macOS AppKit.

Usage: python3 -I scripts/render-demo.py
No app is launched. No desktop capture, user config, account store, credential,
installed app, or live Magpie endpoint is used. Requires macOS and full Xcode.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "docs" / "images"
FIXTURE = ROOT / "docs" / "demo-allowances.json"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strip_png_metadata(path):
    """Retain only image data and sRGB; drop AppKit's automatically added EXIF."""
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    clean = bytearray(raw[:8])
    offset = 8
    while offset < len(raw):
        size = struct.unpack(">I", raw[offset:offset + 4])[0]
        chunk = raw[offset + 4:offset + 8]
        end = offset + size + 12
        assert end <= len(raw), "Invalid PNG chunk"
        expected_crc = struct.unpack(">I", raw[end - 4:end])[0]
        assert zlib.crc32(raw[offset + 4:end - 4]) & 0xFFFFFFFF == expected_crc
        if chunk in (b"IHDR", b"PLTE", b"IDAT", b"IEND", b"sRGB", b"tRNS"):
            clean.extend(raw[offset:end])
        offset = end
    path.write_bytes(clean)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-only", action="store_true", help="Verify and export synthetic text/report without rendering PNGs")
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # Importing these modules does not call main, read_config or fetch_allowances.
    # Use the production pure functions, not a second implementation of the math.
    magpie = load_module("demo_magpie", ROOT / "magpie.py")
    configure = load_module("demo_configure", ROOT / "configure.py")
    def forbidden(*args, **kwargs):
        raise RuntimeError("The public demo cannot read live services or user settings")
    for module in (magpie, configure.magpie):
        module.fetch_allowances = forbidden
        module.read_config = forbidden
    now = dt.datetime.fromisoformat(fixture["now"].replace("Z", "+00:00"))
    config, rows = fixture["config"], fixture["data"]
    magpie.validate_config(config)
    report = magpie.aggregate_allowances(rows, config, now=now)
    assert report["limits"][0]["usedPercent"] == 50.0
    # The explanatory formula is intentionally specific to this stable fixture.
    assert [limit["usedPercent"] for limit in report["limits"]] == [50, 62, 24, 34, 52]
    assert report["balance"] == {"amount": 18.4, "currency": "USD"}
    assert all("Qoder" not in limit["label"] for limit in report["limits"])
    assert all("@" not in row["user"] and row["user"].endswith("-demo") for row in rows)

    (ROOT / ".local").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="demo-", dir=ROOT / ".local"))
    (work / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, function, kwargs in [
        ("demo-providers.txt", configure.print_providers, {}),
        ("demo-details.txt", configure.print_details, {"now": now}),
    ]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            function(config, rows, **kwargs)
        text = stream.getvalue()
        assert "@" not in text
        (work / name).write_text(text, encoding="utf-8")
    IMAGES.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "demo-providers.txt", "demo-details.txt"):
        # Public text equivalents make every value accessible without the PNGs.
        (IMAGES / ("demo-report.json" if name == "report.json" else name)).write_bytes((work / name).read_bytes())
    if args.data_only:
        print("Verified and exported wholly synthetic report and complete CLI output.")
        return
    env = {**os.environ, "TZ": "UTC", "LC_ALL": "en_US.UTF-8"}
    subprocess.run(["xcrun", "swift", "-module-cache-path", str(work / "module-cache"),
        str(ROOT / "scripts" / "render-demo.swift"), str(work), str(IMAGES)],
        check=True, cwd=work, env=env)
    for name in ("magpie-usage.png", "provider-settings.png"):
        strip_png_metadata(IMAGES / name)
    manifest = {
        "kind": "Synthetic illustrations, not running screenshots or native Pulse component renders",
        "data": "Wholly fictional fixture; no screen capture, live service, user config, account, or credential reads",
        "fixtureSHA256": sha256(FIXTURE),
        "magpieSourceSHA256": sha256(ROOT / "magpie.py"),
        "configureSourceSHA256": sha256(ROOT / "configure.py"),
        "reportSHA256": sha256(IMAGES / "demo-report.json"),
        "cli": "Unedited configure.print_providers and configure.print_details output, evaluated at fixture.now",
        "artwork": "Typography and simple AppKit geometry; no third-party logos, icon assets, or fonts",
        "images": {name: sha256(IMAGES / name) for name in ("magpie-usage.png", "provider-settings.png")},
        "reproducibility": "Fixed fixture, values, UTC timestamps, and explicit colors. AppKit text rasterization may differ by macOS/Xcode/font version."
    }
    (IMAGES / "render-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Generated " + str(IMAGES / "magpie-usage.png"))
    print("Generated " + str(IMAGES / "provider-settings.png"))
    print("Scratch folder: " + str(work))


if __name__ == "__main__":
    main()
