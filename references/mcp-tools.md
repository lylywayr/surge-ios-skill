# Surge iOS MCP 工具清单（Controller Protocol 41 / Surge 6.100.0 TF）

共 61 个工具，按功能分组。参数以 `tools/list` 的 inputSchema 为准；下表只列必填与常用可选参数。

## 状态与环境

| 工具 | 说明 | 必填参数 |
|---|---|---|
| `get_status` | Show the current profile name and path, outbound mode, global policy,  | — |
| `get_network_summary` | Passive snapshot of the network: interfaces, router, IPv4/IPv6 availab | — |
| `get_environment` | Return the raw runtime environment dictionary: ProxyGroupSelection (se | — |
| `run_diagnostics` | Run Surge's network self-check (interfaces, router, DNS, proxy connect | — |
| `run_benchmark` | rule-matching measures the average time to match a request against the | benchmark |
| `restart_engine` | Restart the proxy engine. Every connection is dropped, and this MCP co | — |
| `stop_surge` | Stop Surge. Proxying ends, and this MCP endpoint becomes unreachable u | — |
| `set_outbound_mode` | Change the outbound mode: rule (route by rules), direct (everything di | mode |
| `set_global_policy` | Change the policy used in global proxy mode. | policy |
| `set_feature` | Turn a feature on or off. The result reflects the actual state after t | feature, enabled |
| `set_environment` | Assign runtime environment key paths, as shown by get_environment. Use | values |
| `set_log_level` | Change the runtime log level until the next reload. The profile is not | level |

## 策略

| 工具 | 说明 | 必填参数 |
|---|---|---|
| `list_policies` | List every proxy policy and policy group of the active profile, with t | — |
| `list_policy_groups` | List policy groups with their type, current selection, and options. Au | — |
| `get_policy_detail` | Show the parsed definition and parameters of one policy. | policy |
| `select_group_policy` | Choose the policy of a select group, or override the choice of an auto | group, policy |
| `set_policy_avoidance` | Temporarily keep a policy out of the decisions of automatic groups (ur | action |
| `get_proxy_runtime_status` | Show the runtime internals of one proxy: connection state and, for Tai | policy |

## 规则

| 工具 | 说明 | 必填参数 |
|---|---|---|
| `list_rules` | List the effective rules of the active profile in matching order, incl | — |
| `match_rule` | Evaluate the active rule set for a destination without creating a conn | target |
| `list_temporary_rules` | List the temporary rules, which take precedence over all profile rules | — |
| `edit_temporary_rules` | Add, remove, or retarget temporary rules, or remove them all. Temporar | action |

## DNS

| 工具 | 说明 | 必填参数 |
|---|---|---|
| `dns_lookup` | Resolve a domain through Surge's DNS client and show the addresses, th | domain |
| `geoip_lookup` | Look up an IP address in the GeoIP and IP-ASN databases Surge uses for | address |
| `flush_dns_cache` | Clear Surge's DNS cache. | — |

## 请求与抓包

| 工具 | 说明 | 必填参数 |
|---|---|---|
| `list_requests` | List active and recent requests, newest first, with their URL, policy, | — |
| `get_captured_body` | Read the captured request or response body of a request recorded while | id |
| `kill_connection` | Terminate one active connection by its request id. | id |
| `list_capture_sessions` | List the HTTP capture sessions saved to disk, newest first, including  | — |
| `list_capture_session_requests` | List the requests saved in one capture session, in the order they were | session |
| `get_capture_session_body` | Read the request or response body of a request saved in a capture sess | session, key |
| `set_capture_filter` | Change one capture filter; omitted options stay as they are. keywords  | scope |

## Profile

| 工具 | 说明 | 必填参数 |
|---|---|---|
| `get_profile` | Return the profile text. effective is the profile after includes, modu | — |
| `switch_profile` | Switch to another profile by name and reload. | name |
| `reload_profile` | Reload the active profile from disk. | — |
| `list_profile_sections` | List the sections of the active profile in order, with the file that h | — |
| `get_profile_section` | Return the text of one profile section as written in the file that hol | section |
| `replace_profile_section` | Replace the whole content of one profile section, or create it, and re | section, content |

## 模块与资源

| 工具 | 说明 | 必填参数 |
|---|---|---|
| `list_modules` | List the available modules and which are enabled. Each entry in module | — |
| `get_module` | Show one module: the details of list_modules plus its text as written. | name |
| `set_modules_enabled` | Enable or disable modules by name. The profile reloads afterwards. | names, enabled |
| `list_external_resources` | List the external resources of the profile (rule sets, modules, script | — |
| `update_external_resource` | Download one external resource again, by its key as listed by list_ext | key |

## 脚本

| 工具 | 说明 | 必填参数 |
|---|---|---|
| `list_scripts` | List the scripts of the active profile. | — |
| `run_cron_script` | Run a cron script of the profile now and return its output and result. | name |
| `evaluate_script` | Evaluate JavaScript in Surge's script engine with the Surge script API | code |
| `get_script_log` | Read the log of one script execution, identified by the log name and s | name, session |

## 测试

| 工具 | 说明 | 必填参数 |
|---|---|---|
| `test_policies` | Test proxy policies. latency measures TCP connection latency and udp-l | policies |
| `test_policy_group` | Retest the members of an automatic policy group; the group may select  | group |
| `test_all_policies` | Test the latency of every policy. Automatic groups may select differen | — |
| `test_policy_bandwidth` | Measure the download or upload throughput of a policy. It transfers re | policy |
| `test_network` | Run an active network test without a proxy. latency: network latency.  | test |
| `test_ponte` | Diagnose the Ponte connection to another device of the same account. | device |
| `http_probe` | Send a real HTTP HEAD request through Surge and show the status code,  | url |

## 日志与监控

| 工具 | 说明 | 必填参数 |
|---|---|---|
| `get_logs` | Read recent log lines. memory holds recent entries of all levels; file | — |
| `get_logbook` | Return recent logbook records: notable events such as profile reloads, | — |
| `watch_events` | Subscribe to live events for a short window and return what arrived. l | events |
| `dump_runtime_data` | Return one runtime dataset. dns: DNS cache. dns-lookup-times: recent l | type |

## 安全

| 工具 | 说明 | 必填参数 |
|---|---|---|
| `list_security_bans` | List addresses banned after repeated failed authentication to the cont | — |
| `clear_security_bans` | Lift every unauthorized-access ban. | — |

## 未归类

- `get_capture_filters` — Show the filters that decide which requests are recorded: in（必填：无）
