# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jiar and contributors
import datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

import install
import magpie
import configure
from test_magpie import account, NOW


def settings(**changes):
    return {"managedBy": install.MANAGED_BY, "mode": "aggregate", "providers": {}, "showNewProviders": True, "maxAgeSeconds": 0, **changes}


class AggregateTests(unittest.TestCase):
    def test_provider_switch_hides_all_its_accounts(self):
        rows = [account(), account(user="second@example.com"), account(provider="cursor", name="Cursor")]
        result = magpie.aggregate_allowances(rows, settings(providers={"codex": False}), NOW)
        self.assertEqual(len(result["limits"]), 2)
        self.assertEqual(result["limits"][0]["id"], magpie.AVERAGE_LIMIT_ID)
        self.assertTrue(result["limits"][1]["label"].startswith("Cursor"))
        self.assertEqual(result["plan"], "1 个服务 · 1 个账号")

    def test_limits_are_scoped_to_accounts_and_stable_after_reordering(self):
        rows = [account(), account(user="second@example.com"), account(provider="opencode-go", name="OpenCode Go", user="")]
        first = magpie.aggregate_allowances(rows, settings(), NOW)["limits"]
        second = magpie.aggregate_allowances(rows[::-1], settings(), NOW)["limits"]
        self.assertEqual(first, second)
        self.assertEqual(len({limit["id"] for limit in first}), 4)
        self.assertTrue(all(len(limit["id"]) <= 64 and len(limit["label"]) <= 60 for limit in first))

    def test_new_providers_follow_default_without_reinstallation(self):
        rows = [account(), account(provider="new-service", name="New service")]
        hidden = magpie.aggregate_allowances(rows, settings(providers={"codex": True}, showNewProviders=False), NOW)
        shown = magpie.aggregate_allowances(rows, settings(providers={"codex": True}, showNewProviders=True), NOW)
        self.assertEqual(len(hidden["limits"]), 2)
        self.assertEqual(len(shown["limits"]), 3)

    def test_average_weights_providers_equally_after_accounts_and_windows(self):
        rows = [
            account(windows=[{"name": "5 hours", "used": 10}, {"name": "7 days", "used": 80}]),
            account(user="second@example.com", windows=[{"name": "7 days", "used": 20}]),
            account(provider="cursor", name="Cursor", windows=[{"name": "Month", "amount": 1, "limit": 4}]),
        ]
        result = magpie.aggregate_allowances(rows, settings(), NOW)
        average = result["limits"][0]
        # Codex: (max(10, 80) + 20) / 2 = 50; Cursor: 25; equal providers: 37.5.
        self.assertEqual(average["id"], magpie.AVERAGE_LIMIT_ID)
        self.assertEqual(average["usedPercent"], 37.5)
        self.assertEqual(average["label"], "平均用量（2 个服务等权）")
        self.assertEqual(len(result["limits"]), 5)

    def test_average_excludes_hidden_failed_and_money_only_accounts(self):
        rows = [
            account(windows=[{"name": "7 days", "used": 40}]),
            account(user="broken@example.com", error="connection refused"),
            account(provider="hidden", windows=[{"name": "Month", "used": 100}]),
            account(provider="openrouter", windows=[], balance="$-0.02"),
        ]
        result = magpie.aggregate_allowances(rows, settings(providers={"hidden": False}), NOW)
        self.assertEqual(result["limits"][0]["usedPercent"], 40)
        self.assertEqual(result["limits"][0]["label"], "平均用量（1 个服务等权）")
        self.assertEqual(result["balance"]["amount"], -0.02)
        self.assertEqual(len(result["limits"]), 2)

    def test_average_handles_zero_and_over_quota_without_clamping(self):
        for used in (0, 125):
            with self.subTest(used=used):
                result = magpie.aggregate_allowances([account(windows=[{"name": "Month", "used": used}])], settings(), NOW)
                self.assertEqual(result["limits"][0]["usedPercent"], used)

    def test_average_identity_survives_provider_switches(self):
        rows = [account(), account(provider="cursor", name="Cursor")]
        shown = magpie.aggregate_allowances(rows, settings(), NOW)["limits"][0]
        hidden = magpie.aggregate_allowances(rows[::-1], settings(providers={"codex": False}), NOW)["limits"][0]
        self.assertEqual(shown["id"], hidden["id"])

    def test_money_only_does_not_invent_average(self):
        result = magpie.aggregate_allowances([account(windows=[], balance="$3")], settings(), NOW)
        self.assertNotIn("limits", result)
        self.assertEqual(result["balance"]["amount"], 3)

    def test_empty_selection_does_not_invent_quota(self):
        self.assertEqual(magpie.aggregate_allowances([account()], settings(providers={"codex": False}), NOW), {"schemaVersion": 1, "status": "noLimits"})

    def test_one_failed_provider_does_not_remove_healthy_quota(self):
        broken = account(provider="workbuddy", error="certificate validation failed")
        result = magpie.aggregate_allowances([account(), broken], settings(), NOW)
        self.assertEqual(len(result["limits"]), 2)
        self.assertEqual(result["metrics"][0]["id"], "unavailable-accounts")
        with self.assertRaises(magpie.SourceError) as caught:
            magpie.aggregate_allowances([broken], settings(), NOW)
        self.assertEqual(caught.exception.status, "unreachable")

    def test_balances_keep_currency_and_do_not_sum_across_accounts(self):
        usd = account(provider="openrouter", user="", windows=[], balance="$-0.02")
        eur = account(provider="other", user="", windows=[], balance="EUR 8.5")
        single = magpie.aggregate_allowances([usd], settings(), NOW)
        self.assertEqual(single["balance"], {"amount": -0.02, "currency": "USD"})
        multi = magpie.aggregate_allowances([account(), usd, eur], settings(), NOW)
        self.assertNotIn("balance", multi)
        self.assertEqual({m["unit"] for m in multi["metrics"] if m["id"].endswith(".balance")}, {"USD", "EUR"})
        chosen = magpie.aggregate_allowances([usd, eur], settings(balanceAccount=magpie.extension_id(eur)), NOW)
        self.assertEqual(chosen["balance"], {"amount": 8.5, "currency": "EUR"})
        with self.assertRaises(magpie.SourceError) as caught:
            magpie.aggregate_allowances([usd, eur], settings(), NOW)
        self.assertEqual(caught.exception.status, "noLimits")

    def test_duplicate_accounts_are_rejected(self):
        with self.assertRaises(magpie.SourceError):
            magpie.aggregate_allowances([account(), account()], settings(), NOW)

    def test_metric_cap_and_credit_units(self):
        rows = [account(balance="15146.96 credits", resets={"count": 1}), account(provider="workbuddy", error="certificate error")]
        result = magpie.aggregate_allowances(rows, settings(), NOW)
        self.assertEqual(len(result["metrics"]), 4)
        self.assertNotIn("balance", result)
        self.assertTrue(any(metric["unit"] == "credits" for metric in result["metrics"]))


class DetailsTests(unittest.TestCase):
    def test_details_include_last_window_hidden_sources_and_uncapped_balances(self):
        rows = [account(windows=[{"name": "Window %d" % i, "used": i, "amount": i, "limit": 100, "resetsAt": "2026-12-01T00:00:00Z"} for i in range(12)])]
        rows.extend(account(provider="money-%d" % i, name="Money %d" % i, windows=[], balance="$%d" % i) for i in range(6))
        rows.append(account(provider="hidden", name="Hidden", balance="123 credits", resets={"count": 2}))
        rows.append(account(provider="broken", name="Broken", error="connection refused"))
        output = io.StringIO()
        with redirect_stdout(output):
            configure.print_details(settings(providers={"hidden": False}), rows, NOW)
        text = output.getvalue()
        self.assertIn("平均用量（1 个服务等权）：11.00%", text)
        self.assertIn("Window 11：11.00%", text)
        self.assertIn("实际使用量：11 / 100", text)
        self.assertIn("重置时间：2026-12-01T00:00:00+00:00", text)
        self.assertIn("[隐藏] Hidden", text)
        self.assertIn("余额：123 credits", text)
        self.assertIn("可用重置次数：2", text)
        self.assertIn("来源更新时间：" + NOW.isoformat(), text)
        self.assertIn("不可用：unreachable", text)
        for i in range(6):
            self.assertIn("余额：$%d" % i, text)

    def test_all_hidden_keeps_full_details_without_inventing_average(self):
        output = io.StringIO()
        with redirect_stdout(output):
            configure.print_details(settings(providers={"codex": False}), [account()], NOW)
        text = output.getvalue()
        self.assertIn("无参与计算的有效额度", text)
        self.assertIn("[隐藏] Codex", text)
        self.assertIn("7 days：99.00%", text)


class SettingsAndMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class SourceHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"data": cls.rows}).encode())

            def log_message(self, *args):
                pass
        cls.source = ThreadingHTTPServer(("127.0.0.1", 0), SourceHandler)
        cls.source_thread = threading.Thread(target=cls.source.serve_forever, daemon=True)
        cls.source_thread.start()
        cls.endpoint = "http://127.0.0.1:%d/v1/magpie/quotas" % cls.source.server_port

    @classmethod
    def tearDownClass(cls):
        cls.source.shutdown()
        cls.source.server_close()
        cls.source_thread.join()

    def setUp(self):
        type(self).rows = [account(readAt=dt.datetime.now(dt.timezone.utc).isoformat())]
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "config.json"
        magpie.save_config(self.config, settings(endpoint=self.endpoint))

    def tearDown(self):
        self.temp.cleanup()

    def test_switch_saved_and_sync_retains_it_when_provider_removed_and_returns(self):
        configure.change_preferences(self.config, providers={"codex": False})
        type(self).rows.append(account(provider="cursor", name="Cursor"))
        config, rows = configure.sync_providers(self.config)
        flags = {p["id"]: p["enabled"] for p in configure.provider_list(config, rows)}
        self.assertEqual(flags, {"codex": False, "cursor": True})
        type(self).rows = [row for row in type(self).rows if row["provider"] != "codex"]
        config, rows = configure.sync_providers(self.config)
        codex = next(p for p in configure.provider_list(config, rows) if p["id"] == "codex")
        self.assertFalse(codex["present"])
        self.assertEqual(codex["accounts"], [])
        type(self).rows.append(account())
        config, rows = configure.sync_providers(self.config)
        self.assertFalse(next(p for p in configure.provider_list(config, rows) if p["id"] == "codex")["enabled"])

    def test_settings_patch_does_not_clobber_other_provider_switches(self):
        configure.change_preferences(self.config, providers={"codex": False})
        configure.change_preferences(self.config, providers={"cursor": False}, show_new=False)
        saved = magpie.read_config(self.config)
        self.assertEqual(saved["providers"], {"codex": False, "cursor": False})
        self.assertFalse(saved["showNewProviders"])

    def test_invalid_switch_does_not_write_config(self):
        before = self.config.read_bytes()
        for patch in [{"providers": {"codex": "false"}}, {"show_new": "false"}]:
            with self.assertRaises(ValueError):
                configure.change_preferences(self.config, **patch)
            self.assertEqual(self.config.read_bytes(), before)

    def test_aggregate_install_execute_and_toggle_without_reinstalling(self):
        destination = self.root / "extensions"
        manifest = install.install_aggregate(type(self).rows, destination, self.endpoint)
        target = destination / manifest["id"]
        environment = {"HOME": str(Path.home()), "PATH": str(Path(sys.executable).parent) + ":/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", "PULSE_EXTENSION_ID": manifest["id"], "PULSE_EXTENSION_SCHEMA": "1"}
        def run():
            result = subprocess.run([str(target / "run")], cwd=target, env=environment, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertEqual(len(run()["limits"]), 2)
        type(self).rows.append(account(provider="cursor", name="Cursor"))
        self.assertEqual(len(run()["limits"]), 3)
        config_path = target / "config.json"
        config = magpie.read_config(config_path)
        config["providers"]["codex"] = False
        magpie.save_config(config_path, config)
        self.assertEqual(len(run()["limits"]), 2)
        install.install_aggregate(type(self).rows, destination, self.endpoint)
        self.assertFalse(magpie.read_config(config_path)["providers"]["codex"])
        self.assertTrue((target / "manage.command").stat().st_mode & 0o100)
        self.assertTrue((target / "configure.py").is_file())
        self.assertFalse((target / "manager.py").exists())

    def test_installed_details_command_reads_all_windows_without_writing_settings(self):
        type(self).rows = [account(windows=[{"name": "Window %d" % i, "used": i} for i in range(12)])]
        destination = self.root / "extensions"
        manifest = install.install_aggregate(type(self).rows, destination, self.endpoint)
        target = destination / manifest["id"]
        config_path = target / "config.json"
        before = config_path.read_bytes()
        result = subprocess.run([sys.executable, "-I", "-B", str(target / "configure.py"), "--config", str(config_path), "--details"], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("平均用量（1 个服务等权）：11.00%", result.stdout)
        self.assertIn("Window 11：11.00%", result.stdout)
        self.assertEqual(config_path.read_bytes(), before)

    def test_legacy_migration_moves_only_owned_directories_and_is_reversible(self):
        destination = self.root / "extensions"
        legacy = install.install_account(account(), destination, self.endpoint, 0)
        unrelated = destination / "unrelated"
        unrelated.mkdir()
        (unrelated / "config.json").write_text('{"managedBy":"someone-else"}')
        (unrelated / "pulse-extension.json").write_text('{"id":"unrelated"}')
        install.install_aggregate(type(self).rows, destination, self.endpoint)
        backup = self.root / "backup"
        moved = install.archive_legacy(destination, backup)
        self.assertEqual(len(moved), 1)
        self.assertTrue((backup / legacy["id"] / "run").exists())
        self.assertFalse((destination / legacy["id"]).exists())
        self.assertTrue((destination / install.AGGREGATE_ID).is_dir())
        self.assertTrue(unrelated.is_dir())


if __name__ == "__main__":
    unittest.main()
