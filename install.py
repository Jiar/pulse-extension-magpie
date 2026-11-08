#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jiar and contributors
"""Install one Magpie Pulse extension with dynamic provider selection."""

import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import sys
import tempfile

import magpie

MANAGED_BY = "pulse-extension-magpie"
AGGREGATE_ID = "magpie-allowances"
DEFAULT_DESTINATION = Path.home() / "Library/Application Support/Pulse/Extensions"
ICON_FILE = "magpie-icon.png"
FILES = ("magpie.py", "run", "configure.py", "manage.command", ICON_FILE)


def existing_config(target):
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError("Refusing to replace a non-directory or symlink: %s" % target)
    if not target.exists():
        return {}
    config = json.loads((target / "config.json").read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("managedBy") != MANAGED_BY:
        raise ValueError("Refusing to overwrite another project's extension: %s" % target)
    return config


def publish(target, manifest, config, files):
    source = Path(__file__).resolve().parent
    target.mkdir(parents=True, mode=0o700, exist_ok=True)
    for name in (*files, "config.json", "pulse-extension.json"):
        output = target / name
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".install-", delete=False) as temp:
            temporary = Path(temp.name)
        try:
            if name in files:
                shutil.copyfile(source / name, temporary)
            else:
                data = config if name == "config.json" else manifest
                temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.chmod(0o700 if name in ("run", "manage.command") else 0o600)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)


def install_account(row, destination, endpoint, max_age, dry_run=False):
    """Compatibility helper for existing per-account installations and tests."""
    target = destination / magpie.extension_id(row)
    config = {**existing_config(target), "managedBy": MANAGED_BY, "provider": row["provider"], "user": row.get("user", ""), "endpoint": endpoint}
    if max_age is not None:
        config["maxAgeSeconds"] = max_age
    else:
        config.setdefault("maxAgeSeconds", magpie.DEFAULT_MAX_AGE)
    magpie.validate_config(config)
    magpie.validate_endpoint(endpoint)
    manifest = {"schemaVersion": 1, "id": magpie.extension_id(row), "name": magpie.display_name(row), "executable": "run", "timeoutSeconds": 15, "icon": ICON_FILE}
    if not dry_run:
        publish(target, manifest, config, ("magpie.py", "run", ICON_FILE))
    return manifest


def install_aggregate(rows, destination, endpoint, max_age=None, dry_run=False):
    target = destination / AGGREGATE_ID
    config = {**existing_config(target), "managedBy": MANAGED_BY, "mode": "aggregate", "endpoint": endpoint}
    config.setdefault("showNewProviders", True)
    config.setdefault("providers", {})
    if not isinstance(config["providers"], dict):
        raise ValueError("Existing provider preferences are invalid")
    for row in rows:
        config["providers"].setdefault(row["provider"], config["showNewProviders"])
    if max_age is not None:
        config["maxAgeSeconds"] = max_age
    else:
        config.setdefault("maxAgeSeconds", magpie.DEFAULT_MAX_AGE)
    magpie.validate_config(config)
    magpie.validate_endpoint(endpoint)
    manifest = {"schemaVersion": 1, "id": AGGREGATE_ID, "name": "Magpie", "executable": "run", "timeoutSeconds": 15, "icon": ICON_FILE}
    if not dry_run:
        publish(target, manifest, config, FILES)
    return manifest


def archive_legacy(destination, backup_root, dry_run=False):
    """Move only verified, project-owned legacy extensions outside discovery."""
    candidates = []
    if not destination.exists():
        return candidates
    for target in sorted(destination.iterdir()):
        if target.is_symlink() or not target.is_dir() or target.name == AGGREGATE_ID:
            continue
        config_path = target / "config.json"
        manifest_path = target / "pulse-extension.json"
        if not config_path.is_file() or not manifest_path.is_file():
            continue
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            owned = config.get("managedBy") == MANAGED_BY and config.get("mode") != "aggregate" and isinstance(config.get("provider"), str)
            if not owned or manifest.get("id") != magpie.extension_id(config) or target.name != manifest["id"]:
                continue
        except (ValueError, KeyError, AttributeError):
            continue
        candidates.append(target)
    if candidates and not dry_run:
        backup_root.mkdir(parents=True, mode=0o700, exist_ok=False)
        for target in candidates:
            shutil.move(str(target), str(backup_root / target.name))
    return candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", help="Local Magpie endpoint; preserves the installed endpoint by default")
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--max-age-seconds", type=int, help="Optional data age cutoff; zero follows Magpie")
    parser.add_argument("--keep-legacy", action="store_true", help="Keep the old per-account extension directories")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    args = parser.parse_args()
    if args.max_age_seconds is not None and args.max_age_seconds < 0:
        parser.error("--max-age-seconds must be nonnegative")
    try:
        previous = existing_config(args.destination / AGGREGATE_ID)
        endpoint = args.endpoint or previous.get("endpoint", magpie.DEFAULT_ENDPOINT)
        rows = magpie.fetch_allowances(endpoint)
        manifest = install_aggregate(rows, args.destination, endpoint, args.max_age_seconds, dry_run=args.dry_run)
        print("%s one extension: %s" % ("Would install" if args.dry_run else "Installed", manifest["name"]))
        print("Magpie: %d providers, %d accounts" % (len({row["provider"] for row in rows}), len(rows)))
        if not args.keep_legacy:
            backup = Path(__file__).resolve().parent / ".local" / ("legacy-extensions-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
            archived = archive_legacy(args.destination, backup, dry_run=args.dry_run)
            if archived:
                print("%s %d legacy extensions to %s" % ("Would move" if args.dry_run else "Moved", len(archived), backup))
        print("Settings: %s" % (args.destination / AGGREGATE_ID / "manage.command"))
        print("Icon: %s (requires Pulse with manifest icon support; older builds use the generic icon)" % ICON_FILE)
        if not args.dry_run:
            print("Pulse → Manage extensions → Look again → Magpie → Show in panel")
    except (magpie.SourceError, OSError, ValueError, KeyError) as error:
        print("Installation failed: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
