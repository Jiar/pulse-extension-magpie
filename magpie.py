#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jiar and contributors
"""Translate Magpie Allowances into one Pulse extension with provider switches."""

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ENDPOINT = "http://127.0.0.1:3425/v1/magpie/quotas"
DEFAULT_MAX_AGE = 0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 256 * 1024
AVERAGE_LIMIT_ID = "magpie-average"


class SourceError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def limit_percentage(limit):
    """Read a finite percentage from an already converted Pulse limit."""
    if "usedPercent" in limit:
        percent = limit["usedPercent"]
    else:
        percent = limit["used"] / limit["limit"] * 100
    return percent if number(percent) and percent >= 0 else None


def mean_percentage(values):
    """Average finite nonnegative values without overflowing their sum."""
    scale = max(values)
    return scale * (math.fsum(value / scale for value in values) / len(values)) if scale else 0


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def validate_endpoint(endpoint):
    """Never send a request to a remote host or through the system proxy."""
    if not isinstance(endpoint, str):
        raise SourceError("serverError", "endpoint must be a local HTTP URL")
    try:
        url = urllib.parse.urlsplit(endpoint)
        host = ipaddress.ip_address(url.hostname or "")
        valid = (
            url.scheme == "http"
            and host.is_loopback
            and url.port is not None
            and not url.username
            and not url.password
            and url.path == "/v1/magpie/quotas"
            and not url.query
            and not url.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise SourceError(
            "serverError",
            "endpoint must be http://127.0.0.1:PORT/v1/magpie/quotas "
            "(a literal IPv6 loopback address is also supported)",
        )
    return endpoint


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_allowances(endpoint=DEFAULT_ENDPOINT):
    endpoint = validate_endpoint(endpoint)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
    try:
        with opener.open(request, timeout=8) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise SourceError("serverError", "Magpie response exceeds 2 MiB")
        payload = json.loads(raw)
    except urllib.error.HTTPError as error:
        status = {401: "signedOut", 403: "signedOut", 429: "rateLimited"}.get(
            error.code, "serverError"
        )
        error.close()
        raise SourceError(status, "Magpie HTTP error: %s" % error.code) from error
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        raise SourceError("unreachable", "Cannot reach local Magpie: %s" % error) from error
    except (ValueError, UnicodeError) as error:
        raise SourceError("serverError", "Magpie returned invalid JSON") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise SourceError("serverError", "Magpie response must contain a data array")
    rows = payload["data"]
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("provider"), str)
        or not row["provider"]
        or not isinstance(row.get("user", ""), str)
        for row in rows
    ):
        raise SourceError("serverError", "Magpie returned an invalid account")
    return rows


def identity(row):
    return row["provider"], row.get("user", "")


def extension_id(row):
    provider, user = identity(row)
    slug = re.sub(r"[^a-z0-9._-]+", "-", provider.lower()).strip(".-_")[:36] or "account"
    digest = hashlib.sha256((provider + "\0" + user).encode()).hexdigest()[:12]
    return "magpie-%s-%s" % (slug, digest)


def display_name(row):
    name = row.get("name") or row["provider"]
    user = row.get("user", "")
    return ("Magpie · %s%s" % (name, " · " + user if user else ""))[:60]


def select_account(rows, provider, user):
    matches = [row for row in rows if identity(row) == (provider, user)]
    if not matches:
        raise SourceError("signedOut", "Account is no longer listed in Magpie Allowances")
    if len(matches) != 1:
        raise SourceError("serverError", "Account selector is ambiguous; refusing to mix accounts")
    return matches[0]


def window_seconds(name):
    # Calendar months cannot be represented by one fixed duration.
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|days?|d|weeks?|w)\s*", name, re.I)
    if not match:
        return None
    unit = match[2].lower()[0]
    seconds = float(match[1]) * {"h": 3600, "d": 86400, "w": 604800}[unit]
    # Pulse decodes windowSeconds as a signed 64-bit integer. Do not round a
    # fractional duration or let invalid metadata discard an otherwise valid quota.
    if number(seconds) and 0 < seconds < 2**63 and seconds.is_integer():
        return int(seconds)
    return None


def balance_value(value):
    """Magpie balance strings carry units; credits are never treated as money."""
    if not isinstance(value, str):
        return None, None
    value = value.strip()
    numeric = r"([-+]?(?:\d[\d,]*(?:\.\d+)?|\.\d+))"
    credits = re.fullmatch(numeric + r"\s+credits?", value, re.I)
    if credits:
        amount = float(credits[1].replace(",", ""))
        if number(amount):
            return None, {"id": "credits", "label": "Credits balance", "value": amount, "unit": "credits"}
    currencies = {"$": "USD", "US$": "USD", "¥": "CNY", "￥": "CNY", "€": "EUR", "£": "GBP", "RMB": "CNY"}
    token = r"(US\$|\$|¥|￥|€|£|[A-Za-z]{3})"
    prefix = re.fullmatch(token + r"\s*" + numeric, value)
    suffix = re.fullmatch(numeric + r"\s*" + token, value)
    if prefix:
        unit, amount = prefix[1], prefix[2]
    elif suffix:
        amount, unit = suffix[1], suffix[2]
    else:
        return None, None
    amount = float(amount.replace(",", ""))
    currency = currencies.get(unit.upper(), unit.upper())
    if number(amount):
        return {"amount": amount, "currency": currency}, None
    return None, None


def convert_allowance(row, max_age=DEFAULT_MAX_AGE, now=None):
    if row.get("error"):
        message = str(row["error"])
        lowered = message.lower()
        if any(term in lowered for term in ("certificate", "connection refused", "timeout", "unreachable")):
            status = "unreachable"
        elif any(term in lowered for term in ("signed out", "not logged in", "unauthorized")):
            status = "signedOut"
        elif "429" in lowered or "rate limit" in lowered:
            status = "rateLimited"
        else:
            status = "serverError"
        raise SourceError(status, "Magpie account error: " + message)
    read_at = timestamp(row.get("readAt"))
    now = now or dt.datetime.now(dt.timezone.utc)
    if max_age > 0 and (read_at is None or (now - read_at).total_seconds() > max_age):
        raise SourceError("unreachable", "Magpie allowance is missing a timestamp or is older than %ss" % max_age)
    result = {"schemaVersion": 1}
    if isinstance(row.get("plan"), str) and row["plan"].strip():
        result["plan"] = row["plan"].strip()[:60]
    limits = []
    occurrences = {}
    windows = row.get("windows", [])
    if not isinstance(windows, list):
        raise SourceError("serverError", "Magpie windows must be an array")
    for window in windows:
        if not isinstance(window, dict):
            continue
        label = window.get("name")
        if not isinstance(label, str) or not label.strip():
            continue
        label = label.strip()
        occurrence = occurrences.get(label, 0)
        occurrences[label] = occurrence + 1
        limit_id = "window-" + hashlib.sha256((label + "\0" + str(occurrence)).encode()).hexdigest()[:12]
        limit = {"id": limit_id, "label": label[:60]}
        # Magpie's `used` is already a percentage. `amount` is the raw usage.
        percent = window.get("used")
        amount, capacity = window.get("amount"), window.get("limit")
        if number(percent) and percent >= 0:
            limit["usedPercent"] = percent
        if number(amount) and amount >= 0 and number(capacity) and capacity > 0:
            amounts = {"used": amount, "limit": capacity}
            if limit_percentage(amounts) is not None:
                limit.update(amounts)
        if "usedPercent" not in limit and "used" not in limit:
            continue
        reset = timestamp(window.get("resetsAt"))
        if reset:
            limit["resetsAt"] = reset.isoformat()
            duration = window_seconds(label)
            if duration:
                limit["windowSeconds"] = duration
        limits.append(limit)
    if limits:
        result["limits"] = limits
    balance, credit_metric = balance_value(row.get("balance"))
    if balance:
        result["balance"] = balance
    metrics = []
    if credit_metric:
        metrics.append(credit_metric)
    resets = row.get("resets")
    if isinstance(resets, dict) and number(resets.get("count")) and resets["count"] >= 0:
        metrics.append({"id": "resets", "label": "Quota resets available", "value": resets["count"], "unit": "times"})
    if read_at is not None:
        metrics.append({"id": "source-age", "label": "Magpie data age", "value": max(0, (now - read_at).total_seconds() / 60), "unit": "min"})
    if metrics:
        result["metrics"] = metrics
    if not limits and not balance:
        return {"schemaVersion": 1, "status": "noLimits"}
    return result


def read_config(path):
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SourceError("serverError", "Cannot read extension config: %s" % error) from error
    return validate_config(config)


def validate_config(config):
    """Share runtime validation with installation before any files are replaced."""
    if not isinstance(config, dict):
        raise SourceError("serverError", "config.json must be an object")
    if config.get("mode") == "aggregate":
        preferences = config.get("providers", {})
        if not isinstance(preferences, dict) or any(
            not isinstance(key, str) or not key or not isinstance(value, bool)
            for key, value in preferences.items()
        ):
            raise SourceError("serverError", "providers must map provider IDs to true or false")
        if not isinstance(config.get("showNewProviders", True), bool):
            raise SourceError("serverError", "showNewProviders must be a boolean")
        if config.get("balanceAccount") is not None and not isinstance(config["balanceAccount"], str):
            raise SourceError("serverError", "balanceAccount must be an account ID or null")
    elif not isinstance(config.get("provider"), str) or not config["provider"] or not isinstance(config.get("user", ""), str):
        raise SourceError("serverError", "config.json requires aggregate mode or a provider selector")
    age = config.get("maxAgeSeconds", DEFAULT_MAX_AGE)
    if not number(age) or age < 0:
        raise SourceError("serverError", "maxAgeSeconds must be a nonnegative number")
    return config


def save_config(path, config):
    """Atomically publish settings so a simultaneous Pulse refresh sees a complete file."""
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".settings-", delete=False) as temp:
        temporary = Path(temp.name)
        try:
            json.dump(config, temp, ensure_ascii=False, allow_nan=False, indent=2)
            temp.write("\n")
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def provider_enabled(config, provider):
    return config.get("providers", {}).get(provider, config.get("showNewProviders", True))


def account_label(row):
    name = str(row.get("name") or row["provider"])
    return name + (" · " + row["user"] if row.get("user") else "")


def prefixed_label(prefix, label):
    suffix = " · " + label[:30]
    return prefix[:60 - len(suffix)] + suffix


def aggregate_allowances(rows, config, now=None):
    """One Pulse account, with account-scoped limit identities and provider switches."""
    now = now or dt.datetime.now(dt.timezone.utc)
    selected = [row for row in rows if provider_enabled(config, row["provider"])]
    identities = [identity(row) for row in selected]
    if len(set(identities)) != len(identities):
        raise SourceError("serverError", "Magpie returned duplicate account identities")
    limits, metrics, balances, ages, errors = [], [], [], [], []
    provider_usage = {}
    for row in sorted(selected, key=identity):
        try:
            reading = convert_allowance(row, config.get("maxAgeSeconds", DEFAULT_MAX_AGE), now)
        except SourceError as error:
            errors.append(error)
            continue
        if reading.get("status"):
            continue
        account_id = extension_id(row)
        short_id = account_id.rsplit("-", 1)[-1]
        label = account_label(row)
        account_limits = reading.get("limits", [])
        if account_limits:
            percentages = [limit_percentage(limit) for limit in account_limits]
            provider_usage.setdefault(row["provider"], []).append(max(percentages))
        for limit in account_limits:
            limits.append({**limit, "id": short_id + "." + limit["id"], "label": prefixed_label(label, limit["label"])})
        for metric in reading.get("metrics", []):
            if metric["id"] == "source-age":
                ages.append(metric["value"])
            else:
                metrics.append({**metric, "id": short_id + "." + metric["id"], "label": prefixed_label(label, metric["label"])})
        if "balance" in reading:
            balances.append((account_id, label, reading["balance"]))
    balance_selector = config.get("balanceAccount")
    primary_balance = None
    if balance_selector:
        primary_balance = next((entry for entry in balances if entry[0] == balance_selector), None)
    elif len(balances) == 1:
        primary_balance = balances[0]
    # Different providers and currencies never silently become a combined balance.
    extra_balances = [entry for entry in balances if entry is not primary_balance]
    for account_id, label, balance in reversed(extra_balances):
        metrics.insert(0, {"id": account_id.rsplit("-", 1)[-1] + ".balance", "label": prefixed_label(label, "余额"), "value": balance["amount"], "unit": balance["currency"]})
    if ages:
        metrics.append({"id": "source-age", "label": "最早来源数据距今", "value": max(ages), "unit": "min"})
    if errors:
        metrics.insert(0, {"id": "unavailable-accounts", "label": "暂不可用的账号", "value": len(errors), "unit": "个"})
    result = {
        "schemaVersion": 1,
        "plan": "%d 个服务 · %d 个账号" % (len({row["provider"] for row in selected}), len(selected)),
    }
    if limits:
        provider_averages = [mean_percentage(values) for values in provider_usage.values()]
        average = mean_percentage(provider_averages)
        result["limits"] = [{
            "id": AVERAGE_LIMIT_ID,
            "label": "平均用量（%d 个服务等权）" % len(provider_averages),
            "usedPercent": average,
        }, *limits]
    if primary_balance is not None:
        result["balance"] = primary_balance[2]
    if not limits and primary_balance is None:
        # Balance-only selections still need a monetary reading for Pulse's ring.
        if balances:
            raise SourceError("noLimits", "Multiple balances: select a balance account in Magpie settings")
        if errors:
            raise SourceError(errors[0].status, "%d selected Magpie accounts are unavailable" % len(errors))
        return {"schemaVersion": 1, "status": "noLimits"}
    if metrics:
        result["metrics"] = metrics[:4]
    return result


def encode_report(output):
    """Respect Pulse's byte limit without truncating or dropping quota rows."""
    try:
        encoded = json.dumps(output, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (ValueError, OverflowError) as error:
        raise SourceError("serverError", "Magpie reading cannot be encoded as finite JSON") from error
    if len(encoded.encode("utf-8")) + 1 > MAX_OUTPUT_BYTES:
        raise SourceError("serverError", "Magpie reading exceeds Pulse's 256 KiB output limit")
    return encoded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().with_name("config.json"))
    parser.add_argument("--list", action="store_true", help="List local Magpie Allowances accounts")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Local endpoint, for --list only")
    args = parser.parse_args()
    try:
        if args.list:
            rows = fetch_allowances(args.endpoint)
            output = [{"id": extension_id(row), "name": display_name(row), "provider": row["provider"], "user": row.get("user", ""), "error": row.get("error")} for row in rows]
        else:
            config = read_config(args.config)
            rows = fetch_allowances(config.get("endpoint", DEFAULT_ENDPOINT))
            if config.get("mode") == "aggregate":
                output = aggregate_allowances(rows, config)
            else:
                account = select_account(rows, config["provider"], config.get("user", ""))
                output = convert_allowance(account, config.get("maxAgeSeconds", DEFAULT_MAX_AGE))
        encoded = encode_report(output)
    except SourceError as error:
        print(str(error), file=sys.stderr)
        encoded = encode_report({"schemaVersion": 1, "status": error.status})
    except Exception as error:
        print("Unexpected Magpie extension error: %s" % error, file=sys.stderr)
        encoded = encode_report({"schemaVersion": 1, "status": "serverError"})
    print(encoded)


if __name__ == "__main__":
    main()
