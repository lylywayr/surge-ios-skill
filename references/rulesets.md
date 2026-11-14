# 规则集与 DOMAIN-SET

官方正文：[Rule Sets](https://manual.nssurge.com/rules/ruleset.html)、[Domain Rules](https://manual.nssurge.com/rules/domain.html)。改动前读相关节，不按其他客户端语法推断。

## 选型

- **纯域名大表用 DOMAIN-SET**：`DOMAIN-SET,<url|本地路径>,<策略>`。文件是每行一个主机名（行首可加点表示后缀匹配），加载时预处理成索引，几十万条也能快速查找；iOS 6.0.0+ 无条目上限（更早版本单表上限 100 万）。
- **混合类型用 RULE-SET**：`RULE-SET,<url|本地路径>,<策略>[,选项]`，文件里写完整规则行。RULE-SET 的域名/后缀条目同样进索引；超过 50 条 IP-CIDR 会编译成二进制 IP 库，IP-ASN 常量时间，其余类型线性匹配。
- 同一 URL / 文件路径不能同时当 RULE-SET 和 DOMAIN-SET 用。远程表默认 24 小时更新（`update-interval=<秒>`，负数关闭）；本地文件变化会自动重载。
- 常用行选项：`no-resolve`（整表不做 DNS 解析）、`extended-matching`（域名规则同时匹配 TLS SNI / HTTP Host）、`pre-matching`（REJECT 类策略可进预匹配阶段）。内联 `[Ruleset <名>]` 可嵌套引用，最多 8 层，循环引用会被拒绝。

## 选源（blackmatrix7 等）

- `rule/Surge/<名>/` 下的同名 `<名>.list` 常是旧的拼装件，可能混多种规则类型；Surge ≥ 5.21.0(2952) 优先用 `_All.list`（完整规则）或 `_Domain.list`（纯域名，配 DOMAIN-SET）。
- `ChinaMaxNoIP.list` 只有 147 行，是去 IP 的精简件，不是全量；全量在 `ChinaMaxNoIP_All.list`（约 11 万条，含 IP）和 `ChinaMaxNoIP_Domain.list`（纯域名）。
- `ChinaASN.list` 自 2024-02 停更，不要用。
- `China` 版含大量 USER-AGENT 规则，匹配开销大；只需分流时用 ChinaMaxNoIP 系列。
- 换源前先把候选文件下载下来看行数与首尾内容，避免把停更或残缺文件当全量写入。

## 摆放与验证

- 具体清单规则放在 `GEOIP,CN` 等兜底和 `FINAL` 之前；一条 DOMAIN-SET 就能覆盖整张表，不必展开成上万条规则。
- 实测 11 万条 DOMAIN-SET 加载后 Surge 内存占用无明显变化；不要用「会不会太大」当拒绝理由，但也不要把同一张表重复挂成多条规则。
- 改完抽测：`surge-cli --raw rule match <域名>`；命中分布看 `dump rule-usage`，匹配耗时看 `benchmark rule-matching`。
- 整档校验和 reload 由 `profile section set` 负责，改完不要再手动 `reload`。

minis_url: minis://skills/surge-ios/references/rulesets.md
