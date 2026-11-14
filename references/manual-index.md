# Surge 官方配置手册索引

本参考补充官方 Surge Skill 仅附带 CLI/Controller 命令参考、未附带完整配置语法手册的问题。

## 权威来源与查阅顺序

1. 配置文件、模块、规则、代理协议和策略组语法：查阅 [Surge Manual](https://manual.nssurge.com/)。
2. `surge-cli` / Controller 命令、参数和响应：查阅本 Skill 的 [Command Reference](command-reference.md)。
3. 若保存的具体页面失效，从手册首页或侧栏目录重新定位；不要猜测 URL，也不要先用搜索引擎摘要代替官方正文。

`surge-cli --check` 的上传风险见 SKILL.md；有 Mac 时可用 `/Applications/Surge.app/Contents/Applications/surge-cli --check <path>` 本地校验，不上传。没有 Mac 时注意在线校验器版本落后于 TF 构建，vless 等新语法会被误报，本机能力以 `profile section set` 回写实测为准。

## 常用配置入口

### Profile

- [Profile Format](https://manual.nssurge.com/profile/format.html)
- [Requirement Expressions](https://manual.nssurge.com/profile/requirement.html) — iOS 5.22.0 / Mac 6.9.0 起支持 `DEVICE_NAME`
- [General Section Options](https://manual.nssurge.com/profile/general.html)
- [Module](https://manual.nssurge.com/profile/module.html)
- [Managed Profile](https://manual.nssurge.com/profile/managed-profile.html)
- [Keystore](https://manual.nssurge.com/profile/keystore.html)

### 规则

- [Rule System Overview](https://manual.nssurge.com/rules/overview.html)
- [Domain Rules](https://manual.nssurge.com/rules/domain.html)
- [IP Rules](https://manual.nssurge.com/rules/ip.html)
- [Protocol and Network Rules](https://manual.nssurge.com/rules/protocol-and-network.html)
- [Logical Rules](https://manual.nssurge.com/rules/logical.html)
- [Rule Sets](https://manual.nssurge.com/rules/ruleset.html)

### 代理策略与协议

- [Policy Overview](https://manual.nssurge.com/policies/overview.html)
- [Common Policy Parameters](https://manual.nssurge.com/policies/parameters.html) — 包含 `underlying-proxy` 代理链
- [TLS and Shadow TLS](https://manual.nssurge.com/policies/tls.html)
- [UDP Relay](https://manual.nssurge.com/policies/udp.html)
- [HTTP and HTTP/2](https://manual.nssurge.com/policies/http.html)
- [SOCKS5](https://manual.nssurge.com/policies/socks5.html)
- [Shadowsocks](https://manual.nssurge.com/policies/shadowsocks.html)
- [Snell](https://manual.nssurge.com/policies/snell.html)
- [VMess](https://manual.nssurge.com/policies/vmess.html)
- [Trojan](https://manual.nssurge.com/policies/trojan.html)
- [TUIC](https://manual.nssurge.com/policies/tuic.html)
- [Hysteria 2](https://manual.nssurge.com/policies/hysteria2.html)
- [VLESS](https://manual.nssurge.com/policies/vless.html) — iOS 6.0.0+；RAW / WS / gRPC / XHTTP，REALITY 与 XTLS Vision
- [WireGuard](https://manual.nssurge.com/policies/wireguard.html)
- [Tailscale](https://manual.nssurge.com/policies/tailscale.html)

### 策略组

- [Policy Group Overview](https://manual.nssurge.com/policy-groups/overview.html)
- [Manual Selection Group](https://manual.nssurge.com/policy-groups/select.html)
- [Automatic Testing Group](https://manual.nssurge.com/policy-groups/url-test.html)
- [Smart Group](https://manual.nssurge.com/policy-groups/smart.html)
- [Policy Including](https://manual.nssurge.com/policy-groups/policy-including.html)
- [Common Group Parameters](https://manual.nssurge.com/policy-groups/parameters.html)

### DNS、HTTP 与脚本

- [DNS Overview](https://manual.nssurge.com/dns/overview.html)
- [HTTP Processing Overview](https://manual.nssurge.com/http/overview.html)
- [HTTPS Decryption (MITM)](https://manual.nssurge.com/http/mitm.html)
- [URL Rewrite](https://manual.nssurge.com/http/url-rewrite.html)
- [Scripting Overview](https://manual.nssurge.com/scripting/overview.html)
- [JavaScript API Reference](https://manual.nssurge.com/scripting/api.html)

### 工具与远程控制

- [Surge Mac CLI](https://manual.nssurge.com/tools/cli.html)
- [Dashboard and Remote Access](https://manual.nssurge.com/tools/dashboard.html)
- [Testing](https://manual.nssurge.com/tools/testing.html)
