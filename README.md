# surge-ios-skill

Surge iOS 的 Minis 技能：让 AI agent 通过 Surge 的 HTTP API（MCP）检查和控制 Surge。

- 后端：`POST /v1/mcp`（JSON-RPC，X-Key 鉴权），默认 `http://127.0.0.1:6171`
- 实测版本：Surge 6.100.0 (4019)，Controller Protocol **41**，**61 个 MCP 工具**
- 派生自 Surge Mac 应用自带的官方技能（`Surge.app/Contents/Resources/Skills/surge`），做了 iOS 适配

## 安装（Minis）

```sh
cd /var/minis/skills
git clone https://github.com/lylywayr/surge-ios-skill.git surge-ios
ln -sf /var/minis/skills/surge-ios/scripts/surge_cli.py /usr/local/bin/surge-cli
chmod +x /var/minis/skills/surge-ios/scripts/surge_cli.py
```

没有 git 时，直接下载 zip 解压到 `/var/minis/skills/surge-ios`。

## 配置

1. Surge → 设置 → 通用 → HTTP API，开启并记录密码；`http-api-mcp = true`
2. Minis 环境变量里加 `SURGE_CLI_PASSWORD`

## 用法

```sh
surge-cli status
surge-cli policy-group list
surge-cli policy detail 代理策略
surge-cli rule match www.google.com
surge-cli profile section get General
surge-cli module get <模块名>
surge-cli capture sessions
```

完整命令见 `SKILL.md`，61 个 MCP 工具见 `references/mcp-tools.md`。

## iOS 限制

- 无模块卸载端点（只能 App 内左滑删除）
- 无 `plugin` / `vmnet` / `device` / `profile list|check` / `managed-profile`
- Profile 只能按节读写（`profile section get|set`），整份文件不支持写入

## 同步官方技能

有装了 Surge 的 Mac 时：

```sh
scripts/sync_upstream.sh <ssh主机> [--apply]
```
