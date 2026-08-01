# 补文本作战清单 — 25 个 text-gap 格(2026-08-01)

依据:`round2_gap_worklist.csv`(FETCH_GAP 11 + CORPUS_QUALITY 14)× `round2_inventory.jsonl` 法名/URL。
按**成功率从高到低**排序;每条给主源 + 备源。爬不动大声报告,绝不造假。

## 🟢 第一梯队(源站历史可靠,预期直接拿下)

| 格 | 法 | 拿法 |
|---|---|---|
| IDN 8.4 | Permenkominfo No.5/2020 + No.10/2021 (Private Electronic System Operators) | peraturan.bpk.go.id Details/203049 + 203121 —— 我们全部 IDN 文本都来自这站,重抓即可 |
| MNG 5.4 | Law of Mongolia on Communications | legalinfo.mn/mn/detail/523 —— autofix 曾从该站拿到 640K 字符,可靠 |
| MNG 7.3(已有文本可复用) | Law on Personal Data Protection | legalinfo.mn lawId=16390288615991(111K 字符已在 corpus,确认 manifest 指向) |

## 🟡 第二梯队(换官方源即可绕过封锁 —— 之前只试过 consultant/garant)

| 格 | 法 | 拿法 |
|---|---|---|
| RUS 4.9 | Federal Law 374-FZ (Yarovaya) | **pravo.gov.ru 官方公布平台** publication.pravo.gov.ru(检索 374-ФЗ 2016-07-06)或 kremlin.ru/acts/bank |
| RUS 5.7 | Presidential Decree No.215 (2018) | **kremlin.ru/acts**(总统令官方全文)/ publication.pravo.gov.ru |
| RUS 6.3 | Federal Law 152-FZ "On Personal Data" | pravo.gov.ru / kremlin.ru;GitHub 上也有 152-ФЗ 全文镜像 repo |
| RUS 8.2 | Federal Law 149-FZ "On Information" | 同上 |
| RUS 11.3 | EEC Decision No.30 (EAEU 非关税措施) | **docs.eaeunion.org**(欧亚经济委员会官方文库,英/俄双语)|
| CHN 10.3 | 网上境外影视剧管理通知 (2014) | chinafilm.gov.cn 原链 + 各大官媒/地方广电局转载镜像(全文常见) |
| CHN 5.7 | 2008 国务院机构改革方案 | gov.cn 原文(现有 1691 字符 stub)→ 找人大官网/新华社全文版 |

## 🟠 第三梯队(PDF 解析,源站可达)

| 格 | 法 | 拿法 |
|---|---|---|
| IND 3.4 | FDI Policy Circular 2020 + Press Note 3 | dpiit.gov.in PDF ×2(dpiit 之前可抓)|
| IND 3.5 | FDI Circular + RBI Master Circular 03/2011-12 | rbi.org.in PDF + indembkwt.gov.in 镜像 |
| IND 8.3 | DoT Aadhaar e-KYC F.No.800-26/2016 | dot.gov.in PDF(?download=1 直链)|
| CHN 10.2 | MOFCOM Notice 37/2021 目录 PDF | images.mofcom.gov.cn PDF(直链,之前超时→Wayback PDF 模式)+ 海关法已在 corpus |
| CHN 10.4 | 两用物项目录 2025 PDF + 禁止出口技术目录 PDF | mofcom cms PDF + most.gov.cn PDF |
| CHN 1.4 | MOFCOM 公告 2022#37 + 2023#16(反倾销) | mofcom.gov.cn 页面(超时→Wayback);trb.mofcom.gov.cn 备链 |

## 🔴 第四梯队(硬骨头,语言/扫描件问题)

| 格 | 法 | 障碍与残招 |
|---|---|---|
| THA 5.3/5.4 | NBTC 电信牌照/会计分离通知 | nbtc.go.th 超时 → Wayback;泰文;ratchakitcha.soc.go.th(皇家公报)可试 |
| THA 11.3 | NBTC 会计分离报告要求 B.E.2565 | 同上 |
| LAO 12.3 | Decree on E-Commerce 296/GoL | 已有 8.6M 字符老挝文(质量=文种问题);laotradeportal 找英文版;ZICO/Tilleke 只能进 Notes |
| LAO 7.4 | Law on Electronic Data Protection 25/NA | 已有 1.17M 字符老挝文;dataguidance 有英文 PDF(cyber crime law 同源盘)|
| LAO 8.3 | Decree 327/Gov (Internet Info Mgmt) + SIM 登记通知 | lsp.moic.gov.la 条文页(可抓)+ laotradeportal PDF |
| MNG 11.3 | Resolution 29 + CRC Resolution 52 | crc.gov.mn PDF(西里尔蒙文)|
| MNG/RUS/IND 5.3 | SOE 股权证据(Rostelecom 年报、BSNL/MTNL 官网、Telkom)| 非法条,是所有权证据页 —— 抓 About/Shareholding 页面文本 |

## GitHub 资源(评估结论)

- **LawRefBook/Laws**(中文法律 Markdown 全库):覆盖**法律/法规**,但我们缺的是 MOFCOM **公告/目录**级文书 —— 大概率不在;可作为海关法等 statute 的干净文本备源
- **俄法 GitHub 镜像**:152-ФЗ/149-ФЗ 常见;374-ФЗ(Yarovaya)镜像也有 —— 关键词 `"152-ФЗ" full text site:github.com`
- 泰/老/蒙:GitHub 无成规模资源,走官方源

## 执行序(窗口开了就跑)

1. WebFetch 第一梯队 3 条 → Write 入 corpus → Edit manifest
2. WebFetch RUS 官方源 5 条(pravo/kremlin/eaeunion)
3. PDF 类走 Bash(curl + pdf-reader 管线)
4. 每拿一条:字节数 sanity(≠2770!)+ 开头正文抽查 + sha256 → manifest
5. 全部入库后:重跑受影响 (economy, pillar) 组合 → merge → coverage
