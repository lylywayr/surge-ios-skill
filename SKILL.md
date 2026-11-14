---
name: surge-ios
description: 通过同机 Surge External Controller 检查和控制 Surge iOS，处理策略与节点、规则、DNS、连接、模块、脚本及代理诊断。涉及 Surge 专有命令或配置时使用。
---

# Surge for Minis

## 入口

`surge-cli`（默认 `http://127.0.0.1:6171`，Surge iOS 的 HTTP API；`-r 127.0.0.1:6170` 则走 Surge Mac 的 CLI socket，`-r host:port` 可连其他实例），脚本化读取用 `--raw`。密码只来自 `SURGE_CLI_PASSWORD` 或 `--password-stdin`，不进参数、文件、日志或回复。检查：`[ -n "$SURGE_CLI_PASSWORD" ] && echo set || echo missing`；缺失时给 [设置 SURGE_CLI_PASSWORD](minis://settings/environments?create_key=SURGE_CLI_PASSWORD&create_value=&create_note=Surge%20External%20Controller%20password)，不让用户在聊天里发密码。30 秒内 10 次密码错误会临时封禁来源：连接被拒先停手，用 `security ban list` 查看，不反复重试。

客户端是 `scripts/surge_cli.py`（软链为 `/usr/local/bin/surge-cli`，缺失时 `ln -sf` 重建），命令原样透传，新命令一般无需改客户端。

**两种后端（按 `-r` 前缀自动选）**：`http://` → Surge iOS 的 HTTP API（`POST /v1/mcp`，JSON-RPC，X-Key 鉴权，实现在 `scripts/surge_mcp.py`）；裸 `host:port` → Surge Mac 的 CLI 行协议（密码行 + 引号命令）。iOS 6.0+ 没有行协议，Mac 没有 `/v1/mcp`，别互相套。HTTP 后端覆盖：`status`、`summary`、`version`、`mode`、`global-policy`、`policy-group`、`policy detail|avoid`、`rule match|explain`、`rule temp`、`dns lookup|trace`、`flush dns`、`geoip`、`http probe`、`test*`、`diagnostics`、`benchmark`、`profile current|switch|section`、`dump *`、`module list|get|enable|disable`、`feature`、`capture-filter`、`capture sessions|requests|body|session-body`、`environment`、`set`、`set-log-level`、`log`、`logbook`、`script`、`script-log`、`kill`、`reload`、`restart-engine`、`stop`、`switch-profile`、`external-resource`、`proxy-runtime-status`、`security ban`、`watch`；`plugin`、`vmnet`、`device`、`profile list|check`、`managed-profile`、`unattended-upgrade` 在 iOS 上无对应端点，会报错而不是假装成功。`watch` 在 HTTP 后端是有界窗口（`watch request|speed [秒]`，1–60，默认 10），不是无限流。

当前实测 **Controller Protocol 41**（Surge 6.100.0 4026，iOS 27.0.1）共 **61 个 MCP 工具**，全量清单（分组 + 必填参数）见 [mcp-tools.md](references/mcp-tools.md)。新增能力：`policy detail` 看单个策略的解析结果、`policy avoid` 临时把节点排除在自动组之外、`capture sessions` 读磁盘上的抓包会话、`module get` 看模块原文。

iOS 不支持 `plugin`、`vmnet`、`device`、`lsp`；命令缺失或异常时先 `surge-cli --raw version` 核对 Controller Protocol，再查命令参考，不凭协议号推断。`restart-engine` 与 `reload` 不同，见变更规则。

改 Profile 内容：用 `profile section list|get|set`（protocol ≥31），不直接编辑挂载的文件。它会写到这一节实际所在的文件（跟随 `#!include`），写入前校验整个 Profile，写入后自动 reload。流程：`get <name> > f`，编辑 f，再执行 `set <name> f [revision]`（revision 可省；从 `get --raw` 或 `list` 拿，对不上会被拒绝写入）。`get` 返回的是 JSON 包装，节正文在 `.content`，直接回写包装会报「第 N 行格式无效」；文件带 BOM 时 `sed '^'` 之类的行首匹配会失效，改用 Python 读写。**校验是整份配置级的**：单独改 `[Proxy Group]` 里的组名、而 `[Rule]` 还指向旧名，会直接报"该规则使用了未知的策略：X"并拒绝写入。跨节改名要分三步过渡，每步都是合法配置：① 先加新名（旧名并存）→ ② 改引用方 → ③ 删旧名。`get` 的输出可能含代理密码，不要原样贴出来。抓包过滤用 `capture-filter`（protocol ≥36）；`capture sessions` / `capture requests <session>` / `capture body <id> [request|response]` 读磁盘上的抓包会话（protocol ≥41）。

模块：`surge-cli module list|get|enable|disable <#!name>`，按 `#!name` 匹配（不是文件名），会自动安排 reload；返回的 `enabled` 即结果。`module get` 会返回模块原文（header、arguments、各节行数、脚本与 MITM 主机），排查"这条规则从哪来的"用它。**iOS 没有卸载端点**：API 只有 list/get/enable/disable，`DELETE /v1/modules/...` 返回 405，iSH 也访问不到 Surge 容器目录，所以删除模块只能请用户在 App 内左滑，或用 `disable` 让它不生效。新模块先把 `.sgmodule` 写入已核实的 Surge `Module/` 目录（常见挂载 `/var/minis/mounts/surge`，不覆盖同名文件），`module list` 出现后再启用。

## 先看状态

依赖 Surge 联网的任务先 `surge-cli --raw status`；意外 EOF 或超时后重查。`status`/`environment` 没有暂停字段，Controller 能响应也不代表引擎在处理流量。是否暂停看 `logbook` 中最新一条 `type=network-switching` 记录：subtitle 含 `Surge iOS is now suspended`（如 "The network is managed by Surge Gateway"）即为自动暂停，切到其他网络后的记录则表示已恢复：

```sh
surge-cli --raw logbook 50 | python3 -c "import json,sys;r=[x for x in json.load(sys.stdin)['records'] if x.get('type')=='network-switching'];x=r[0] if r else {};print('suspended' if 'suspended' in x.get('subtitle','') else 'active',x.get('content'),'|',x.get('subtitle'))"
```

暂停由网络环境自动触发（Surge Mac 网关接管当前 Wi-Fi 等），首页显示 WAITING。CLI 没有恢复命令；需要时请用户点首页右上角状态按钮 → **Bypass Suspension**（临时绕过，不必离开网络），Bypass 不写 logbook，上面命令仍会显示 suspended，所以之后以重试原操作为准。不擅自重启、换模式或换实例。

## 参考

| 任务 | 文档 |
|---|---|
| **MCP 工具全量清单（61 个，按功能分组 + 必填参数）** | [mcp-tools.md](references/mcp-tools.md) |
| 命令、响应字段、环境 key-path | [command-reference.md](references/command-reference.md)（官方，只读相关节） |
| Profile/模块/代理/策略组/DNS/MITM/脚本配置语法 | [manual-index.md](references/manual-index.md) → 官方手册正文 |
| 规则集选源与体积（DOMAIN-SET / RULE-SET、blackmatrix7 结构、停更清单） | [rulesets.md](references/rulesets.md) |
| 路由解释、临时规则、DNS、实时日志、抓包、性能、Tailscale/WireGuard、未配置节点测试 | [diagnostics.md](references/diagnostics.md) |

不照搬其他代理客户端的语法；不确定时查官方正文，不猜字段或命令。

## 变更规则

- 改动前确认目标存在，只做最小授权变更，改后重读相关状态。
- **不追加 reload**：运行时操作（`set`、`set-log-level`、`feature set`、模式/策略选择、临时规则、DNS flush）即时生效；模块启停、Profile 切换自己会安排加载。直接改配置文件（含 `#!include` 的 .dconf）后 Surge 会检测到变化并自动重载（iPhone 实测约 2 秒，日志里会出现 `iCloud profile content changed` → `Reload profile`），不要再手动 reload；`profile section set` 也会自己 reload。Mac 端靠 iCloud 同步，可能延迟几十秒，急用时可以在 Mac 本机写入。`reload` 不是清理手段，会恢复配置中的日志等级等运行时状态。
- `restart-engine` 关闭连接并清空缓存和临时规则，`stop` 关闭 Surge：都须用户明确要求。
- 临时 verbose：变更完成后再设，结束或失败时恢复**原**等级，期间不要 reload 或切模块。
- 临时规则：只删本次添加的；`rule temp flush` 会清掉用户已有的，不用于清理。
- `<nil>` 赋值要加引号：`surge-cli --raw set 'AutoPolicyGroupOverride.Streaming=<nil>'`。

## 隐私与外部影响

- `dump profile` 含节点、订阅和凭据，确有必要才读，不原样输出。
- `--check <path>` 会把文件上传到 Surge 官方在线校验服务；不自动上传当前 Profile，含凭据时先用脱敏副本并告知用户。校验器版本落后于 TestFlight 构建，新语法（如 vless）会被误报 `Unknown proxy type`，不能据此判断本机不支持；验证本机能力用 `profile section set` 写入实测（本地整档校验 + reload）。
- `http probe`、节点/DNS/带宽测试会产生真实流量，按需执行。`benchmark encryption` 测的是本机加密性能，不是带宽。
- `watch`、诊断、带宽测试是 JSON Lines 流，以 `hasMore=false` 或结束载荷为准，不拿首帧当结果。

## 交付

报告实际状态、做了什么、验证结果和未确认之处。规则推演不冒充联网成功。

## 维护

`scripts/sync_upstream.sh <host> [--apply]` 经 SSH 从装有 Surge 的 Mac（用 `~/.ssh/config` 中用户确认的 alias）拉取官方技能：不加 `--apply` 只显示差异；加了会更新 command-reference.md（只替换 §1.1 为 Minis 说明）并写入 `references/UPSTREAM_VERSION`。官方 SKILL.md 的新流程手工合并到本文件。客户端 `scripts/surge_cli.py` 只在协议或官方本地转换变化时修改。
