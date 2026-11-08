#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jiar and contributors
"""Configure provider visibility for the Magpie Pulse extension, without a server."""

import argparse
import datetime as dt
import importlib.util
from pathlib import Path
import sys

SPEC = importlib.util.spec_from_file_location("magpie_bridge", Path(__file__).resolve().with_name("magpie.py"))
magpie = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(magpie)

DEFAULT_CONFIG = Path.home() / "Library/Application Support/Pulse/Extensions/magpie-allowances/config.json"


def change_preferences(path, providers=None, show_new=None, balance_account=None, set_balance=False):
    config = magpie.read_config(path)
    if config.get("mode") != "aggregate":
        raise ValueError("This command requires the unified Magpie extension")
    providers = {} if providers is None else providers
    if not isinstance(providers, dict) or any(not isinstance(key, str) or not key or not isinstance(value, bool) for key, value in providers.items()):
        raise ValueError("Provider switches must be true or false")
    if show_new is not None and not isinstance(show_new, bool):
        raise ValueError("New-provider visibility must be true or false")
    if set_balance and balance_account is not None and (not isinstance(balance_account, str) or len(balance_account) > 64):
        raise ValueError("Invalid balance account ID")
    config.setdefault("providers", {}).update(providers)
    if show_new is not None:
        config["showNewProviders"] = show_new
    if set_balance:
        config["balanceAccount"] = balance_account
    magpie.save_config(path, config)
    return config


def sync_providers(path):
    config = magpie.read_config(path)
    rows = magpie.fetch_allowances(config.get("endpoint", magpie.DEFAULT_ENDPOINT))
    preferences = {provider: magpie.provider_enabled(config, provider) for provider in {row["provider"] for row in rows}}
    config = change_preferences(path, providers=preferences)
    return config, rows


def provider_list(config, rows):
    groups = {}
    for row in rows:
        provider = row["provider"]
        group = groups.setdefault(provider, {"id": provider, "name": str(row.get("name") or provider), "accounts": [], "present": True})
        group["accounts"].append(row)
    for provider in config.get("providers", {}):
        groups.setdefault(provider, {"id": provider, "name": provider, "accounts": [], "present": False})
    for group in groups.values():
        group["enabled"] = magpie.provider_enabled(config, group["id"])
    return sorted(groups.values(), key=lambda group: (not group["present"], group["name"].casefold()))


def print_providers(config, rows):
    groups = provider_list(config, rows)
    print("\nMagpie Allowances 来源\n")
    for index, group in enumerate(groups, 1):
        status = "显示" if group["enabled"] else "隐藏"
        suffix = "%d 个账号" % len(group["accounts"]) if group["present"] else "已移除，保留显示偏好"
        print("%d. [%s] %s (%s) — %s" % (index, status, group["name"], group["id"], suffix))
        for row in group["accounts"]:
            if row.get("user"):
                print("      " + row["user"])
            if row.get("error"):
                print("      Magpie 查询失败：" + str(row["error"]))
    print("\n新增服务默认：%s" % ("显示" if config.get("showNewProviders", True) else "隐藏"))
    return groups


def print_details(config, rows, now=None):
    """Show every source row without Pulse's card height or four-metric limit."""
    now = now or dt.datetime.now(dt.timezone.utc)
    print("\nMagpie Allowances 完整额度\n")
    try:
        reading = magpie.aggregate_allowances(rows, config, now)
        average = next((limit for limit in reading.get("limits", []) if limit["id"] == magpie.AVERAGE_LIMIT_ID), None)
        if average:
            print("%s：%.2f%%" % (average["label"], average["usedPercent"]))
        else:
            print("平均用量：无参与计算的有效额度")
    except magpie.SourceError as error:
        print("汇总状态：%s — %s" % (error.status, error))
    print("计算规则：账号取最高额度用量 → 服务内账号平均 → 服务等权平均。")
    print("隐藏、不可用及只有余额的来源不参与平均；下方仍列出全部来源。")
    for group in provider_list(config, rows):
        print("\n[%s] %s (%s)" % ("显示" if group["enabled"] else "隐藏", group["name"], group["id"]))
        if not group["present"]:
            print("  已从 Magpie 移除，仅保留显示偏好。")
        for row in sorted(group["accounts"], key=magpie.identity):
            print("  账号：%s" % (row.get("user") or "默认账号"))
            if row.get("plan"):
                print("    套餐：%s" % row["plan"])
            print("    来源更新时间：%s" % (row.get("readAt") or "未知"))
            try:
                reading = magpie.convert_allowance(row, config.get("maxAgeSeconds", magpie.DEFAULT_MAX_AGE), now)
            except magpie.SourceError as error:
                print("    不可用：%s — %s；不参与当前读数。" % (error.status, error))
                continue
            for limit in reading.get("limits", []):
                percent = magpie.limit_percentage(limit)
                print("    %s：%.2f%%" % (limit["label"], percent))
                if "used" in limit:
                    print("      实际使用量：%.12g / %.12g" % (limit["used"], limit["limit"]))
                if "resetsAt" in limit:
                    print("      重置时间：%s" % limit["resetsAt"])
            if row.get("balance") is not None:
                print("    余额：%s" % row["balance"])
            resets = row.get("resets")
            if isinstance(resets, dict) and magpie.number(resets.get("count")) and resets["count"] >= 0:
                print("    可用重置次数：%.12g" % resets["count"])
            if reading.get("status"):
                print("    无有效额度或可用货币余额，不参与当前读数。")


def interactive(path):
    if not sys.stdin.isatty():
        raise ValueError("Interactive settings require a terminal; use --show / --hide instead")
    config, rows = sync_providers(path)
    while True:
        groups = print_providers(config, rows)
        command = input("\n输入编号切换显示；v 查看完整额度；r 同步 Magpie；n 切换新增默认；q 退出：").strip().lower()
        if command == "q":
            return
        if command == "v":
            config = magpie.read_config(path)
            rows = magpie.fetch_allowances(config.get("endpoint", magpie.DEFAULT_ENDPOINT))
            print_details(config, rows)
            continue
        if command == "r":
            config, rows = sync_providers(path)
        elif command == "n":
            config = change_preferences(path, show_new=not config.get("showNewProviders", True))
        elif command.isdigit() and 1 <= int(command) <= len(groups):
            group = groups[int(command) - 1]
            config = change_preferences(path, providers={group["id"]: not group["enabled"]})
        else:
            print("请输入列表编号、v、r、n 或 q。")
            continue
        print("已保存。点击 Pulse 的 Magpie 圆环或等待自动刷新后生效。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--show", nargs="+", default=[], metavar="PROVIDER", help="Show providers, e.g. codex cursor")
    parser.add_argument("--hide", nargs="+", default=[], metavar="PROVIDER", help="Hide providers, e.g. qoder workbuddy")
    parser.add_argument("--new-providers", choices=("show", "hide"), help="Default visibility for newly discovered providers")
    parser.add_argument("--balance-account", help="Main monetary balance account ID, or auto")
    parser.add_argument("--sync", action="store_true", help="Sync the current provider list while retaining switches")
    parser.add_argument("--list", action="store_true", help="List current providers and switches")
    parser.add_argument("--details", action="store_true", help="Show all quota windows, balances, reset times and source status")
    parser.add_argument("--interactive", action="store_true", help="Open interactive terminal settings")
    args = parser.parse_args()
    if set(args.show) & set(args.hide):
        parser.error("A provider cannot be both shown and hidden")
    try:
        if args.interactive:
            interactive(args.config)
            return 0
        providers = {**{provider: True for provider in args.show}, **{provider: False for provider in args.hide}}
        mutated = bool(providers or args.new_providers or args.balance_account)
        if mutated:
            config = change_preferences(args.config, providers=providers, show_new=None if args.new_providers is None else args.new_providers == "show", balance_account=None if args.balance_account == "auto" else args.balance_account, set_balance=args.balance_account is not None)
            print("已保存。下次 Pulse 刷新时生效。")
        if args.sync:
            config, rows = sync_providers(args.config)
            print("已同步 Magpie，已有显示开关保持不变。")
        elif args.list or args.details or not mutated:
            config = magpie.read_config(args.config)
            rows = magpie.fetch_allowances(config.get("endpoint", magpie.DEFAULT_ENDPOINT))
        else:
            return 0
        if args.details:
            print_details(config, rows)
        else:
            print_providers(config, rows)
    except (magpie.SourceError, OSError, ValueError, EOFError, KeyboardInterrupt) as error:
        print("配置未完成：%s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
