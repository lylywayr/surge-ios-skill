#!/usr/bin/env python3
"""Surge iOS HTTP API backend for surge-cli.

Surge iOS does not expose the Mac CLI line protocol (password line + quoted
command). It exposes the HTTP API instead: JSON-RPC over POST /v1/mcp, with the
same command set as surge-cli, authenticated by the X-Key header.

This module maps surge-cli argv (already normalized) onto MCP tools and returns
objects shaped like the CLI socket responses, so surge_cli.py's renderers work
unchanged.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "surge-cli-minis", "version": "2"}


class BackendError(Exception):
    pass


class McpController:
    """Minimal MCP stdio-less client over the Surge HTTP API."""

    def __init__(self, base: str, key: str, timeout: float = 120.0):
        self.base = base.rstrip("/")
        self.url = self.base + "/v1/mcp"
        self.key = key
        self.timeout = timeout
        self._id = 0
        self._ready = False

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode()
        request = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "X-Key": self.key,
                "MCP-Protocol-Version": PROTOCOL_VERSION,
                "User-Agent": "surge-cli-minis/2",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace").strip()
            if e.code in (401, 403):
                raise BackendError(
                    "Authorization denied: the HTTP API rejected the key "
                    f"(HTTP {e.code}). Check the password in Surge's HTTP API settings."
                ) from None
            raise BackendError(f"HTTP API returned HTTP {e.code}: {detail[:300]}") from None
        except urllib.error.URLError as e:
            raise BackendError(f"Cannot connect to Surge HTTP API at {self.base}: {e.reason}") from None
        except (socket.timeout, TimeoutError):
            raise BackendError(f"Surge HTTP API timed out after {self.timeout:.0f}s") from None
        except OSError as e:
            raise BackendError(f"Cannot connect to Surge HTTP API at {self.base}: {e}") from None

        if "text/event-stream" in content_type:
            data_lines = [
                line[5:].strip()
                for line in raw.splitlines()
                if line.startswith("data:")
            ]
            raw = "\n".join(data_lines)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise BackendError(f"Surge HTTP API returned a non-JSON response: {raw[:200]}") from None

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            payload["params"] = params
        frame = self._post(payload)
        if "error" in frame:
            error = frame["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise BackendError(f"MCP error: {message}")
        return frame.get("result", {})

    def _initialize(self) -> None:
        if self._ready:
            return
        self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except BackendError:
            pass  # Notifications usually get no body; a failure here is harmless.
        self._ready = True

    def call(self, name: str, arguments: dict | None = None):
        self._initialize()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        text = "".join(
            item.get("text", "")
            for item in result.get("content", [])
            if item.get("type") == "text"
        )
        if result.get("isError"):
            raise BackendError(text.strip() or f"{name} failed")
        structured = result.get("structuredContent")
        if structured is not None:
            return structured
        stripped = text.strip()
        if not stripped:
            return {}
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return {"log": text} if name in ("get_logs", "get_script_log") else {"result": text}

    def run(self, argv: list[str]) -> list:
        tool, args, adapt = route(argv)
        value = self.call(tool, args)
        if adapt:
            value = adapt(value, self)
        return [value]


def _flag_map(argv: list[str], start: int) -> dict:
    """Parse trailing key=value pairs, e.g. interface=en0."""
    out = {}
    for item in argv[start:]:
        if "=" in item:
            key, _, val = item.partition("=")
            out[key.strip()] = val.strip()
    return out


def _off(value: str) -> bool:
    return str(value).strip().lower() in ("on", "true", "1", "yes", "enable", "enabled")


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _default_rule_policy(value, _controller):
    """The MCP explain payload names the matched rule `rule-policy`."""
    if isinstance(value, dict) and "rule" not in value and "rule-policy" in value:
        value["rule"] = value["rule-policy"]
    return value


def _policy_view(value, controller):
    """dump policy wants proxy and group names side by side."""
    if isinstance(value, dict) and "policy-groups" not in value:
        try:
            groups = controller.call("list_policy_groups") or {}
            value["policy-groups"] = [g.get("name") for g in groups.get("groups", []) if g.get("name")]
        except BackendError:
            value.setdefault("policy-groups", [])
    return value


def _section_content(value, _controller):
    """get_profile_section returns metadata + blank line + section text."""
    if isinstance(value, dict) and isinstance(value.get("result"), str):
        text = value["result"]
        _, _, body = text.partition("\n\n")
        return {"content": body if body else text}
    return value


def _profile_section_set(argv: list[str]):
    # normalize() already turned the file argument into base64 text.
    _, _, _, name, encoded, *rest = argv
    import base64

    try:
        content = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        raise BackendError("profile section set: section content is not valid base64/UTF-8") from None
    args = {"section": name, "content": content}
    if rest:
        args["revision"] = rest[0]
    return "replace_profile_section", args


def route(argv: list[str]):
    """Map normalized surge-cli argv to (tool, arguments, post-processor)."""
    if not argv:
        raise BackendError("Empty command")
    cmd = argv[0]
    a = argv

    if cmd == "status":
        return "get_status", {}, None
    if cmd == "version":
        return "get_status", {}, None
    if cmd == "environment":
        return "get_environment", {}, None
    if a[:2] == ["dump", "summary"]:
        return "get_network_summary", {}, None

    if cmd == "mode":
        if len(a) == 1 or a[1] == "get":
            return "get_status", {}, None
        if a[1] == "set" and len(a) >= 3:
            mode = a[2].lower()
            return "set_outbound_mode", {"mode": mode}, lambda v, _c: v or {"mode": mode}
        raise BackendError("Usage: mode [get | set <rule|direct|proxy>]")

    if cmd == "global-policy":
        if len(a) == 1 or a[1] == "get":
            return "get_status", {}, None
        if a[1] == "set" and len(a) >= 3:
            return "set_global_policy", {"policy": a[2]}, lambda v, _c: v or {"policy": a[2]}
        raise BackendError("Usage: global-policy [get | set <policy>]")

    if cmd == "policy-group":
        if len(a) >= 2 and a[1] == "list":
            return "list_policy_groups", {}, None
        if len(a) >= 3 and a[1] == "get":
            return "list_policy_groups", {"group": a[2]}, None
        if len(a) >= 4 and a[1] == "set":
            return "select_group_policy", {"group": a[2], "policy": a[3]}, None
        raise BackendError("Usage: policy-group <list | get <group> | set <group> <policy|auto>>")

    if cmd == "policy":
        if len(a) >= 3 and a[1] == "detail":
            return "get_policy_detail", {"policy": a[2]}, None
        if len(a) >= 2 and a[1] == "avoid":
            sub = a[2] if len(a) >= 3 else "list"
            if sub in ("list", "clear"):
                return "set_policy_avoidance", {"action": sub}, None
            if sub in ("add", "remove") and len(a) >= 4:
                return "set_policy_avoidance", {"action": sub, "policy": a[3]}, None
            raise BackendError("Usage: policy avoid <list | add <name> | remove <name> | clear>")
        raise BackendError("Usage: policy detail <name> | policy avoid ...")

    if cmd == "rule":
        if len(a) >= 3 and a[1] in ("match", "explain"):
            args = {"target": a[2], "explain": a[1] == "explain"}
            port = _int(a[3]) if len(a) > 3 else None
            if port is not None:
                args["port"] = port
            extra = _flag_map(a, 3)
            for key in ("url", "sni", "http_host", "protocol", "source_address", "device_name", "user_agent", "process_path", "client_mac"):
                if key in extra:
                    args[key] = extra[key]
            if "is_local" in extra:
                args["is_local"] = _off(extra["is_local"])
            return "match_rule", args, _default_rule_policy
        raise BackendError("Usage: rule <match|explain> <host|url> [port] [key=value ...]")

    if cmd == "add-temp-rule":
        return "edit_temporary_rules", {"action": "add", "rule": " ".join(a[1:])}, None
    if cmd == "del-temp-rule":
        return "edit_temporary_rules", {"action": "remove", "rule": " ".join(a[1:])}, None
    if cmd == "update-temp-rule":
        if len(a) < 3:
            raise BackendError("Usage: rule temp set-policy <rule> <policy>")
        return "edit_temporary_rules", {"action": "set-policy", "rule": a[1], "policy": a[2]}, None
    if cmd == "flush-temp-rule":
        return "edit_temporary_rules", {"action": "flush"}, None
    if a[:2] == ["dump", "temp-rule"]:
        return "list_temporary_rules", {}, None

    if cmd == "dns" and len(a) >= 3 and a[1] in ("lookup", "trace"):
        args = {"domain": a[2], "trace": a[1] == "trace"}
        extra = _flag_map(a, 3)
        if "interface" in extra:
            args["interface"] = extra["interface"]
        return "dns_lookup", args, None
    if a[:2] == ["flush", "dns"]:
        return "flush_dns_cache", {}, None
    if cmd == "geoip" and len(a) >= 2:
        return "geoip_lookup", {"address": a[1]}, None
    if cmd == "http" and len(a) >= 3 and a[1] == "probe":
        args = {"url": a[2]}
        if len(a) > 3:
            args["policy"] = a[3]
        return "http_probe", args, None

    if cmd == "test-network":
        return "test_network", {"test": "latency"}, None
    if cmd == "test" and len(a) >= 2 and a[1] in ("latency", "v4-router", "dns", "encrypted-dns", "external-ip", "nat-type"):
        return "test_network", {"test": a[1]}, None
    if cmd == "test-all-policies":
        return "test_all_policies", {}, None
    if cmd == "test-group" and len(a) >= 2:
        return "test_policy_group", {"group": a[1]}, None
    if cmd == "test-policy" and len(a) >= 2:
        return "test_policies", {"policies": [a[1]]}, None
    if cmd == "test-policy-udp" and len(a) >= 2:
        return "test_policies", {"policies": [a[1]], "test": "udp-latency"}, None
    if cmd == "test-policy-external-ip" and len(a) >= 2:
        return "test_policies", {"policies": [a[1]], "test": "external-ip"}, None
    if cmd == "test-policy-nat-type" and len(a) >= 2:
        return "test_policies", {"policies": [a[1]], "test": "nat-type"}, None
    if cmd == "test-policy-bandwidth" and len(a) >= 3:
        direction = "upload" if a[1] == "upload" else "download"
        return "test_policy_bandwidth", {"policy": a[2], "direction": direction}, None
    if cmd == "test-ponte" and len(a) >= 2:
        return "test_ponte", {"device": a[1]}, None
    if cmd == "diagnostics":
        return "run_diagnostics", {}, None
    if cmd == "benchmark" and len(a) >= 2:
        args = {"benchmark": a[1]}
        if len(a) > 2 and _int(a[2]):
            args["size_mib"] = _int(a[2])
        return "run_benchmark", args, None

    if cmd == "profile":
        sub = a[1] if len(a) > 1 else ""
        if sub in ("current", "diff"):
            variant = "original" if sub == "diff" else "effective"
            return "get_profile", {"variant": variant}, None
        if sub == "switch" and len(a) >= 3:
            return "switch_profile", {"name": a[2]}, None
        if sub == "section":
            if len(a) >= 3 and a[2] == "list":
                return "list_profile_sections", {}, None
            if len(a) >= 4 and a[2] == "get":
                return "get_profile_section", {"section": a[3]}, _section_content
            if len(a) >= 5 and a[2] == "set":
                return (*_profile_section_set(a), None)
            raise BackendError("Usage: profile section <list | get <name> | set <name> <file|-> [revision]>")
        raise BackendError("Usage: profile <current | diff | switch <name> | section ...>")

    if a[:2] == ["dump", "profile"]:
        return "get_profile", {}, None
    if cmd == "dump" and len(a) >= 2:
        target = a[1]
        if target in ("active", "recent"):
            return "list_requests", {"scope": target, "limit": 100}, None
        if target == "request" and len(a) >= 3 and _int(a[2]) is not None:
            return "list_requests", {"id": _int(a[2])}, None
        if target == "rule":
            return "list_rules", {}, None
        if target == "policy":
            return "list_policies", {}, _policy_view
        if target == "temp-rule":
            return "list_temporary_rules", {}, None
        if target == "traffic":
            return "dump_runtime_data", {"type": "traffic"}, None
        args = {"type": target}
        if len(a) > 2:
            args["argument"] = a[2]
        return "dump_runtime_data", args, None

    if cmd == "module":
        if len(a) >= 2 and a[1] == "list":
            return "list_modules", {}, None
        if len(a) >= 3 and a[1] == "get":
            return "get_module", {"name": a[2]}, None
        if len(a) >= 3 and a[1] in ("enable", "disable"):
            return "set_modules_enabled", {"names": a[2:], "enabled": a[1] == "enable"}, None
        raise BackendError("Usage: module <list | get <name> | enable <name...> | disable <name...>>")

    if cmd == "feature":
        if len(a) >= 2 and a[1] == "list":
            return "get_status", {}, None
        if len(a) >= 3 and a[1] == "get":
            return "get_status", {}, lambda v, _c: {"feature": a[2], "enabled": (v.get("features") or {}).get(a[2])}
        if len(a) >= 4 and a[1] == "set":
            enabled = _off(a[3])
            return "set_feature", {"feature": a[2], "enabled": enabled}, lambda v, _c: {"feature": a[2], "enabled": enabled}
        raise BackendError("Usage: feature <list | get <name> | set <name> <on|off>>")

    if cmd == "capture-filter":
        if len(a) >= 2 and a[1] == "list":
            return "get_capture_filters", {}, None
        if len(a) >= 3 and a[1] == "get":
            return "get_capture_filters", {"scope": a[2]}, None
        if len(a) >= 4 and a[1] == "set":
            scope = a[2]
            args = {"scope": scope}
            for pair in a[3:]:
                key, _, raw = pair.partition("=")
                key = key.strip()
                if key == "http-only":
                    args["httpOnly"] = _off(raw)
                elif key == "hide-crash-reporter":
                    args["hideCrashReporterRequests"] = _off(raw)
                elif key == "hide-apple":
                    args["hideAppleRequests"] = _off(raw)
                elif key == "hide-udp":
                    args["hideUDP"] = _off(raw)
                elif key == "type":
                    args["type"] = raw
                elif key == "keywords":
                    args["keywords"] = [x for x in raw.split(",") if x]
                elif key == "add-keyword":
                    args.setdefault("addKeywords", []).append(raw)
                elif key == "remove-keyword":
                    args.setdefault("removeKeywords", []).append(raw)
                elif key == "enable-keyword":
                    args.setdefault("enableKeywords", []).append(raw)
                elif key == "disable-keyword":
                    args.setdefault("disableKeywords", []).append(raw)
                else:
                    raise BackendError(f"capture-filter: unknown option {key}")
            return "set_capture_filter", args, None
        raise BackendError("Usage: capture-filter <list | get <scope> | set <scope> <option=value ...>>")

    if cmd == "capture":
        sub = a[1] if len(a) >= 2 else ""
        if sub == "sessions":
            return "list_capture_sessions", {"include_size": "--size" in a}, None
        if sub == "requests" and len(a) >= 3:
            args = {"session": a[2], "detail": "--detail" in a}
            if len(a) >= 4 and not a[3].startswith("--"):
                args["filter"] = a[3]
            for i, tok in enumerate(a):
                if tok in ("--limit", "--offset") and i + 1 < len(a):
                    num = _int(a[i + 1])
                    if num is not None:
                        args[tok[2:]] = num
            return "list_capture_session_requests", args, None
        if sub == "body" and len(a) >= 3:
            rid = _int(a[2])
            if rid is None:
                raise BackendError("capture body: request id must be a number")
            args = {"id": rid}
            if len(a) >= 4:
                args["part"] = a[3]
            return "get_captured_body", args, None
        if sub in ("session-body", "session-request") and len(a) >= 4:
            args = {"session": a[2], "key": a[3]}
            if len(a) >= 5:
                args["part"] = a[4]
            for i, tok in enumerate(a):
                if tok == "--offset" and i + 1 < len(a):
                    num = _int(a[i + 1])
                    if num is not None:
                        args["offset"] = num
            return "get_capture_session_body", args, None
        raise BackendError(
            "Usage: capture <sessions [--size] | requests <session> [filter] [--limit N] [--offset N] [--detail]"
            " | body <id> [request|response] | session-body <session> <key> [request|response] [--offset N]>"
        )

    if cmd == "set":
        values = {}
        for pair in a[1:]:
            key, _, raw = pair.partition("=")
            if not _:
                raise BackendError(f"set: expected key=value, got {pair}")
            if raw == "<nil>":
                values[key] = None
            elif raw.lower() in ("true", "false"):
                values[key] = raw.lower() == "true"
            elif _int(raw) is not None:
                values[key] = _int(raw)
            else:
                values[key] = raw
        return "set_environment", {"values": values}, None
    if cmd == "set-log-level" and len(a) >= 2:
        return "set_log_level", {"level": a[1]}, None

    if cmd == "logbook":
        args = {}
        if len(a) >= 2 and _int(a[1]):
            args["limit"] = _int(a[1])
        return "get_logbook", args, None
    if cmd == "log":
        args = {}
        if len(a) >= 2 and a[1] in ("file", "memory"):
            args["source"] = a[1]
            if len(a) >= 3 and _int(a[2]):
                args["lines"] = _int(a[2])
        elif len(a) >= 2 and _int(a[1]):
            args["lines"] = _int(a[1])
        return "get_logs", args, None

    if cmd == "script":
        if len(a) >= 2 and a[1] == "list":
            return "list_scripts", {}, None
        if len(a) >= 3 and a[1] == "run":
            return "run_cron_script", {"name": a[2]}, None
        if len(a) >= 3 and a[1] == "evaluate":
            import base64

            try:
                code = base64.b64decode(a[2]).decode("utf-8")
            except Exception:
                raise BackendError("script evaluate: invalid base64 script content") from None
            args = {"code": code}
            mock = a[3] if len(a) > 3 else "generic"
            types = {"generic": "generic", "cron": "cron", "event": "event", "rule": "rule",
                     "dns": "dns", "http-request": "http-request", "http-response": "http-response"}
            args["type"] = types.get(mock, "generic")
            if len(a) > 4 and _int(a[4]):
                args["timeout"] = max(1, min(60, _int(a[4])))
            return "evaluate_script", args, None
        raise BackendError("Usage: script <list | run <cron-name> | evaluate <file> [type] [timeout]>")
    if cmd == "script-log" and len(a) >= 3:
        return "get_script_log", {"name": a[1], "session": a[2]}, None

    if cmd == "kill" and len(a) >= 2 and _int(a[1]) is not None:
        return "kill_connection", {"id": _int(a[1])}, None
    if cmd == "reload":
        return "reload_profile", {}, None
    if cmd == "restart-engine":
        return "restart_engine", {}, None
    if cmd == "stop":
        return "stop_surge", {}, None
    if cmd == "switch-profile" and len(a) >= 2:
        return "switch_profile", {"name": a[1]}, None

    if cmd == "external-resource":
        if len(a) >= 2 and a[1] == "list":
            return "list_external_resources", {}, None
        if len(a) >= 3 and a[1] == "update":
            return "update_external_resource", {"key": a[2]}, None
        raise BackendError("Usage: external-resource <list | update <key|all>>")
    if cmd == "proxy-runtime-status" and len(a) >= 2:
        return "get_proxy_runtime_status", {"policy": a[1]}, None
    if cmd == "security" and len(a) >= 3 and a[1] == "ban":
        if a[2] == "list":
            return "list_security_bans", {}, None
        if a[2] == "clear":
            return "clear_security_bans", {}, None
    if cmd == "watch":
        event = "real-time-speed" if len(a) > 1 and a[1] == "speed" else "request"
        seconds = _int(a[2]) if len(a) > 2 else (_int(a[1]) if len(a) > 1 and _int(a[1]) else 10)
        return "watch_events", {"events": [event], "seconds": max(1, min(60, seconds or 10))}, None

    raise BackendError(
        f"`{' '.join(argv)}` has no equivalent in the Surge iOS HTTP API.\n"
        "Available on this backend: status, summary, version, mode, global-policy, "
        "policy-group, rule match/explain, rule temp, dns lookup/trace, flush dns, geoip, "
        "http probe, test-*, diagnostics, benchmark, profile current/switch/section, dump, "
        "module, feature, capture-filter, environment, set, set-log-level, log, logbook, "
        "script, script-log, kill, reload, restart-engine, stop, switch-profile, "
        "external-resource, proxy-runtime-status, security ban, watch."
    )
