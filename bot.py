import asyncio
import hashlib
import html
import json
import os
import re
import sys
import time
from urllib.parse import quote_plus, unquote
import urllib.parse
import requests
from playwright.async_api import async_playwright
import product_intelligence as pi

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r", encoding="utf-8") as _ef:
        for _line in _ef:
            if "=" in _line and not _line.lstrip().startswith("#"):
                _k, _v = _line.strip().split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# إعدادات تليجرام (تُقرأ من ملف .env محلياً أو من GitHub Secrets سحابياً)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
MAIN_CHANNEL_ID = os.getenv("CHANNEL_CHAT_ID", "-1004497784406")
MAIN_CHANNEL_USERNAME = "@loqta78"
# ممكن تحط أكتر من ID مفصولين بفاصلة (مثلاً حسابك + القناة): "6725805788,-1004497784406"
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", MAIN_CHANNEL_ID)
CHAT_IDS = [c.strip() for c in CHAT_ID.split(",") if c.strip()]
# نضمن دائماً أن قناة «لقطة» (-1004497784406) موجودة دائماً في قائمة الوجهات الأساسية
if MAIN_CHANNEL_ID not in CHAT_IDS and MAIN_CHANNEL_USERNAME not in CHAT_IDS:
    CHAT_IDS.insert(0, MAIN_CHANNEL_ID)
# الـ Chat ID الخاص بصاحب البوت لاستقبال أي لينك في الخاص وتحويله لأفلييت القناة ونشره فوراً
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID", "6725805788"))
MIN_DISCOUNT = 30
MAX_PER_CYCLE = 20  # أقصى عدد عروض تتبعت لكل متجر في الدورة الواحدة
HASHTAG = "#عروض_لقطة"
# كود أفلييت أمازون مصر الخاص بالقناة (Tracking ID)
AMAZON_TAG = os.getenv("AMAZON_TAG", "anashesham-21")
# كود الخصم الخاص بالقناة على نون (يُفعّل بعد تحديد الأقسام المشمولة)
NOON_COUPON = os.getenv("NOON_COUPON", "")
HISTORY_DAYS = 90
# المدة بين كل فحص والتاني بالثواني (افتراضياً 3 دقايق - فترة العروض)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "180"))
# الفاصل الزمني بالثواني بين كل رسالة والتانية (20 ثانية، ما عدا عروض "ببلاش" تتبعت فوراً)
MESSAGE_DELAY = int(os.getenv("MESSAGE_DELAY", "20"))

SENT_DEALS_FILE = os.path.join(BASE_DIR, "sent_deals.txt")
HISTORY_FILE = os.path.join(BASE_DIR, "price_history.json")
LEARNED_FILE = os.path.join(BASE_DIR, "learned_preferences.json")
PENDING_DEALS_FILE = os.path.join(BASE_DIR, "pending_deals.json")

# أشهر البراندات والأقسام اللي عليها عروض قوية في مصر (بيتم فحصها واكتشاف عروضها المجمعة)
HOT_BRANDS = [
    ("أنكر (Anker)", ["شاحن انكر", "anker", "انكر", "أنكر", "باور بانك انكر"]),
    ("ساوند كور (Soundcore)", ["سماعة انكر ساوند كور", "soundcore", "ساوند كور", "سماعة ساوند كور"]),
    ("آي لوك (iLock)", ["مشترك اي لوك", "ilock", "i-lock", "اي لوك", "آي لوك", "اى لوك"]),
    ("UGREEN (يوغرين)", ["ugreen", "يوغرين", "يوجرين"]),
    ("أسوس (ASUS)", ["asus", "اسوس", "أسوس", "vivobook"]),
    ("لينوفو (Lenovo)", ["lenovo", "لينوفو", "ideapad", "thinkpad"]),
    ("تورنيدو (Tornado)", ["tornado", "تورنيدو"]),
    ("فريش (Fresh)", ["fresh", "فريش"]),
    ("فيليبس / براون", ["philips", "فيليبس", "braun", "براون"]),
    ("ميانتا / بلاك اند ديكر", ["mienta", "ميانتا", "black+decker", "بلاك اند ديكر"]),
    ("مولينكس / تيفال / كينوود", ["moulinex", "مولينكس", "tefal", "تيفال", "kenwood", "كينوود"]),
    ("أورايمو (Oraimo)", ["oraimo", "أورايمو", "اورايمو"]),
    ("بيسوس / جوي روم", ["baseus", "بيسوس", "joyroom", "جوي روم"]),
    ("شاومي (Xiaomi)", ["xiaomi", "شاومي", "redmi", "ريدمي"]),
    ("سامسونج (Samsung)", ["samsung", "سامسونج"]),
    ("Redragon (ريدراجون)", ["redragon", "ريدراجون", "ريد دراجون"]),
    ("لوجيتك (Logitech)", ["logitech", "لوجيتك"]),
    ("سوني / JBL", ["jbl", "جي بي ال", "sony", "سوني"]),
    ("فيتراك (Vitrac)", ["vitrac", "فيتراك"]),
    ("أبو عوف", ["ابو عوف", "أبو عوف", "abu auf"]),
    ("Fogg (فوج)", ["fogg", "فوج"]),
    ("نيفيا / لوريال", ["nivea", "نيفيا", "loreal", "l'oreal", "لوريال"]),
    ("أريال / برسيل", ["ariel", "اريال", "أريال", "ايريال", "persil", "برسيل"]),
    ("أديداس / نايكي", ["adidas", "اديداس", "أديداس", "nike", "نايكي"]),
    ("نسبرسو / نسكافيه", ["nespresso", "nescafe", "نسبرسو", "نسكافيه"]),
]

# أقسام بحث إضافية لعروض السماعات والمشتركات والأجهزة المنزلية والهاردوير في أمازون
AMAZON_CATEGORY_SEARCHES = [
    ("عروض سماعات أنكر وساوند كور", "https://www.amazon.eg/s?k=%D8%B3%D9%85%D8%A7%D8%B9%D8%A9+%D8%A7%D9%86%D9%83%D8%B1+soundcore"),
    ("عروض مشتركات آي لوك والكهرباء", "https://www.amazon.eg/s?k=%D9%85%D8%B4%D8%AA%D8%B1%D9%83+%D8%A7%D9%8A+%D9%84%D9%88%D9%83+ilock"),
    ("عروض القلايات وأجهزة المطبخ", "https://www.amazon.eg/s?k=%D9%82%D9%84%D8%A7%D9%8A%D8%A9+%D8%A8%D8%AF%D9%88%D9%86+%D8%B2%D9%8A%D8%AA+%D8%AE%D9%84%D8%A7%D8%B7+%D9%83%D8%A8%D8%A9"),
    ("عروض الأجهزة المنزلية والمكاوي", "https://www.amazon.eg/s?k=%D9%85%D9%83%D9%88%D8%A7%D8%A9+%D8%A8%D8%AE%D8%A7%D8%B1+%D9%85%D9%83%D9%86%D8%B3%D8%A9+%D8%BA%D9%84%D8%A7%D9%8A%D8%A9"),
    ("عروض الشواحن السريعة والباور بانك", "https://www.amazon.eg/s?k=%D8%B4%D8%A7%D8%AD%D9%86+%D8%B3%D8%B1%D9%8A%D8%B9+%D8%A8%D8%A7%D9%88%D8%B1+%D8%A8%D8%A7%D9%86%D9%83"),
    ("عروض السماعات والبلوتوث", "https://www.amazon.eg/s?k=%D8%B3%D9%85%D8%A7%D8%B9%D8%A9+%D8%A8%D9%84%D9%88%D8%AA%D9%88%D8%AB&rh=p_n_deal_type%3A26901043031"),
    ("عروض الهاردوير والكمبيوتر", "https://www.amazon.eg/s?k=%D9%83%D9%8A%D8%A8%D9%88%D8%B1%D8%AF+%D9%85%D9%8A%D9%83%D8%A7%D9%86%D9%8A%D9%83%D9%8A"),
    ("عروض ماكينات الحلاقة والعناية", "https://www.amazon.eg/s?k=%D9%85%D8%A7%D9%83%D9%8A%D9%86%D8%A9+%D8%AD%D9%84%D8%A7%D9%82%D8%A9+%D8%A8%D8%B1%D8%A7%D9%88%D9%86+%D9%81%D9%8A%D9%84%D9%8A%D8%A8%D8%B3"),
    ("عروض السوبرماركت وفلاش", "https://www.amazon.eg/s?k=%D8%B9%D8%B1%D9%88%D8%B6&i=grocery"),
    ("عروض الإلكترونيات اليومية", "https://www.amazon.eg/s?i=electronics&rh=p_n_deal_type%3A26901043031"),
    ("عروض المنزل والمطبخ اليومية", "https://www.amazon.eg/s?i=kitchen&rh=p_n_deal_type%3A26901043031"),
]
_brand_rot_idx = 0
_amz_cat_rot_idx = 0

# ---------------------------------------------------------------------------
# حفظ العروض المرسلة وسجل الأسعار
# ---------------------------------------------------------------------------
def short_link(link):
    """رابط قصير وثابت للمنتج (بيفضل شغال لما حد ينسخ الرسالة ويشيل أي كود أفلييت قديم)."""
    if not link:
        return link
    # 1. روابط أمازون العادية: /dp/ASIN أو /gp/product/ASIN أو /product/ASIN
    m = re.search(r'/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})', link, re.IGNORECASE)
    if m and ("amazon" in link.lower() or "amzn" in link.lower()):
        return f"https://www.amazon.eg/dp/{m.group(1).upper()}"
    # 2. روابط بحث وتجميعات أمازون المتضمنة لـ ASIN (مثل hidden-keywords=B0FQFKG4Y1|B0FQFNT8WR أو keywords=ASIN أو asins=ASIN)
    if "amazon" in link.lower() or "amzn" in link.lower():
        m_search = re.search(r'[?&](?:hidden-keywords|keywords|asins|asin|k)=([^&]+)', link, re.IGNORECASE)
        if m_search:
            asins = re.findall(r'([A-Z0-9]{10})', m_search.group(1), re.IGNORECASE)
            b_asins = [a for a in asins if a.upper().startswith("B")]
            best_asin = (b_asins[0] if b_asins else asins[0]) if asins else None
            if best_asin:
                return f"https://www.amazon.eg/dp/{best_asin.upper()}"
    m = re.search(r'/([A-Z0-9]{8,})/p/?', link, re.IGNORECASE)
    if m and "noon.com" in link.lower():
        return f"https://www.noon.com/egypt-ar/{m.group(1).upper()}/p/"
    return link

_branded_cache = {}

def add_affiliate_tag(url):
    """يضيف كود أفلييت أمازون مصر (Tracking ID) بنفس صيغة SiteStripe الرسمية تلقائياً."""
    if not url or not url.startswith("http"):
        return url
    if "amazon." in url and AMAZON_TAG:
        if "tag=" in url:
            return re.sub(r'tag=[^&#]+', f'tag={AMAZON_TAG}', url)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}linkCode=ll2&tag={AMAZON_TAG}&ref_=as_li_ss_tl"
    return url

def branded_url(url):
    """يضيف كود الأفلييت ثم يختصر الرابط باسم القناة (loqta) مثل https://is.gd/loqta_7f3a9c."""
    if not url or not url.startswith("http"):
        return url
    url = add_affiliate_tag(url)
    if url in _branded_cache:
        return _branded_cache[url]
    slug_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:6]
    custom_slug = f"loqta_{slug_hash}"
    try:
        r = requests.get(
            "https://is.gd/create.php",
            params={"format": "simple", "url": url, "shorturl": custom_slug},
            timeout=8,
        )
        if r.status_code == 200 and r.text.strip().startswith("http"):
            res = r.text.strip()
            _branded_cache[url] = res
            return res
        if "already exists" in r.text.lower():
            res = f"https://is.gd/{custom_slug}"
            _branded_cache[url] = res
            return res
    except Exception:
        pass
    return url

_COLOR_SIZE_RE = re.compile(
    r'\b(black|white|red|blue|green|yellow|grey|gray|beige|navy|pink|purple|brown|orange|silver|gold|'
    r'multicolour|multicolor|xxxl|xxl|xl|xs|small|medium|large|l|m|s|مقاس|'
    r'أسود|اسود|أبيض|ابيض|أحمر|احمر|أزرق|ازرق|أخضر|اخضر|أصفر|اصفر|رمادي|بيج|كحلي|وردي|بني|بنفسجي|فضي|ذهبي)\b',
    re.IGNORECASE,
)

def _normalize_ar(text):
    """توحيد الحروف العربية وإزالة التشكيل للمقارنة والبحث الدقيق."""
    if not text:
        return ""
    t = str(text).lower()
    t = re.sub(r'[أإآا]', 'ا', t)
    t = re.sub(r'[ةه]', 'ه', t)
    t = re.sub(r'[يى]', 'ي', t)
    t = re.sub(r'[\u064B-\u065F\u0640]', '', t)
    return t.strip()

def normalize_title_key(title):
    """ينظف اسم المنتج (مع تجاهل اللون والمقاس) لمنع تكرار نفس المنتج بألوان مختلفة."""
    if not title:
        return ""
    s = _COLOR_SIZE_RE.sub(" ", str(title).lower())
    s = re.sub(r'[^\w\u0600-\u06FF]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:65] if len(s) >= 12 else ""

sent_deals = set()
if os.path.exists(SENT_DEALS_FILE):
    with open(SENT_DEALS_FILE, "r", encoding="utf-8") as f:
        sent_deals = {short_link(line.strip()) for line in f if line.strip()}

price_history = {}
sent_title_prices = {}
if os.path.exists(HISTORY_FILE):
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for k, v in json.load(f).items():
                sk = short_link(k)
                price_history[sk] = v
                if sk in sent_deals and v.get("last_sent_price") is None and v.get("prices"):
                    v["last_sent_price"] = v["prices"][-1][1]
                    v["last_sent_at"] = v["prices"][-1][0]
                t_key = v.get("title_key")
                if t_key and v.get("last_sent_price"):
                    prev_tp = sent_title_prices.get(t_key)
                    if prev_tp is None or v["last_sent_price"] < prev_tp:
                        sent_title_prices[t_key] = v["last_sent_price"]
    except Exception:
        price_history = {}

def save_history():
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(price_history, f, ensure_ascii=False)

# ---------------------------------------------------------------------------
# ذاكرة التعلم الذاتي (تتعلم من الروابط المرسلة ومن القنوات المراقبة)
# ---------------------------------------------------------------------------
learned_prefs = {
    "brands": [],
    "queries": [],
    "channels": [],
    "seen_posts": [],
}
if os.path.exists(LEARNED_FILE):
    try:
        with open(LEARNED_FILE, "r", encoding="utf-8") as _lf:
            _loaded = json.load(_lf)
            for _k in learned_prefs:
                if isinstance(_loaded.get(_k), list):
                    learned_prefs[_k] = _loaded[_k]
    except Exception:
        pass

_learned_rot_idx = 0

def save_learned_prefs():
    try:
        with open(LEARNED_FILE, "w", encoding="utf-8") as f:
            json.dump(learned_prefs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"تعذر حفظ ملف التعلم الذاتي: {e}")

# ---------------------------------------------------------------------------
# العروض المعلقة المعروضة كأزرار تفاعلية للموافقة على النشر (Inline Buttons)
# ---------------------------------------------------------------------------
pending_deals = {}
if os.path.exists(PENDING_DEALS_FILE):
    try:
        with open(PENDING_DEALS_FILE, "r", encoding="utf-8") as _pf:
            pending_deals = json.load(_pf)
    except Exception:
        pending_deals = {}

def save_pending_deals():
    try:
        now_ts = time.time()
        expired = [k for k, v in pending_deals.items() if (now_ts - v.get("timestamp", 0)) > 86400]
        for k in expired:
            pending_deals.pop(k, None)
        with open(PENDING_DEALS_FILE, "w", encoding="utf-8") as _pf:
            json.dump(pending_deals, _pf, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"تعذر حفظ ملف العروض المعلقة: {e}")

_STOP_WORDS_LEARN = {
    "من", "في", "على", "مع", "إلى", "الى", "عن", "أو", "او", "حتى", "لكل", "كل",
    "جديد", "أصلي", "اصلي", "عرض", "خصم", "سعر", "مميز", "منتج", "أمازون", "نون",
    "مصر", "قطعة", "قطع", "عدد", "مقاس", "لون", "موديل", "رقم", "نوع", "حجم",
    "for", "with", "and", "the", "in", "to", "of", "by", "new", "pro", "max",
}

def learn_from_product(title, brand=None):
    """يتعلم الماركة ونوع المنتج من أي عرض يبعته صاحب البوت أو من القنوات المراقبة ليبحث عن عروض مشابهة تلقائياً."""
    changed = False
    b_en_norm = pi.normalize_brand_english(brand, title=title, allow_network=False) if (brand or title) else ""
    effective_brand = b_en_norm or (brand or "").strip()
    if effective_brand:
        b_clean = effective_brand.strip()
        b_low = b_clean.lower()
        if (
            len(b_clean) >= 2
            and len(b_clean) <= 30
            and b_low not in _GENERIC_BRAND_NAMES
            and "متجر" not in b_low
            and b_low not in [x.lower() for x in learned_prefs["brands"]]
        ):
            learned_prefs["brands"].append(b_clean)
            changed = True

    if title and not is_blocked_title(title):
        t_clean = _COLOR_SIZE_RE.sub(" ", str(title))
        t_clean = re.sub(r'[^\w\u0600-\u06FF\s]+', ' ', t_clean)
        words = [
            w for w in t_clean.split()
            if len(w) >= 3 and not w.isdigit() and w.lower() not in _STOP_WORDS_LEARN
        ]
        if len(words) >= 2:
            query = " ".join(words[:3]).strip()
            if brand and brand.lower() not in query.lower() and len(brand) <= 15:
                query = f"{query} {brand.strip()}"
            q_low = query.lower()
            if len(query) >= 6 and q_low not in [x.lower() for x in learned_prefs["queries"]]:
                learned_prefs["queries"].append(query)
                if len(learned_prefs["queries"]) > 80:
                    learned_prefs["queries"] = learned_prefs["queries"][-80:]
                changed = True

    if changed:
        save_learned_prefs()
        print(f"🧠 تعلم البوت اهتمام جديد: الماركة={brand or '-'} | بحث={learned_prefs['queries'][-1] if learned_prefs['queries'] else '-'}")

def should_send_deal(link, title, current_price, promo_sig=""):
    """
    يمنع تكرار إرسال العرض إلا في الحالات التالية:
    1) لو المنتج كان خلص/نفد من المخزون (Out of stock) في أمازون أو نون وتوفر من جديد (Back in Stock!).
    2) لو العرض خلص (سعره ارتفع) ثم رجع لخصم من جديد.
    3) لو السعر نزل أكثر بشكل ملحوظ (خصم إضافي 8%+ وبفرق 15 جنيه+).
    4) لو أضيف كود خصم جديد أو كود دمج برومو.
    5) لو مر أكثر من يومين على آخر نشر والعرض ما زال سارياً ومميزاً.
    """
    if current_price is None:
        return False, None
    entry = price_history.get(link, {})
    last_p = entry.get("last_sent_price")
    last_at = entry.get("last_sent_at") or 0
    last_promo = entry.get("last_sent_promo") or ""
    now = time.time()

    if link in sent_deals:
        if last_p is None:
            return False, None

        # 1) لو العرض كان خلص/نفد من المتجر ورجع توفر من جديد (Back in Stock!)
        if entry.get("was_out_of_stock"):
            entry["was_out_of_stock"] = False
            save_history()
            return True, "🔄 رجع توفر من جديد في المتجر بعد نفاد الكمية! (Back in Stock)"

        # 2) لو سجل الأسعار يوضح أن المنتج كان غير متوفر أو مسجل كنفاد بعد تاريخ آخر إرسال
        prices_after = [p for p in entry.get("prices", []) if p[0] > last_at]
        if any(p[1] is None or p[1] <= 0 for p in prices_after):
            return True, "🔄 رجع توفر من جديد في المتجر بعد نفاد الكمية! (Back in Stock)"

        # 3) السعر نزل أكتر بشكل ملحوظ (على الأقل 8% وبفرق 15 جنيه أو أكتر)
        if current_price <= last_p * 0.92 and (last_p - current_price) >= 15:
            return True, "🔥 تحديث عرض (السعر نزل أكتر!)"

        # 4) العرض كان خلص (السعر طلع فوق سعر العرض بـ 15%+) وبعدين رجع تاني لعرض خصم
        if any(p[1] is not None and p[1] >= last_p * 1.15 for p in prices_after) and current_price <= last_p * 1.02:
            return True, "🔄 العرض رجع تاني بعد ما خلص!"

        # 5) اتضاف كود خصم أو خصم Checkout جديد مكنش موجود وقت الإرسال الأول
        if promo_sig and promo_sig != last_promo:
            return True, "🔥 تحديث عرض (تم إضافة خصم/كوبون جديد!)"

        # 6) لو مر أكثر من يومين على آخر نشر والعرض ما زال سارياً ومميزاً
        if (now - last_at) > (86400 * 2):
            return True, "🔄 تجديد عرض مميز ومستمر في المتجر"

        return False, None

    # لو الرابط جديد بس نفس المنتج بالظبط (لون تاني أو بائع تاني) اتبعت قبل كده بنفس السعر
    t_key = normalize_title_key(title)
    if t_key and t_key in sent_title_prices:
        prev_tp = sent_title_prices[t_key]
        if current_price > prev_tp * 0.90:
            return False, None

    return True, None

def mark_deal_sent(link, title=None, effective_price=None, promo_sig=""):
    now = time.time()
    if link not in sent_deals:
        sent_deals.add(link)
        with open(SENT_DEALS_FILE, "a", encoding="utf-8") as f:
            f.write(link + "\n")
    entry = price_history.setdefault(link, {"prices": [], "last_sent": None})
    entry["last_sent"] = now
    entry["last_sent_at"] = now
    if effective_price is not None:
        entry["last_sent_price"] = effective_price
    entry["last_sent_promo"] = promo_sig or ""
    t_key = normalize_title_key(title)
    if t_key:
        entry["title_key"] = t_key
        if effective_price is not None:
            prev_tp = sent_title_prices.get(t_key)
            if prev_tp is None or effective_price < prev_tp:
                sent_title_prices[t_key] = effective_price
    save_history()

def record_price(link, price):
    """يسجّل السعر الحالي ويرجع (أقل سعر سابق، أعلى سعر، أقل سعر) خلال آخر 90 يوم."""
    now = time.time()
    entry = price_history.setdefault(link, {"prices": [], "last_sent": None})
    cutoff = now - HISTORY_DAYS * 86400
    # تنظيف أي أسعار خاطئة قديمة (أقل من 10 جنيه لمنتج سعره فوق 50 جنيه)
    entry["prices"] = [
        p for p in entry["prices"]
        if p[0] >= cutoff and not (price >= 50 and p[1] < 10)
    ]
    prev_min = min((p[1] for p in entry["prices"]), default=None)
    entry["prices"].append([now, price])
    all_prices = [p[1] for p in entry["prices"]]
    save_history()
    return prev_min, max(all_prices), min(all_prices)

def is_deal_already_sent(link, title=None, current_price=None, promo_sig=""):
    """يرجع True إذا كان العرض مرسلاً سابقاً بنفس السعر والمواصفات بدون تغيير جديد يبرر إعادة النشر."""
    should_send, _ = should_send_deal(link, title, current_price, promo_sig)
    return not should_send

# ---------------------------------------------------------------------------
# أدوات مساعدة وذكاء العروض
# ---------------------------------------------------------------------------
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٬٫", "0123456789,.")

def clean(text):
    s = (text or "").translate(_AR_DIGITS)
    return re.sub(r'[\u200e\u200f\xa0\u2009\u202f]', ' ', s)

def to_float(s):
    try:
        return float(clean(s).replace(',', '').strip())
    except Exception:
        return None

def fmt(n):
    if n is None:
        return "-"
    return f"{n:,.2f}".rstrip('0').rstrip('.') if n != int(n) else f"{int(n):,}"

def is_blocked_title(text):
    t = (text or "").lower()
    return any(s in t for s in ("access denied", "robot check", "captcha", "verify you are human",
                                 "sorry", "something went wrong", "حصل خطأ", "page not found"))

def is_almost_free(price, list_price, badge_discount=None):
    """يكتشف العروض الحقيقية اللي تعتبر ببلاش (لما السعر الفعلي يكون نزل من 300+ لتحت 100 ونسبة الخصم متطابقة)."""
    if price is None or price < 10 or not list_price or list_price <= price:
        return False
    calc_disc = (1 - price / list_price) * 100
    if badge_discount is not None and abs(calc_disc - badge_discount) > 12:
        return False
    if list_price >= 300 and price < 100 and calc_disc >= 68:
        return True
    if list_price >= 150 and price <= 25 and calc_disc >= 80:
        return True
    return False

def detect_brand(title):
    if not title:
        return None
    b_en = pi.normalize_brand_english("", title=title, allow_network=False)
    if b_en:
        return b_en
    t_words = (title or "").lower().split()[:5]
    t_head = " ".join(t_words)
    t_head_norm = _normalize_ar(t_head)
    for label, keywords in HOT_BRANDS:
        for k in keywords:
            k_low = k.lower()
            k_norm = _normalize_ar(k_low)
            if re.search(r'\b' + re.escape(k_low) + r'\b', t_head) or re.search(r'\b' + re.escape(k_norm) + r'\b', t_head_norm):
                return pi.normalize_brand_english(label, allow_network=False) or label
    return None

def parse_reviews_count(reviews_str):
    if not reviews_str:
        return 0
    s = clean(str(reviews_str)).upper().replace(',', '')
    m = re.search(r'(\d+(?:\.\d+)?)', s)
    if not m:
        return 0
    val = float(m.group(1))
    if "ألف" in s or "K" in s:
        val *= 1000
    return int(val)

_GENERIC_BRAND_NAMES = {
    "generic", "عام", "أخرى", "اخرى", "other", "others", "no brand", "unbranded",
    "بدون ماركة", "بدون علامة تجارية", "غير محدد", "n/a", "oem", "none", "unknown",
    "جينيريك", "جينريك",
}

TRUSTED_BRAND_KEYWORDS = (
    # تقنية، هاردوير، شواحن، مشتركات، إلكترونيات، موبايلات
    "ugreen", "يوغرين", "يوجرين", "anker", "أنكر", "انكر", "soundcore", "ساوند كور", "eufy", "يوفي",
    "ilock", "i-lock", "آي لوك", "اي لوك", "اى لوك", "ldnio", "لدنيو", "ال دي نيو",
    "redragon", "ريدراجون", "ريد دراجون", "logitech", "لوجيتك", "razer", "ريزر", "hyperx", "هايبر اكس",
    "fantech", "فانتك", "baseus", "بيسوس", "joyroom", "جوي روم", "oraimo", "أورايمو", "اورايمو",
    "xiaomi", "شاومي", "redmi", "ريدمي", "poco", "بوكو", "samsung", "سامسونج", "apple", "أبل", "ابل",
    "huawei", "هواوي", "honor", "هونر", "realme", "ريلمي", "oppo", "أوبو", "اوبو", "vivo", "فيفو",
    "infinix", "انفينكس", "tecno", "تكنو", "nokia", "نوكيا", "motorola", "موتورولا",
    "sony", "سوني", "jbl", "جي بي ال", "bose", "بوز", "sennheiser", "سنهايزر", "edifier", "إديفاير",
    "tp-link", "تي بي لينك", "tapo", "تابو", "d-link", "دي لينك", "ezviz", "hikvision", "هيكفيجن",
    "sandisk", "سانديسك", "kingston", "كينجستون", "lexar", "ليكسر", "wd", "western digital", "seagate", "crucial",
    "hp", "اتش بي", "dell", "ديل", "lenovo", "لينوفو", "asus", "أسوس", "اسوس", "acer", "أيسر", "msi", "gigabyte",
    "hollyland", "fujifilm", "instax", "canon", "كانون", "nikon", "نيكون", "epson", "إبسون", "casio", "كاسيو",
    "energizer", "انرجايزر", "duracell", "دوراسيل", "hama", "هاما", "belkin", "بيلكن", "promate", "بروميت",
    # أجهزة منزلية ومطبخ وعدة وعناية شخصية
    "tornado", "تورنيدو", "fresh", "فريش", "sharp", "شارب", "panasonic", "باناسونيك", "philips", "فيليبس",
    "braun", "براون", "kenwood", "كينوود", "moulinex", "مولينكس", "tefal", "تيفال", "delonghi", "ديلونجي",
    "mienta", "ميانتا", "مينتا", "nespresso", "نسبرسو", "نسبريسو", "black+decker", "black & decker", "بلاك اند ديكر", "بلاك + ديكر",
    "bosch", "بوش", "beko", "بيكو", "lg", "ال جي", "إل جي", "toshiba", "توشيبا", "midea", "ميديا", "carrier", "كاريير",
    "unionaire", "يونيون إير", "ariston", "أريستون", "اريستون", "olympic", "أوليمبيك", "اوليمبيك",
    "zanussi", "زانوسي", "hoover", "هوفر", "karcher", "كارشر", "vileda", "فيليدا", "tank", "تانك",
    "total", "توتال", "ingco", "انجكو", "إنجكو", "luminarc", "لومينارك", "pasabahce", "pyrex", "بايركس",
    "nouval", "نوفال", "zahran", "زهران", "sokany", "سوكاني", "sonai", "سوناي", "raf", "راف",
    "rush brush", "راش براش", "babyliss", "بيبي ليس", "kemei", "كيمي", "vgr", "في جي ار", "klug", "كلوج",
    # سوبرماركت وعناية شخصية وملابس
    "vitrac", "فيتراك", "abu auf", "أبو عوف", "ابو عوف", "nescafe", "نسكافيه", "lipton", "ليبتون",
    "ahmad tea", "أحمد تي", "rich mix", "ريتش ميكس", "gullon", "جولون", "ariel", "أريال", "اريال", "ايريال",
    "persil", "برسيل", "downy", "داوني", "tide", "تايد", "pril", "بريل", "finish", "فينيش",
    "dettol", "ديتول", "clorox", "كلوركس", "harpic", "هاربيك", "vanish", "فانيش", "glade", "جليد",
    "nivea", "نيفيا", "loreal", "l'oreal", "لوريال", "garnier", "غارنييه", "جارنييه", "dove", "دوف",
    "axe", "أكس", "rexona", "ريكسونا", "fogg", "فوج", "bioderma", "بيوديرما", "بايوديرما",
    "la roche", "لاروش", "vichy", "فيتشي", "فيشي", "cerave", "سيرافي", "cetaphil", "سيتافيل",
    "eva", "إيفا", "ايفا", "beesline", "بيزلين", "bobai", "بوباى", "pantene", "بانتين",
    "head & shoulders", "هيد اند شولدرز", "tresemme", "تريسمي", "sunsilk", "صانسيلك", "clear", "كلير",
    "gillette", "جيليت", "oral-b", "أورال بي", "sensodyne", "سنسوداين", "signal", "سيجنال", "listerine", "ليسترين",
    "johnson", "جونسون", "pampers", "بامبرز", "molfix", "مولفيكس", "babyjoy", "بيبي جوي",
    "sanosan", "سانوسان", "penduline", "بندولين", "vatika", "فاتيكا", "karseell", "كارسيل", "maybelline", "ميبيلين",
    "adidas", "أديداس", "اديداس", "nike", "نايكي", "نايك", "puma", "بوما", "reebok", "ريبوك",
    "skechers", "سكيتشرز", "defacto", "ديفاكتو", "lc waikiki", "ال سي وايكيكي", "cottonil", "قطونيل",
    "dice", "دايس", "naviforce", "نافي فورس", "lacoste", "لاكوست", "ray-ban", "راي بان",
)

def has_famous_brand(title, brand=None):
    """يتحقق مما إذا كان المنتج ينتمي لبراند معروف ومشهور (أو براند اتعلمه البوت من اختياراتك)."""
    combined = f"{(brand or '').strip().lower()} {(title or '').lower()}"
    if any(kw in combined for kw in TRUSTED_BRAND_KEYWORDS):
        return True
    return any(lb.lower() in combined for lb in learned_prefs.get("brands", []) if len(lb) >= 2)

def is_deal_currently_active(
    price, list_price, discount, is_available=True,
    stack_promos=None, extra_pct=0, extra_egp=0,
    brand=None, title="", prev_min=None,
    is_user_submission=False
):
    """
    يتحقق بدقة أن العرض ما زال سارياً ومتاحاً للشراء في المتجر وليس منتهياً أو نافداً:
    1) أن المنتج متوفر في المخزون (غير نافد أو غير متاح).
    2) أن السعر الحالي موجود ومسحوب مباشرة من المتجر أو من تفاصيل العرض.
    3) أن هناك خصم حقيقي ساري أو أن المستخدم اختار العرض بنفسه.
    """
    # 1) لو الرابط مرسل يدوياً من المستخدم في الشات الخاص:
    # نقبله فوراً وننشره طالما له سعر متاح (> 0)، لأن المستخدم اختاره بنفسه من مصر
    # ولا نسمح لقيود شحن السيرفرات السحابية برفضه!
    if is_user_submission:
        if price and price > 0:
            if stack_promos or (extra_pct and extra_pct > 0) or (extra_egp and extra_egp > 0):
                return True, "العرض ساري مع كود خصم/كوبون إضافي"
            if discount and discount > 0:
                return True, f"العرض ساري بخصم {discount:.0f}%"
            if list_price and price and (list_price - price) > 0:
                return True, f"العرض ساري بتوفير {list_price - price:.0f} ج.م"
            return True, "العرض متاح للشراء بسعر مميز بناءً على اختيارك"
        return False, "السعر غير متاح على صفحة المتجر أو تم إيقاف البيع"

    if not is_available:
        return False, "المنتج غير متوفر في المخزون (Out of Stock / نفد من المتجر)"
    if price is None or price <= 0:
        return False, "السعر غير متاح على صفحة المتجر أو تم إيقاف البيع"

    has_promos = bool(stack_promos) or (extra_pct and extra_pct > 0) or (extra_egp and extra_egp > 0)
    is_famous = has_famous_brand(title, brand)

    # 2) لو عليه كوبون أو كود خصم أو برومو نشط
    if has_promos:
        return True, "العرض ساري مع كود خصم/كوبون إضافي"

    # 3) لو فيه نسبة خصم سارية ومسجلة على المتجر
    min_disc = 8.0 if is_famous else 10.0
    if discount and discount >= min_disc:
        return True, f"العرض ساري بخصم {discount:.0f}%"

    # 4) لو فرق السعر القديم والجديد ملحوظ (15 جنيه للبراندات المشهورة أو 25 جنيه عام)
    min_diff = 15 if is_famous else 25
    if list_price and price and (list_price - price) >= min_diff:
        return True, f"العرض ساري بفرق سعر {list_price - price:.0f} ج.م"

    # 5) لو السعر الحالي عند أو أقل من أقل سعر تاريخي مسجل
    if prev_min and price <= prev_min * 1.02:
        return True, "العرض ساري عند أقل سعر تاريخي مسجل للمنتج"

    # 6) لو العرض من قناة تليجرام متابعة وله أي نسبة خصم إيجابية
    if discount and discount >= 5.0:
        return True, f"العرض ساري بخصم {discount:.0f}%"

    return False, "العرض انتهى على المتجر ورجع للسعر الأصلي بدون خصم كافي"

def is_trusted_product(title, brand=None, rating=None, reviews=None):
    """
    يفلتر المنتجات بذكاء:
    1) لو المنتج من براند مشهور ومعروف (مثل أنكر، آي لوك، تورنيدو، فريش، فيليبس، براون، شاومي، سامسونج، يوغرين...):
       يُقبل فوراً طالما تقييمه مش ضعيف (أعلى من أو يساوي 3.8 أو لو كارت العرض في أمازون مظهّرش التقييم).
    2) لو البراند مش من القائمة المشهورة:
       يُرفض لو مكتوب Generic/عام، ولازم يكون عليه تقييم فعلي قوي (>= 4.1) من 10 مشترين على الأقل.
    """
    r_val = to_float(rating) if rating else None
    r_cnt = parse_reviews_count(reviews)
    b_clean = (brand or "").strip().lower()

    # أي منتج تقييمه ضعيف فعلياً (< 3.8) يترفض دائماً
    if r_val is not None and r_val < 3.8:
        return False

    # 1) لو براند معروف ومشهور في مصر -> نقبله فوراً
    if has_famous_brand(title, brand):
        return True

    # 2) رفض أي منتج بدون ماركة (Generic / عام)
    if b_clean in _GENERIC_BRAND_NAMES:
        return False

    # 3) لو ماركة تانية غير مشهورة، لازم تقييم عالي (>= 4.1) وعدد تقييمات كافي (>= 10)
    if r_val is not None and r_val >= 4.1 and r_cnt >= 10:
        if b_clean and len(b_clean) >= 2 and b_clean not in _GENERIC_BRAND_NAMES:
            return True

    return False

def clean_image_url(url):
    """ينظف رابط الصورة (خصوصاً نون وأمازون) عشان تليجرام يقبلها كصورة JPG عالية الجودة."""
    if not url or not isinstance(url, str):
        return None
    u = url.strip()
    if not u.startswith("http"):
        return None
    if "nooncdn.com/" in u:
        u = u.split("?")[0]
    if "media-amazon.com/images/I/" in u:
        u = re.sub(r'\._AC_[A-Z0-9,_]+_\.', '._AC_SL1000_.', u)
    return u

BILINGUAL_BRANDS = {
    "انكر": ("أنكر", "Anker"), "أنكر": ("أنكر", "Anker"), "anker": ("أنكر", "Anker"),
    "soundcore": ("ساوند كور", "Soundcore"), "ساوند كور": ("ساوند كور", "Soundcore"), "ساوندكور": ("ساوند كور", "Soundcore"),
    "eufy": ("يوفي", "Eufy"), "يوفي": ("يوفي", "Eufy"),
    "اي لوك": ("آي لوك", "iLock"), "آي لوك": ("آي لوك", "iLock"), "ilock": ("آي لوك", "iLock"), "i-lock": ("آي لوك", "iLock"),
    "يوجرين": ("يوغرين", "UGREEN"), "يوغرين": ("يوغرين", "UGREEN"), "ugreen": ("يوغرين", "UGREEN"),
    "شاومي": ("شاومي", "Xiaomi"), "xiaomi": ("شاومي", "Xiaomi"), "redmi": ("ريدمي", "Redmi"), "ريدمي": ("ريدمي", "Redmi"),
    "poco": ("بوكو", "POCO"), "بوكو": ("بوكو", "POCO"),
    "سامسونج": ("سامسونج", "Samsung"), "samsung": ("سامسونج", "Samsung"),
    "ابل": ("أبل", "Apple"), "أبل": ("أبل", "Apple"), "apple": ("أبل", "Apple"),
    "تورنيدو": ("تورنيدو", "Tornado"), "tornado": ("تورنيدو", "Tornado"),
    "سنوز": ("سنوز", "Snooze"), "snooze": ("سنوز", "Snooze"),
    "اديداس": ("أديداس", "Adidas"), "أديداس": ("أديداس", "Adidas"), "adidas": ("أديداس", "Adidas"),
    "نايكي": ("نايكي", "Nike"), "نايك": ("نايكي", "Nike"), "nike": ("نايكي", "Nike"),
    "بوما": ("بوما", "Puma"), "puma": ("بوما", "Puma"),
    "ريبوك": ("ريبوك", "Reebok"), "reebok": ("ريبوك", "Reebok"),
    "سكيتشرز": ("سكيتشرز", "Skechers"), "skechers": ("سكيتشرز", "Skechers"),
    "سوكاني": ("سوكاني", "Sokany"), "sokany": ("سوكاني", "Sokany"),
    "فريش": ("فريش", "Fresh"), "fresh": ("فريش", "Fresh"),
    "فيليبس": ("فيليبس", "Philips"), "philips": ("فيليبس", "Philips"),
    "براون": ("براون", "Braun"), "braun": ("براون", "Braun"),
    "بيسوس": ("بيسوس", "Baseus"), "baseus": ("بيسوس", "Baseus"),
    "جوي روم": ("جوي روم", "Joyroom"), "joyroom": ("جوي روم", "Joyroom"),
    "اورايمو": ("أورايمو", "Oraimo"), "أورايمو": ("أورايمو", "Oraimo"), "oraimo": ("أورايمو", "Oraimo"),
    "لدنيو": ("لدنيو", "LDNIO"), "ldnio": ("لدنيو", "LDNIO"),
    "سوني": ("سوني", "Sony"), "sony": ("سوني", "Sony"),
    "جي بي ال": ("جي بي إل", "JBL"), "جي بي إل": ("جي بي إل", "JBL"), "jbl": ("جي بي إل", "JBL"),
    "بوز": ("بوز", "Bose"), "bose": ("بوز", "Bose"),
    "ديل": ("ديل", "Dell"), "dell": ("ديل", "Dell"),
    "اتش بي": ("إتش بي", "HP"), "إتش بي": ("إتش بي", "HP"), "hp": ("إتش بي", "HP"),
    "لينوفو": ("لينوفو", "Lenovo"), "lenovo": ("لينوفو", "Lenovo"),
    "اسوس": ("أسوس", "ASUS"), "أسوس": ("أسوس", "ASUS"), "asus": ("أسوس", "ASUS"),
    "راش براش": ("راش براش", "Rush Brush"), "rush brush": ("راش براش", "Rush Brush"),
    "بيبي ليس": ("بيبي ليس", "BaByliss"), "babyliss": ("بيبي ليس", "BaByliss"),
    "كيمي": ("كيمي", "Kemei"), "kemei": ("كيمي", "Kemei"),
    "في جي ار": ("في جي آر", "VGR"), "vgr": ("في جي آر", "VGR"),
    "apt": ("APT", "APT"),
    "توتال": ("توتال", "Total"), "total": ("توتال", "Total"),
    "انجكو": ("إنجكو", "Ingco"), "إنجكو": ("إنجكو", "Ingco"), "ingco": ("إنجكو", "Ingco"),
    "كينوود": ("كينوود", "Kenwood"), "kenwood": ("كينوود", "Kenwood"),
    "مولينكس": ("مولينكس", "Moulinex"), "moulinex": ("مولينكس", "Moulinex"),
    "تيفال": ("تيفال", "Tefal"), "tefal": ("تيفال", "Tefal"),
    "ديلونجي": ("ديلونجي", "DeLonghi"), "delonghi": ("ديلونجي", "DeLonghi"),
    "ميانتا": ("ميانتا", "Mienta"), "mienta": ("ميانتا", "Mienta"),
    "شارب": ("شارب", "Sharp"), "sharp": ("شارب", "Sharp"),
    "توشيبا": ("توشيبا", "Toshiba"), "toshiba": ("توشيبا", "Toshiba"),
    "ال جي": ("إل جي", "LG"), "إل جي": ("إل جي", "LG"), "lg": ("إل جي", "LG"),
    "بوش": ("بوش", "Bosch"), "bosch": ("بوش", "Bosch"),
    "بيكو": ("بيكو", "Beko"), "beko": ("بيكو", "Beko"),
    "ريدراجون": ("ريدراجون", "Redragon"), "redragon": ("ريدراجون", "Redragon"),
    "لوجيتك": ("لوجيتك", "Logitech"), "logitech": ("لوجيتك", "Logitech"),
    "ريزر": ("ريزر", "Razer"), "razer": ("ريزر", "Razer"),
    "هواوي": ("هواوي", "Huawei"), "huawei": ("هواوي", "Huawei"),
    "هونر": ("هونر", "Honor"), "honor": ("هونر", "Honor"),
    "ريلمي": ("ريلمي", "Realme"), "realme": ("ريلمي", "Realme"),
    "اوبو": ("أوبو", "OPPO"), "أوبو": ("أوبو", "OPPO"), "oppo": ("أوبو", "OPPO"),
    "انفينكس": ("إنفينيكس", "Infinix"), "infinix": ("إنفينيكس", "Infinix"),
    "كاماي": ("كاماي", "Camay"), "camay": ("كاماي", "Camay"),
    "نيفيا": ("نيفيا", "Nivea"), "nivea": ("نيفيا", "Nivea"),
    "لوريال": ("لوريال", "L'Oreal"), "loreal": ("لوريال", "L'Oreal"),
    "غارنييه": ("غارنييه", "Garnier"), "garnier": ("غارنييه", "Garnier"),
    "دوف": ("دوف", "Dove"), "dove": ("دوف", "Dove"),
    "سيرافي": ("سيرافي", "CeraVe"), "cerave": ("سيرافي", "CeraVe"),
    "لاروش": ("لا روش بوزيه", "La Roche-Posay"), "la roche": ("لا روش بوزيه", "La Roche-Posay"),
    "فيتراك": ("فيتراك", "Vitrac"), "vitrac": ("فيتراك", "Vitrac"),
    "ابو عوف": ("أبو عوف", "Abu Auf"), "أبو عوف": ("أبو عوف", "Abu Auf"), "abu auf": ("أبو عوف", "Abu Auf"),
    "نسكافيه": ("نسكافيه", "Nescafe"), "nescafe": ("نسكافيه", "Nescafe"),
    "تيكزون": ("تيكزون", "Techzone"), "techzone": ("تيكزون", "Techzone"),
    "نيمبوت": ("نيمبوت", "Niimbot"), "niimbot": ("نيمبوت", "Niimbot"),
    "jepeerbz": ("جيبيربز", "JEPEErbz"), "جيبيربز": ("جيبيربز", "JEPEErbz"),
}

def _norm_ar_brand(text):
    """توحيد وتبسيط اسم الماركة بالعربي والإنجليزي للمقارنة والمطابقة الدقيقة."""
    if not text:
        return ""
    t = str(text).lower()
    t = re.sub(r'[أإآا]', 'ا', t)
    t = re.sub(r'[ةه]', 'ه', t)
    t = re.sub(r'[يى]', 'ي', t)
    t = re.sub(r'[\u064B-\u065F\u0640]', '', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

_NORM_BILINGUAL_BRANDS = {}
for _k, _v in BILINGUAL_BRANDS.items():
    _NORM_BILINGUAL_BRANDS[_norm_ar_brand(_k)] = _v
    _NORM_BILINGUAL_BRANDS[_k.lower().strip()] = _v

BILINGUAL_CATEGORIES = [
    # 1. كروت التسجيل والكابتشر كارد
    (r'كابتشر\s*كارد|كرت\s*تسجيل|video\s*capture|capture\s*card', 'كابتشر كارد', 'Video Capture Card'),

    # 2. الطابعات الحرارية والمحمولة
    (r'طابعة\s*(?:حرارية|صغيرة|ملصقات|محمولة|جيب)?|mini\s*printer|thermal\s*printer|label\s*(?:maker|printer)|printer\b', 'طابعة حرارية محمولة', 'Mini Thermal Portable Printer'),

    # 3. إكسسوارات الكمبيوتر واللابتوب (يجب فحصها قبل أجهزة اللابتوب والكمبيوتر حتى لا يُصنف الماوس أو الشنطة كلابتوب)
    (r'ماوس\s*باد|بساط\s*(?:ماوس|فأرة)|mouse\s*pad', 'ماوس باد', 'Mouse Pad'),
    (r'ماوس\s*(?:ألعاب|العاب|جيمنج)|فأرة\s*(?:ألعاب|العاب)|gaming\s*mouse', 'ماوس ألعاب', 'Gaming Mouse'),
    (r'ماوس|فأرة|mouse\b', 'ماوس كمبيوتر', 'Computer Mouse'),
    (r'كيبورد\s*(?:ألعاب|العاب|جيمنج|ميكانيك|ميكانيكي)|لوحة\s*مفاتيح\s*(?:ألعاب|العاب)|gaming\s*keyboard|mechanical\s*keyboard', 'كيبورد ألعاب ميكانيكي', 'Gaming Keyboard'),
    (r'كيبورد|لوحة\s*مفاتيح|keyboard\b', 'لوحة مفاتيح', 'Keyboard'),
    (r'شنطة\s*لابتوب|حقيبة\s*لابتوب|جراب\s*لابتوب|laptop\s*(?:bag|backpack|sleeve|case)', 'حقيبة لابتوب', 'Laptop Backpack & Bag'),
    (r'قاعدة\s*تبريد\s*لابتوب|مروحة\s*تبريد\s*لابتوب|cooling\s*pad|laptop\s*cooler', 'قاعدة تبريد لابتوب', 'Laptop Cooling Pad'),
    (r'حامل\s*لابتوب|ستاند\s*لابتوب|laptop\s*stand', 'حامل لابتوب مريح', 'Laptop Stand Holder'),

    # 4. إكسسوارات وملحقات الموبايل والتابلت (يجب فحصها قبل الهواتف والتابلت حتى لا يُصنف الشاحن أو الكابل كجهاز موبايل أو تابلت)
    (r'باور\s*بانك|شاحن\s*متنقل|بطارية\s*متنقلة|شاحن\s*محمول|power\s*bank|portable\s*charger', 'باور بانك', 'Power Bank'),
    (r'لاصقة\s*حماية|سكرين\s*بروتكتور|شاشة\s*حماية|حامي\s*شاشة|screen\s*protector|tempered\s*glass', 'لاصقة حماية شاشة', 'Screen Protector Glass'),
    (r'جراب|كفر|غطاء\s*حماية|حافظة|phone\s*case|tablet\s*case|protective\s*case|case\s*cover', 'جراب حماية', 'Protective Case'),
    (r'شاحن\s*سيارة|car\s*charger', 'شاحن سيارة سريع', 'Fast Car Charger'),
    (r'شاحن\s*لاسلكي|wireless\s*charger', 'شاحن لاسلكي', 'Wireless Charger'),
    (r'شاحن\s*(?:حائط|جداري|سريع|منزلي|مكتبي|راس|رأس)?|راس\s*شاحن|رأس\s*شاحن|مهايئ\s*شحن|wall\s*charger|fast\s*charger|charger\b|adapter\b', 'شاحن سريع', 'Fast Charger'),
    (r'كابل\s*شحن|سلك\s*شحن|وصلة\s*شحن|charging\s*cable|usb\s*cable|كابل\b|سلك\b|cable\b', 'كابل شحن سريع', 'Fast Charging Cable'),
    (r'مشترك\s*كهربائ?ي?|مشترك|power\s*strip', 'مشترك كهربائي', 'Power Strip'),
    (r'ستاند|حامل\s*(?:موبايل|هاتف|شاشة|تابلت)|stand\b|holder\b', 'حامل ستاند مريح', 'Adjustable Stand Holder'),

    # 5. أجهزة اللابتوب والكمبيوتر المحمول
    (r'لابتوب|حاسوب\s*محمول|كمبيوتر\s*محمول|laptop\b|notebook\b|vivobook\b|zenbook\b|ideapad\b|thinkpad\b|legion\b|macbook\b', 'لابتوب', 'Laptop'),

    # 6. أجهزة التابلت واللوحي
    (r'\b(?:تابلت|جهاز\s*لوحي|ipad|tablet|galaxy\s*tab)\b', 'تابلت ذكي', 'Smart Tablet'),

    # 7. الشاشات والتلفزيونات
    (r'(?:^|[^\w])(?:شاشة\s*(?:كمبيوتر|ألعاب|تلفزيون|عرض|سمارت|ذكية)|تلفزيون|تلفاز|smart\s*tv|tv\b|monitor\b)', 'شاشة ذكية', 'Smart TV & Monitor'),

    # 8. الهواتف الذكية والموبايل
    (r'موبايل|هاتف\s*(?:ذكي|محمول)?|smartphone\b|iphone\b|آيفون|ايفون|جالكسي|جالاكسي|galaxy\b|ريدمي|redmi\b|poco\b|بوكو\b|realme\b|ريلمي\b|infinix\b|إنفينيكس\b|انفينكس\b', 'موبايل', 'Smartphone'),

    # 9. السماعات والصوتيات
    (r'سماعة\s*(?:اذن|أذن|بلوتوث|لاسلكية|ايربودز?|داخل\s*الأذن)?|earbuds|airpods|true\s*wireless|tws\b', 'سماعة أذن لاسلكية', 'True Wireless Earbuds'),
    (r'سماعة\s*(?:راس|رأس|العاب|ألعاب|محيطية)|gaming\s*headset|headphones|headset\b', 'سماعة رأس', 'Gaming Headset'),
    (r'مكبر\s*صوت|ساوند\s*بار|سبيكر|speaker\b|soundbar\b', 'مكبر صوت ساوند بار', 'Bluetooth Speaker'),

    # 10. الساعات الذكية
    (r'ساعة\s*(?:ذكية|سمارت)|smart\s*watch|smartwatch', 'ساعة ذكية', 'Smartwatch'),

    # 11. مراوح التبريد
    (r'مروحة\s*(?:تبريد|مكتب|عمود)?|cooling\s*fan|fan\b', 'مروحة تبريد', 'Cooling Fan'),

    # 12. الأجهزة المنزلية وأجهزة المطبخ
    (r'ماكينة\s*(?:تحضير\s*)?ال?قهوة|صانعة\s*ال?قهوة|coffee\s*maker', 'ماكينة تحضير قهوة', 'Coffee Maker'),
    (r'ماكينة\s*حلاقة|shaver\b|clipper\b|trimmer\b', 'ماكينة حلاقة', 'Hair Clipper & Shaver'),
    (r'قلاية\s*(?:هوائية|بدون\s*زيت)|اير\s*فراير|air\s*fryer', 'قلاية هوائية', 'Air Fryer'),
    (r'خلاط\s*(?:كهربائي|يدوي)?|هاند\s*بلندر|blender\b', 'خلاط كهربائي', 'Blender'),
    (r'مكواة\s*بخار|steam\s*iron', 'مكواة بخار', 'Steam Iron'),
    (r'سخان|غلاية|kettle\b', 'غلاية مياه كهربائية', 'Electric Water Kettle'),
    (r'مفرمة|كبة|chopper\b|food\s*processor', 'كبة ومفرمة كهربائية', 'Electric Food Chopper'),
    (r'مكنسة\s*(?:كهربائية|روبوت|لاسلكية)?|vacuum\s*cleaner', 'مكنسة كهربائية', 'Vacuum Cleaner'),

    # 13. الأدوات والأزياء والعناية الشخصية
    (r'كرسي\s*(?:بوسادة|طبي|مريح)?|مسند\s*(?:ظهر|طبي)|وسادة\s*(?:ظهر|جلوس)|cushion\b', 'كرسي ومسند ظهر مريح', 'Back Support Cushion Chair'),
    (r'حذاء\s*رياضي|كوتشي|running\s*shoes|sneakers\b', 'حذاء رياضي', 'Running Shoes'),
    (r'طقم\s*مفكات|screwdriver\s*set', 'طقم مفكات براغي', 'Screwdriver Set'),
    (r'جل\s*استحمام|شاور\s*جل|shower\s*gel', 'جل استحمام', 'Shower Gel'),
    (r'غسول\s*(?:للوجه|وجه)|cleanser\b|face\s*wash', 'غسول للوجه', 'Face Cleanser'),
    (r'كريم\s*(?:مرطب|للوجه)|سيروم|moisturizer|serum\b', 'كريم مرطب للعناية بالبشرة', 'Moisturizing Cream'),
    (r'شامبو|بلسم|shampoo|conditioner', 'شامبو للعناية بالشعر', 'Hair Care Shampoo'),
]

def extract_bilingual_product_names(title, brand=None, features=None, en_slug=None, breadcrumbs=None, specs=None, image_url=None):
    """
    يستخرج اسم المنتج الذكي والمختصر ببراعة بالعربي وبالإنجليزي (مع كتابة الماركة بالإنجليزية دائماً)
    بالاعتماد على العنوان الكامل والوصف والمواصفات ومسار الفئة وصورة المنتج (Computer Vision).
    """
    intel = pi.analyze_product(
        title,
        brand=brand,
        features=features,
        en_slug=en_slug,
        breadcrumbs=breadcrumbs,
        specs=specs,
        image_url=image_url,
        use_vision=bool(image_url),
    )
    return intel["name_ar"], intel["name_en"]

def build_description(title, features=None, extra_desc=None, brand=None):
    """
    يكوّن وصفاً ذكياً ومفهوماً للمنتج باللغة العربية فقط، يشرح القيمة الحقيقية
    ووظائف ومميزات المنتج بدقة وبدون أخطاء تصنيف أو حشو غير مفهوم.
    """
    intel = pi.analyze_product(
        title,
        brand=brand,
        features=features,
        extra_desc=extra_desc,
        use_vision=False,
    )
    return intel["description"]

def rewrite_channel_insight(raw_text):
    """
    يحلل كلام القنوات التانية لو قالوا إن العرض كويس أو تجربته كويسة،
    ويعيد صياغته بالكامل بأسلوب وطريقة قناة (لقطة) الخاصة بدون نقل حرفي.
    """
    if not raw_text:
        return None
    t = clean(raw_text)
    t = re.sub(r'https?://\S+', ' ', t)
    t = re.sub(r'@[A-Za-z0-9_]+', ' ', t)
    t = re.sub(r'#[\w\u0600-\u06FF]+', ' ', t)

    traits = []
    tl = t.lower()
    if any(w in tl for w in ("تجربة", "تجربته", "مجرب", "عن تجربه", "جربته")):
        traits.append("تجارب استخدامه الفعلية ممتازة وواخد إشادة كبيرة")
    if any(w in tl for w in ("خامة", "خامته", "خامات", "تقفيل", "متين")):
        traits.append("خامات تصنيعه قوية وتقفيله محترم يعيش معاك")
    if any(w in tl for w in ("صوت", "بيز", "bass", "مايك", "مكالمات", "عزل")):
        traits.append("أداء صوتي نقي وواضح في الاستخدام والمكالمات")
    if any(w in tl for w in ("بطارية", "بطاريته", "بتقعد", "شحن سريع")):
        traits.append("أداء بطارية وشحن يعتمد عليه طوال اليوم")
    if any(w in tl for w in ("أمان", "امان", "آمن", "حماية", "الأجهزة التقيلة")):
        traits.append("مزود بحماية وأمان عالي لتشغيل الأجهزة باطمئنان")
    if any(w in tl for w in ("عملي", "عملية", "مريح", "سريع", "منجز")):
        traits.append("عملي جداً ومريح في الاستخدام اليومي")
    if any(w in tl for w in ("لقطة", "أقل سعر", "اقل سعر", "سعر تاريخي", "سعره حلو", "عرض كويس", "عرض ممتاز", "فرصة", "يستاهل")):
        traits.append("نازل حالياً بقيمة ممتازة جداً مقابل السعر")

    if not traits:
        return None
    return "💡 خلاصة التجربة والترشيح: " + "، و".join(traits[:3]) + "."

def build_review_summary(rating, reviews, review_snippets=None, bought_badge=None, custom_insight=None):
    """يبني مراجعة مختصرة ومفيدة للمنتج بناءً على تعليقات وتقييمات المشترين وخلاصة التجربة."""
    parts = []
    r_val = to_float(rating) if rating else None
    r_cnt = parse_reviews_count(reviews)

    if r_val is not None:
        if r_val >= 4.5 and r_cnt >= 50:
            verdict = "إشادة عالية جداً من المشترين بالجودة مقابل السعر"
        elif r_val >= 4.2:
            verdict = "انطباع إيجابي وتجارب شراء ناجحة"
        elif r_val >= 3.8:
            verdict = "تقييمات جيدة مقابل السعر"
        else:
            verdict = "تقييمات متفاوتة؛ راجع المواصفات قبل الشراء"
        cnt_txt = f" من {reviews} مشتري" if reviews else ""
        parts.append(f"حاصل على {rating}/5{cnt_txt} ({verdict}).")

    if bought_badge:
        parts.append(f"{bought_badge}.")

    if custom_insight:
        parts.append(custom_insight)
    elif review_snippets:
        valid_snips = [
            re.sub(r'\s+', ' ', s).strip()
            for s in review_snippets
            if s and "لو اشتريت منتج من نون" not in s and "تقديم التقييم" not in s
        ]
        if valid_snips:
            snippet = valid_snips[0][:100]
            if len(snippet) > 12:
                parts.append(f"من التعليقات: «{snippet}»")

    if not parts:
        return "منتج عليه خصم قوي؛ لم تتوفر تعليقات كافية بعد."
    return " ".join(parts)

def _is_bank_promo(text):
    """يكتشف عروض البنوك والفيزا والتقسيط لتجاهلها تماماً عشان الرسالة متبقاش طويلة ومملة."""
    t = (text or "").lower()
    bank_words = (
        "visa", "mastercard", "credit card", "debit", "بطاقات", "بطاقة", "بنك", "bank",
        "nbe", "qnb", "aaib", "alex", "cib", "hsbc", "fab", "valu", "فاليو",
        "تقسيط", "قسط", "شهرياً", "فائدة", "installment", "ائتمان", "ائتمانية",
    )
    return any(b in t for b in bank_words)

def detect_stacking_promos(card_text, page_promos=None, promo_links=None):
    """يكتشف فرص دمج الخصومات (خصم الـ Checkout، أكواد الخصم مثل FLASH، عروض اشترِ 1 والثانية هدية، وعروض الفئة)."""
    promos = []
    how_to = []
    extra_pct = 0.0
    extra_egp = 0.0
    extra_label = None
    t = clean(card_text or "")

    bogo_words = ("اشترِ", "اشتري", "اشتر ", "واحصل على", "مجانية", "مجاناً", "هدية", "قطعتين", "2 بسعر 1", "buy 1", "get 1")

    # 1. فحص نص الكارت (نون وأمازون) مع تجاهل أي عروض بنكية/فيزا
    for line in t.split('\n'):
        l = line.strip()
        if not l or _is_bank_promo(l):
            continue
        if any(bw in l.lower() for bw in bogo_words) and len(l) < 120:
            promos.append(f"🎁 عرض خاص: {l}")
            how_to.append("أضف الكمية المطلوبة (أو القطعة الثانية من العرض) للسلة وهيتطبق عرض الهدية/الخصم تلقائياً عند الدفع!")
            continue
        m_egp = re.search(r'(?:خصم|وفر|وفِّر)\s+(\d+(?:\.\d+)?)\s*(?:جنيه|ج\.م)', l)
        if m_egp and any(k in l for k in ("كوبون", "كود", "إضافي", "سلة", "الدفع")):
            val = float(m_egp.group(1))
            if val > extra_egp:
                extra_egp = val
                extra_label = "بعد الكوبون/الخصم الإضافي"
            promos.append(f"كوبون خصم إضافي: {l}")
            how_to.append("فعّل الكوبون الظاهر تحت السعر أو في السلة قبل الدفع.")
        elif "متاح عرض ترويجي بخصم" in l or "عند الدفع" in l:
            m_pct = re.search(r'(\d+)\s*[%٪]', l)
            if m_pct:
                extra_pct = max(extra_pct, float(m_pct.group(1)))
                extra_label = "بعد الخصم التلقائي عند الدفع (Checkout)" if "عند الدفع" in l else "بعد العرض الترويجي الإضافي"
            promos.append(l)
            how_to.append("أضف المنتج للسلة وادخل صفحة الدفع (Checkout) هتلاقي الخصم الإضافي اتخصم تلقائياً!")
        elif any(k in l for k in ("مع الكوبون", "كوبون خصم", "كود خصم", "استخدم الكود", "كود:")):
            if not re.fullmatch(r'خصم\s*\d+%', l) and len(l) < 110:
                promos.append(l)
                m_pct = re.search(r'(\d+)\s*[%٪]', l)
                if m_pct and any(w in l for w in ("كوبون", "كود", "وفر", "إضافي")):
                    extra_pct = max(extra_pct, float(m_pct.group(1)))
                    extra_label = "بعد الكوبون"
                how_to.append("علّم على مربع الكوبون تحت السعر أو اكتب الكود في صفحة الدفع.")

    # 2. فحص العروض وأكواد الخصم من صفحة المنتج (خصم الـ Checkout، كود FLASH، وعروض اشترِ 1 والثانية هدية)
    all_p_lines = []
    for p in (page_promos or []):
        p_no_css = re.sub(r'\.cxcwEmphasisLink\s*\{[^}]*\}', ' ', clean(p))
        for sub in p_no_css.split('\n'):
            s_clean = re.sub(r'^تسجيل الدخول للاستفادة من الكوبون\.?\s*', '', sub).strip()
            s_clean = re.sub(r'\s+', ' ', s_clean)
            if len(s_clean) >= 6 and not s_clean.startswith('{') and "margin-" not in s_clean:
                if not _is_bank_promo(s_clean):
                    all_p_lines.append(s_clean)

    page_found_promos = []
    page_found_howto = []
    for p_clean in all_p_lines:
        short_p = p_clean.split("الشروط")[0].replace("تسوق المنتجات", "").strip()[:115]
        if not short_p:
            continue
        code_m = re.search(r'(?:أدخل الرمز|رمز العرض الترويجي:?|استخدم الكود:?|كود الخصم:?|كود:?|رمز:?|code:?)\s*([A-Z0-9]{3,20})', p_clean, re.IGNORECASE)
        pct_m = re.search(r'(\d+)\s*[%٪]', p_clean)
        egp_m = re.search(r'(\d+(?:\.\d+)?)\s*(?:جنيه|ج\.م|EGP)', p_clean, re.IGNORECASE)

        # أ) عروض اشترِ 1 والثانية هدية / اشترِ 2 بخصم
        if any(bw in short_p.lower() for bw in bogo_words):
            page_found_promos.insert(0, f"🎁 عرض خاص: {short_p}")
            page_found_howto.insert(0, "أضف القطعتين (أو الكمية المطلوبة من العرض) في السلة وهيتطبق عرض الهدية/الخصم تلقائياً عند الدفع!")
            continue

        # ب) كود خصم صريح (مثل FLASH)
        if code_m and code_m.group(1).upper() not in ("OFF", "EGP", "VIP"):
            code = code_m.group(1).upper()
            page_found_promos.insert(0, f"🔥 {short_p} (كود: {code})")
            if pct_m:
                extra_pct = max(extra_pct, float(pct_m.group(1)))
                extra_label = f"بعد كود الخصم ({code})"
                page_found_howto.insert(0, f"اكتب كود ({code}) في خانة الكوبون عند الدفع (أو اضغط تفعيل تحت السعر) لخصم {pct_m.group(1)}% إضافي!")
            elif egp_m:
                extra_egp = max(extra_egp, float(egp_m.group(1)))
                extra_label = f"بعد كود الخصم ({code})"
                page_found_howto.insert(0, f"اكتب كود ({code}) عند الدفع لخصم {egp_m.group(1)} ج.م إضافي!")
            else:
                page_found_howto.insert(0, f"استخدم كود ({code}) في صفحة الدفع للحصول على الخصم الإضافي.")

        # ج) خصم تلقائي عند الدفع (Checkout) أو خصم برايم
        elif any(w in p_clean for w in ("عند الدفع", "التوفير مع خدمة برايم", "خصم تلقائي", "عند إتمام الشراء")):
            page_found_promos.insert(0, f"⚡ {short_p} (بيخصم تلقائياً في الـ Checkout)")
            if pct_m:
                extra_pct = max(extra_pct, float(pct_m.group(1)))
                extra_label = "بعد الخصم التلقائي في الـ Checkout"
            elif egp_m:
                extra_egp = max(extra_egp, float(egp_m.group(1)))
                extra_label = "بعد الخصم التلقائي في الـ Checkout"
            page_found_howto.insert(0, "أضف المنتج للسلة وادخل صفحة الدفع (Checkout) هتلاقي الخصم الإضافي اتخصم تلقائياً!")

        # د) كوبونات وعروض توفير إضافية (بالجنيه أو بالنسبة المئوية)
        elif any(w in p_clean.lower() for w in ("كوبون", "coupon", "وفر", "وفِّر", "توفير", "خصم إضافي", "كاش باك")):
            page_found_promos.append(short_p)
            if pct_m and any(w in short_p.lower() for w in ("كوبون", "coupon", "وفر", "وفِّر", "توفير", "إضافي")):
                extra_pct = max(extra_pct, float(pct_m.group(1)))
                if not extra_label:
                    extra_label = "بعد الكوبون/العرض الإضافي"
                page_found_howto.append("علّم على مربع الكوبون تحت السعر في صفحة المنتج عشان يتدمج مع الخصم الأساسي.")
            elif egp_m and any(w in short_p.lower() for w in ("كوبون", "coupon", "وفر", "وفِّر", "توفير", "إضافي", "apply")):
                extra_egp = max(extra_egp, float(egp_m.group(1)))
                if not extra_label:
                    extra_label = "بعد الكوبون"
                page_found_howto.append("علّم على مربع (تطبيق الكوبون) تحت السعر في صفحة المنتج قبل الإضافة للسلة.")

    combined_promos = page_found_promos + [p for p in promos if not (page_found_promos and "متاح عرض ترويجي" in p)]
    combined_howto = page_found_howto + how_to

    unique_promos = list(dict.fromkeys(combined_promos))[:2]
    unique_howto = list(dict.fromkeys(combined_howto))[:1]
    if unique_promos and not unique_howto:
        unique_howto.append("فعّل العرض الإضافي من تحت السعر أو في صفحة الدفع لدمجه مع خصم المنتج.")
    valid_links = (promo_links or [])[:1] if (unique_promos or extra_pct > 0 or extra_egp > 0) else []
    return unique_promos, unique_howto, extra_pct, extra_egp, extra_label, valid_links

def build_message(store, title, price, list_price, discount, link,
                  seller=None, rating=None, reviews=None, features=None,
                  prev_min=None, max_price=None, min_price=None,
                  review_snippets=None, bought_badge=None,
                  stack_promos=None, stack_howto=None, section_note=None,
                  extra_pct=0.0, extra_egp=0.0, extra_label=None, promo_links=None,
                  brand=None, custom_insight=None,
                  en_slug=None, breadcrumbs=None, specs=None, image_url=None):
    store_ar = "أمازون" if store.lower() == "amazon" else ("نون" if store.lower() == "noon" else store)
    icon = "🔥" if store.lower() == "amazon" else "🟡"

    b_raw = (brand or "").strip()
    if b_raw.lower() in _GENERIC_BRAND_NAMES:
        b_raw = ""

    # التحليل الذكي متعدد الوسائط (العنوان الكامل + الوصف والمواصفات + مسار الفئة + الصورة بالرؤية الحاسوبية)
    intel = pi.analyze_product(
        title,
        brand=b_raw,
        features=features,
        en_slug=en_slug,
        breadcrumbs=breadcrumbs,
        specs=specs,
        image_url=image_url,
        use_vision=bool(image_url),
    )
    brand_en = intel["brand_en"]
    name_ar = intel["name_ar"]
    name_en = intel["name_en"]
    desc = intel["description"]

    final_price = None
    if price is not None:
        if extra_pct > 0:
            final_price = round(price * (1 - extra_pct / 100.0), 2)
        elif extra_egp > 0 and price > extra_egp:
            final_price = round(price - extra_egp, 2)
        elif store.lower() == "noon" and NOON_COUPON and price >= 100:
            noon_saving = round(min(price * 0.10, 50.0), 2)
            if noon_saving >= 1:
                final_price = round(price - noon_saving, 2)
                extra_label = f"بعد كود خصم نون ({NOON_COUPON})"

    effective_price = final_price if final_price is not None else price
    freebie = is_almost_free(effective_price, list_price, discount)
    if freebie:
        header = f"🚨🔥 ببلاش حرفياً على {store_ar}! (نزل من {fmt(list_price)} ج.م لـ {fmt(effective_price)} ج.م)"
    elif section_note:
        header = f"{icon} على {store_ar} — {section_note}"
    else:
        header = f"{icon} على {store_ar}"

    lines = [
        f"<b>{header}</b>",
        "",
        f"📦 <b>{html.escape(name_ar)}</b>",
        f"🇬🇧 <b>{html.escape(name_en)}</b>",
        "",
    ]

    if list_price and list_price > (price or 0):
        lines.append(f"❌ السعر القديم: <s>{fmt(list_price)} ج.م</s>")
    if price is not None:
        tag = " 🔥 (ببلاش تقريباً!)" if (freebie and final_price is None) else ""
        lines.append(f"💰 السعر الجديد: <b>{fmt(price)} ج.م</b>{tag}")
    if final_price is not None and final_price < price:
        lbl = extra_label or "بعد دمج الخصم الإضافي"
        lines.append(f"🔥 <b>السعر النهائي {html.escape(lbl)}: {fmt(final_price)} ج.م فقط!</b>")
    if store.lower() == "noon" and NOON_COUPON:
        lines.append(f"🎟️ <b>كود خصم نون الإضافي (10%):</b> <code>{html.escape(NOON_COUPON)}</code> <i>(اضغط على الكود لنسخه)</i>")
    if effective_price is not None and list_price and list_price > effective_price:
        eff_disc = (1 - effective_price / list_price) * 100
        lines.append(f"📉 إجمالي الخصم: <b>{eff_disc:.0f}%</b> (وفّرت {fmt(list_price - effective_price)} ج.م)")
    elif discount and discount > 0:
        lines.append(f"📉 الخصم: <b>{discount:.0f}%</b>")

    if brand_en:
        lines.append(f"🏷️ الماركة: <b>{html.escape(brand_en[:40])}</b>")
    if seller:
        lines.append(f"🏪 البائع: {html.escape(seller[:40])}")
    if rating:
        lines.append(f"⭐ التقييم: {rating}" + (f" ({reviews} تقييم)" if reviews else ""))

    # 1) بعد السعر على طول: دمج الكوبونات والخصومات (لو موجودة)
    if stack_promos:
        lines += ["", "🎁 <b>عروض إضافية ودمج خصومات:</b>"]
        for sp in stack_promos[:2]:
            lines.append(f"• {html.escape(sp)}")
        if stack_howto:
            lines.append(f"💡 <b>طريقة التفعيل:</b> {html.escape(stack_howto[0])}")

    # 2) رابط المنتج مباشرةً (بعد دمج الخصومات، أو بعد السعر على طول لو مفيش دمج خصومات)
    short_branded_link = branded_url(link)
    lines += [
        "",
        f"🔗 <b>رابط المنتج:</b>\n{short_branded_link}",
    ]

    # 3) وصف المنتج (مختصر ومفهوم وذكي بالعربي فقط)
    if desc:
        lines += ["", f"📝 <b>وصف المنتج:</b>\n{html.escape(desc)}"]

    # 4) مراجعة المشترين (مختصرة)
    rev_summary = build_review_summary(rating, reviews, review_snippets, bought_badge, custom_insight=custom_insight)
    if rev_summary:
        lines += ["", f"💬 <b>مراجعة المشترين:</b>\n{html.escape(rev_summary)}"]

    # 5) لينك عروض الفئة دي (لو موجود)
    for pl in (promo_links or [])[:1]:
        lines += [
            "",
            f"🏷️ <b>{store_ar} عاملة عرض إضافي على الفئة دي هنا:</b>\n{branded_url(pl)}",
        ]

    if max_price is not None and min_price is not None and max_price > min_price and min_price >= 10:
        lines += [
            "",
            f"📊 أعلى سعر مسجّل: {fmt(max_price)} ج.م | أقل سعر: {fmt(min_price)} ج.م",
        ]

    lines += [
        "",
        "⚠️ <i>ملحوظة: ده مجرد ترشيح للعرض، والتجربة وقرار الشراء عليك.</i>",
        "",
        HASHTAG,
    ]
    return "\n".join(lines)

def build_section_alert(store, brand_label, section_url, items):
    """يبني رسالة تنبيه ذكية لما يلاقي خصومات قوية على سكشن/براند كامل (زي أبو عوف أو Fogg)."""
    store_ar = "أمازون" if store.lower() == "amazon" else "نون"
    max_disc = max(it["discount"] for it in items)
    min_p = min(it["price"] for it in items if it["price"])
    lines = [
        f"🚨🏷️ <b>حملة خصومات على قسم {html.escape(brand_label)} على {store_ar}!</b>",
        "",
        f"🔥 لقينا <b>{len(items)} منتجات</b> من <b>{html.escape(brand_label)}</b> عليها خصومات قوية توصل لـ <b>{max_disc:.0f}%</b> (والأسعار بتبدأ من <b>{fmt(min_p)} ج.م</b>):",
        "",
    ]
    for it in items[:4]:
        old_s = f"<s>{fmt(it['list_price'])}</s> ← " if it.get("list_price") else ""
        lines.append(
            f"• <b>{html.escape(it['title'][:65])}</b>\n"
            f"  💰 {old_s}<b>{fmt(it['price'])} ج.م</b> (خصم {it['discount']:.0f}%)\n"
            f"  🔗 {it['link']}"
        )
    lines += [
        "",
        f"🛒 <b>رابط كل عروض {html.escape(brand_label)} على {store_ar}:</b>\n{section_url}",
        "",
        "⚠️ <i>ملحوظة: ده مجرد ترشيح للعرض، والتجربة وقرار الشراء عليك.</i>",
        "",
        HASHTAG,
    ]
    return "\n".join(lines)

def _fit_caption_for_photo(text):
    """
    يضمن أن طول الكابشن لا يتخطى حد تليجرام الصارم للصور (1024 حرف)،
    ويختصر الأقسام تدريجياً مع إغلاق أي وسوم HTML مفتوحة لتجنب رفض الصورة نهائياً.
    """
    if not text or len(text) <= 950:
        return text

    t = text
    # 1. إزالة سطر التنويه وإخلاء المسؤولية
    t = re.sub(r'\n*⚠️\s*<i>ملحوظة:[^\n]+</i>', '', t)
    if len(t) <= 950:
        return t

    # 2. إزالة سطر سجل الأسعار التاريخي
    t = re.sub(r'\n*📊\s*أعلى سعر مسجّل:[^\n]+', '', t)
    if len(t) <= 950:
        return t

    # 3. إزالة الهاشتاجات الإضافية
    t = re.sub(r'\n*#\w+(?:\s+#\w+)*\s*$', '', t)
    if len(t) <= 950:
        return t

    # 4. إزالة مراجعات المشترين بالكامل (حتى لو متعددة الأسطر)
    t = re.sub(r'\n\n💬\s*<b>مراجعة المشترين:</b>\n[\s\S]*?(?=\n\n|\Z)', '', t)
    if len(t) <= 950:
        return t

    # 5. إزالة وصف المنتج لو لسه طويل (حتى لو متعدد الأسطر)
    t = re.sub(r'\n\n📝\s*<b>وصف المنتج:</b>\n[\s\S]*?(?=\n\n|\Z)', '', t)
    if len(t) <= 950:
        return t

    # 6. اختصار المميزات للإبقاء على أول نقطتين فقط
    m_feat = re.search(r'(\n\n⭐\s*<b>أهم المميزات:</b>\n(?:[•\-][^\n]+\n?){1,2})', t)
    if m_feat:
        t = re.sub(r'\n\n⭐\s*<b>أهم المميزات:</b>\n(?:[•\-][^\n]+\n?)+', m_feat.group(1), t)
    if len(t) <= 950:
        return t

    # 7. لو لسه أطول من 950، اقتطاع آمن عند أقرب مسافة وإغلاق أي وسوم HTML
    if len(t) > 950:
        t = t[:930].rsplit(' ', 1)[0] + "..."
        for tag in ("b", "i", "s", "u", "code", "a"):
            open_count = len(re.findall(rf'<{tag}\b[^>]*>', t))
            close_count = len(re.findall(rf'</{tag}>', t))
            if open_count > close_count:
                t += f"</{tag}>" * (open_count - close_count)

    return t

def send_telegram_msg(text, image=None, target_chat_ids=None, reply_markup=None):
    """يبعت العرض بصورة المنتج دائماً (سواء برابط مباشر أو بتحميل الصورة ورفعها لتليجرام أو file_id)، ويدعم أزرار تليجرام التفاعلية."""
    if not BOT_TOKEN:
        return False
    img_url = clean_image_url(image)
    is_tg_file_id = bool(image and isinstance(image, str) and not image.startswith("http") and len(image) > 20)
    destinations = target_chat_ids if target_chat_ids is not None else CHAT_IDS
    photo_caption = _fit_caption_for_photo(text)
    at_least_one_success = False
    for chat_id in destinations:
        try:
            resp = None
            if img_url or is_tg_file_id:
                photo_val = img_url if img_url else image
                # 1. محاولة إرسال الصورة بالرابط المباشر أو file_id
                post_data = {
                    "chat_id": chat_id,
                    "photo": photo_val,
                    "caption": photo_caption,
                    "parse_mode": "HTML",
                }
                if reply_markup:
                    post_data["reply_markup"] = reply_markup
                resp = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    json=post_data,
                    timeout=20,
                )
                # 2. لو تليجرام رفض تحميل الرابط مباشرة (مثلاً بسبب حماية CDN)، نحمّل الصورة ونرفعها كملف
                if not resp.ok and img_url:
                    try:
                        img_r = requests.get(
                            img_url,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"},
                            timeout=15,
                        )
                        if img_r.ok and len(img_r.content) > 500:
                            f_data = {
                                "chat_id": chat_id,
                                "caption": photo_caption,
                                "parse_mode": "HTML",
                            }
                            if reply_markup:
                                f_data["reply_markup"] = json.dumps(reply_markup)
                            resp = requests.post(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                                data=f_data,
                                files={"photo": ("product.jpg", img_r.content, "image/jpeg")},
                                timeout=25,
                            )
                    except Exception as img_e:
                        print(f"تعذر رفع صورة المنتج كملف: {img_e}")

                # 3. لو sendPhoto فشل بسبب وسم HTML أو طول كابشن، نجرب كابشن نصي صافي (بدون HTML)
                if not resp.ok and (img_url or is_tg_file_id):
                    try:
                        plain_cap = re.sub(r'<[^>]+>', '', photo_caption)[:950]
                        p_data = {
                            "chat_id": chat_id,
                            "photo": photo_val,
                            "caption": plain_cap,
                        }
                        if reply_markup:
                            p_data["reply_markup"] = reply_markup
                        resp = requests.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                            json=p_data,
                            timeout=15,
                        )
                    except Exception as p_err:
                        print(f"تعذر إرسال الصورة بكابشن نصي: {p_err}")

                # 4. لو الكابشن ما زال يسبب رفض الصورة، نرسل الصورة منفردة أولاً ثم الرسالة كنص حتى لا تضيع صورة المنتج أبداً!
                if not resp.ok and (img_url or is_tg_file_id):
                    try:
                        p_solo = {"chat_id": chat_id, "photo": photo_val}
                        resp_solo = requests.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                            json=p_solo,
                            timeout=15,
                        )
                        if resp_solo.ok:
                            msg_payload = {
                                "chat_id": chat_id,
                                "text": text,
                                "parse_mode": "HTML",
                                "disable_web_page_preview": True,
                            }
                            if reply_markup:
                                msg_payload["reply_markup"] = reply_markup
                            resp = requests.post(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                json=msg_payload,
                                timeout=10,
                            )
                    except Exception as s_err:
                        print(f"تعذر إرسال الصورة منفردة: {s_err}")

            if resp is None or not resp.ok:
                msg_payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                }
                if reply_markup:
                    msg_payload["reply_markup"] = reply_markup
                resp = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json=msg_payload,
                    timeout=10,
                )
            if resp is None or not resp.ok:
                # لو فشل بسبب كابشن أو وسم HTML معطوب، نبعته كنص صافي بدون HTML لتجنب ضياع البوست
                plain_text = re.sub(r'<[^>]+>', '', text)
                msg_payload = {
                    "chat_id": chat_id,
                    "text": plain_text,
                    "disable_web_page_preview": True,
                }
                if reply_markup:
                    msg_payload["reply_markup"] = reply_markup
                resp = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json=msg_payload,
                    timeout=10,
                )
            if resp and resp.ok:
                print(f"تم إرسال العرض إلى تليجرام ({chat_id}) بنجاح.")
                at_least_one_success = True
            else:
                code = resp.status_code if resp is not None else 0
                r_txt = resp.text if resp is not None else "No response"
                print(f"Telegram API error ({chat_id}, {code}): {r_txt}")
        except Exception as e:
            print(f"Error sending message to {chat_id}: {e}")
    return at_least_one_success

def answer_callback_query(callback_query_id, text=None, show_alert=False):
    """الرد على ضغطات أزرار تليجرام التفاعلية لمنع دوران أيقونة التحميل في تليجرام."""
    if not callback_query_id or not BOT_TOKEN:
        return
    try:
        payload = {"callback_query_id": str(callback_query_id)}
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = bool(show_alert)
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
            json=payload,
            timeout=10,
        )
    except Exception as e:
        print(f"Error answering callback {callback_query_id}: {e}")

def edit_telegram_msg(chat_id, message_id, text, reply_markup=None):
    """تعديل نص الرسالة أو كابشن الصورة في تليجرام وإلغاء أو تعديل الأزرار."""
    if not BOT_TOKEN:
        return
    try:
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
            json=payload,
            timeout=10,
        )
        if not r.ok and any(k in r.text.lower() for k in ("no text in the message", "message to edit not found")):
            cap_payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "caption": text,
                "parse_mode": "HTML",
            }
            if reply_markup is not None:
                cap_payload["reply_markup"] = reply_markup
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageCaption",
                json=cap_payload,
                timeout=10,
            )
    except Exception as e:
        print(f"Error editing message {message_id}: {e}")

_last_send_ts = 0.0

async def pace_and_send(text, image=None, is_freebie=False):
    """ينتظر 20 ثانية بين كل رسالة والتانية، ما عدا عروض (ببلاش) يبعتها فوراً في نفس اللحظة."""
    global _last_send_ts
    if not is_freebie and _last_send_ts > 0:
        elapsed = time.time() - _last_send_ts
        if elapsed < MESSAGE_DELAY:
            wait_s = MESSAGE_DELAY - elapsed
            print(f"انتظار {wait_s:.0f} ثانية قبل إرسال العرض التالي...")
            await asyncio.sleep(wait_s)
    send_telegram_msg(text, image=image)
    _last_send_ts = time.time()

# ---------------------------------------------------------------------------
# أمازون مصر (صفحة العروض + فحص البراندات والأقسام + المراجعات ودمج الخصومات)
# ---------------------------------------------------------------------------
def parse_amazon_card(text):
    t = clean(text)
    deal = re.search(r'سعر العرض:+\s*([\d,]+(?:\.\d+)?)', t)
    if not deal:
        deal = re.search(r'([\d,]+(?:\.\d+)?)\s*جنيه', t)
    lst = re.search(r'سعر القائمه:\s*([\d,]+(?:\.\d+)?)', t)
    rating = re.search(r'^\s*(\d\.\d)(?:\s*من\s*5)?', t, re.MULTILINE)
    reviews = re.search(r'\(([\d.,]+\s*(?:ألف|K)?)\s*\)', t)
    bought = re.search(r'(تم شراء [^\n]+)', t)
    lines = [
        l.strip() for l in t.split('\n')
        if len(l.strip()) > 15
        and not any(s in l for s in ("سعر العرض", "سعر القائمه", "تمت المطالبة", "عروض من هذه العلامة", "تم شراء", "الخيارات:"))
    ]
    return {
        "price": to_float(deal.group(1)) if deal else None,
        "list_price": to_float(lst.group(1)) if lst else None,
        "rating": rating.group(1) if rating else None,
        "reviews": reviews.group(1).strip() if reviews else None,
        "bought": bought.group(1).strip() if bought else None,
        "title": lines[0][:150] if lines else "منتج على أمازون",
    }

async def amazon_product_details(context, link):
    """يفتح صفحة المنتج لجلب البائع، الماركة، التقييمات، المميزات، تعليقات المشترين، الصورة، وعروض دمج الخصومات وروابطها، والسياق الكامل للمنتج."""
    page = await context.new_page()
    seller, brand, pdp_rating, pdp_reviews, features, image, reviews_list, promos_list, promo_links = None, None, None, None, [], None, [], [], []
    extra_ctx = {}
    try:
        await page.goto(link, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2000)
        title = await page.title()
        if is_blocked_title(title) or await page.query_selector('form[action*="validateCaptcha"]'):
            print(f"صفحة منتج أمازون محجوبة ({title[:40]}) - هنكتفي ببيانات الكارت.")
            return None, None, None, None, None, None, [], [], [], {}
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.65)")
        await page.wait_for_timeout(1200)
        data = await page.evaluate("""() => {
            const q = s => document.querySelector(s)?.innerText?.trim();
            const pdp_title = q('#productTitle') || q('#title') || '';
            const seller = q('#sellerProfileTriggerId')
                || q('#merchantInfoFeature_feature_div .offer-display-feature-text-message')
                || q('#merchant-info a') || q('#merchant-info');
            let brand = q('tr.po-brand td.a-span9') || q('#bylineInfo');
            if (brand) {
                brand = brand
                    .replace(/^(قم بزيارة متجر|زيارة متجر|العلامة التجارية:|الماركة:|Visit the|Brand:)\\s*/i, '')
                    .replace(/\\s*Store$/i, '')
                    .trim();
            }
            const ratingTxt = document.querySelector('#acrPopover')?.getAttribute('title') || q('#acrPopover .a-size-base');
            const reviewsTxt = q('#acrCustomerReviewText');
            const feats = [...document.querySelectorAll('#feature-bullets li span.a-list-item')]
                .map(e => e.innerText.trim()).filter(x => x.length > 10);
            const overview = (q('#productDescription') || '').replace(/\\s+/g, ' ').trim();
            if (!feats.length && overview.length > 20) {
                feats.push(overview.slice(0, 220));
            }
            const breadcrumbs = [...document.querySelectorAll('#wayfinding-breadcrumbs_feature_div li a, #wayfinding-breadcrumbs_container a')]
                .map(e => e.innerText.trim()).filter(Boolean);
            const specs = [...document.querySelectorAll('#productOverview_feature_div tr, #prodDetails tr, #technicalSpecifications_section_1 tr')]
                .map(r => r.innerText.replace(/\\s+/g, ' ').trim()).filter(x => x.length > 3 && x.length < 140).slice(0, 18);
            const en_slug = document.querySelector('link[rel="alternate"][hreflang="en-eg"], link[rel="alternate"][href*="/-/en/"], link[rel="canonical"]')?.href || '';
            const img = document.querySelector('#landingImage, #imgBlkFront, #main-image, #imgTagWrapperId img');
            let image = img?.getAttribute('data-old-hires');
            if (!image || !image.startsWith('http')) {
                const dyn = img?.getAttribute('data-a-dynamic-image');
                if (dyn) {
                    try { image = Object.keys(JSON.parse(dyn))[0]; } catch (e) {}
                }
            }
            if (!image || !image.startsWith('http')) {
                image = [
                    img?.currentSrc,
                    img?.getAttribute('src'),
                    document.querySelector('meta[property="og:image"]')?.content,
                    ...[...document.querySelectorAll('#altImages img, #imageBlock img')].map(i => i.src)
                ].find(u => u && u.startsWith('http') && !u.includes(' play-button') && !u.includes('transparent-pixel'));
            }
            const promos = [
                ...document.querySelectorAll(
                    '#promoPriceBlockMessage_feature_div .promoPriceBlockMessage > div, ' +
                    '#promoPriceBlockMessage_feature_div .a-section, ' +
                    '#promoPriceBlockMessage_feature_div, #couponBadgeRegularVpc, [id*="coupon" i], #sopp_feature_div'
                )
            ].map(e => e.innerText.trim()).filter(x => x && x.length > 5 && x.length < 1500);
            const promo_links = [...new Set(
                [...document.querySelectorAll('#promoPriceBlockMessage_feature_div a[href*="/promotion/psp/"], a[href*="/promotion/psp/"]')]
                    .map(a => a.href.split('&ref=')[0].split('?ref=')[0])
                    .filter(Boolean)
            )];
            const revs = [...document.querySelectorAll('[data-hook="reviewText"], [data-hook="review-collapsed"], .review-text-content')]
                .map(e => e.innerText.trim()).filter(x => x.length > 15).slice(0, 3);
            return {pdp_title, seller, brand, ratingTxt, reviewsTxt, feats, breadcrumbs, specs, en_slug, image, promos: promos.slice(0, 10), promo_links: promo_links.slice(0, 2), revs};
        }""")
        seller = data.get("seller")
        brand = data.get("brand")
        r_m = re.search(r'(\d\.\d)', clean(data.get("ratingTxt") or ""))
        if r_m:
            pdp_rating = r_m.group(1)
        rv_m = re.search(r'([\d,]+)', clean(data.get("reviewsTxt") or ""))
        if rv_m:
            pdp_reviews = rv_m.group(1)
        features = data.get("feats") or []
        image = clean_image_url(data.get("image"))
        promos_list = data.get("promos") or []
        promo_links = data.get("promo_links") or []
        reviews_list = data.get("revs") or []
        extra_ctx = {
            "pdp_title": data.get("pdp_title") or "",
            "en_slug": data.get("en_slug") or "",
            "breadcrumbs": data.get("breadcrumbs") or [],
            "specs": data.get("specs") or [],
        }
    except Exception as e:
        print(f"تعذر جلب تفاصيل المنتج: {e}")
    finally:
        await page.close()
    return seller, brand, pdp_rating, pdp_reviews, features, image, reviews_list, promos_list, promo_links, extra_ctx

AMAZON_SCROLLS = int(os.getenv("AMAZON_SCROLLS", "10"))

async def scrape_amazon_eg(page):
    global _brand_rot_idx, _amz_cat_rot_idx
    print("جاري فحص عروض أمازون مصر...")
    await page.goto("https://www.amazon.eg/deals", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)
    await page.evaluate("window.scrollBy(0, 1500)")
    try:
        await page.wait_for_selector('div[data-testid="product-card"], div[data-testid="deal-card"]', timeout=15000)
    except Exception:
        pass

    products = {}
    for _ in range(AMAZON_SCROLLS):
        cards = await page.evaluate("""() => [...document.querySelectorAll('div[data-testid="product-card"], div[data-testid="deal-card"]')]
            .map(c => ({href: (c.querySelector('a[data-testid="product-card-link"]') || c.querySelector('a'))?.getAttribute('href'),
                        text: c.innerText,
                        img: [...c.querySelectorAll('img')].map(i => i.currentSrc || i.src).find(s => s && s.includes('/images/I/')) || null}))""")
        for c in cards:
            if c["href"]:
                base = c["href"].split('?')[0]
                link = short_link(f"https://www.amazon.eg{base}" if base.startswith('/') else base)
                if link not in products:
                    products[link] = c
                elif c.get("img") and not products[link].get("img"):
                    products[link]["img"] = c["img"]
        await page.mouse.wheel(0, 900)
        await page.wait_for_timeout(900)

    # فحص أقسام وبراندات مختارة + الاهتمامات والبراندات اللي البوت اتعلمها تلقائياً
    all_brands_pool = list(HOT_BRANDS)
    for lb in learned_prefs.get("brands", []):
        if len(lb) >= 2 and not any(lb.lower() in [k.lower() for k in b[1]] for b in HOT_BRANDS):
            all_brands_pool.append((lb, [lb]))

    brands_to_check = [
        (b_lbl, f"https://www.amazon.eg/s?k={quote_plus(kw_list[0])}")
        for b_lbl, kw_list in (all_brands_pool[(_brand_rot_idx + i) % len(all_brands_pool)] for i in range(8))
    ]
    _brand_rot_idx = (_brand_rot_idx + 8) % len(all_brands_pool)

    cats_to_check = [
        AMAZON_CATEGORY_SEARCHES[(_amz_cat_rot_idx + i) % len(AMAZON_CATEGORY_SEARCHES)]
        for i in range(5)
    ]
    _amz_cat_rot_idx = (_amz_cat_rot_idx + 5) % len(AMAZON_CATEGORY_SEARCHES)

    learned_to_check = []
    l_queries = learned_prefs.get("queries", [])
    if l_queries:
        global _learned_rot_idx
        for i in range(min(5, len(l_queries))):
            lq = l_queries[(_learned_rot_idx + i) % len(l_queries)]
            learned_to_check.append((f"اهتمام متعلّم ({lq})", f"https://www.amazon.eg/s?k={quote_plus(lq)}"))
        _learned_rot_idx = (_learned_rot_idx + 5) % len(l_queries)

    for section_label, search_url in (brands_to_check + cats_to_check + learned_to_check):
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(1800)
            scards = await page.evaluate("""() => [...document.querySelectorAll('div[data-component-type="s-search-result"]')].slice(0, 28).map(c => {
                const asin = c.getAttribute('data-asin');
                const title = c.querySelector('h2')?.innerText?.trim();
                const price = c.querySelector('.a-price:not(.a-text-price) .a-offscreen')?.innerText
                    || c.querySelector('.a-price .a-offscreen')?.innerText;
                const list_price = c.querySelector('.a-price.a-text-price .a-offscreen')?.innerText
                    || c.querySelector('span[data-a-strike="true"] .a-offscreen')?.innerText;
                const rating = c.querySelector('i[class*="a-icon-star"] span.a-icon-alt, span[aria-label*="من 5"]')?.innerText
                    || c.querySelector('span[aria-label*="نجوم"]')?.getAttribute('aria-label');
                const reviews = c.querySelector('a[href*="#customerReviews"] span, span.s-underline-text')?.innerText;
                const img = c.querySelector('img.s-image')?.src;
                return {asin, title, price, list_price, rating, reviews, img, text: c.innerText};
            })""")
            for sc in scards:
                if not sc.get("asin") or not sc.get("price"):
                    continue
                card_txt = sc.get("text") or ""
                has_promo_txt = any(w in card_txt for w in ("وفر ", "مع الكوبون", "كوبون", "عند الدفع", "عرض ترويجي", "اشترِ", "اشتري", "صفقة", "خصم", "deal"))
                if not sc.get("list_price") and not has_promo_txt:
                    continue
                link = f"https://www.amazon.eg/dp/{sc['asin']}"
                list_line = f"سعر القائمه: {sc['list_price']}\n" if sc.get("list_price") else ""
                rat_line = ""
                if sc.get("rating"):
                    rm = re.search(r'(\d[.,]\d)', sc["rating"])
                    if rm:
                        rat_line = f"{rm.group(1).replace(',', '.')} من 5\n"
                rev_line = f"({sc['reviews']})\n" if sc.get("reviews") else ""
                synth_text = f"سعر العرض: {sc['price']}\n{list_line}{rat_line}{rev_line}{sc.get('title') or ''}\n{card_txt}"
                if link not in products:
                    products[link] = {
                        "href": link,
                        "text": synth_text,
                        "img": sc.get("img"),
                    }
                elif sc.get("img") and not products[link].get("img"):
                    products[link]["img"] = sc.get("img")
        except Exception as e:
            print(f"تعذر فحص قسم {section_label} في أمازون: {e}")

    print(f"تم العثور على {len(products)} عرض في أمازون مصر.")

    candidates = []
    for full_link, card in products.items():
        try:
            text_content = card["text"]
            info = parse_amazon_card(text_content)
            if not info["price"] or info["price"] < 5 or is_blocked_title(info["title"]):
                continue
            match = re.search(r'(\d+)\s*%', text_content)
            badge_disc = int(match.group(1)) if match else None
            discount = float(badge_disc or 0)
            if info["list_price"] and info["list_price"] > info["price"]:
                discount = (1 - info["price"] / info["list_price"]) * 100

            has_card_promo = any(w in text_content for w in ("متاح عرض ترويجي", "مع الكوبون", "كوبون خصم", "وفر ", "عند الدفع", "اشترِ", "اشتري", "صفقة", "deal"))
            if discount <= 0 and has_card_promo:
                egp_m = re.search(r'وفر\s+(\d+(?:\.\d+)?)\s*(?:جنيه|ج\.م)', clean(text_content))
                if egp_m and info["price"] > float(egp_m.group(1)):
                    saving_v = float(egp_m.group(1))
                    info["list_price"] = info["price"]
                    discount = (saving_v / info["price"]) * 100
                else:
                    discount = 12.0
            if discount <= 0:
                continue

            prev_min, max_p, min_p = record_price(full_link, info["price"])
            freebie = is_almost_free(info["price"], info["list_price"], badge_disc)
            famous = has_famous_brand(info["title"])
            saving_egp = (info["list_price"] - info["price"]) if (info["list_price"] and info["list_price"] > info["price"]) else 0

            # للبراندات المشهورة والمتعلمة (مثل أنكر، آي لوك، تورنيدو، سنوز، يوجرين، فريش، فيليبس، براون...) نقبل خصم من 8%
            if famous:
                qualifies = (discount >= 8) or (discount >= 6 and (has_card_promo or saving_egp >= 40)) or freebie
            else:
                qualifies = (discount >= 20) or (discount >= 15 and has_card_promo) or freebie

            ok_prelim, _ = should_send_deal(full_link, info["title"], info["price"])
            if qualifies and ok_prelim:
                candidates.append((1 if freebie else 0, 1 if famous else 0, 1 if has_card_promo else 0, discount, full_link, card, info, prev_min, max_p, min_p))
        except Exception as e:
            print(f"خطأ في كارت أمازون: {e}")
            continue

    # ترتيب العروض: عروض "ببلاش" أولاً، ثم البراندات المشهورة (أنكر، آي لوك، الأجهزة...)، ثم العروض الإضافية والأعلى خصماً
    candidates.sort(key=lambda x: (x[0], x[1], x[2], x[3]), reverse=True)
    amazon_sent = 0
    consecutive_blocks = 0
    pdp_Lookups = 0

    for _, famous, _, discount, full_link, card, info, prev_min, max_p, min_p in candidates:
        if amazon_sent >= MAX_PER_CYCLE:
            break
        try:
            seller, brand, pdp_rating, pdp_reviews, features, image, rev_snippets, page_promos, promo_links, extra_ctx = None, None, None, None, [], None, [], [], [], {}
            if consecutive_blocks < 3 and pdp_Lookups < 28:
                pdp_Lookups += 1
                seller, brand, pdp_rating, pdp_reviews, features, image, rev_snippets, page_promos, promo_links, extra_ctx = await amazon_product_details(page.context, full_link)
                if features is None:
                    consecutive_blocks += 1
                    features = []
                else:
                    consecutive_blocks = 0

            full_title_amz = extra_ctx.get("pdp_title") or info["title"]
            if is_blocked_title(full_title_amz):
                full_title_amz = info["title"]
            rating = info["rating"] or pdp_rating
            reviews = info["reviews"] or pdp_reviews
            if not is_trusted_product(full_title_amz, brand=brand, rating=rating, reviews=reviews):
                continue

            stack_promos, stack_howto, extra_pct, extra_egp, extra_label, promo_links = detect_stacking_promos(
                card["text"], page_promos, promo_links
            )

            eff_price = info["price"]
            if extra_pct > 0:
                eff_price = round(eff_price * (1 - extra_pct / 100.0), 2)
            elif extra_egp > 0 and eff_price > extra_egp:
                eff_price = round(eff_price - extra_egp, 2)

            promo_sig = "|".join(stack_promos)
            ok_send, update_reason = should_send_deal(full_link, full_title_amz, eff_price, promo_sig)
            if not ok_send:
                continue

            mark_deal_sent(full_link, full_title_amz, eff_price, promo_sig)
            amazon_sent += 1

            chosen_img_amz = image or card.get("img")
            msg = build_message(
                "Amazon", full_title_amz, info["price"], info["list_price"], discount, full_link,
                seller=seller, rating=rating, reviews=reviews, features=features,
                prev_min=prev_min, max_price=max_p, min_price=min_p,
                review_snippets=rev_snippets, bought_badge=info.get("bought"),
                stack_promos=stack_promos, stack_howto=stack_howto, section_note=update_reason,
                extra_pct=extra_pct, extra_egp=extra_egp, extra_label=extra_label, promo_links=promo_links,
                brand=brand,
                en_slug=extra_ctx.get("en_slug"),
                breadcrumbs=extra_ctx.get("breadcrumbs"),
                specs=extra_ctx.get("specs"),
                image_url=chosen_img_amz,
            )
            is_free_now = is_almost_free(eff_price, info["list_price"], discount)
            await pace_and_send(msg, image=chosen_img_amz, is_freebie=is_free_now)
        except Exception as e:
            print(f"خطأ في إرسال عرض أمازون: {e}")
            continue

# ---------------------------------------------------------------------------
# نون مصر (تغطية شاملة + البراندات والأقسام + دمج الخصومات + المراجعات)
# ---------------------------------------------------------------------------
def parse_noon_card(text, price_text=None, badge_discount=None):
    t = clean(text)
    lines = [l.strip() for l in t.split('\n') if l.strip()]
    price = list_price = rating = reviews = None
    if price_text:
        pt = re.sub(r'خصم\s*\d+\s*%|\d+\s*%', ' ', clean(price_text))
        nums = [to_float(x) for x in re.findall(r'\d[\d,]*(?:\.\d+)?', pt)]
        nums = [n for n in nums if n and n >= 1]
        if nums:
            price = nums[0]
        if len(nums) > 1 and nums[1] > price:
            list_price = nums[1]
    if price is None:
        for i, l in enumerate(lines):
            if "جنيه" in l or "EGP" in l:
                window = " ".join(lines[i:i + 4])
                window = re.sub(r'خصم\s*\d+\s*%|\d+\s*%', ' ', window)
                nums = [to_float(x) for x in re.findall(r'\d[\d,]*(?:\.\d+)?', window)]
                nums = [n for n in nums if n and n >= 1]
                if nums:
                    price = nums[0]
                if len(nums) > 1 and nums[1] > price:
                    list_price = nums[1]
                break
    # التحقق الصارم من السعر لمنع أي رقم مقسوم بالخطأ
    if price is not None and list_price is not None and badge_discount:
        calc_d = (1 - price / list_price) * 100
        if abs(calc_d - badge_discount) > 15:
            # لو السعر القديم أو الجديد اتقرأ غلط نحسب السعر القديم بدقة من نسبة الخصم المكتوبة على الكارت
            if price < 15 and badge_discount < 85:
                price = None
            else:
                list_price = round(price / (1 - badge_discount / 100.0), 2)
    for j, l in enumerate(lines):
        if re.fullmatch(r'\d\.\d', l):
            rating = l
            if j + 1 < len(lines) and re.fullmatch(r'[\d.,]+K?', lines[j + 1]):
                reviews = lines[j + 1]
            break
    rank_badge = next((l for l in lines if l.startswith('#') and 'في ' in l), None)
    return {"price": price, "list_price": list_price, "rating": rating, "reviews": reviews, "bought": rank_badge}

NOON_CORE_URLS = [
    "https://www.noon.com/egypt-ar/search/?q=%D8%B3%D9%85%D8%A7%D8%B9%D8%A9+%D8%A7%D9%86%D9%83%D8%B1",
    "https://www.noon.com/egypt-ar/search/?q=%D9%85%D8%B4%D8%AA%D8%B1%D9%83+%D8%A7%D9%8A+%D9%84%D9%88%D9%83",
    "https://www.noon.com/egypt-ar/electronics-and-mobiles/?sort[by]=popularity&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/electronics-and-mobiles/mobiles-and-accessories/?sort[by]=popularity&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/home-appliances-31235/?sort[by]=popularity&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/home-and-kitchen/?sort[by]=popularity&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/electronics-and-mobiles/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/home-appliances-31235/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/tools-and-home-improvement/?sort[by]=popularity&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/grocery-store/?sort[by]=discount_percent&sort[dir]=desc",
]

NOON_EXTRA_URLS = [
    "https://www.noon.com/egypt-ar/search/?q=%D9%82%D9%84%D8%A7%D9%8A%D8%A9+%D8%A8%D8%AF%D9%88%D9%86+%D8%B2%D9%8A%D8%AA",
    "https://www.noon.com/egypt-ar/search/?q=%D8%AE%D9%84%D8%A7%D8%B7+%D9%83%D8%A8%D8%A9",
    "https://www.noon.com/egypt-ar/search/?q=%D9%85%D9%83%D9%88%D8%A7%D8%A9+%D8%A8%D8%AE%D8%A7%D8%B1+%D9%85%D9%83%D9%86%D8%B3%D8%A9",
    "https://www.noon.com/egypt-ar/search/?q=%D8%B4%D8%A7%D8%AD%D9%86+%D8%B3%D8%B1%D9%8A%D8%B9+%D8%A8%D8%A7%D9%88%D8%B1+%D8%A8%D8%A7%D9%86%D9%83",
    "https://www.noon.com/egypt-ar/search/?q=%D8%B3%D9%85%D8%A7%D8%B9%D8%A9+%D8%A8%D9%84%D9%88%D8%AA%D9%88%D8%AB",
    "https://www.noon.com/egypt-ar/search/?q=%D9%83%D9%8A%D8%A8%D9%88%D8%B1%D8%AF+%D9%85%D9%8A%D9%83%D8%A7%D9%86%D9%8A%D9%83%D9%8A",
    "https://www.noon.com/egypt-ar/search/?q=%D9%85%D8%A7%D9%83%D9%8A%D9%86%D8%A9+%D8%AD%D9%84%D8%A7%D9%82%D8%A9",
    "https://www.noon.com/egypt-ar/electronics-and-mobiles/computers-and-accessories/?sort[by]=popularity&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/electronics-and-mobiles/television-and-video/?sort[by]=popularity&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/fashion/men-31225/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/fashion/women-31229/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/health/?sort[by]=popularity&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/baby-products/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/sports-and-outdoors/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/automotive/?sort[by]=discount_percent&sort[dir]=desc",
]
_noon_rot_idx = 0

def noon_title(text):
    skip = ("أفضل المنتجات", "في ", "باقي", "خصم", "جنيه", "express", "الأكثر مبيعاً", "عرض الميجا")
    for l in clean(text).split('\n'):
        l = l.strip()
        if len(l) > 15 and not any(l.startswith(s) for s in skip) and not l.startswith('#'):
            return l[:150]
    return "منتج على نون"

async def noon_product_details(context, link):
    """يفتح صفحة المنتج في نون لجلب الاسم الكامل، الماركة، البائع، المميزات، المواصفات، الرابط الإنجليزي، التعليقات، العروض الإضافية، والصورة."""
    page = await context.new_page()
    full_title, brand, seller, features, image, promos, reviews_list = None, None, None, [], None, [], []
    extra_ctx = {}
    try:
        await page.goto(link, wait_until="domcontentloaded", timeout=40000)
        try:
            await page.wait_for_selector('[data-qa="pdp-product-name"], h1', timeout=10000)
        except Exception:
            await page.wait_for_timeout(3000)
        page_title = await page.title()
        h1 = await page.evaluate("() => document.querySelector('h1')?.innerText || ''")
        if is_blocked_title(page_title) or is_blocked_title(h1) or not await page.query_selector('[data-qa="pdp-container"]'):
            print(f"صفحة منتج نون محجوبة ({(h1 or page_title)[:40]}) - هنكتفي ببيانات الكارت.")
            return None, None, None, None, None, [], [], {}
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
        await page.wait_for_timeout(800)
        data = await page.evaluate("""() => {
            const h1El = document.querySelector('[data-qa="pdp-product-name"]') || document.querySelector('h1');
            const full_title = h1El?.innerText?.trim();
            let brand = document.querySelector('[data-qa*="brand" i], a[class*="brand" i]')?.innerText;
            if (!brand && h1El?.previousElementSibling) {
                const prevTxt = (h1El.previousElementSibling.innerText || '').replace(/[>›]/g, '').trim();
                if (prevTxt.length >= 2 && prevTxt.length <= 35 && !prevTxt.includes('عرض')) {
                    brand = prevTxt;
                }
            }
            if (!brand) {
                for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                    try {
                        const j = JSON.parse(s.textContent);
                        const b = j?.brand?.name || (typeof j?.brand === 'string' ? j.brand : null);
                        if (b) { brand = b; break; }
                    } catch (e) {}
                }
            }
            if (brand) brand = brand.replace(/[>›]/g, '').split('\\n')[0].trim();
            let image = document.querySelector('meta[property="og:image"]')?.content;
            if (!image || !image.startsWith('http')) {
                image = [...document.querySelectorAll('img')]
                    .map(i => i.currentSrc || i.src || i.getAttribute('data-src'))
                    .find(s => s && s.includes('nooncdn.com/p/'));
            }
            let seller = null;
            for (const el of document.querySelectorAll('a[href*="seller"], [class*="seller" i], [class*="partner" i], div, span')) {
                const t = (el.innerText || '').trim();
                if (t.startsWith('يتم البيع عبر') || t.startsWith('البائع')) {
                    seller = t.split('\\n')[0].replace('يتم البيع عبر', '').replace('البائع:', '').replace('البائع', '').trim();
                    if (seller) break;
                }
            }
            const container = document.querySelector('[data-qa="pdp-container"]');
            const feats = container
                ? [...container.querySelectorAll('ul li')]
                    .filter(e => !e.querySelector('a') && !e.closest('a') && !e.closest('header') && !e.closest('nav') && !e.closest('footer'))
                    .map(e => e.innerText.trim())
                    .filter(x => x.length > 20 && x.length < 220 && !x.includes('\\n'))
                : [];
            const overview = (container?.querySelector('[data-qa*="overview" i], [class*="overview" i]')?.innerText || '')
                .replace(/^(نظرة عامة|المميزات الأساسية|Overview)\\s*/i, '')
                .replace(/\\s+/g, ' ').trim();
            if (!feats.length && overview.length > 25) {
                feats.push(overview.slice(0, 220));
            }
            const breadcrumbs = [...document.querySelectorAll('[data-qa*="breadcrumb" i] a, nav[aria-label*="breadcrumb" i] a, [class*="breadcrumb" i] a')]
                .map(e => e.innerText.trim()).filter(Boolean);
            const specs = [...(container || document).querySelectorAll('table tr')]
                .map(r => r.innerText.replace(/\\s+/g, ' ').trim()).filter(x => x.length > 3 && x.length < 140).slice(0, 18);
            const en_slug = document.querySelector('link[rel="alternate"][hreflang*="en"], link[rel="alternate"][href*="-en/"]')?.href || '';
            const promos = container
                ? [...container.querySelectorAll('[class*="coupon" i], [class*="voucher" i], [class*="promo" i], [data-qa*="coupon" i], [class*="cashback" i]')]
                    .map(e => e.innerText.trim()).filter(x => x.length > 6 && x.length < 220)
                : [];
            const revs = [...document.querySelectorAll('[class*="reviewComment" i], [class*="reviewDesc" i], [data-qa*="review" i] p')]
                .map(e => e.innerText.trim())
                .filter(x => x.length > 15 && x.length < 220 && !x.includes('لو اشتريت منتج من نون') && !x.includes('تقديم التقييم'))
                .slice(0, 2);
            return {full_title, brand, seller, feats, breadcrumbs, specs, en_slug, image, promos: promos.slice(0, 5), revs};
        }""")
        full_title = data.get("full_title")
        if is_blocked_title(full_title):
            full_title = None
        brand = data.get("brand")
        seller = data.get("seller")
        features = data.get("feats") or []
        image = clean_image_url(data.get("image"))
        promos = data.get("promos") or []
        reviews_list = data.get("revs") or []
        extra_ctx = {
            "en_slug": data.get("en_slug") or "",
            "breadcrumbs": data.get("breadcrumbs") or [],
            "specs": data.get("specs") or [],
        }
    except Exception as e:
        print(f"تعذر جلب تفاصيل منتج نون: {e}")
    finally:
        await page.close()
    return full_title, brand, seller, features, image, promos, reviews_list, extra_ctx

NOON_CARDS_JS = """() => [...document.querySelectorAll('a[href*="/p/"]')].map(a => {
    const qaImg = a.querySelector('[data-qa^="productImagePLP_"]');
    const qaName = qaImg ? qaImg.getAttribute('data-qa').replace('productImagePLP_', '').trim() : null;
    const boxEl = a.querySelector('[data-qa="plp-product-box-name"]');
    const boxName = boxEl?.innerText?.replace(/\\s+/g, ' ')?.trim() || null;
    const titleAttr = a.getAttribute('title')?.trim() || null;
    let brand = a.querySelector('[data-qa*="brand" i]')?.innerText?.trim() || null;
    if (!brand && boxName && qaName && boxName.length > qaName.length && boxName.endsWith(qaName)) {
        brand = boxName.slice(0, boxName.length - qaName.length).trim();
    }
    const bestName = [boxName, titleAttr, qaName].filter(Boolean).sort((x, y) => y.length - x.length)[0] || null;
    const rawImg = [...a.querySelectorAll('img')]
        .map(i => i.currentSrc || i.src || i.getAttribute('data-src') || i.getAttribute('srcset')?.split(' ')[0])
        .find(s => s && s.includes('nooncdn.com/p/')) || null;
    return {
        href: a.getAttribute('href'),
        text: a.innerText,
        name: bestName,
        brand: brand,
        price_text: a.querySelector('[data-qa="plp-product-box-price"]')?.innerText || null,
        express: !!a.querySelector('[data-qa="product-noon-express"]'),
        img: rawImg ? rawImg.split('?')[0] : null,
    };
})"""

async def scrape_noon_eg(page):
    global _noon_rot_idx, _brand_rot_idx
    print("جاري فحص عروض نون مصر...")
    extra_batch = [
        NOON_EXTRA_URLS[(_noon_rot_idx + i) % len(NOON_EXTRA_URLS)]
        for i in range(4)
    ]
    _noon_rot_idx = (_noon_rot_idx + 4) % len(NOON_EXTRA_URLS)

    # إضافة بحث مباشر عن البراندات الساخنة + كل البراندات اللي البوت اتعلمها تلقائياً
    all_noon_brands = list(HOT_BRANDS)
    for lb in learned_prefs.get("brands", []):
        if len(lb) >= 2 and not any(lb.lower() in [k.lower() for k in b[1]] for b in HOT_BRANDS):
            all_noon_brands.append((lb, [lb]))

    brand_urls = []
    for i in range(8):
        b_label, kw_list = all_noon_brands[(_brand_rot_idx + i) % len(all_noon_brands)]
        brand_urls.append((b_label, f"https://www.noon.com/egypt-ar/search/?q={quote_plus(kw_list[0])}"))
    _brand_rot_idx = (_brand_rot_idx + 8) % len(all_noon_brands)

    l_queries = learned_prefs.get("queries", [])
    if l_queries:
        global _learned_rot_idx
        for i in range(min(5, len(l_queries))):
            lq = l_queries[(_learned_rot_idx + i) % len(l_queries)]
            brand_urls.append((None, f"https://www.noon.com/egypt-ar/search/?q={quote_plus(lq)}"))
        _learned_rot_idx = (_learned_rot_idx + 5) % len(l_queries)

    urls_to_scan = [(None, u) for u in (NOON_CORE_URLS + extra_batch)] + brand_urls

    products = {}
    for b_hint, url in urls_to_scan:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_selector('a[href*="/p/"]', timeout=15000)
            except Exception:
                pass
            for _ in range(8):
                for c in await page.evaluate(NOON_CARDS_JS):
                    if c["href"]:
                        base = c["href"].split('?')[0]
                        link = short_link(f"https://www.noon.com{base}" if base.startswith('/') else base)
                        if link not in products:
                            products[link] = c
                        else:
                            if c.get("img") and not products[link].get("img"):
                                products[link]["img"] = c["img"]
                            if c.get("brand") and not products[link].get("brand"):
                                products[link]["brand"] = c["brand"]
                await page.mouse.wheel(0, 650)
                await page.wait_for_timeout(400)
        except Exception as e:
            print(f"تعذر فتح {url}: {e}")
            continue

    print(f"تم العثور على {len(products)} منتج في نون مصر.")

    candidates = []
    for full_link, card in products.items():
        try:
            card_text = card["text"]
            match = re.search(r'(?:خصم\s*(\d+)%|(\d+)%\s*(?:خصم|OFF))', clean(card_text), re.IGNORECASE)
            badge_disc = int(match.group(1) or match.group(2)) if match else None
            info = parse_noon_card(card_text, card.get("price_text"), badge_disc)
            if not info["price"] or info["price"] < 5:
                continue

            prelim_title = card.get("name") or noon_title(card_text)
            c_brand = card.get("brand")
            # فلترة الموثوقية مسبقاً من الكارت لمنع تضييع الوقت في فتح صفحات منتجات غير معروفة
            if not is_trusted_product(prelim_title, brand=c_brand, rating=info["rating"], reviews=info["reviews"]):
                continue

            discount = float(badge_disc or 0)
            if info["list_price"] and info["list_price"] > info["price"]:
                discount = (1 - info["price"] / info["list_price"]) * 100
            if discount <= 0:
                continue

            prev_min, max_p, min_p = record_price(full_link, info["price"])
            freebie = is_almost_free(info["price"], info["list_price"], badge_disc)
            has_card_promo = any(w in card_text for w in ("مع الكوبون", "كوبون", "كود", "وفر ", "اشترِ", "اشتري"))
            famous = has_famous_brand(prelim_title, c_brand)
            saving_egp = (info["list_price"] - info["price"]) if (info["list_price"] and info["list_price"] > info["price"]) else 0

            if famous:
                qualifies = (discount >= 8) or (discount >= 6 and (has_card_promo or saving_egp >= 40)) or freebie
            else:
                qualifies = (discount >= 20) or (discount >= 15 and has_card_promo) or freebie

            ok_prelim, _ = should_send_deal(full_link, prelim_title, info["price"])
            if qualifies and ok_prelim:
                candidates.append((1 if freebie else 0, 1 if famous else 0, 1 if has_card_promo else 0, discount, full_link, card, info, prev_min, max_p, min_p))
        except Exception:
            continue

    # ترتيب العروض: عروض "ببلاش" أولاً، ثم البراندات المشهورة، ثم العروض الإضافية والأعلى خصماً
    candidates.sort(key=lambda x: (x[0], x[1], x[2], x[3]), reverse=True)
    print(f"تم العثور على {len(candidates)} عرض موثوق جديد في نون مصر.")

    noon_sent = 0
    consecutive_blocks = 0
    pdp_lookups = 0
    for _, famous, _, discount, full_link, card, info, prev_min, max_p, min_p in candidates:
        if noon_sent >= MAX_PER_CYCLE:
            break
        try:
            card_title = card.get("name") or noon_title(card["text"])
            full_title, pdp_brand, seller, features, image, page_promos, rev_snippets, extra_ctx = None, None, None, [], None, [], [], {}
            if consecutive_blocks < 3 and pdp_lookups < 28:
                pdp_lookups += 1
                full_title, pdp_brand, seller, features, image, page_promos, rev_snippets, extra_ctx = await noon_product_details(page.context, full_link)
                if features is None:
                    consecutive_blocks += 1
                    features = []
                else:
                    consecutive_blocks = 0

            title = full_title or card_title
            if not title or is_blocked_title(title):
                continue
            brand = pdp_brand or card.get("brand")
            if not is_trusted_product(title, brand=brand, rating=info["rating"], reviews=info["reviews"]):
                continue
            if not seller and card.get("express"):
                seller = "نون (Express)"

            stack_promos, stack_howto, extra_pct, extra_egp, extra_label, promo_links = detect_stacking_promos(
                card["text"], page_promos
            )

            eff_price = info["price"]
            if extra_pct > 0:
                eff_price = round(eff_price * (1 - extra_pct / 100.0), 2)
            elif extra_egp > 0 and eff_price > extra_egp:
                eff_price = round(eff_price - extra_egp, 2)

            promo_sig = "|".join(stack_promos)
            ok_send, update_reason = should_send_deal(full_link, title, eff_price, promo_sig)
            if not ok_send:
                continue

            mark_deal_sent(full_link, title, eff_price, promo_sig)
            noon_sent += 1
            chosen_img_noon = image or card.get("img")
            msg = build_message(
                "Noon", title, info["price"], info["list_price"], discount, full_link,
                seller=seller, rating=info["rating"], reviews=info["reviews"], features=features,
                prev_min=prev_min, max_price=max_p, min_price=min_p,
                review_snippets=rev_snippets, bought_badge=info.get("bought"),
                stack_promos=stack_promos, stack_howto=stack_howto, section_note=update_reason,
                extra_pct=extra_pct, extra_egp=extra_egp, extra_label=extra_label, promo_links=promo_links,
                brand=brand,
                en_slug=extra_ctx.get("en_slug"),
                breadcrumbs=extra_ctx.get("breadcrumbs"),
                specs=extra_ctx.get("specs"),
                image_url=chosen_img_noon,
            )
            is_free_now = is_almost_free(eff_price, info["list_price"], discount)
            await pace_and_send(msg, image=chosen_img_noon, is_freebie=is_free_now)
        except Exception as e:
            print(f"خطأ في منتج نون: {e}")
            continue

# ---------------------------------------------------------------------------
# تحويل روابط المنتجات في الشات الخاص إلى أفلييت القناة ونشرها تلقائياً
# ---------------------------------------------------------------------------
_IGNORE_DOMAINS = (
    "t.me/", "telegram.me/", "telegram.org/", "facebook.com/", "fb.watch/",
    "instagram.com/", "youtube.com/", "youtu.be/", "whatsapp.com/", "wa.me/",
    "twitter.com/", "x.com/", "tiktok.com/",
)

def extract_urls_from_message(msg):
    """يستخرج كل روابط المنتجات أو الروابط المختصرة من الرسالة أو البوست المحوّل (Forwarded)."""
    raw_urls = []
    for field in ("text", "caption"):
        txt = msg.get(field) or ""
        for u in re.findall(r'https?://[^\s<>"\'()]+', txt):
            raw_urls.append(u.rstrip(".,;:!?)>]"))
    for ent_field in ("entities", "caption_entities"):
        for ent in (msg.get(ent_field) or []):
            if ent.get("type") == "text_link" and ent.get("url"):
                raw_urls.append(ent["url"].strip())
    reply_markup = msg.get("reply_markup") or {}
    for row in (reply_markup.get("inline_keyboard") or []):
        for btn in row:
            if isinstance(btn, dict) and btn.get("url"):
                raw_urls.append(btn["url"].strip())

    filtered = []
    for u in raw_urls:
        ul = u.lower()
        if any(d in ul for d in _IGNORE_DOMAINS):
            continue
        if u not in filtered:
            filtered.append(u)
    # ترتيب الروابط بحيث روابط المنتج المباشرة تيجي قبل روابط صفحات العروض الفرعية
    filtered.sort(key=lambda x: (1 if "/promotion/psp/" in x.lower() else 0))
    return filtered

def split_message_into_deals(text, urls):
    """
    يفصل رسالة المستخدم التي تحتوي على أكثر من عرض إلى عروض مستقلة،
    بحيث يرتبط كل رابط بالنص والوصف والأسعار الخاصة به بدقة، تمهيداً لمعالجة كل عرض بمفرده.
    """
    if not urls:
        return []
    unique_urls = []
    for u in urls:
        if u not in unique_urls:
            unique_urls.append(u)
    if len(unique_urls) <= 1:
        return [(unique_urls[0], text)]

    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    chunks_by_url = {}
    cur_chunk = []
    for l in lines:
        cur_chunk.append(l)
        found_u = next((u for u in unique_urls if u in l and u not in chunks_by_url), None)
        if found_u:
            chunks_by_url[found_u] = "\n".join(cur_chunk)
            cur_chunk = []

    out = []
    for u in unique_urls:
        out.append((u, chunks_by_url.get(u, text)))
    return out

def _extract_nested_store_url(url_str):
    """يستخرج أي رابط أمازون أو نون مدفون داخل روابط التحويل أو شبكات الأفلييت مثل Viglink أو Skimlinks."""
    if not url_str:
        return None
    try:
        parsed = urllib.parse.urlparse(url_str)
        qs = urllib.parse.parse_qs(parsed.query)
        for param in ("u", "url", "target", "dest", "redirect", "link", "r", "to", "out"):
            if param in qs and qs[param]:
                val = urllib.parse.unquote(qs[param][0])
                if "noon.com" in val.lower() or "amazon." in val.lower() or "amzn." in val.lower():
                    return val
    except Exception:
        pass
    m = re.search(r'(https?%3A%2F%2F(?:www\.)?(?:amazon\.eg|noon\.com)[^\s&"\'<>]+)', url_str, re.IGNORECASE)
    if m:
        try:
            return urllib.parse.unquote(m.group(1))
        except Exception:
            pass
    m2 = re.search(r'(https?://(?:www\.)?(?:amazon\.eg|noon\.com)[^\s&"\'<>]+)', url_str, re.IGNORECASE)
    if m2:
        return m2.group(1)
    return None

def _strip_foreign_affiliate_params(url):
    """يحذف أي كود أفلييت أو باراميتر تتبع خاص بقنوات أخرى من الرابط."""
    if not url:
        return url
    nested = _extract_nested_store_url(url)
    if nested:
        url = nested
    s = short_link(url)
    if s != url:
        return s
    if "amazon." in url.lower():
        m_asin = re.search(r'([A-Z0-9]{10})', url)
        if m_asin and re.search(r'(?:dp|gp/product|keywords|hidden-keywords|asins)', url, re.IGNORECASE):
            return f"https://www.amazon.eg/dp/{m_asin.group(1).upper()}"
        clean_base = url.split("?")[0].split("#")[0]
        if clean_base.rstrip("/").endswith("amazon.eg") or clean_base.rstrip("/").endswith("/s"):
            return url
        return clean_base
    if "noon.com" in url.lower():
        clean_base = url.split("?")[0].split("#")[0]
        if clean_base.rstrip("/").endswith("noon.com") or clean_base.rstrip("/").endswith("egypt-ar") or clean_base.rstrip("/").endswith("egypt-en"):
            return url
        return clean_base
    return url

async def resolve_original_url(context, raw_url):
    """يفك أي رابط مختصر (مثل tinyurl أو amzn.eu أو sal7.ly أو is.gd أو bit.ly أو viglink) ويجيب الرابط الأصلي الصافي للمنتج."""
    u = (raw_url or "").strip()
    if not u:
        return u

    # 1. فحص فوري لو الرابط نفسه يحتوي على رابط متجر مدفون
    nested = _extract_nested_store_url(u)
    if nested:
        u = nested

    direct = short_link(u)
    if direct != u and ("/dp/" in direct or "/p/" in direct):
        return direct

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ar-EG,ar;q=0.9,en;q=0.8",
    }

    # 2. فحص سريع لهيدر التحويل HEAD قبل الدخول في متصفح أو شبكات تتبع
    try:
        head_r = await asyncio.to_thread(
            requests.head, u, headers=headers, allow_redirects=False, timeout=8
        )
        loc = head_r.headers.get("Location") or ""
        nested_loc = _extract_nested_store_url(loc)
        if nested_loc:
            s = short_link(nested_loc)
            if "/dp/" in s or "/p/" in s:
                return s
            return _strip_foreign_affiliate_params(nested_loc)
        if loc and ("/dp/" in loc or "/p/" in loc):
            return short_link(loc)
    except Exception:
        pass

    # 3. فحص بالـ GET مع استخراج الرابط من الـ body
    try:
        r = await asyncio.to_thread(
            requests.get, u, headers=headers, allow_redirects=True, timeout=12
        )
        final_u = r.url or u
        nested_final = _extract_nested_store_url(final_u)
        if nested_final:
            final_u = nested_final
        s = short_link(final_u)
        if "/dp/" in s or "/p/" in s:
            return s
        body = r.text or ""
        nested_body = _extract_nested_store_url(body)
        if nested_body:
            s_body = short_link(nested_body)
            if "/dp/" in s_body or "/p/" in s_body:
                return s_body
        if "amazon." not in final_u.lower() and "noon.com" not in final_u.lower():
            m_amz = re.search(r'https?://(?:www\.)?amazon\.eg[^\s"\'<>]+/(?:dp|gp/product)/([A-Z0-9]{10})', body, re.IGNORECASE)
            if m_amz:
                return f"https://www.amazon.eg/dp/{m_amz.group(1).upper()}"
            m_noon = re.search(r'https?://(?:www\.)?noon\.com/[^\s"\'<>]*?/([A-Z0-9]{8,})/p', body, re.IGNORECASE)
            if m_noon:
                return f"https://www.noon.com/egypt-ar/{m_noon.group(1).upper()}/p/"
        if "amazon." in final_u.lower() or "noon.com" in final_u.lower():
            return _strip_foreign_affiliate_params(final_u)
    except Exception:
        pass

    # 4. لو الرابط المختصر بيستخدم تحويل JavaScript أو Cloudflare، نفتحه بالمتصفح
    if context is not None:
        page = await context.new_page()
        try:
            await page.goto(u, wait_until="domcontentloaded", timeout=25000)
            for _ in range(8):
                cur = page.url
                nested_cur = _extract_nested_store_url(cur)
                if nested_cur:
                    cur = nested_cur
                s = short_link(cur)
                if "/dp/" in s or "/p/" in s:
                    return s
                if ("amazon." in cur.lower() or "noon.com" in cur.lower()) and cur != u:
                    await page.wait_for_timeout(800)
                    return _strip_foreign_affiliate_params(page.url)
                await page.wait_for_timeout(600)
            return _strip_foreign_affiliate_params(page.url)
        except Exception as e:
            print(f"تعذر فك الرابط بالمتصفح ({u}): {e}")
        finally:
            await page.close()
    return _strip_foreign_affiliate_params(u)

def _parse_fallback_message_info(text):
    """يستخرج الاسم والسعر القديم والجديد احتياطياً لو المستخدم محوّل بوست جاهز وصفحة المنتج محجوبة."""
    t = clean(text or "")
    old_m = re.search(r'(?:السعر القديم|بدلاً من|بدل من|سعر القائمه|سعر القائمة|كان|السابق|كنت جايبه ب|جايبه ب)\s*:?\s*([\d,]+(?:\.\d+)?)', t)

    # تفضيل السعر المرتبط بكلمات صريحة (سعره / السعر النهائي / السعر الجديد / سعر العرض / بسعر)
    deal_matches = re.findall(r'(?:السعر الحالي|السعر النهائي|سعر العرض|السعر الجديد|سعره|بسعر|السعر)\s*:?\s*([\d,]+(?:\.\d+)?)', t)
    new_price = to_float(deal_matches[-1]) if deal_matches else None

    if not new_price:
        gen_m = re.findall(r'([\d,]+(?:\.\d+)?)\s*(?:ج\.م|جنيه|جنية|ج|EGP|LE)', t, re.IGNORECASE)
        if gen_m:
            prices = [to_float(x) for x in gen_m if to_float(x)]
            if prices:
                new_price = min(prices)

    disc_m = re.search(r'(\d+)\s*%', t)
    title_cand = None
    HYPE_PREFIXES = (
        "اتوفر من تاني", "اتوفّر من تاني", "رجع توفر", "رجع من تاني", "توفر من تاني",
        "الحق العرض", "عرض نار", "خصم جبار", "سعر لقطة", "عرض لقطة", "ببلاش",
        "فرصة لا تعوض", "عاجل", "تنبيه", "كود خصم", "كوبون خصم", "وصل حديثاً"
    )
    for line in [l.strip() for l in t.split('\n') if l.strip()]:
        clean_l = re.sub(r'^[📦🔥🟡🚨🏷️✨•\-🏃‍♂️🏃‍♀️🏃]+\s*', '', line).strip()
        # تجاهل الأسطر التي تمثل مجرد عبارات ترويجية/حماسية ولا تصف منتج
        if any(hp in clean_l for hp in HYPE_PREFIXES) and not any(dev in clean_l.lower() for dev in ("موبايل", "سماعة", "شاحن", "لابتوب", "شاشة", "ساعة", "phone", "iphone", "samsung")):
            continue
        # حذف السعر لو كان ملحقاً في نفس السطر (مثل: موبايل iPhone 17 بسعر 66949 جنيه)
        clean_l = re.sub(r'(?:بسعر|بـ|سعر)\s*:?\s*[\d,]+(?:\.\d+)?\s*(?:ج\.م|جنيه|جنية|ج|EGP|LE)?', '', clean_l).strip()
        clean_l = clean_l.rstrip(":-• ")
        if (
            len(clean_l) >= 4
            and not clean_l.startswith("http")
            and not any(w in clean_l for w in ("السعر", "سعره", "إجمالي الخصم", "الخصم:", "البائع:", "التقييم:", "على أمازون", "على نون", "رابط العرض", "ملحوظة:", "لينك الشراء", "هنا:"))
        ):
            title_cand = clean_l[:140]
            break
    return {
        "title": title_cand,
        "price": new_price,
        "list_price": to_float(old_m.group(1)) if old_m else None,
        "discount": float(disc_m.group(1)) if disc_m else 0.0,
    }

async def scrape_single_product(context, raw_url, fallback_text="", fallback_image=None, is_user_submission=False):
    """
    يستقبل أي رابط منتج (أمازون أو نون أو رابط مختصر)، يستخرج الرابط الأصلي الصافي،
    يسحب كل بيانات المنتج، يضيف كود الأفلييت الخاص بالقناة، ويبني الرسالة الكاملة.
    """
    canonical_url = await resolve_original_url(context, raw_url)
    fb = _parse_fallback_message_info(fallback_text)
    ul = canonical_url.lower()

    if "amazon." in ul or "amzn." in ul:
        page = await context.new_page()
        try:
            await page.goto(canonical_url, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_selector('#productTitle, #title', timeout=10000)
            except Exception:
                await page.wait_for_timeout(2500)
            if "/dp/" not in canonical_url:
                canonical_url = _strip_foreign_affiliate_params(page.url)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.55)")
            await page.wait_for_timeout(1000)
            data = await page.evaluate("""() => {
                const q = s => document.querySelector(s)?.innerText?.trim();
                const title = q('#productTitle') || q('#title') || document.querySelector('meta[property="og:title"]')?.content || '';
                const priceSelectors = [
                    '#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen',
                    '#corePriceDisplay_desktop_feature_div .a-price:not(.a-text-price) .a-offscreen',
                    '#corePrice_desktop .a-price:not(.a-text-price) .a-offscreen',
                    '#corePrice_feature_div .a-price .a-offscreen',
                    '#apex_desktop .priceToPay .a-offscreen',
                    '#apex_desktop .a-price:not(.a-text-price) .a-offscreen',
                    '.apexPriceToPay .a-offscreen',
                    '#priceblock_dealprice',
                    '#priceblock_ourprice',
                    '#priceblock_saleprice',
                    '#price_inside_buybox',
                    '#newBuyBoxPrice',
                    '#tp_price_block_total_price_ww .a-offscreen',
                    '#ppd .a-price:not(.a-text-price) .a-offscreen',
                    'span[data-a-color="price"] span.a-offscreen',
                    '#olpLinkWidget_feature_div .a-price .a-offscreen',
                    '#olp_feature_div .a-price .a-offscreen',
                    '#buybox-see-all-buying-choices .a-color-price',
                    '#all-offers-display-scroller .a-price .a-offscreen',
                    '#aod-pinned-offer .a-price .a-offscreen',
                    '#aod-price-1 .a-price .a-offscreen',
                    'span.a-color-price',
                ];
                let priceTxt = priceSelectors.map(q).find(x => x && /\\d/.test(x)) || null;
                if (!priceTxt) {
                    const whole = q('#corePriceDisplay_desktop_feature_div .priceToPay .a-price-whole')
                        || q('#apex_desktop .priceToPay .a-price-whole')
                        || q('#corePrice_desktop .a-price-whole')
                        || q('.priceToPay .a-price-whole');
                    const frac = q('#corePriceDisplay_desktop_feature_div .priceToPay .a-price-fraction') || '00';
                    if (whole) priceTxt = whole.replace(/[^0-9,]/g, '') + '.' + frac.replace(/[^0-9]/g, '');
                }
                if (!priceTxt) {
                    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                        try {
                            const j = JSON.parse(s.textContent);
                            const off = Array.isArray(j?.offers) ? j.offers[0] : j?.offers;
                            if (off?.price) { priceTxt = String(off.price); break; }
                        } catch(e) {}
                    }
                }
                if (!priceTxt) {
                    priceTxt = document.querySelector('meta[property="og:price:amount"]')?.content || document.querySelector('meta[name="twitter:data1"]')?.content;
                }
                if (!priceTxt) {
                    const centerTxt = document.querySelector('#centerCol, #dp, #ppd')?.innerText || '';
                    const mPrice = centerTxt.match(/(?:EGP|جنيه)\\s*([\\d,]+(?:\\.\\d+)?)/i)
                        || centerTxt.match(/([\\d,]+(?:\\.\\d+)?)\\s*(?:EGP|جنيه)/i);
                    if (mPrice) priceTxt = mPrice[1];
                }
                const listSelectors = [
                    '#corePriceDisplay_desktop_feature_div .basisPrice .a-offscreen',
                    '#corePriceDisplay_desktop_feature_div span[data-a-strike="true"] .a-offscreen',
                    '#corePrice_desktop .basisPrice .a-offscreen',
                    '#apex_desktop .basisPrice .a-offscreen',
                    '#apex_desktop span[data-a-strike="true"] .a-offscreen',
                    '.basisPrice .a-offscreen',
                    '#price .a-text-price .a-offscreen',
                    'span[data-a-strike="true"] .a-offscreen',
                ];
                let listTxt = listSelectors.map(q).find(x => x && /\\d/.test(x)) || null;
                if (!listTxt) {
                    const centerTxt = document.querySelector('#centerCol, #dp, #ppd')?.innerText || '';
                    const mWas = centerTxt.match(/(?:Was:|السعر السابق:|سعر القائمة:)\\s*(?:EGP|جنيه)?\\s*([\\d,]+(?:\\.\\d+)?)/i)
                        || centerTxt.match(/(?:Was:|السعر السابق:|سعر القائمة:)\\s*([\\d,]+(?:\\.\\d+)?)\\s*(?:EGP|جنيه)?/i);
                    if (mWas) listTxt = mWas[1];
                }
                const savingsTxt = q('#corePriceDisplay_desktop_feature_div .savingsPercentage') || q('.savingsPercentage');
                const bought = q('#social-proofing-faceout-title-tk_bought');
                const seller = q('#sellerProfileTriggerId')
                    || q('#merchantInfoFeature_feature_div .offer-display-feature-text-message')
                    || q('#merchant-info a') || q('#merchant-info');
                let brand = q('tr.po-brand td.a-span9') || q('#bylineInfo');
                if (brand) {
                    brand = brand
                        .replace(/^(قم بزيارة متجر|زيارة متجر|العلامة التجارية:|الماركة:|Visit the|Brand:)\\s*/i, '')
                        .replace(/\\s*Store$/i, '')
                        .trim();
                }
                const ratingTxt = document.querySelector('#acrPopover')?.getAttribute('title') || q('#acrPopover .a-size-base');
                const reviewsTxt = q('#acrCustomerReviewText');
                const feats = [...document.querySelectorAll('#feature-bullets li span.a-list-item')]
                    .map(e => e.innerText.trim()).filter(x => x.length > 10);
                const overview = (q('#productDescription') || '').replace(/\\s+/g, ' ').trim();
                if (!feats.length && overview.length > 20) {
                    feats.push(overview.slice(0, 220));
                }
                const breadcrumbs = [...document.querySelectorAll('#wayfinding-breadcrumbs_feature_div li a, #wayfinding-breadcrumbs_container a')]
                    .map(e => e.innerText.trim()).filter(Boolean);
                const specs = [...document.querySelectorAll('#productOverview_feature_div tr, #prodDetails tr, #technicalSpecifications_section_1 tr')]
                    .map(r => r.innerText.replace(/\\s+/g, ' ').trim()).filter(x => x.length > 3 && x.length < 140).slice(0, 18);
                const en_slug = document.querySelector('link[rel="alternate"][hreflang="en-eg"], link[rel="alternate"][href*="/-/en/"], link[rel="canonical"]')?.href || '';
                const img = document.querySelector('#landingImage, #imgBlkFront, #main-image, #imgTagWrapperId img');
                let image = img?.getAttribute('data-old-hires');
                if (!image || !image.startsWith('http')) {
                    const dyn = img?.getAttribute('data-a-dynamic-image');
                    if (dyn) {
                        try { image = Object.keys(JSON.parse(dyn))[0]; } catch (e) {}
                    }
                }
                if (!image || !image.startsWith('http')) {
                    image = [
                        img?.currentSrc,
                        img?.getAttribute('src'),
                        document.querySelector('meta[property="og:image"]')?.content,
                        ...[...document.querySelectorAll('#altImages img, #imageBlock img')].map(i => i.src)
                    ].find(u => u && u.startsWith('http') && !u.includes('play-button') && !u.includes('transparent-pixel'));
                }
                const promos = [
                    ...document.querySelectorAll(
                        '#promoPriceBlockMessage_feature_div .promoPriceBlockMessage > div, ' +
                        '#promoPriceBlockMessage_feature_div .a-section, ' +
                        '#promoPriceBlockMessage_feature_div, #couponBadgeRegularVpc, [id*="coupon" i], #sopp_feature_div'
                    )
                ].map(e => e.innerText.trim()).filter(x => x && x.length > 5 && x.length < 1500);
                const promo_links = [...new Set(
                    [...document.querySelectorAll('#promoPriceBlockMessage_feature_div a[href*="/promotion/psp/"], a[href*="/promotion/psp/"]')]
                        .map(a => a.href.split('&ref=')[0].split('?ref=')[0])
                        .filter(Boolean)
                )];
                const revs = [...document.querySelectorAll('[data-hook="reviewText"], [data-hook="review-collapsed"], .review-text-content')]
                    .map(e => e.innerText.trim()).filter(x => x.length > 15).slice(0, 3);
                
                // فحص دقيق للتوفر الفعلي في المخزون وعدم الخلط بين قيود شحن السيرفر والنفاد الحقيقي
                const hasAddToCart = Boolean(
                    document.querySelector(
                        '#add-to-cart-button, #buy-now-button, input[name="submit.add-to-cart"], ' +
                        '#buybox-see-all-buying-choices, #addToCart, form[action*="/cart/add"], ' +
                        'a[href*="/offer-listing/"], #all-offers-display, #olpLinkWidget_feature_div'
                    )
                );
                const outOfStockBox = Boolean(document.querySelector('#outOfStock, .out-of-stock'));
                const availTxt = (document.querySelector('#availability, #availability_feature_div')?.innerText || '').trim();
                const isExplicitlyUnavailable = /غير متوفر حالياً|غير متوفر مؤقتاً|currently unavailable/i.test(availTxt);
                const isShippingRestrictionOnly = /غير متوفر للشحن|غير متاح للشحن|لا يمكن شحن|cannot be shipped|delivery location|التوصيل إلى موقعك|موقع التوصيل المحدد/i.test(availTxt);

                let isOutOfStock = false;
                if (hasAddToCart) {
                    isOutOfStock = false;
                } else if (outOfStockBox || (isExplicitlyUnavailable && !isShippingRestrictionOnly)) {
                    isOutOfStock = true;
                }
                return {title, priceTxt, listTxt, savingsTxt, bought, seller, brand, ratingTxt, reviewsTxt, feats, breadcrumbs, specs, en_slug, image, promos: promos.slice(0, 10), promo_links: promo_links.slice(0, 2), revs, isOutOfStock, hasAddToCart};
            }""")
        finally:
            await page.close()

        raw_t = data.get("title") or ""
        p_m = re.search(r'([\d,]+(?:\.\d+)?)', clean(data.get("priceTxt") or ""))
        l_m = re.search(r'([\d,]+(?:\.\d+)?)', clean(data.get("listTxt") or ""))
        price = to_float(p_m.group(1)) if p_m else None
        list_price = to_float(l_m.group(1)) if l_m else None
        r_m = re.search(r'(\d\.\d)', clean(data.get("ratingTxt") or ""))
        rating = r_m.group(1) if r_m else None
        rv_m = re.search(r'([\d,]+)', clean(data.get("reviewsTxt") or ""))
        reviews = rv_m.group(1) if rv_m else None
        brand = data.get("brand")
        seller = data.get("seller")
        features = data.get("feats") or []
        image = clean_image_url(data.get("image"))
        promos_list = data.get("promos") or []
        promo_links = data.get("promo_links") or []
        rev_snippets = data.get("revs") or []
        bought_badge = data.get("bought")

        # لو صفحة المنتج في أمازون محجوبة على السحابة أو الصورة/السعر مظهروش أو ظهرت رسالة نفاد وهمية بسبب السيرفر الخارجي، نجيبهم فوراً من بحث أمازون بالـ ASIN (مبيتحجبش أبداً)
        live_price_found = bool(price)
        asin_m = re.search(r'/dp/([A-Z0-9]{10})', canonical_url, re.IGNORECASE)
        if asin_m and (not image or not price or not raw_t or is_blocked_title(raw_t) or data.get("isOutOfStock")):
            asin_code = asin_m.group(1).upper()
            spage = await context.new_page()
            try:
                await spage.goto(f"https://www.amazon.eg/s?k={asin_code}", wait_until="domcontentloaded", timeout=35000)
                await spage.wait_for_timeout(1500)
                sdata = await spage.evaluate("""(asin) => {
                    const c = document.querySelector(`div[data-asin="${asin}"]`)
                        || document.querySelector('div[data-component-type="s-search-result"]');
                    if (!c) return null;
                    return {
                        title: c.querySelector('h2')?.innerText?.trim(),
                        price: c.querySelector('.a-price:not(.a-text-price) .a-offscreen')?.innerText
                            || c.querySelector('.a-price .a-offscreen')?.innerText
                            || c.querySelector('.a-color-price')?.innerText,
                        list_price: c.querySelector('.a-price.a-text-price .a-offscreen')?.innerText
                            || c.querySelector('span[data-a-strike="true"] .a-offscreen')?.innerText,
                        rating: c.querySelector('i[class*="a-icon-star"] span.a-icon-alt, span[aria-label*="من 5"]')?.innerText,
                        reviews: c.querySelector('a[href*="#customerReviews"] span, span.s-underline-text')?.innerText,
                        img: c.querySelector('img.s-image')?.src
                    };
                }""", asin_code)
                if sdata:
                    if (not raw_t or is_blocked_title(raw_t)) and sdata.get("title"):
                        raw_t = sdata["title"]
                    if not price and sdata.get("price"):
                        spm = re.search(r'([\d,]+(?:\.\d+)?)', clean(sdata["price"]))
                        if spm:
                            price = to_float(spm.group(1))
                            live_price_found = True
                    if not list_price and sdata.get("list_price"):
                        slm = re.search(r'([\d,]+(?:\.\d+)?)', clean(sdata["list_price"]))
                        if slm:
                            list_price = to_float(slm.group(1))
                    if not rating and sdata.get("rating"):
                        srm = re.search(r'(\d[.,]\d)', clean(sdata["rating"]))
                        if srm:
                            rating = srm.group(1).replace(",", ".")
                    if not reviews and sdata.get("reviews"):
                        srvm = re.search(r'([\d,]+)', clean(sdata["reviews"]))
                        if srvm:
                            reviews = srvm.group(1)
                    if not image and sdata.get("img"):
                        image = clean_image_url(sdata["img"])
                    if sdata.get("price"):
                        data["isOutOfStock"] = False
            except Exception as se:
                print(f"تعذر جلب بيانات ASIN الاحتياطية من البحث: {se}")
            finally:
                await spage.close()

        title = (raw_t if raw_t and not is_blocked_title(raw_t) else fb["title"]) or "منتج مميز على أمازون مصر"
        price = price or fb["price"]
        list_price = list_price or fb["list_price"]
        image = image or fallback_image
        s_m = re.search(r'(\d+)\s*%', clean(data.get("savingsTxt") or ""))
        discount = float(s_m.group(1)) if s_m else (fb["discount"] or 0.0)
        if price and list_price and list_price > price:
            discount = (1 - price / list_price) * 100
        elif price and discount > 0 and not list_price:
            list_price = round(price / (1 - discount / 100.0), 2)

        prev_min, max_p, min_p = record_price(canonical_url, price) if price else (None, None, None)
        clean_fb_text = "\n".join(
            l for l in (fallback_text or "").splitlines()
            if "http" not in l.lower() and "هنا:" not in l
        )
        stack_promos, stack_howto, extra_pct, extra_egp, extra_label, promo_links = detect_stacking_promos(
            "" if promos_list else clean_fb_text, promos_list, promo_links
        )
        eff_price = price
        if eff_price and extra_pct > 0:
            eff_price = round(eff_price * (1 - extra_pct / 100.0), 2)
        elif eff_price and extra_egp > 0 and eff_price > extra_egp:
            eff_price = round(eff_price - extra_egp, 2)

        # 🧠 التعلم من أي منتج يمر على البوت (الماركة وفئة المنتج) حتى لو العرض منتهي
        learn_from_product(title, brand)
        custom_insight = rewrite_channel_insight(fallback_text)

        # 🔎 التحقق الصارم أن العرض لسه متاح وساري على المتجر
        has_add_to_cart = data.get("hasAddToCart")
        is_out_of_stock = data.get("isOutOfStock") and not has_add_to_cart
        is_available = not is_out_of_stock
        if live_price_found:
            is_available = True
        if is_user_submission and price and price > 0:
            is_available = True
        elif not live_price_found and not fb.get("price"):
            is_available = False

        if not is_available and canonical_url in price_history:
            price_history[canonical_url]["was_out_of_stock"] = True
            save_history()

        is_active, active_reason = is_deal_currently_active(
            price, list_price, discount, is_available=is_available,
            stack_promos=stack_promos, extra_pct=extra_pct, extra_egp=extra_egp,
            brand=brand, title=title, prev_min=prev_min,
            is_user_submission=is_user_submission
        )

        msg = build_message(
            "Amazon", title, price, list_price, discount, canonical_url,
            seller=seller, rating=rating, reviews=reviews, features=features,
            prev_min=prev_min, max_price=max_p, min_price=min_p,
            review_snippets=rev_snippets, bought_badge=bought_badge,
            stack_promos=stack_promos, stack_howto=stack_howto,
            extra_pct=extra_pct, extra_egp=extra_egp, extra_label=extra_label, promo_links=promo_links,
            brand=brand, custom_insight=custom_insight,
            en_slug=data.get("en_slug") or canonical_url,
            breadcrumbs=data.get("breadcrumbs"),
            specs=data.get("specs"),
            image_url=image,
        )
        brand_en_out = pi.normalize_brand_english(brand, title=title, allow_network=False) or brand
        return msg, image, canonical_url, branded_url(canonical_url), title, eff_price, "|".join(stack_promos), is_active, active_reason, brand_en_out

    if "noon.com" in ul:
        page = await context.new_page()
        try:
            await page.goto(canonical_url, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_selector('[data-qa="pdp-product-name"], h1', timeout=10000)
            except Exception:
                await page.wait_for_timeout(3000)
            if "/p/" not in canonical_url:
                canonical_url = _strip_foreign_affiliate_params(page.url)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
            await page.wait_for_timeout(900)
            data = await page.evaluate("""() => {
                const h1El = document.querySelector('[data-qa="pdp-product-name"]') || document.querySelector('h1');
                const full_title = h1El?.innerText?.trim() || document.querySelector('meta[property="og:title"]')?.content || '';
                let brand = document.querySelector('[data-qa*="brand" i], a[class*="brand" i]')?.innerText;
                if (!brand && h1El?.previousElementSibling) {
                    const prevTxt = (h1El.previousElementSibling.innerText || '').replace(/[>›]/g, '').trim();
                    if (prevTxt.length >= 2 && prevTxt.length <= 35 && !prevTxt.includes('عرض')) {
                        brand = prevTxt;
                    }
                }
                let ldPrice = null, ldRating = null, ldReviews = null;
                for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                    try {
                        const j = JSON.parse(s.textContent);
                        const b = j?.brand?.name || (typeof j?.brand === 'string' ? j.brand : null);
                        if (!brand && b) brand = b;
                        const off = Array.isArray(j?.offers) ? j.offers[0] : j?.offers;
                        if (off?.price && !ldPrice) ldPrice = String(off.price);
                        if (j?.aggregateRating?.ratingValue) ldRating = String(j.aggregateRating.ratingValue);
                        if (j?.aggregateRating?.reviewCount) ldReviews = String(j.aggregateRating.reviewCount);
                    } catch (e) {}
                }

                let nextPrice = null, nextWas = null, nextTitle = null, nextBrand = null, nextImage = null;
                try {
                    const nextEl = document.querySelector('#__NEXT_DATA__');
                    if (nextEl) {
                        const nj = JSON.parse(nextEl.textContent);
                        const prod = nj?.props?.pageProps?.catalog?.product
                            || nj?.props?.pageProps?.product
                            || nj?.props?.pageProps?.initialData?.product;
                        if (prod) {
                            if (prod.price) nextPrice = String(prod.price);
                            if (prod.sale_price) nextPrice = String(prod.sale_price);
                            if (prod.was_price) nextWas = String(prod.was_price);
                            if (prod.name) nextTitle = prod.name;
                            if (prod.brand) nextBrand = prod.brand;
                            if (prod.image_keys && prod.image_keys[0]) {
                                nextImage = 'https://f.nooncdn.com/p/' + prod.image_keys[0] + '.jpg';
                            }
                        }
                    }
                } catch (e) {}

                if (!brand && nextBrand) brand = nextBrand;
                if (!full_title && nextTitle) full_title = nextTitle;
                if (brand) brand = brand.replace(/[>›]/g, '').split('\\n')[0].trim();

                let priceNow = document.querySelector('[data-qa="div-price-now"], [class*="priceNow" i], [data-qa*="price-now" i], .priceNow')?.innerText
                    || nextPrice || ldPrice;
                let priceWas = document.querySelector('[data-qa="div-price-was"], [class*="priceWas" i], [class*="oldPrice" i], .priceWas')?.innerText
                    || nextWas || null;

                if (!priceNow) {
                    const containerTxt = document.querySelector('[data-qa="pdp-container"], #__next, body')?.innerText || '';
                    const mPrice = containerTxt.match(/(?:EGP|جنيه)\\s*([\\d,]+(?:\\.\\d+)?)/i)
                        || containerTxt.match(/([\\d,]+(?:\\.\\d+)?)\\s*(?:EGP|جنيه)/i);
                    if (mPrice) priceNow = mPrice[1];
                }
                if (!priceWas) {
                    const containerTxt = document.querySelector('[data-qa="pdp-container"], #__next, body')?.innerText || '';
                    const mWas = containerTxt.match(/(?:Was:|السعر السابق:|سعر القائمة:)\\s*(?:EGP|جنيه)?\\s*([\\d,]+(?:\\.\\d+)?)/i)
                        || containerTxt.match(/(?:Was:|السعر السابق:|سعر القائمة:)\\s*([\\d,]+(?:\\.\\d+)?)\\s*(?:EGP|جنيه)?/i);
                    if (mWas) priceWas = mWas[1];
                }

                const savingTxt = document.querySelector('[data-qa="div-price-saving"], [class*="priceSaving" i], [class*="profit" i]')?.innerText || null;
                const ratingTxt = ldRating || document.querySelector('[data-qa*="rating" i], [class*="ratingValue" i]')?.innerText || null;
                const reviewsTxt = ldReviews || document.querySelector('[data-qa*="review-count" i], [class*="count" i]')?.innerText || null;
                let image = document.querySelector('meta[property="og:image"]')?.content || nextImage;
                if (!image || !image.startsWith('http')) {
                    image = [...document.querySelectorAll('img')]
                        .map(i => i.currentSrc || i.src || i.getAttribute('data-src'))
                        .find(s => s && s.includes('nooncdn.com/p/'));
                }
                let seller = null;
                for (const el of document.querySelectorAll('a[href*="seller"], [class*="seller" i], [class*="partner" i], div, span')) {
                    const t = (el.innerText || '').trim();
                    if (t.startsWith('يتم البيع عبر') || t.startsWith('البائع')) {
                        seller = t.split('\\n')[0].replace('يتم البيع عبر', '').replace('البائع:', '').replace('البائع', '').trim();
                        if (seller) break;
                    }
                }
                const container = document.querySelector('[data-qa="pdp-container"]');
                const feats = container
                    ? [...container.querySelectorAll('ul li')]
                        .filter(e => !e.querySelector('a') && !e.closest('a') && !e.closest('header') && !e.closest('nav') && !e.closest('footer'))
                        .map(e => e.innerText.trim())
                        .filter(x => x.length > 20 && x.length < 220 && !x.includes('\\n'))
                    : [];
                const overview = (container?.querySelector('[data-qa*="overview" i], [class*="overview" i]')?.innerText || '')
                    .replace(/^(نظرة عامة|المميزات الأساسية|Overview)\\s*/i, '')
                    .replace(/\\s+/g, ' ').trim();
                if (!feats.length && overview.length > 25) {
                    feats.push(overview.slice(0, 220));
                }
                const breadcrumbs = [...document.querySelectorAll('[data-qa*="breadcrumb" i] a, nav[aria-label*="breadcrumb" i] a, [class*="breadcrumb" i] a')]
                    .map(e => e.innerText.trim()).filter(Boolean);
                const specs = [...(container || document).querySelectorAll('table tr')]
                    .map(r => r.innerText.replace(/\\s+/g, ' ').trim()).filter(x => x.length > 3 && x.length < 140).slice(0, 18);
                const en_slug = document.querySelector('link[rel="alternate"][hreflang*="en"], link[rel="alternate"][href*="-en/"]')?.href || '';
                const promos = container
                    ? [...container.querySelectorAll('[class*="coupon" i], [class*="voucher" i], [class*="promo" i], [data-qa*="coupon" i], [class*="cashback" i]')]
                        .map(e => e.innerText.trim()).filter(x => x.length > 6 && x.length < 220)
                    : [];
                const revs = [...document.querySelectorAll('[class*="reviewComment" i], [class*="reviewDesc" i], [data-qa*="review" i] p')]
                    .map(e => e.innerText.trim())
                    .filter(x => x.length > 15 && x.length < 220 && !x.includes('لو اشتريت منتج من نون') && !x.includes('تقديم التقييم'))
                    .slice(0, 2);
                const hasAddToCart = Boolean(
                    document.querySelector('button[data-qa="btn-add-to-cart"]:not([disabled]), button[class*="addToCart" i]:not([disabled])')
                );
                const unavailEl = document.querySelector('[data-qa="pdp-out-of-stock"], [class*="outOfStock" i], [class*="soldOut" i]');
                const unavailTxt = (unavailEl?.innerText || document.querySelector('[data-qa*="stock" i]')?.innerText || '').trim();
                const isExplicitlyUnavailable = /غير متوفر|نفدت|out of stock|sold out/i.test(unavailTxt);
                let isOutOfStock = false;
                if (hasAddToCart) {
                    isOutOfStock = false;
                } else if (unavailEl || isExplicitlyUnavailable) {
                    isOutOfStock = true;
                }
                return {full_title, brand, seller, priceNow, priceWas, savingTxt, ratingTxt, reviewsTxt, feats, breadcrumbs, specs, en_slug, image, promos: promos.slice(0, 5), revs, isOutOfStock, hasAddToCart};
            }""")
        finally:
            await page.close()

        raw_t = data.get("full_title") or ""
        title = (raw_t if raw_t and not is_blocked_title(raw_t) else fb["title"]) or "منتج مميز على نون مصر"
        p_m = re.search(r'([\d,]+(?:\.\d+)?)', clean(data.get("priceNow") or ""))
        l_m = re.search(r'([\d,]+(?:\.\d+)?)', clean(data.get("priceWas") or ""))
        live_price_found = bool(p_m)
        price = to_float(p_m.group(1)) if p_m else fb["price"]
        list_price = to_float(l_m.group(1)) if l_m else fb["list_price"]
        s_m = re.search(r'(\d+)\s*%', clean(data.get("savingTxt") or ""))
        discount = float(s_m.group(1)) if s_m else (fb["discount"] or 0.0)
        if price and list_price and list_price > price:
            discount = (1 - price / list_price) * 100
        elif price and discount > 0 and not list_price:
            list_price = round(price / (1 - discount / 100.0), 2)

        r_m = re.search(r'(\d\.\d)', clean(data.get("ratingTxt") or ""))
        rating = r_m.group(1) if r_m else None
        rv_m = re.search(r'([\d.,]+K?)', clean(data.get("reviewsTxt") or ""))
        reviews = rv_m.group(1) if rv_m else None
        brand = data.get("brand")
        seller = data.get("seller") or "نون (Express)"
        features = data.get("feats") or []
        image = clean_image_url(data.get("image")) or fallback_image
        promos_list = data.get("promos") or []
        rev_snippets = data.get("revs") or []

        prev_min, max_p, min_p = record_price(canonical_url, price) if price else (None, None, None)
        # بالنسبة لنون: لا نعتمد أكواد الخصم الخارجية أو الخاصة بقنوات تانية، وننشر العرض بخصمه المباشر من المتجر
        stack_promos, stack_howto, extra_pct, extra_egp, extra_label, promo_links = detect_stacking_promos(
            "", promos_list
        )
        eff_price = price
        if eff_price and extra_pct > 0:
            eff_price = round(eff_price * (1 - extra_pct / 100.0), 2)
        elif eff_price and extra_egp > 0 and eff_price > extra_egp:
            eff_price = round(eff_price - extra_egp, 2)

        # 🧠 التعلم من أي منتج يمر على البوت (الماركة وفئة المنتج) حتى لو العرض منتهي
        learn_from_product(title, brand)
        custom_insight = rewrite_channel_insight(fallback_text)

        # 🔎 التحقق الصارم أن العرض لسه متاح وساري على المتجر
        has_add_to_cart = data.get("hasAddToCart")
        is_out_of_stock = data.get("isOutOfStock") and not has_add_to_cart
        is_available = not is_out_of_stock
        if live_price_found:
            is_available = True
        if is_user_submission and price and price > 0:
            is_available = True
        elif not live_price_found and not fb.get("price"):
            is_available = False

        if not is_available and canonical_url in price_history:
            price_history[canonical_url]["was_out_of_stock"] = True
            save_history()

        is_active, active_reason = is_deal_currently_active(
            price, list_price, discount, is_available=is_available,
            stack_promos=stack_promos, extra_pct=extra_pct, extra_egp=extra_egp,
            brand=brand, title=title, prev_min=prev_min,
            is_user_submission=is_user_submission
        )

        msg = build_message(
            "Noon", title, price, list_price, discount, canonical_url,
            seller=seller, rating=rating, reviews=reviews, features=features,
            prev_min=prev_min, max_price=max_p, min_price=min_p,
            review_snippets=rev_snippets,
            stack_promos=stack_promos, stack_howto=stack_howto,
            extra_pct=extra_pct, extra_egp=extra_egp, extra_label=extra_label, promo_links=promo_links,
            brand=brand, custom_insight=custom_insight,
            en_slug=data.get("en_slug") or canonical_url,
            breadcrumbs=data.get("breadcrumbs"),
            specs=data.get("specs"),
            image_url=image,
        )
        brand_en_out = pi.normalize_brand_english(brand, title=title, allow_network=False) or brand
        return msg, image, canonical_url, branded_url(canonical_url), title, eff_price, "|".join(stack_promos), is_active, active_reason, brand_en_out

    return None, None, canonical_url, branded_url(canonical_url), None, None, "", False, "رابط غير مدعوم", None

def extract_telegram_channel_info(text, msg=None):
    """يستخرج اسم قناة تليجرام (ورقم البوست ونوع الرابط) من أي رابط t.me أو معرّف @channel أو رسالة محولة (Forward)."""
    if not text and not msg:
        return None, None, None

    # 1. فحص إذا كانت الرسالة Forward محولة من قناة (سواء في Telegram Bot API الحديث أو القديم)
    if msg:
        fwd_orig = msg.get("forward_origin") or {}
        if fwd_orig.get("type") == "channel":
            c = fwd_orig.get("chat") or {}
            u = (c.get("username") or "").strip().lower()
            msg_id = str(fwd_orig.get("message_id") or "")
            if u:
                return u, msg_id, "public"
            elif c.get("title"):
                return c.get("title"), msg_id, "private_forward"
        fwd_chat = msg.get("forward_from_chat") or {}
        u = (fwd_chat.get("username") or "").strip().lower()
        msg_id = str(msg.get("forward_from_message_id") or "")
        if u:
            return u, msg_id, "public"
        elif fwd_chat.get("title"):
            return fwd_chat.get("title"), msg_id, "private_forward"

    full_text = text or ""
    if msg:
        for ent in (msg.get("entities") or []) + (msg.get("caption_entities") or []):
            if ent.get("type") == "text_link" and ent.get("url"):
                full_text += " " + ent["url"]
            elif ent.get("type") == "url":
                offset = ent.get("offset", 0)
                length = ent.get("length", 0)
                if offset + length <= len(full_text):
                    full_text += " " + full_text[offset:offset+length]

    reserved = {"joinchat", "addstickers", "share", "proxy", "iv", "s", "loqta78", "sosanasbot", "c"}

    # 2. روابط الدعوة الخاصة (+ أو joinchat)
    inv_m = re.search(r'(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/|\+)([A-Za-z0-9_-]+)', full_text, re.I)
    if inv_m:
        return inv_m.group(1), None, "invite"

    # 3. روابط الويب تلجرام web.telegram.org
    web_m = re.search(r'web\.telegram\.org/[ak]/#@?([A-Za-z0-9_]{3,})', full_text, re.I)
    if web_m:
        ch = web_m.group(1).lower()
        if ch not in reserved:
            return ch, None, "public"

    # 4. روابط القنوات العامة t.me أو telegram.me أو telegram.dog
    m = re.search(r'(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/(?:s/)?([A-Za-z0-9_]{3,})(?:/(\d+))?', full_text, re.I)
    if m:
        ch = m.group(1).lower()
        post_num = m.group(2)
        if ch not in reserved:
            return ch, post_num, "public"

    # 5. معرّف @channel
    m2 = re.search(r'(?:^|[\s،,:\"\'(])@([A-Za-z0-9_]{3,})\b', full_text)
    if m2:
        ch = m2.group(1).lower()
        if ch not in reserved:
            return ch, None, "public"

    # 6. كتابة كلمة قناة أو تابع وبعدها المعرف
    m3 = re.search(r'(?:قناة|جروب|شات|تابع)\s+([A-Za-z0-9_]{3,})\b', full_text)
    if m3:
        ch = m3.group(1).lower()
        if ch not in reserved:
            return ch, None, "public"

    return None, None, None

def resolve_telegram_invite_link(invite_hash):
    """يفحص رابط الدعوة ويستخرج اسم القناة ووصفها وإذا كانت قناة عامة بمعرّف."""
    url = f"https://t.me/+{invite_hash}" if not invite_hash.startswith("+") and not invite_hash.startswith("joinchat/") else f"https://t.me/{invite_hash}"
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=10,
        )
        if r.ok:
            title_m = re.search(r'<meta property="og:title" content="([^"]+)"', r.text)
            desc_m = re.search(r'<meta property="og:description" content="([^"]+)"', r.text)
            title = html.unescape(title_m.group(1)).strip() if title_m else ""
            desc = html.unescape(desc_m.group(1)).strip() if desc_m else ""
            uname_m = re.search(r'@([A-Za-z0-9_]{3,})\b', desc + " " + title)
            public_uname = (
                uname_m.group(1).lower()
                if uname_m and uname_m.group(1).lower() not in {"joinchat", "share", "s", "loqta78", "sosanasbot"}
                else None
            )
            return title, desc, public_uname
    except Exception:
        pass
    return "", "", None

def fetch_channel_posts_http(channel_username, specific_post_id=None):
    """استخراج سريع وخفيف لبوستات القناة عبر HTTP المباشر في أقل من ثانية بدون استهلاك متصفح."""
    url = f"https://t.me/s/{channel_username}"
    if specific_post_id:
        url += f"/{specific_post_id}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ar,en;q=0.9",
    }
    try:
        r = requests.get(url, headers=headers, timeout=12)
        if not r.ok:
            return []
    except Exception as e:
        print(f"HTTP fetch error for @{channel_username}: {e}")
        return []

    raw_html = r.text
    msg_chunks = re.findall(
        r'<div class="[^"]*tgme_widget_message\b[^>]*data-post="([^"]+)"[^>]*>(.*?)(?=<div class="[^"]*tgme_widget_message\b|\Z)',
        raw_html,
        re.DOTALL,
    )

    posts = []
    for post_id, chunk in msg_chunks:
        text = ""
        text_m = re.search(
            r'<div class="[^"]*tgme_widget_message_text\b[^>]*>(.*?)</div>\s*(?:<div class="tgme_widget_message_footer"|<div class="tgme_widget_message_info"|<div class="tgme_widget_message_reactions"|\Z)',
            chunk,
            re.DOTALL,
        )
        if text_m:
            raw_t = text_m.group(1)
            raw_t = re.sub(r'<br\s*/?>', '\n', raw_t)
            raw_t = re.sub(r'</p>', '\n', raw_t)
            clean_t = re.sub(r'<[^>]+>', '', raw_t)
            text = html.unescape(clean_t).strip()

        links = []
        for a_href in re.findall(r'href="([^"]+)"', chunk):
            h = a_href.strip()
            if h.startswith("http") and "t.me/" not in h and "telegram.me/" not in h and h not in links:
                links.append(h)

        for ru in re.findall(r'https?://[^\s<>"\'()،]+', text):
            if "t.me/" not in ru and "telegram.me/" not in ru and ru not in links:
                links.append(ru)

        photo = None
        photo_m = re.search(r'background-image\s*:\s*url\([\'"]?(https?:[^\'")]+)[\'"]?\)', chunk)
        if photo_m:
            photo = photo_m.group(1)

        posts.append({
            "postId": post_id,
            "text": text,
            "links": links,
            "photo": photo
        })

    return posts

async def scan_monitored_channels(context, target_channel=None, specific_post_id=None, max_to_post=3, notify_chat_id=None):
    """يتابع القنوات المضافة للتعلم منها، يستخرج العروض المرشحة وتجاربهم الإيجابية، يعيد صياغتها بأسلوبنا، ويحول روابطها للأفلييت الخاص بنا."""
    channels = [target_channel.lower()] if target_channel else list(learned_prefs.get("channels", []))
    if not channels:
        return 0

    total_posted = 0
    for ch in channels:
        if total_posted >= max_to_post:
            break
        print(f"📡 فحص قناة تليجرام المتابعة للتعلم منها: @{ch} ...")

        # 1. محاولة السحب السريع عبر HTTP أولاً
        posts = await asyncio.to_thread(fetch_channel_posts_http, ch, specific_post_id)

        # 2. لو الـ HTTP مجابش بوستات، استخدام متصفح Playwright كخطة احتياطية
        if not posts and context:
            preview_url = f"https://t.me/s/{ch}"
            if specific_post_id:
                preview_url = f"https://t.me/s/{ch}/{specific_post_id}"
            page = await context.new_page()
            try:
                await page.goto(preview_url, wait_until="domcontentloaded", timeout=25000)
                await page.wait_for_timeout(1200)
                posts = await page.evaluate("""() => {
                    const out = [];
                    for (const msgEl of document.querySelectorAll('.tgme_widget_message')) {
                        const postId = msgEl.getAttribute('data-post') || '';
                        const textEl = msgEl.querySelector('.tgme_widget_message_text');
                        const text = textEl ? textEl.innerText.trim() : '';
                        const links = [];
                        if (textEl) {
                            for (const a of textEl.querySelectorAll('a[href]')) {
                                const h = (a.getAttribute('href') || '').trim();
                                if (h.startsWith('http') && !h.includes('t.me/') && !h.includes('telegram.me/')) {
                                    links.push(h);
                                }
                            }
                        }
                        const rawUrls = text.match(/https?:\\/\\/[^\\s<>"')\\]،]+/g) || [];
                        for (const ru of rawUrls) {
                            if (!ru.includes('t.me/') && !ru.includes('telegram.me/') && !links.includes(ru)) {
                                links.push(ru);
                            }
                        }
                        let photo = null;
                        const photoEl = msgEl.querySelector('.tgme_widget_message_photo_wrap');
                        if (photoEl) {
                            const style = photoEl.getAttribute('style') || '';
                            const m = style.match(/background-image\\s*:\\s*url\\(['"]?(https?:\\/\\/[^'"]+)['"]?\\)/i);
                            if (m) photo = m[1];
                        }
                        if (links.length > 0) {
                            out.push({ postId, text, links, photo });
                        }
                    }
                    return out;
                }""")
            except Exception as e:
                print(f"تعذر قراءة القناة @{ch} عبر Playwright: {e}")
            finally:
                await page.close()

        if not posts:
            continue

        # لو المستخدم باعت رابط بوست معين بالرقم، نركز عليه هو بس، غير كده نفحص أحدث 10 بوستات
        if specific_post_id:
            target_suffix = f"/{specific_post_id}"
            filtered = [p for p in posts if p.get("postId", "").endswith(target_suffix)]
            candidate_posts = filtered if filtered else [posts[-1]]
        else:
            candidate_posts = list(reversed(posts[-10:]))

        for post in candidate_posts:
            if total_posted >= max_to_post:
                break
            post_id = post.get("postId") or ""
            if not specific_post_id and post_id in learned_prefs.get("seen_posts", []):
                continue

            p_text = post.get("text") or ""
            p_links = post.get("links") or []
            p_photo = post.get("photo")

            # التأكد أن البوست يرشح عرضاً أو يتحدث عن تجربة منتج
            rec_kws = (
                "عرض", "خصم", "سعر", "فرصة", "لقطة", "ممتاز", "تحفة", "جربت", "تجربت",
                "ترشيح", "ارشح", "انصح", "قوي", "خامة", "اصلي", "جنيه", "كوبون", "كود",
                "سماعة", "شاحن", "مشترك", "خلاط", "قلاية", "مكواة", "ماكينة", "باور",
            )
            norm_pt = _normalize_ar(p_text)
            if not specific_post_id and p_text and not any(_normalize_ar(k) in norm_pt for k in rec_kws) and len(p_links) == 0:
                continue

            # تسجيل البوست كـ مقروء حتى لا نعيد فحصه في الدورات القادمة
            if post_id and post_id not in learned_prefs["seen_posts"]:
                learned_prefs["seen_posts"].append(post_id)
                save_learned_prefs()

            if not p_links:
                continue

            # اختيار رابط المنتج الفعلي من روابط البوست
            target_url = p_links[0]
            if len(p_links) > 1:
                for cand_u in p_links:
                    resolved_cand = await resolve_original_url(context, cand_u)
                    if "/dp/" in resolved_cand or "/p/" in resolved_cand:
                        target_url = resolved_cand
                        break

            try:
                deal_msg, deal_img, orig_url, our_short_url, title, eff_p, promo_sig, is_active, active_reason, brand = await scrape_single_product(
                    context, target_url, fallback_text=p_text, fallback_image=p_photo, is_user_submission=False
                )
                if not deal_msg or not title:
                    continue

                # 1) التحقق الصارم أن العرض لسه متاح وساري على المتجر حالياً (مش منتهي أو مخلص أو نافد)
                if not is_active:
                    print(f"⚠️ تخطي نشر عرض من @{ch} لأن العرض غير متاح أو انتهى على المتجر: {title[:50]} ({active_reason})")
                    continue

                # 2) التحقق أن العرض لم يتم نشره مسبقاً بنفس السعر والمواصفات (يمنع التكرار إلا لو السعر نزل أكتر أو اتضاف كود جديد)
                should_send, change_reason = should_send_deal(orig_url, title, eff_p, promo_sig)
                if not should_send and not specific_post_id:
                    print(f"⏩ تخطي نشر العرض من @{ch} لأنه منشور سابقاً في القناة ومحصلش فيه أي تغيير: {title[:50]}")
                    continue

                mark_deal_sent(orig_url, title, eff_p, promo_sig)
                channel_only_ids = [cid for cid in CHAT_IDS if str(cid) != str(notify_chat_id)]
                if not channel_only_ids:
                    channel_only_ids = [MAIN_CHANNEL_ID]
                elif MAIN_CHANNEL_ID not in channel_only_ids and MAIN_CHANNEL_USERNAME not in channel_only_ids:
                    channel_only_ids.append(MAIN_CHANNEL_ID)
                if channel_only_ids:
                    await pace_and_send(deal_msg, deal_img) if not notify_chat_id else await asyncio.to_thread(send_telegram_msg, deal_msg, deal_img, channel_only_ids)
                if notify_chat_id:
                    await asyncio.to_thread(send_telegram_msg, deal_msg, deal_img, [notify_chat_id])
                total_posted += 1
                print(f"✅ تم التعلم من @{ch} وتحويل ونشر عرض ساري ومحدث: {title[:55]} ({active_reason})")
            except Exception as e:
                print(f"خطأ في تحويل بوست {post_id} من @{ch}: {e}")

    return total_posted

_last_tg_offset = None
_processed_tg_msgs = set()
_recent_private_urls = {}

async def poll_private_chat_once(context):
    """يتحقق من رسائل الشات الخاص مع البوت لتحويل أي رابط مرسل أو قناة مرسلة للتعلم منها ونشر العروض بطريقتنا."""
    global _last_tg_offset
    params = {"timeout": 0, "allowed_updates": json.dumps(["message", "callback_query"])}
    if _last_tg_offset is not None:
        params["offset"] = _last_tg_offset
    try:
        r = await asyncio.to_thread(
            requests.get,
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params=params,
            timeout=8,
        )
        if not r.ok:
            return
        updates = r.json().get("result") or []
    except Exception:
        return

    if not updates:
        return

    # تأكيد استلام التحديثات لتليجرام فوراً قبل بدء الفحص لمنع قراءتها مرتين أبداً
    _last_tg_offset = max(u.get("update_id", 0) for u in updates) + 1
    try:
        await asyncio.to_thread(
            requests.get,
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={"offset": _last_tg_offset, "timeout": 0},
            timeout=5,
        )
    except Exception:
        pass

    for upd in updates:
        # 1. معالجة ضغطات الأزرار التفاعلية (Inline Keyboard Callbacks)
        cb = upd.get("callback_query")
        if cb:
            cb_id = cb.get("id")
            cb_from = cb.get("from") or {}
            cb_user_id = cb_from.get("id")
            cb_data = cb.get("data") or ""
            cb_msg = cb.get("message") or {}
            cb_chat = cb_msg.get("chat") or {}
            cb_chat_id = cb_chat.get("id")
            cb_msg_id = cb_msg.get("message_id")

            if cb_user_id != OWNER_CHAT_ID and cb_chat_id != OWNER_CHAT_ID:
                answer_callback_query(cb_id, "غير مصرح لك بتنفيذ هذا الإجراء.")
                continue

            if cb_data.startswith("post_anyway:"):
                deal_token = cb_data.split(":", 1)[1]
                deal_info = pending_deals.get(deal_token)
                if not deal_info:
                    answer_callback_query(cb_id, "⚠️ هذا العرض لم يعد متاحاً أو انتهت صلاحية الطلب.")
                    edit_telegram_msg(cb_chat_id, cb_msg_id, "⚠️ <i>انتهت صلاحية هذا الطلب أو تم اتخاذ إجراء عليه مسبقاً.</i>", reply_markup={"inline_keyboard": []})
                    continue

                answer_callback_query(cb_id, "🚀 جاري النشر في القناة الآن...")
                orig_url = deal_info["orig_url"]
                title = deal_info["title"]
                eff_p = deal_info["eff_p"]
                promo_sig = deal_info.get("promo_sig", "")
                deal_msg = deal_info["deal_msg"]
                deal_img = deal_info.get("deal_img")
                our_short_url = deal_info.get("our_short_url") or orig_url

                channel_destinations = [MAIN_CHANNEL_ID]
                if MAIN_CHANNEL_USERNAME and MAIN_CHANNEL_USERNAME not in channel_destinations:
                    channel_destinations.append(MAIN_CHANNEL_USERNAME)

                sent_ok = await asyncio.to_thread(send_telegram_msg, deal_msg, deal_img, channel_destinations)
                if sent_ok:
                    mark_deal_sent(orig_url, title, eff_p, promo_sig)
                    success_txt = (
                        "✅ <b>تم نشر العرض في قناة «لقطة» (@loqta78) بنجاح بناءً على اختيارك! 📢</b>\n\n"
                        f"📦 <b>المنتج:</b> {html.escape(title[:70])}...\n"
                        f"💰 <b>السعر:</b> {eff_p} ج.م\n"
                        f"🔗 <b>الرابط المنشور:</b> {html.escape(our_short_url)}"
                    )
                    edit_telegram_msg(cb_chat_id, cb_msg_id, success_txt, reply_markup={"inline_keyboard": []})
                    pending_deals.pop(deal_token, None)
                    save_pending_deals()
                else:
                    fail_txt = (
                        "⚠️ <b>تعذر إرسال العرض إلى القناة في هذه اللحظة!</b>\n\n"
                        f"📦 <b>المنتج:</b> {html.escape(title[:70])}...\n"
                        "قد يكون هناك بطء مؤقت في استجابة تليجرام، اضغط على الزر بالأسفل لإعادة المحاولة فوراً."
                    )
                    edit_telegram_msg(cb_chat_id, cb_msg_id, fail_txt, reply_markup={
                        "inline_keyboard": [
                            [
                                {"text": "🔄 إعادة محاولة النشر في القناة", "callback_data": f"post_anyway:{deal_token}"},
                                {"text": "❌ إلغاء", "callback_data": f"cancel_deal:{deal_token}"}
                            ]
                        ]
                    })
                continue

            if cb_data.startswith("cancel_deal:"):
                deal_token = cb_data.split(":", 1)[1]
                answer_callback_query(cb_id, "تم إلغاء النشر.")
                pending_deals.pop(deal_token, None)
                save_pending_deals()
                cancel_txt = "❌ <b>تم إلغاء نشر العرض بناءً على اختيارك (لن يتم إرساله للقناة).</b>"
                edit_telegram_msg(cb_chat_id, cb_msg_id, cancel_txt, reply_markup={"inline_keyboard": []})
                continue

            continue

        msg = upd.get("message")
        if not msg:
            continue
        chat = msg.get("chat") or {}
        if chat.get("type") != "private":
            continue
        user_chat_id = chat.get("id")
        msg_id = msg.get("message_id")
        if (user_chat_id, msg_id) in _processed_tg_msgs:
            continue
        _processed_tg_msgs.add((user_chat_id, msg_id))

        text = (msg.get("text") or msg.get("caption") or "").strip()

        if text.startswith("/start"):
            welcome_reply = (
                "👋 <b>أهلاً بيك في بوت قناة «لقطة» (@loqta78) الذكي!</b>\n\n"
                "🔗 <b>1. تحويل الروابط والتعلم منها:</b>\n"
                "ابعتلي أي <b>لينك منتج</b> من أمازون أو نون (أو اعمل <b>Forward</b> لبوست عرض)، وهفك الاختصار، أحط كود الأفلييت بتاعنا (<code>is.gd/loqta_...</code>)، أنشر العرض بالصورة، وأتعلم الماركة ونوع المنتج عشان أدور على عروض شبهه تلقائياً!\n\n"
                "📡 <b>2. التعلم من قنوات تليجرام تانية:</b>\n"
                "ابعتلي <b>لينك أي قناة تليجرام</b> (مثل <code>https://t.me/channel</code> أو <code>@channel</code>) وهتابعها تلقائياً؛ أول ما ينزلوا عرض كويس أو تجربة منتج ممتازة، هعيد صياغة التجربة بأسلوبنا الخاص وأحول اللينك للأفلييت بتاعنا وأنزله في القناة! 🚀💰"
            )
            await asyncio.to_thread(send_telegram_msg, welcome_reply, None, [user_chat_id])
            continue

        if user_chat_id != OWNER_CHAT_ID:
            continue

        all_urls = extract_urls_from_message(msg)
        product_urls = [u for u in all_urls if not re.search(r'(?:t\.me|telegram\.me|telegram\.dog)/', u, re.I)]
        ch_ref, specific_post_id, ch_kind = extract_telegram_channel_info(text, msg)

        # 1. لو الرابط رابط دعوة خاص (+ أو joinchat)
        if ch_kind == "invite":
            inv_title, inv_desc, public_uname = resolve_telegram_invite_link(ch_ref)
            if public_uname:
                ch_ref = public_uname
                ch_kind = "public"
            else:
                if "invite_channels" not in learned_prefs:
                    learned_prefs["invite_channels"] = []
                inv_entry = inv_title or ch_ref
                if inv_entry not in learned_prefs["invite_channels"]:
                    learned_prefs["invite_channels"].append(inv_entry)
                    save_learned_prefs()
                reply_invite = (
                    f"📡 <b>تم استلام رابط القناة بنجاح{' (' + html.escape(inv_title) + ')' if inv_title else ''}!</b>\n\n"
                    "ℹ️ <i>ملاحظة:</i> الرابط ده رابط دعوة خاص (Invite Link). تليجرام مش بيسمح بقراءة البوستات من المتصفح تلقائياً للروابط الخاصة.\n\n"
                    "💡 <b>الحل المباشر والسهل جداً:</b> أي بوست عرض يعجبك في القناة دي، اعمله <b>Forward للشات هنا مع البوت</b>، والبوت فوراً هيسحب تفاصيل المنتج، يعيد صياغة التجربة لأسلوب «لقطة»، يحط كود الأفلييت الخاص بينا (<code>is.gd/loqta_...</code>)، وينشره في قناتك فوراً! 🚀💰"
                )
                await asyncio.to_thread(send_telegram_msg, reply_invite, None, [user_chat_id])
                continue

        # 2. لو الرسالة محولة من قناة خاصة بدون معرف عام ولا تحتوي على روابط منتج
        if ch_kind == "private_forward" and not product_urls:
            reply_fwd = (
                f"📡 <b>تم استلام الرسالة المحولة من قناة «{html.escape(ch_ref)}»!</b>\n\n"
                "💡 عشان أجهز العرض بالصورة وأحط كود الأفلييت بتاعك، ابعت أو اعمل Forward لبوست فيه <b>رابط المنتج</b> (أمازون أو نون) وهتعامل معاه فوراً! 🚀"
            )
            await asyncio.to_thread(send_telegram_msg, reply_fwd, None, [user_chat_id])
            continue

        # 3. لو القناة عامة (رابط t.me أو معرف @ أو معرف مكتوب)
        if ch_kind == "public":
            is_new_ch = ch_ref not in learned_prefs["channels"]
            if is_new_ch:
                learned_prefs["channels"].append(ch_ref)
                save_learned_prefs()
                print(f"📡 تم حفظ قناة تليجرام جديدة للمتابعة: @{ch_ref}")

            # لو المستخدم باعت فقط رابط القناة بدون روابط منتجات مباشرة في نفس الرسالة
            if not product_urls:
                ack_ch_txt = (
                    f"📡 <b>فهمت إن ديه قناة تليجرام (@{html.escape(ch_ref)})!</b>\n\n"
                    "✅ <b>تم حفظ القناة في قائمة المتابعة الدائمة للبوت.</b>\n"
                    "🔄 <b>البوت هيفضل متابعها دايماً في كل دورات الفحص القادمة (مش بس دلوقتي):</b>\n"
                    "• هيتعلم من ترشيحاتهم وتجاربهم تلقائياً.\n"
                    "• هيتأكد أن أي عرض لسه ساري ومتاح على المتجر بالشروط اللي حددناها.\n"
                    "• هيصيغ العرض بأسلوب «لقطة» ويضيف كود الأفلييت بتاعنا وينزله على قناتنا (@loqta78).\n"
                    "• لو العرض نزل قبل كده ومحصلش فيه تغيير جديد، مش هيكرره أبداً.\n\n"
                    "⏳ <i>جاري الآن الدخول على القناة وفحص أحدث العروض الموجودة فيها فوراً...</i>"
                )
                await asyncio.to_thread(send_telegram_msg, ack_ch_txt, None, [user_chat_id])

                try:
                    posted_cnt = await scan_monitored_channels(
                        context, target_channel=ch_ref, specific_post_id=specific_post_id, max_to_post=3, notify_chat_id=user_chat_id
                    )
                except Exception as sc_err:
                    print(f"Error scanning channel @{ch_ref}: {sc_err}")
                    posted_cnt = 0
                done_msg = (
                    f"✅ <b>تم الانتهاء من فحص قناة @{html.escape(ch_ref)} بنجاح!</b>\n\n"
                    f"📦 <b>العروض المطابقة للشروط والمنشورة الآن:</b> {posted_cnt} عرض.\n"
                    f"🧠 <b>المتابعة الدائمة نشطة:</b> القناة اتسجلت بشكل دائم في الذاكرة، وهيفضل يفحصها في كل دورة فحص دورية وينشر أي عرض جديد ومميز منها تلقائياً! 🚀"
                )
                await asyncio.to_thread(send_telegram_msg, done_msg, None, [user_chat_id])
                continue

        urls = product_urls
        if not urls:
            guide_txt = (
                "👋 <b>تقدر تبعت للبوت أي حاجة من دول ويتعامل معاها فوراً:</b>\n\n"
                "1️⃣ <b>لينك أي منتج</b> من أمازون مصر أو نون مصر (وحتى لو الرابط مختصر)، وهيحوله لكود الأفلييت الخاص بينا (<code>is.gd/loqta_...</code>) وينشره في القناة بالصورة فوراً.\n\n"
                "2️⃣ <b>لينك أي قناة تليجرام</b> (مثل: <code>https://t.me/channel</code> أو <code>@channel</code> أو رابط دعوة)، وهيتابعها تلقائياً ويعيد صياغة عروضها بأسلوبنا ولينك الأفلييت بتاعنا.\n\n"
                "3️⃣ <b>Forward لأي بوست عرض</b> من أي قناة تانية للشات هنا، وهيحوله وينشره فوراً! 🚀💰"
            )
            await asyncio.to_thread(send_telegram_msg, guide_txt, None, [user_chat_id])
            continue

        photos = msg.get("photo") or []
        fallback_img_id = photos[-1].get("file_id") if photos else None

        deal_items = split_message_into_deals(text, urls)
        if len(deal_items) > 1:
            ack_prod_txt = (
                f"📦 <b>فهمت إن الرسالة فيها {len(deal_items)} عروض ومنتجات!</b>\n"
                "🧠 <b>جاري فصل كل عرض، تحليله، والتعلم منه فوراً</b> (حفظ الماركات وفئات المنتجات للبحث التلقائي عنها مستقبلاً).\n"
                "⏳ <b>وجاري الآن:</b> التأكد من التوفر وسريان الخصم لكل عرض في المتجر، صياغة كل بوست بالاسم العربي والإنجليزي ووصف «لقطة»، إضافة كود الأفلييت الخاص بينا (<code>is.gd/loqta_...</code>)، ونشر كل عرض بالصورة في قناتنا... 🚀"
            )
        else:
            ack_prod_txt = (
                "📦 <b>فهمت إن ده عرض ومنتج!</b>\n"
                "🧠 <b>جاري تحليله والتعلّم منه فوراً</b> (حفظ الماركة وفئة المنتج للبحث التلقائي عنها مستقبلاً).\n"
                "⏳ <b>وجاري الآن:</b> التأكد من التوفر وسريان الخصم على المتجر، صياغة البوست بالاسم العربي والإنجليزي ووصف «لقطة»، إضافة كود الأفلييت الخاص بينا (<code>is.gd/loqta_...</code>)، وتجهيز الصورة لنشره في قناتنا... 🚀"
            )
        await asyncio.to_thread(send_telegram_msg, ack_prod_txt, None, [user_chat_id])

        total_posted = 0
        for target_url, deal_chunk in deal_items:
            try:
                deal_msg, deal_img, orig_url, our_short_url, title, eff_p, promo_sig, is_active, active_reason, brand = await scrape_single_product(
                    context, target_url, fallback_text=deal_chunk, fallback_image=fallback_img_id, is_user_submission=True
                )
                # منع نشر نفس الرابط مرتين لو اتبعت في خلال دقيقتين
                now_ts = time.time()
                if orig_url in _recent_private_urls and (now_ts - _recent_private_urls[orig_url]) < 120:
                    continue
                _recent_private_urls[orig_url] = now_ts

                if not deal_msg or not title:
                    # لو الرابط لصفحة عامة في أمازون/نون مش منتج مفرد
                    summary_txt = (
                        "✅ <b>تم استخراج الرابط الأصلي وتحويله لكود الأفلييت الخاص بينا:</b>\n\n"
                        f"🔗 <b>الرابط الأصلي:</b>\n{html.escape(orig_url)}\n\n"
                        f"💰 <b>رابط الأفلييت المختصر:</b>\n{html.escape(our_short_url)}"
                    )
                    await asyncio.to_thread(send_telegram_msg, summary_txt, None, [user_chat_id])
                    continue

                # 1) فحص هل العرض لسه متاح وساري حالياً في المتجر (مش مخلص أو انتهى)
                if not is_active:
                    warn_txt = (
                        "⚠️ <b>نتيجة فحص العرض:</b>\n"
                        f"❌ <i>العرض حالياً غير متاح أو انتهى على المتجر ({html.escape(active_reason)})، لذلك تم منع نشره في القناة حتى لا يكون مضللاً للمتابعين.</i>\n\n"
                        f"🧠 <b>لكن تم التعلّم منه بنجاح:</b> تم حفظ ماركة <b>{html.escape(brand or 'المنتج')}</b> وفئة المنتج في ذاكرة البوت عشان يبحث عن عروض جديدة عليها تلقائياً ويجيبها فوراً!\n\n"
                        f"🔗 <b>الرابط الأصلي الصافي:</b>\n{html.escape(orig_url)}\n\n"
                        f"💰 <b>رابط الأفلييت الخاص بيك:</b>\n{html.escape(our_short_url)}"
                    )
                    await asyncio.to_thread(send_telegram_msg, warn_txt, None, [user_chat_id])
                    continue

                # 2) فحص هل العرض نزل قبل كده في القناة بدون أي تغيير جديد (منع التكرار مع إتاحة زر النشر اليدوي)
                should_send, change_reason = should_send_deal(orig_url, title, eff_p, promo_sig)
                if not should_send:
                    deal_token = hashlib.md5(f"{orig_url}_{time.time()}".encode("utf-8")).hexdigest()[:16]
                    pending_deals[deal_token] = {
                        "deal_msg": deal_msg,
                        "deal_img": deal_img,
                        "orig_url": orig_url,
                        "our_short_url": our_short_url,
                        "title": title,
                        "eff_p": eff_p,
                        "promo_sig": promo_sig,
                        "brand": brand,
                        "timestamp": time.time(),
                    }
                    save_pending_deals()

                    markup = {
                        "inline_keyboard": [
                            [
                                {"text": "📢 انشر في القناة على أي حال", "callback_data": f"post_anyway:{deal_token}"},
                                {"text": "❌ لا تنشر (تجاهل)", "callback_data": f"cancel_deal:{deal_token}"}
                            ]
                        ]
                    }

                    already_txt = (
                        "ℹ️ <b>العرض ده منشور بالفعل في القناة قبل كده بنفس السعر والمواصفات!</b>\n\n"
                        f"📦 <b>المنتج:</b> {html.escape(title[:70])}...\n"
                        f"💰 <b>السعر:</b> {eff_p} ج.م\n"
                        f"🧠 <b>الماركة المتعلمة:</b> {html.escape(brand or 'معروفة')}\n\n"
                        f"🔗 <b>الرابط الصافي:</b>\n{html.escape(orig_url)}\n\n"
                        f"💰 <b>رابط الأفلييت الخاص بينا:</b>\n{html.escape(our_short_url)}\n\n"
                        "👇 <b>هل تحب تنشره في القناة دلوقتي على أي حال؟</b>"
                    )
                    await asyncio.to_thread(send_telegram_msg, already_txt, deal_img, [user_chat_id], markup)
                    continue

                # 3) العرض ساري وجديد أو نزل سعره أكتر: نشره في القناة وفي الشات
                mark_deal_sent(orig_url, title, eff_p, promo_sig)
                total_posted += 1
                channel_only_ids = [cid for cid in CHAT_IDS if str(cid) != str(user_chat_id)]
                if not channel_only_ids:
                    channel_only_ids = [MAIN_CHANNEL_ID]
                elif MAIN_CHANNEL_ID not in channel_only_ids and MAIN_CHANNEL_USERNAME not in channel_only_ids:
                    channel_only_ids.append(MAIN_CHANNEL_ID)

                await asyncio.to_thread(send_telegram_msg, deal_msg, deal_img, channel_only_ids)
                await asyncio.to_thread(send_telegram_msg, deal_msg, deal_img, [user_chat_id])
                channel_note = f"\n📡 <i>وتم حفظ قناة @{html.escape(ch_ref)} في ذاكرة المتابعة التلقائية للبوت!</i>" if ch_kind == "public" else ""
                summary_txt = (
                    "✅ <b>تم استلام العرض، والتعلّم منه، ونشره بنجاح في القناة!</b>\n\n"
                    f"🧠 <b>ما تعلمه البوت:</b> تم حفظ ماركة <b>{html.escape(brand or 'المنتج')}</b> وفئة المنتج في ذاكرة البحث التلقائي المستمر.\n"
                    f"📦 <b>المنتج:</b> {html.escape(title[:60])}...\n"
                    f"💰 <b>السعر النهائي:</b> {eff_p} ج.م\n"
                    f"🚀 <b>النشر:</b> نزل بالصورة والاسم العربي والإنجليزي ووصف «لقطة» وكود الأفلييت على قناتنا (@loqta78)."
                    f"{channel_note}\n\n"
                    f"🔗 <b>الرابط الأصلي الصافي:</b>\n{html.escape(orig_url)}\n\n"
                    f"💰 <b>رابط الأفلييت المختصر الخاص بينا:</b>\n{html.escape(our_short_url)}"
                )
                await asyncio.to_thread(send_telegram_msg, summary_txt, None, [user_chat_id])
                if len(deal_items) > 1:
                    await asyncio.sleep(2)
            except Exception as e:
                print(f"خطأ أثناء تحويل الرابط ({target_url}): {e}")
                await asyncio.to_thread(
                    send_telegram_msg,
                    f"❌ حصل خطأ أثناء فحص الرابط: {html.escape(str(e)[:120])}",
                    None,
                    [user_chat_id],
                )

        if len(deal_items) > 1:
            multi_done_txt = (
                f"🏁 <b>تم الانتهاء من معالجة كل العروض في رسالتك ({len(deal_items)} عروض)!</b>\n\n"
                f"✅ <b>تم نشر:</b> {total_posted} عرض في قناتنا (@loqta78) بالصور والأسماء العربية والإنجليزية وأسلوب «لقطة» بروابط الأفلييت.\n"
                "🧠 <b>تم التعلم منها جميعاً:</b> تم حفظ كل الماركات والأصناف في ذاكرة البوت لمتابعتها والبحث التلقائي عنها!"
            )
            await asyncio.to_thread(send_telegram_msg, multi_done_txt, None, [user_chat_id])

async def private_chat_listener_loop(context, stop_event):
    """يفحص رسائل الشات الخاص كل 3 ثواني في الخلفية طوال فترة تشغيل البوت."""
    while not stop_event.is_set():
        await poll_private_chat_once(context)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            pass

async def run_cycle(p, listen_only_seconds=0):
    launch_args = ["--disable-blink-features=AutomationControlled"]
    if sys.platform == "win32":
        launch_args.append("--window-position=-32000,-32000")
    else:
        launch_args.extend(["--window-position=0,0", "--window-size=1366,768"])
    browser = await p.chromium.launch(
        headless=False,
        args=launch_args
    )
    stop_event = asyncio.Event()
    listener_task = None
    try:
        context = await browser.new_context(
            locale="ar-EG",
            viewport={"width": 1366, "height": 768}
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        try:
            await context.add_cookies([
                {"name": "i18n-prefs", "value": "EGP", "domain": ".amazon.eg", "path": "/"},
                {"name": "lc-acbeg", "value": "ar_AE", "domain": ".amazon.eg", "path": "/"},
            ])
        except Exception:
            pass
        listener_task = asyncio.create_task(private_chat_listener_loop(context, stop_event))
        if listen_only_seconds > 0:
            await asyncio.sleep(listen_only_seconds)
        else:
            try:
                await scan_monitored_channels(context, max_to_post=3)
            except Exception as ce:
                print(f"Channel monitoring error: {ce}")
            page = await context.new_page()
            for scraper in (scrape_amazon_eg, scrape_noon_eg):
                try:
                    await scraper(page)
                except Exception as e:
                    print(f"Scraping error ({scraper.__name__}): {e}")
    finally:
        stop_event.set()
        if listener_task:
            try:
                await listener_task
            except Exception:
                pass
        await browser.close()

async def main():
    if "--listen-only" in sys.argv:
        idx = sys.argv.index("--listen-only")
        wait_secs = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else CHECK_INTERVAL
        async with async_playwright() as p:
            await run_cycle(p, listen_only_seconds=wait_secs)
        return

    run_once = "--once" in sys.argv or os.getenv("RUN_ONCE") == "1" or os.getenv("GITHUB_ACTIONS") == "true"
    async with async_playwright() as p:
        while True:
            print(f"\n===== بدء الفحص: {time.strftime('%Y-%m-%d %H:%M:%S')} =====")
            try:
                await run_cycle(p)
            except Exception as e:
                print(f"Cycle error: {e}")

            if run_once:
                print("اكتملت دورة الفحص بنجاح.")
                break

            print(f"انتظار {CHECK_INTERVAL // 60} دقيقة قبل الفحص القادم (مع الاستماع لرسائل الخاص)...")
            try:
                await run_cycle(p, listen_only_seconds=CHECK_INTERVAL)
            except Exception as e:
                print(f"Listen interval error: {e}")
                await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
