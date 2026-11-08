# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jiar
"""Regression checks for malformed data and installation boundaries; no live services."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import install
import magpie
from test_aggregate import settings
from test_magpie import account, NOW


class NumericBoundaryTests(unittest.TestCase):
    def test_unrepresentable_integer_does_not_discard_healthy_accounts(self):
        self.assertFalse(magpie.number(10**400))
        rows = [account(windows=[{"name": "Week", "used": 42}]),
                account(provider="broken", windows=[{"name": "Week", "used": 10**400}])]
        result = magpie.aggregate_allowances(rows, settings(), NOW)
        self.assertEqual(result["limits"][0]["usedPercent"], 42)
        self.assertEqual(len(result["limits"]), 2)
        magpie.encode_report(result)

    def test_raw_ratio_overflow_keeps_other_windows_and_reported_percent(self):
        windows = [{"name": "Overflow", "amount": 1e308, "limit": 1e-308},
                   {"name": "Reported", "used": 25, "amount": 1e308, "limit": 1e-308}]
        result = magpie.convert_allowance(account(windows=windows), now=NOW)
        self.assertEqual(len(result["limits"]), 1)
        self.assertEqual(result["limits"][0]["usedPercent"], 25)
        self.assertNotIn("used", result["limits"][0])
        magpie.encode_report(result)

    def test_provider_and_account_averages_do_not_overflow(self):
        rows = [account(windows=[{"name": "Week", "used": 1e308}]),
                account(user="demo-secondary", windows=[{"name": "Week", "used": 1e308}]),
                account(provider="other", windows=[{"name": "Week", "used": 1e308}])]
        result = magpie.aggregate_allowances(rows, settings(), NOW)
        self.assertEqual(result["limits"][0]["usedPercent"], 1e308)
        magpie.encode_report(result)

    def test_invalid_duration_does_not_remove_quota(self):
        for label in ["9" * 309 + " hours", "9" * 20 + " days", "0.0005 hours"]:
            with self.subTest(label=label):
                window = {"name": label, "used": 42, "resetsAt": "2026-12-01T00:00:00Z"}
                result = magpie.convert_allowance(account(windows=[window]), now=NOW)
                self.assertEqual(result["limits"][0]["usedPercent"], 42)
                self.assertNotIn("windowSeconds", result["limits"][0])
                magpie.encode_report(result)
        self.assertEqual(magpie.window_seconds("0.5 hours"), 1800)
        self.assertIsInstance(magpie.window_seconds("7 days"), int)


class ProtocolBoundaryTests(unittest.TestCase):
    def test_output_limit_counts_utf8_bytes_and_newline(self):
        output = {"label": "演示额度"}
        encoded = json.dumps(output, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        size = len(encoded.encode("utf-8")) + 1
        with patch.object(magpie, "MAX_OUTPUT_BYTES", size):
            self.assertEqual(magpie.encode_report(output), encoded)
        with patch.object(magpie, "MAX_OUTPUT_BYTES", size - 1):
            with self.assertRaises(magpie.SourceError):
                magpie.encode_report(output)

    def test_oversized_report_emits_one_failure_object(self):
        rows = [account(windows=[{"name": "Window %d" % i, "used": 42} for i in range(20)])]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            magpie.save_config(config, settings())
            out, err = io.StringIO(), io.StringIO()
            with patch("sys.argv", ["magpie.py", "--config", str(config)]), \
                    patch.object(magpie, "fetch_allowances", return_value=rows), \
                    patch.object(magpie, "MAX_OUTPUT_BYTES", 300), \
                    redirect_stdout(out), redirect_stderr(err):
                magpie.main()
            self.assertEqual(len(out.getvalue().splitlines()), 1)
            self.assertEqual(json.loads(out.getvalue()), {"schemaVersion": 1, "status": "serverError"})
            self.assertIn("output limit", err.getvalue())

    def test_nonfinite_serialization_is_a_classified_failure(self):
        with self.assertRaises(magpie.SourceError) as caught:
            magpie.encode_report({"value": float("inf")})
        self.assertEqual(caught.exception.status, "serverError")


class InstallationBoundaryTests(unittest.TestCase):
    def test_invalid_existing_configuration_never_replaces_programs(self):
        for invalid in [{"showNewProviders": "false"}, {"providers": {"codex": "true"}},
                        {"maxAgeSeconds": "60"}]:
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory)
                install.install_aggregate([account()], destination, magpie.DEFAULT_ENDPOINT)
                target = destination / install.AGGREGATE_ID
                (target / "run").write_text("original program\n")
                config_path = target / "config.json"
                config = json.loads(config_path.read_text())
                config.update(invalid)
                config_path.write_text(json.dumps(config))
                before = {p.name: p.read_bytes() for p in target.iterdir()}
                with self.assertRaises(magpie.SourceError):
                    install.install_aggregate([account()], destination, magpie.DEFAULT_ENDPOINT)
                self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()}, before)

    def test_remote_endpoint_is_rejected_before_creating_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            with self.assertRaises(magpie.SourceError):
                install.install_aggregate([account()], destination, "https://example.invalid/v1/magpie/quotas")
            self.assertEqual(list(destination.iterdir()), [])

    def test_manifest_uses_magpie_display_name(self):
        manifest = install.install_aggregate([], Path("unused"), magpie.DEFAULT_ENDPOINT, dry_run=True)
        self.assertEqual(manifest["name"], "Magpie")
        self.assertEqual(manifest["id"], "magpie-allowances")
        self.assertEqual(manifest["icon"], install.ICON_FILE)

    def test_fresh_install_includes_declared_icon_without_local_app_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "Extensions"
            manifest = install.install_aggregate([account()], destination, magpie.DEFAULT_ENDPOINT)
            self.assertEqual([path.name for path in destination.iterdir()], [install.AGGREGATE_ID])
            target = destination / install.AGGREGATE_ID
            installed = json.loads((target / "pulse-extension.json").read_text())
            self.assertEqual(installed, manifest)
            icon = target / installed["icon"]
            source = Path(install.__file__).resolve().with_name(install.ICON_FILE)
            self.assertEqual(icon.read_bytes(), source.read_bytes())
            self.assertTrue(icon.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(icon.stat().st_mode & 0o777, 0o600)

    def test_reinstall_updates_icon_and_keeps_existing_provider_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            row = account()
            install.install_aggregate([row], destination, magpie.DEFAULT_ENDPOINT)
            target = destination / install.AGGREGATE_ID
            config_path = target / "config.json"
            config = json.loads(config_path.read_text())
            config["providers"][row["provider"]] = False
            config["showNewProviders"] = False
            config_path.write_text(json.dumps(config))
            manifest_path = target / "pulse-extension.json"
            previous = json.loads(manifest_path.read_text())
            previous.pop("icon")
            manifest_path.write_text(json.dumps(previous))
            (target / install.ICON_FILE).write_bytes(b"outdated icon")

            install.install_aggregate([row], destination, magpie.DEFAULT_ENDPOINT)
            updated = json.loads(manifest_path.read_text())
            self.assertEqual(updated["id"], previous["id"])
            self.assertEqual(updated["icon"], install.ICON_FILE)
            self.assertEqual(json.loads(config_path.read_text()), config)
            source = Path(install.__file__).resolve().with_name(install.ICON_FILE)
            self.assertEqual((target / updated["icon"]).read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
