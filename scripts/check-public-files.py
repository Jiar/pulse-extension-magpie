#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jiar and contributors
"""Check staged/tracked publication files; never inspect ignored local material."""

from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
EMAIL = re.compile(r"[A-Za-z0-9_.+%-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PRIVATE_PATH = re.compile(r"(?:/(?:Users|home)/|[A-Za-z]:\\Users\\)[^\s/\\]+[/\\]")
SECRET = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}|\bsk-[A-Za-z0-9_-]{24,}")
UPSTREAM_FILES = {"README.md", "LICENSE-Pulse.txt", "detail-card-overflow.patch"}


def check_png(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "invalid PNG signature"
    cursor = 8
    while cursor < len(data):
        if len(data) - cursor < 12:
            return "truncated PNG chunk"
        length = struct.unpack_from(">I", data, cursor)[0]
        end = cursor + 12 + length
        if end > len(data):
            return "truncated PNG data"
        kind = data[cursor + 4:cursor + 8]
        payload = data[cursor + 8:cursor + 8 + length]
        stored_crc = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != stored_crc:
            return "invalid PNG checksum"
        if kind in (b"tEXt", b"zTXt", b"iTXt", b"eXIf"):
            return "unexpected text/EXIF metadata in demo PNG"
        if kind == b"IEND":
            return None if end == len(data) else "unexpected trailing PNG data"
        cursor = end
    return "missing PNG end marker"


def main():
    listing = subprocess.run(["git", "ls-files", "--stage", "-z"], cwd=ROOT,
                             capture_output=True, check=True).stdout
    entries = listing.split(b"\0")
    problems, count = [], 0
    for entry in entries:
        if not entry:
            continue
        info, raw_name = entry.split(b"\t", 1)
        mode, object_id, stage = info.decode("ascii").split()
        name = raw_name.decode("utf-8")
        path = PurePosixPath(name)
        count += 1
        if mode not in ("100644", "100755") or stage != "0":
            problems.append((name, "symlink, submodule or unresolved index entry"))
            continue
        if (any(part in {".local", "__pycache__", ".venv", "build.noindex"} or part.endswith(".app") for part in path.parts)
                or path.name in {"config.json", "VERIFICATION.md"}
                or path.name.startswith(".env")
                or path.suffix.lower() in {".zip", ".dmg", ".pyc", ".p12", ".pem", ".key"}
                or (path.parts[0] == "native-pulse" and (len(path.parts) != 2 or path.name not in UPSTREAM_FILES))):
            problems.append((name, "private/local file must not be published"))
            continue
        # Inspect the bytes that would actually be committed, even if the worktree differs.
        data = subprocess.run(["git", "cat-file", "blob", object_id], cwd=ROOT,
                              capture_output=True, check=True).stdout
        if len(data) > 2 * 1024 * 1024:
            problems.append((name, "unexpected file larger than 2 MiB"))
            continue
        if path.suffix.lower() == ".png":
            reason = check_png(data)
            if reason:
                problems.append((name, reason))
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            problems.append((name, "unexpected binary file"))
            continue
        if PRIVATE_PATH.search(text):
            problems.append((name, "personal absolute path"))
        if SECRET.search(text):
            problems.append((name, "possible credential material"))
        if any(domain.lower() not in {"example.com", "example.invalid"} for domain in EMAIL.findall(text)):
            problems.append((name, "email outside reserved example domains"))
    if not count:
        problems.append(("index", "no tracked files to inspect"))
    for name, reason in problems:
        print("%s: %s" % (name, reason), file=sys.stderr)
    if problems:
        return 1
    print("Checked %d publication files; no common private-file or metadata markers found." % count)
    print("This check does not replace manual review of content and image pixels.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("Public-file check failed: %s" % error, file=sys.stderr)
        sys.exit(1)
