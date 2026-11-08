# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jiar and contributors
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import install
import magpie

NOW = dt.datetime(2026, 11, 7, 6, 0, tzinfo=dt.timezone.utc)


def account(**changes):
    row = {"provider": "codex", "name": "Codex", "user": "test@example.com", "plan": "pro", "readAt": NOW.isoformat(), "windows": [{"name": "7 days", "used": 99, "remaining": 1, "resetsAt": "2026-11-10T12:17:02+08:00"}]}
    row.update(changes)
    return row


class ConversionTests(unittest.TestCase):
    def test_magpie_used_is_percentage_not_amount(self):
        result = magpie.convert_allowance(account(), now=NOW)
        window = result["limits"][0]
        self.assertEqual(window["usedPercent"], 99)
        self.assertNotIn("used", window)
        self.assertEqual(window["windowSeconds"], 604800)
        self.assertEqual(window["resetsAt"], "2026-11-10T12:17:02+08:00")

    def test_raw_credit_usage_and_reset_metadata(self):
        row = account(windows=[{"name": "Add-on credits", "used": 189 / 1900 * 100, "amount": 189, "limit": 1900}], balance="15,146.96 credits", resets={"count": 1})
        result = magpie.convert_allowance(row, now=NOW)
        self.assertEqual(result["limits"][0]["used"], 189)
        self.assertEqual(result["limits"][0]["limit"], 1900)
        self.assertNotIn("balance", result)
        self.assertEqual(result["metrics"][0]["value"], 15146.96)
        self.assertEqual(result["metrics"][1]["value"], 1)

    def test_negative_money_balance_is_preserved(self):
        result = magpie.convert_allowance(account(windows=[], balance="$-0.02"), now=NOW)
        self.assertEqual(result["balance"], {"amount": -0.02, "currency": "USD"})
        self.assertNotIn("limits", result)

    def test_currency_formats_and_non_money(self):
        for text, amount, currency in [("16.33 USD", 16.33, "USD"), ("CNY 12", 12, "CNY"), ("¥12.50", 12.5, "CNY"), ("€1.20", 1.2, "EUR")]:
            with self.subTest(text=text):
                self.assertEqual(magpie.balance_value(text)[0], {"amount": amount, "currency": currency})
        for text in ["100 points", "123", None, "∞ credits"]:
            self.assertEqual(magpie.balance_value(text), (None, None))

    def test_invalid_values_do_not_become_zero(self):
        windows = [{"name": "Bad", "used": value} for value in [-1, True, "42", float("nan"), float("inf"), None]]
        result = magpie.convert_allowance(account(windows=windows), now=NOW)
        self.assertEqual(result, {"schemaVersion": 1, "status": "noLimits"})

    def test_exhaustion_and_unknown_month_duration(self):
        row = account(windows=[{"name": "Month", "used": 125, "resetsAt": "2026-12-01T00:00:00Z"}])
        limit = magpie.convert_allowance(row, now=NOW)["limits"][0]
        self.assertEqual(limit["usedPercent"], 125)
        self.assertNotIn("windowSeconds", limit)

    def test_window_ids_survive_reordering(self):
        windows = [{"name": "5 hours", "used": 0}, {"name": "7 days", "used": 57}]
        first = magpie.convert_allowance(account(windows=windows), now=NOW)["limits"]
        second = magpie.convert_allowance(account(windows=windows[::-1]), now=NOW)["limits"]
        self.assertEqual(first[0]["id"], second[1]["id"])
        self.assertEqual(first[1]["id"], second[0]["id"])

    def test_account_selection_does_not_mix_codex_accounts(self):
        first, second = account(), account(user="another@example.com")
        self.assertNotEqual(magpie.extension_id(first), magpie.extension_id(second))
        self.assertIs(magpie.select_account([first, second], "codex", "another@example.com"), second)
        for rows, status in [([first], "signedOut"), ([second, second], "serverError")]:
            with self.assertRaises(magpie.SourceError) as caught:
                magpie.select_account(rows, "codex", "another@example.com")
            self.assertEqual(caught.exception.status, status)

    def test_stale_reading_is_reported_unreachable(self):
        for read_at in ["2026-11-07T04:00:00Z", None, "not-a-date"]:
            with self.subTest(read_at=read_at), self.assertRaises(magpie.SourceError) as caught:
                magpie.convert_allowance(account(readAt=read_at), max_age=1800, now=NOW)
            self.assertEqual(caught.exception.status, "unreachable")
        result = magpie.convert_allowance(account(readAt=None), max_age=0, now=NOW)
        self.assertIn("limits", result)

    def test_default_follows_magpie_and_exposes_source_age(self):
        result = magpie.convert_allowance(account(readAt="2026-11-07T04:00:00Z"), now=NOW)
        self.assertIn("limits", result)
        metric = next(m for m in result["metrics"] if m["id"] == "source-age")
        self.assertEqual(metric["value"], 120)
        self.assertEqual(metric["unit"], "min")

    def test_account_error_does_not_display_old_data(self):
        with self.assertRaises(magpie.SourceError) as caught:
            magpie.convert_allowance(account(error="unable to verify the first certificate"), now=NOW)
        self.assertEqual(caught.exception.status, "unreachable")

    def test_credits_alone_are_not_a_monetary_reading(self):
        result = magpie.convert_allowance(account(windows=[], balance="123 credits"), now=NOW)
        self.assertEqual(result["status"], "noLimits")


class TransportAndInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(cls.status)
                if cls.status == 302:
                    self.send_header("Location", "https://example.com/")
                self.end_headers()
                self.wfile.write(json.dumps(cls.payload).encode())

            def log_message(self, *args):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.endpoint = "http://127.0.0.1:%d/v1/magpie/quotas" % cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        type(self).status = 200
        type(self).payload = {"data": [account(readAt=dt.datetime.now(dt.timezone.utc).isoformat())]}

    def test_local_api_fetch_bypasses_proxy(self):
        with patch.dict("os.environ", {"http_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1", "no_proxy": "", "NO_PROXY": ""}):
            self.assertEqual(magpie.fetch_allowances(self.endpoint)[0]["provider"], "codex")

    def test_http_errors_and_redirects(self):
        for code, status in [(401, "signedOut"), (429, "rateLimited"), (500, "serverError"), (302, "serverError")]:
            type(self).status = code
            with self.subTest(code=code), self.assertRaises(magpie.SourceError) as caught:
                magpie.fetch_allowances(self.endpoint)
            self.assertEqual(caught.exception.status, status)

    def test_malformed_response_is_failure(self):
        for payload in [{}, {"data": {}}, {"data": [None]}, {"data": [{"provider": 1}]}]:
            type(self).payload = payload
            with self.subTest(payload=payload), self.assertRaises(magpie.SourceError):
                magpie.fetch_allowances(self.endpoint)

    def test_endpoint_must_stay_local(self):
        for endpoint in ["https://example.com/v1/magpie/quotas", "http://localhost:3425/v1/magpie/quotas", "http://127.0.0.1:3425/other", "http://user@127.0.0.1:3425/v1/magpie/quotas"]:
            with self.subTest(endpoint=endpoint), self.assertRaises(magpie.SourceError):
                magpie.validate_endpoint(endpoint)

    def test_install_and_run_in_pulse_clean_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            row = type(self).payload["data"][0]
            manifest = install.install_account(row, destination, self.endpoint, None)
            target = destination / manifest["id"]
            self.assertTrue((target / "run").stat().st_mode & 0o100)
            environment = {"HOME": str(Path.home()), "PATH": str(Path(sys.executable).parent) + ":/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", "PULSE_EXTENSION_ID": manifest["id"], "PULSE_EXTENSION_SCHEMA": "1"}
            result = subprocess.run([str(target / "run")], cwd=target, env=environment, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(result.stdout.splitlines()), 1)
            self.assertEqual(json.loads(result.stdout)["limits"][0]["usedPercent"], 99)
            config_path = target / "config.json"
            config = json.loads(config_path.read_text())
            config["maxAgeSeconds"] = 60
            config_path.write_text(json.dumps(config))
            install.install_account(row, destination, self.endpoint, None)
            self.assertEqual(json.loads(config_path.read_text())["maxAgeSeconds"], 60)
            config["managedBy"] = "someone-else"
            config_path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                install.install_account(row, destination, self.endpoint, None)

    def test_unreachable_source_emits_one_status_and_exit_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            row = type(self).payload["data"][0]
            manifest = install.install_account(row, Path(directory), "http://127.0.0.1:1/v1/magpie/quotas", None)
            target = Path(directory) / manifest["id"]
            result = subprocess.run([str(target / "run")], cwd=target, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {"schemaVersion": 1, "status": "unreachable"})
            self.assertEqual(len(result.stdout.splitlines()), 1)
            self.assertIn("Cannot reach local Magpie", result.stderr)


if __name__ == "__main__":
    unittest.main()
