"""Indicator classifier — short-lists which RDTII 2.1 indicators an article touches."""

from __future__ import annotations

import re
from dataclasses import dataclass

from terminology import expand_phrases

# Unified dictionary for all 12 supported RDTII indicators
_BASE_PHRASES = {
    "1.1": ["tariff", "customs duty", "tax", "关税", "贸易防御"],
    "1.4": ["anti-dumping", "countervailing duty", "safeguard", "trade defence",
            "反倾销", "反补贴", "保障措施", "贸易救济",
            "bea masuk antidumping", "bea masuk imbalan", "tindakan pengamanan",
            "антидемпинг", "компенсационная пошлина", "защитная мера"],
    "2.1": [
        "public procurement", "government tender", 
        "การจัดซื้อจัดจ้าง", "พัสดุ", "คณะกรรมการ", 
        "政府采购", "招投标"
    ],
    "2.2": ["source code", "encryption", "trade secret", "algorithm disclosure",
            "源代码", "加密", "商业秘密", "算法",
            "kode sumber", "rahasia dagang", "enkripsi",
            "исходный код", "шифрование", "коммерческая тайна"],
    "2.3": ["procurement bidding", "procurement limitation", "government procurement",
            "采购招标", "政府采购限制",
            "pengadaan", "tender pengadaan",
            "госзакупки", "тендер",
            "худалдан авах", "тендер"],
    "3.1": [
        "foreign direct investment", "FDI", "foreign ownership",
        "外商投资", "外资", "外商投资法",
        "investasi asing", "kepemilikan asing", "penanaman modal asing",
        "иностранные инвестиции", "иностранная собственность",
        "การลงทุนต่างประเทศ", "การถือครองโดยคนต่างด้าว",
    ],
    "3.2": ["joint venture", "JV requirement", "合资企业", "合资要求", "外商投资电信",
            "usaha patungan", "режим совместного предприятия",
            "การร่วมทุน"],
    "3.3": ["board nationality", "board residency", "director nationality", "manager nationality",
            "董事国籍", "经理居住要求",
            "kewarganegaraan direktur", "domisili direktur",
            "гражданство директора", "резидентство"],
    "3.4": ["investment screening", "merger control", "acquisition review", "competition law",
            "投资审查", "并购控制", "经营者集中",
            "penapisan investasi", "kontrol merger", "hukum persaingan",
            "проверка инвестиций", "контроль слияний",
            "การคัดกรองการลงทุน"],
    "3.5": ["commercial presence", "cross-border service", "establishment requirement",
            "商业存在", "跨境服务", "设立要求",
            "kehadiran komersial", "persyaratan pendirian",
            "коммерческое присутствие", "трансграничные услуги",
            "худалдааны оролцоо", "хөрөнгө оруулалт", "компани"],
    "4.1": ["intellectual property", "patent", "copyright", "知识产权", "专利", "著作权",
            "kekayaan intelektual", "paten", "hak cipta",
            "интеллектуальная собственность", "патент", "авторское право",
            "ทรัพย์สินทางปัญญา", "สิทธิบัตร", "ลิขสิทธิ์"],
    "4.5": ["copyright exception", "fair use", "copyright framework",
            "著作权例外", "合理使用",
            "pengecualian hak cipta", "penggunaan wajar",
            "исключение авторского права", "добросовестное использование"],
    "4.9": ["trade secret disclosure", "source code disclosure", "algorithm disclosure",
            "商业秘密披露", "源代码披露", "算法强制披露",
            "pengungkapan rahasia dagang", "pengungkapan kode sumber",
            "разглашение коммерческой тайны", "раскрытие исходного кода",
            "การเปิดเผยความลับทางการค้า",
            # Counter-terrorism / communications interception (374-FZ Yarovaya)
            "терроризм", "террористической", "перехват", "переписка",
            "содержание сообщений", "операторы связи",
            "反恐", "恐怖主义", "拦截通信", "通信运营商",
            "counter-terrorism", "counterterrorism", "interception"],
    "4.10": ["trade secret protection", "trade secret law",
             "商业秘密保护", "商业秘密法律",
             "perlindungan rahasia dagang", "undang-undang rahasia dagang",
             "защита коммерческой тайны"],
    "5.1": ["telecom", "broadband", "frequency", "电信", "宽带"],
    "5.2": ["foreign equity limit", "telecom foreign ownership",
            "外资股权限制", "电信外资",
            "batas kepemilikan asing", "kepemilikan asing telekomunikasi",
            "предел иностранного участия", "иностранная доля в телекоме",
            "สัดส่วนการถือหุ้นของคนต่างด้าว"],
    "5.3": [
        "government equity", "government ownership", "state-owned",
        "majority stake", "government share", "public sector",
        "telecom", "operator", "telecommunication service provider",
        "政府持股", "国有", "国有控股", "控股",
    ],
    "5.4": ["accounting separation", "functional separation", "structural separation",
            "vertical separation", "accounting segregation",
            "会计分离", "功能分离", "结构性分离",
            "pemisahan akuntansi", "pemisahan fungsional",
            "раздельный учет", "функциональное разделение",
            "тусгаарлах", "бүртгэлийн тусгаарлалт",
            "การแยกบัญชี", "การแยกหน้าที่"],
    "5.5": ["telecom license", "telecom licensing", "operator license", "telecommunication license",
            "电信牌照", "电信许可", "运营许可证", "经营许可", "业务许可",
            "izin telekomunikasi", "lisensi operator",
            "лицензия оператора", "разрешение в телекоме",
            "ใบอนุญาตโทรคมนาคม"],
    "5.7": ["telecom authority", "independent regulator", "telecom regulator",
            "电信监管机构", "独立监管机构",
            "otoritas telekomunikasi", "regulator independen",
            "независимый регулятор", "телеком-регулятор",
            "бие даасан зохицуулагч", "харилцаа холбооны зохицуулагч",
            "หน่วยงานกำกับดูแลโทรคมนาคมอิสระ"],
    "6.1": [
        "transfer abroad", "transferred abroad", "transferring abroad", "transferring data abroad", "ban on transfer",
        "process locally", "data localization", "data localisation",
        "xử lý tại chỗ", "pemrosesan", "proses", "ห้ามโอนย้ายไปต่างประเทศ",
        "出境", "境外", "境内处理", "禁止传输", "本地处理",
        "transfer personal data", "transfer of personal data", "restrict transfer",
        "prohibition of transfer", "no transfer", "shall not transfer",
        # Hindi (India DPDP Act 2023 / gazette Hindi): स्थानांतरण = transfer,
        # भारत के बाहर = outside India, स्थानीय प्रसंस्करण = local processing.
        "स्थानांतरण", "भारत के बाहर", "स्थानीय प्रसंस्करण", "बाहर स्थानांतरित"
    ],
    "6.2": [
        "store data within", "local storage", "stored locally",
        "lưu trữ dữ liệu", "disimpan", "penyimpanan", "เก็บรักษาไว้",
        "境内存储", "本地存储",
        # Hindi: भंडारण = storage, संग्रहीत = stored, स्थानीय भंडारण = local storage.
        "स्थानीय भंडारण", "भंडारण", "संग्रहीत", "देश के भीतर"
    ],
    "6.3": [
        "local data centre", "local data center", "data center within", "data centre within",
        "local server", "physical infrastructure", "establish a server",
        "服务器", "数据中心",
        # Hindi: सर्वर = server, डेटा केंद्र = data centre.
        "सर्वर", "डेटा केंद्र"
    ],
    "6.4": [
        "consent", "adequacy", "standard contract", "prior authorization", "security assessment",
        " согласие", "充分性", "标准合同", "安全评估",
        "data exporter", "data importer", "binding corporate", "adequate level of protection",
        "appropriate safeguard", "contractual clause", "transfer mechanism",
        # Conditional cross-border flow language — golden boundary cases:
        # SGP PDPA s.26 ("comparable ... standard of protection") and
        # AUS Privacy Act APP 8.1 ("overseas recipient", "cross-border disclosure").
        "comparable protection", "comparable standard", "standard of protection",
        "adequate protection", "overseas recipient", "cross-border disclosure",
        "cross-border transfer", "跨境提供", "对外提供",
        # Hindi: सहमति = consent, सीमापार = cross-border, पर्याप्त सुरक्षा = adequate protection.
        "सहमति", "सीमापार", "पर्याप्त सुरक्षा"
    ],
    "6.5": [
        "trade agreement", "depa", "cptpp", "rcep", "free flow of data",
        "自由贸易协定", "数字经济伙伴关系"
    ],
    "7.1": [
        "personal data protection", "privacy law", "privacy act", "data protection act",
        "luật bảo vệ dữ liệu", "undang-undang perlindungan data",
        "个人信息保护法", "隐私", "数据主体",
        # Hindi: डेटा संरक्षण = data protection, व्यक्तिगत डेटा = personal data,
        # निजता = privacy (Puttaswamy right-to-privacy term).
        "डेटा संरक्षण", "व्यक्तिगत डेटा", "निजता"
    ],
    "7.2": [
        # AU/UK/SG drafting writes the open compound ("cyber security");
        # the closed form alone missed the AUS Cyber Security Act 2024.
        "cybersecurity", "cyber security", "cybercrime", "cyber crime",
        "an ninh mạng", "keamanan siber",
        "网络安全", "网络犯罪",
        # Hindi: साइबर सुरक्षा = cybersecurity, साइबर अपराध = cybercrime.
        "साइबर सुरक्षा", "साइबर अपराध"
    ],
    "7.3": [
        "retain", "retention period", "minimum period",
        "thời gian lưu trữ", "periode retensi",
        "保留", "至少保存", "保留期",
        # Hindi: प्रतिधारण/अवधारण = retention, अवधि = period.
        "प्रतिधारण", "अवधारण अवधि", "प्रतिधारण अवधि", "न्यूनतम अवधि"
    ],
    "7.4": [
        "data protection officer", "dpo", "dpia", "impact assessment",
        "designate one or more individuals",
        # Malay (PDP Commissioner circulars): DPO = Pegawai Perlindungan Data
        "pegawai perlindungan data",
        "数据保护官", "影响评估",
        "compliance officer", "privacy officer", "registration with",
        "data controller", "data processor", "register of processing",
        "annual audit", "data audit", "compliance audit",
        # Hindi (DPDP accountability): डेटा संरक्षण अधिकारी = DPO,
        # डेटा प्रत्ययी = Data Fiduciary, डेटा संरक्षण बोर्ड = Data Protection Board.
        "डेटा संरक्षण अधिकारी", "डेटा प्रत्ययी", "डेटा संरक्षण बोर्ड"
    ],
    "7.5": [
        "law enforcement access", "without warrant", "surveillance",
        "执法", "国家安全", "监视",
        "public interest", "public authority access", "government access",
        "national security", "public order", "disclosure to law enforcement",
        "obligation to notify", "competent authority", "regulatory authority",
        # Hindi: निगरानी = surveillance, राष्ट्रीय सुरक्षा = national security,
        # विधि प्रवर्तन = law enforcement, सरकारी पहुंच = government access.
        "निगरानी", "राष्ट्रीय सुरक्षा", "विधि प्रवर्तन", "सरकारी पहुंच"
    ],
    "8.1": ["intermediary liability", "safe harbor", "互联网平台责任", "责任承担"],
    "8.2": ["safe harbour", "illegal activity", "intermediary protection",
            "安全港", "非法活动", "平台保护",
            "perlindungan perantara", "aktivitas ilegal",
            "безопасная гавань", "незаконная деятельность",
            "зуучлагчийн хамгаалалт", "хууль бус үйл ажиллагаа",
            "การคุ้มครองคนกลาง", "กิจกรรมที่ผิดกฎหมาย"],
    "8.3": ["user identification", "user identity", "KYC", "customer verification",
            "用户身份", "实名认证", "用户识别",
            "identitas pengguna", "verifikasi pelanggan",
            "идентификация пользователя", "верификация",
            "การระบุตัวตนผู้ใช้"],
    "9.1": ["online content", "illegal content", "在线内容", "违法内容"],
    "9.4": ["content license", "social media license", "online content license", "platform license",
            "内容许可", "社交媒体许可", "平台许可",
            "lisensi konten", "lisensi platform", "lisensi media sosial",
            "лицензия на контент", "лицензия платформы",
            "агуулгын тусгай зөвшөөрөл", "платформын тусгай зөвшөөрөл",
            "ใบอนุญาตเนื้อหา", "ใบอนุญาตแพลตฟอร์ม"],
    "10.1": ["non-tariff measure", "trade restriction", "非关税措施", "贸易限制"],
    "10.2": ["import restriction", "ICT import", "goods import",
             "进口限制", "ICT产品进口",
             "restriksi impor", "impor barang ICT",
             "ограничение импорта", "импорт ICT"],
    "10.3": ["local content requirement", "domestic content", "local sourcing",
             "本地含量要求", "国产化", "本地采购",
             "境外影视剧", "引进境外", "进口影片", "境外剧",  # content-import quotas (CHN 10.3)
             "persyaratan konten lokal", "sumber daya lokal",
             "требование локального содержания",
             "ข้อกำหนดเนื้อหาในประเทศ"],
    "10.4": ["export restriction", "ICT export", "export control",
             "出口限制", "ICT出口管制",
             "restriksi ekspor", "kontrol ekspor",
             "ограничение экспорта", "экспортный контроль",
             "ข้อจำกัดการส่งออก"],
    "11.2": ["self-certification", "conformity assessment", "product safety", "EMC", "EMI",
             "radio transmission", "type approval", "certification",
             "自我认证", "合格评定", "产品安全", "型号核准",
             "sertifikasi mandiri", "penilaian kesesuaian", "keamanan produk",
             "сертификация", "оценка соответствия", "безопасность продукции",
             "การรับรองตนเอง", "การประเมินความสอดคล้อง"],
    "11.3": ["product screening", "product testing", "import testing", "equipment testing",
             "产品检测", "进口检测", "设备测试",
             "pengujian produk", "pengujian impor",
             "тестирование продукции", "испытание оборудования",
             "การทดสอบสินค้า"],
    "12.1": ["online sales", "e-signature", "在线销售", "电子签名"],
    "12.2": ["online purchase", "delivery limitation", "e-commerce delivery",
             "在线购买", "配送限制",
             "pembelian online", "batas pengiriman",
             "покупка онлайн", "ограничение доставки"],
    "12.3": ["e-commerce license", "e-commerce licensing", "online marketplace license", "B2B license", "B2C license",
             "电子商务许可", "电商牌照", "电子商务", "电商经营",
             "lisensi e-commerce", "izin platform online",
             "лицензия электронной коммерции",
             "ใบอนุญาตพาณิชย์อิเล็กทรอนิกส์"],
    "12.4.1": ["local bank account", "online payment bank", "payment local account",
               "本地银行账户", "在线支付银行",
               "rekening bank lokal", "pembayaran online",
               "местный банковский счет", "онлайн-платеж"],
    "12.4.2": ["payment currency", "local currency payment", "international payment currency",
               "支付货币", "本币结算",
               "mata uang pembayaran", "pembayaran mata uang lokal",
               "валюта платежа", "местная валюта"],
    "12.4.4": ["payment license", "payment licensing", "payment system license",
               "支付牌照", "支付许可",
               "lisensi pembayaran", "izin sistem pembayaran",
               "лицензия платежной системы"],
    "12.4.5": ["payment limit", "maximum amount", "transaction ceiling",
               "支付限额", "交易上限",
               "batas pembayaran", "plafon transaksi",
               "лимит платежа", "максимальная сумма"],
    "12.4.6": ["payment intermediary", "mandated intermediary", "payment gateway",
               "支付中介", "指定支付机构",
               "perantara pembayaran", "gateway pembayaran",
               "платежный посредник"],
    "12.4.7": ["payment restriction", "online payment restriction",
               "支付限制", "在线支付限制",
               "restriksi pembayaran",
               "ограничение платежа"],
    "12.5": ["de minimis", "customs threshold", "low value shipment", "duty exemption",
             "最低限度", "海关阈值", "小额免税",
             "de minimis", "ambang bea cukai", "pembebasan bea",
             "де minimis", "таможенный порог", "освобождение от пошлины",
             "การยกเว้นภาษีศุลกากร"],
    "12.6": ["customs duty electronic", "electronic transmission duty", "digital customs",
             "电子传输关税", "数字关税",
             "bea masuk elektronik", "transmisi elektronik",
             "таможенная пошлина на электронные передачи",
             "ภาษีศุลกากรสำหรับการส่งข้อมูลอิเล็กทรอนิกส์"],
    "12.7": ["domain name", "domain registration", "domain requirement",
             "域名", "域名注册",
             "nama domain", "pendaftaran domain",
             "доменное имя", "регистрация домена"],
    "12.8": ["local presence", "local establishment", "online service provider presence",
             "本地存在", "本地设立", "在线服务提供商",
             "kehadiran lokal", "pendirian lokal",
             "локальное присутствие", "местное учреждение",
             "การมีสถานประกอบการในประเทศ"],
}

# Fragments too generic to route on — they appear in nearly every statute.
_GENERIC_FRAGMENTS = {
    "measures", "measure", "requirements", "requirement", "restrictions",
    "restriction", "data", "services", "service", "other", "existence",
    "framework", "issues", "practice", "laws", "law", "related",
    "sectors", "sector", "products", "content",
}


def _phrases_from_category(category: str) -> list[str]:
    """Derive routing phrases from an indicator's official category text.

    Round 2 spans 61 indicators; hand-curating phrases for each is not
    sustainable, so non-curated indicators route on key fragments of their
    official RDTII category (e.g. "Foreign equity limits in e-commerce" ->
    ["foreign equity limits", "e-commerce"]). Curated _BASE_PHRASES always win.
    """

    text = category.split("\n")[0]  # exception notes live on later lines
    text = re.sub(r"\([^)]*\)", " ", text)
    fragments = re.split(
        r"[,;/]| including | such as | related to | relevant to | in | of | for | to | and | or ",
        text, flags=re.IGNORECASE,
    )
    out: list[str] = []
    for fragment in fragments:
        fragment = fragment.strip().lower().strip(" .-–")
        fragment = re.sub(r"^(the|a|an|any|lack of|absence of|existence of|minimum)\s+", "", fragment)
        if (
            4 <= len(fragment) <= 45
            and fragment not in _GENERIC_FRAGMENTS
            and not fragment.isdigit()
        ):
            out.append(fragment)
    return out[:6]


def _methodology_phrases() -> dict[str, list[str]]:
    try:
        from methodology import load_methodology
    except ImportError:  # pragma: no cover — methodology data not provisioned
        return {}
    return {
        iid: phrases
        for iid, rule in load_methodology().items()
        if (phrases := _phrases_from_category(rule.category))
    }


# Build expanded phrases at load time: curated phrases + jurisdiction synonyms,
# unioned with methodology-derived phrases (curated entries keep their hits and
# gain the official category wording; Round 2 indicators without curation get
# the derived phrases alone).
_INDICATOR_PHRASES = {
    k: expand_phrases(v) for k, v in _BASE_PHRASES.items()
}
for _iid, _derived in _methodology_phrases().items():
    _INDICATOR_PHRASES[_iid] = sorted(
        set(_INDICATOR_PHRASES.get(_iid, [])) | set(expand_phrases(_derived))
    )

# Statutes often express localization as a prohibition on offshore handling
# rather than using the concise labels in the RDTII taxonomy. First isolate each
# ``must not`` / ``shall not`` clause so a later positive ``must`` clause cannot
# inherit the earlier negation. ASCII-only boundaries intentionally allow forms
# such as ``规定must not ...`` while still rejecting English word continuations.
_NORMATIVE_PROHIBITION_CLAUSE = re.compile(
    r"(?<![A-Za-z0-9_])(?:must|shall)(?![A-Za-z0-9_])\s+not(?![A-Za-z0-9_])"
    r"(?:(?!(?<![A-Za-z0-9_])(?:must|shall)(?![A-Za-z0-9_])|[.。]).){0,260}",
    re.IGNORECASE | re.DOTALL,
)

_STRUCTURED_INDICATOR_PATTERNS = {
    "6.1": (
        re.compile(
            r"(?<![A-Za-z0-9_])"
            r"(?:process(?:ed|es|ing)?|handle(?:d|s|ing)?)"
            r"(?![A-Za-z0-9_])[^.。]{0,80}"
            r"(?<![A-Za-z0-9_])(?:outside|abroad|overseas)(?![A-Za-z0-9_])",
            re.IGNORECASE,
        ),
    ),
    "6.2": (
        re.compile(
            r"(?<![A-Za-z0-9_])"
            r"(?:hold(?:s|ing)?|held|store(?:d|s|ing)?|keep(?:s|ing)?|kept|"
            r"retain(?:ed|s|ing)?)"
            r"(?![A-Za-z0-9_])[^.。]{0,100}"
            r"(?<![A-Za-z0-9_])(?:outside|abroad|overseas)(?![A-Za-z0-9_])",
            re.IGNORECASE,
        ),
    ),
}

@dataclass(frozen=True)
class IndicatorCandidate:
    """Auditable shortlist evidence for one indicator.

    Keyword routing is recall-only: this score is never treated as mapping
    confidence.  Keeping the exact matched span/rule makes false-positive
    routing diagnosable without asking an LLM to explain itself afterwards.
    """

    indicator_id: str
    matched_span: str
    matched_rule: str
    retrieval_score: float


_SENTENCE_RE = re.compile(r"[^.!?。！？;；\n]+(?:[.!?。！？;；]|$)")


def _bounded_phrase_pattern(phrase: str) -> re.Pattern:
    """Compile an exact phrase with ASCII word boundaries where applicable."""
    escaped = re.escape(phrase)
    left = r"(?<![A-Za-z0-9_])" if phrase[:1].isascii() and phrase[:1].isalnum() else ""
    right = r"(?![A-Za-z0-9_])" if phrase[-1:].isascii() and phrase[-1:].isalnum() else ""
    return re.compile(left + escaped + right, re.IGNORECASE)


def _phrase_match(phrase: str, text: str) -> tuple[str, str, float] | None:
    """Return a local, boundary-aware match; never join words across sentences.

    Exact phrases are preferred.  A conservative proximity fallback handles
    harmless punctuation/word-order damage, but all words must occur in the
    same sentence and within a 120-character window.  The former implementation
    used ``all(word in whole_chunk)`` and therefore routed unrelated paragraphs.
    """
    phrase = phrase.strip()
    if not phrase:
        return None
    exact = _bounded_phrase_pattern(phrase).search(text)
    if exact:
        score = min(1.0, 0.55 + 0.04 * len(phrase.split()) + min(len(phrase), 40) / 200)
        return exact.group(0), f'exact phrase: "{phrase}"', round(score, 3)

    words = [word for word in re.findall(r"[A-Za-z0-9]+", phrase) if len(word) > 1]
    if len(words) < 2:
        return None
    patterns = [_bounded_phrase_pattern(word) for word in words]
    for sentence_match in _SENTENCE_RE.finditer(text):
        sentence = sentence_match.group(0)
        hits = [pattern.search(sentence) for pattern in patterns]
        if not all(hits):
            continue
        starts = [hit.start() for hit in hits if hit]
        ends = [hit.end() for hit in hits if hit]
        start, end = min(starts), max(ends)
        if end - start > 120:
            continue
        span = sentence[start:end]
        score = min(0.74, 0.42 + 0.05 * len(words))
        return span, f'same-sentence proximity: "{phrase}"', round(score, 3)
    return None


def classify_indicator_candidates(article_text: str) -> list[IndicatorCandidate]:
    """Return ranked, auditable recall candidates for an article/chunk."""
    if not article_text or not article_text.strip():
        return []

    best: dict[str, IndicatorCandidate] = {}
    for indicator, phrases in _INDICATOR_PHRASES.items():
        for phrase in phrases:
            match = _phrase_match(phrase, article_text)
            if not match:
                continue
            span, rule, score = match
            candidate = IndicatorCandidate(indicator, span, rule, score)
            if indicator not in best or candidate.retrieval_score > best[indicator].retrieval_score:
                best[indicator] = candidate

    for clause_match in _NORMATIVE_PROHIBITION_CLAUSE.finditer(article_text):
        clause = clause_match.group(0)
        for indicator, patterns in _STRUCTURED_INDICATOR_PATTERNS.items():
            if any(pattern.search(clause) for pattern in patterns):
                candidate = IndicatorCandidate(
                    indicator_id=indicator,
                    matched_span=clause,
                    matched_rule="structured normative prohibition",
                    retrieval_score=0.95,
                )
                if indicator not in best or candidate.retrieval_score > best[indicator].retrieval_score:
                    best[indicator] = candidate

    return sorted(best.values(), key=lambda item: (-item.retrieval_score, item.indicator_id))

def classify_indicator(article_text: str) -> list[str]:
    """Compatibility wrapper returning the historical sorted indicator IDs."""
    return sorted(candidate.indicator_id for candidate in classify_indicator_candidates(article_text))
