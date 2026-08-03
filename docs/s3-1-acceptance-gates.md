# S3-1 Country Bootstrap — 测试集与验收门
_2026-08-03。规则(Dong 定):先立测试,方案过门才准前进;一直迭代,直到新国家能完成 12 pillars 打分直接出分。_

## 测试集
- **真值文件**:`data/holdout/holdout_countries.jsonl` — 5 个引擎从未见过的国家
  (VNM 越南 / KAZ 哈萨克斯坦 / KHM 柬埔寨 / BRN 文莱 / FJI 斐济),
  含官方域名 allowlist + P6/P7 招牌法。
- **铁律**:真值只给测试/评测台读。引擎代码 import 或读取 holdout = 作弊,
  有专门的单元测试静态检查这一点。

## 验收门(顺序过关)

| 门 | 内容 | 通过标准 | 形式 |
|---|---|---|---|
| **G1** | bootstrap 模块单元测试(全 mock) | pytest 全绿 | `tests/test_country_bootstrap.py` |
| **G2** | 门户自主发现 | ≥4/5 国家:bootstrap 自主找到 ≥1 个 allowlist 官方域名 | `scripts/holdout_eval.py --gate 2`(live) |
| **G3** | P6/P7 端到端 | ≥3/5 国家:≥5 行逐字验证证据,零人工步骤 | `scripts/holdout_eval.py --gate 3`(live) |
| **G4** | 12 pillars 直接出分 | ≥1 个新国家:12 pillars 全跑通,每个有证据的指标带确定性分数,CSV+JSON 完整落盘 | `scripts/holdout_eval.py --gate 4`(live) |

每门产出一份 scorecard(JSON)存 `outputs/holdout/`,时间戳留档——这就是决赛
"autonomous generalization" 的证据链。

## 指标口径
- **门户发现命中** = bootstrap 产出的 LegalSourceConfig.domains ∩ allowlist ≠ ∅
- **证据行** = 通过全部提交闸门(逐字校验含)的行
- **零人工** = 从 `--economy <新国家>` 一条命令到 CSV 落盘,无任何中途干预
- **出分** = Zone 3 确定性打分器对该国逐指标输出官方允许值(0/0.5/1 等),
  无官方答案键的国家标注 "our reading, unverified against official"
