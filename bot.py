import asyncio
import hashlib
import html
import json
import os
import re
import sys
import time
from urllib.parse import quote_plus
import requests
from playwright.async_api import async_playwright

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
# ممكن تحط أكتر من ID مفصولين بفاصلة (مثلاً حسابك + الجروب): "6725805788,-100xxxxxxxxxx"
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")
CHAT_IDS = [c.strip() for c in CHAT_ID.split(",") if c.strip()]
# الـ Chat ID الخاص بصاحب البوت لاستقبال أي لينك في الخاص وتحويله لأفلييت القناة ونشره فوراً
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID", "6725805788"))
MIN_DISCOUNT = 30
MAX_PER_CYCLE = 20  # أقصى عدد عروض تتبعت لكل متجر في الدورة الواحدة
HASHTAG = "#عروض_يستاهل"
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

# أشهر البراندات والأقسام اللي عليها عروض قوية في مصر (بيتم فحصها واكتشاف عروضها المجمعة)
HOT_BRANDS = [
    ("أنكر / ساوند كور (Anker)", ["سماعة انكر", "anker", "انكر", "أنكر", "soundcore", "ساوند كور"]),
    ("آي لوك (iLock)", ["مشترك اي لوك", "ilock", "i-lock", "اي لوك", "آي لوك", "اى لوك"]),
    ("UGREEN (يوغرين)", ["ugreen", "يوغرين", "يوجرين"]),
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
    m = re.search(r'/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})', link, re.IGNORECASE)
    if m and ("amazon" in link.lower() or "amzn" in link.lower()):
        return f"https://www.amazon.eg/dp/{m.group(1).upper()}"
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

def should_send_deal(link, title, current_price, promo_sig=""):
    """
    يمنع تكرار إرسال العرض إلا في حالتين فقط:
    1) لو العرض خلص (سعره رجع ارتفع) وبعدين رجع تاني لعرض خصم.
    2) لو حصل تعديل حقيقي على العرض من نون أو أمازون (السعر نزل أكتر أو اتضاف كوبون/خصم جديد).
    وكمان يمنع تكرار نفس المنتج بألوان/بائعين مختلفين بنفس السعر.
    """
    if current_price is None:
        return False, None
    entry = price_history.get(link, {})
    last_p = entry.get("last_sent_price")
    last_at = entry.get("last_sent_at") or 0
    last_promo = entry.get("last_sent_promo") or ""

    if link in sent_deals:
        if last_p is None:
            return False, None
        # 1) السعر نزل أكتر بشكل ملحوظ (على الأقل 8% وبفرق 15 جنيه أو أكتر)
        if current_price <= last_p * 0.92 and (last_p - current_price) >= 15:
            return True, "🔥 تحديث عرض (السعر نزل أكتر!)"
        # 2) العرض كان خلص (السعر طلع فوق سعر العرض بـ 15%+) وبعدين رجع تاني لعرض خصم
        prices_after = [p[1] for p in entry.get("prices", []) if p[0] > last_at]
        if any(p >= last_p * 1.15 for p in prices_after) and current_price <= last_p * 1.02:
            return True, "🔄 العرض رجع تاني بعد ما خلص!"
        # 3) اتضاف كود خصم أو خصم Checkout جديد مكنش موجود وقت الإرسال الأول
        if promo_sig and promo_sig != last_promo:
            return True, "🔥 تحديث عرض (تم إضافة خصم/كوبون جديد!)"
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
    t = (title or "").lower()
    for label, keywords in HOT_BRANDS:
        if any(k.lower() in t for k in keywords):
            return label
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
    """يتحقق مما إذا كان المنتج ينتمي لبراند معروف ومشهور (مثل أنكر، آي لوك، تورنيدو، فريش، يوغرين، إلخ)."""
    combined = f"{(brand or '').strip().lower()} {(title or '').lower()}"
    return any(kw in combined for kw in TRUSTED_BRAND_KEYWORDS)

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

def build_description(title, features=None, extra_desc=None):
    """يكوّن وصف مختصر وسريع للمنتج بدون إطالة مملة."""
    if features:
        clean_feats = [re.sub(r'\s+', ' ', f).strip() for f in features if len(f.strip()) > 12]
        if clean_feats:
            return "؛ ".join(clean_feats[:2])[:150]
    if extra_desc and len(extra_desc.strip()) > 15:
        return re.sub(r'\s+', ' ', extra_desc.strip())[:140]
    clean_t = re.sub(r'\s+', ' ', title).strip()
    return f"{clean_t[:120]} — عرض خاص لفترة محدودة."

def build_review_summary(rating, reviews, review_snippets=None, bought_badge=None):
    """يبني مراجعة مختصرة ومفيدة للمنتج بناءً على تعليقات وتقييمات المشترين."""
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

    if review_snippets:
        snippet = re.sub(r'\s+', ' ', review_snippets[0]).strip()[:100]
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
                  brand=None):
    store_ar = "أمازون" if store.lower() == "amazon" else ("نون" if store.lower() == "noon" else store)
    icon = "🔥" if store.lower() == "amazon" else "🟡"

    brand_clean = (brand or detect_brand(title) or "").strip()
    display_title = title.strip()
    if brand_clean and brand_clean.lower() not in display_title.lower():
        display_title = f"{brand_clean} — {display_title}"

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

    lines = [f"<b>{header}</b>", "", f"📦 <b>{html.escape(display_title[:140])}</b>", ""]

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

    if brand_clean:
        lines.append(f"🏷️ الماركة: <b>{html.escape(brand_clean[:40])}</b>")
    if seller:
        lines.append(f"🏪 البائع: {html.escape(seller[:40])}")
    if rating:
        lines.append(f"⭐ التقييم: {rating}" + (f" ({reviews} تقييم)" if reviews else ""))

    # وصف المنتج (مختصر وواضح)
    desc = build_description(title, features)
    if desc:
        lines += ["", f"📝 <b>وصف المنتج:</b>\n{html.escape(desc)}"]

    # مراجعة بناءً على تعليقات المشترين (مختصرة)
    rev_summary = build_review_summary(rating, reviews, review_snippets, bought_badge)
    if rev_summary:
        lines += ["", f"💬 <b>مراجعة المشترين:</b>\n{html.escape(rev_summary)}"]

    # دمج الخصومات أو عروض اشترِ 1 والثانية هدية أو عروض الفئة
    if stack_promos:
        lines += ["", "🎁 <b>عروض إضافية ودمج خصومات:</b>"]
        for sp in stack_promos[:2]:
            lines.append(f"• {html.escape(sp)}")
        if stack_howto:
            lines.append(f"💡 <b>طريقة التفعيل:</b> {html.escape(stack_howto[0])}")
        for pl in (promo_links or [])[:1]:
            lines.append(f"🏷️ <b>{store_ar} عاملة عرض إضافي على الفئة دي هنا:</b>\n{branded_url(pl)}")

    if max_price is not None and min_price is not None and max_price > min_price and min_price >= 10:
        lines += [
            "",
            f"📊 أعلى سعر مسجّل: {fmt(max_price)} ج.م | أقل سعر: {fmt(min_price)} ج.م",
        ]

    short_branded_link = branded_url(link)
    lines += [
        "",
        "⚠️ <i>ملحوظة: ده مجرد ترشيح للعرض، والتجربة وقرار الشراء عليك.</i>",
        "",
        f"🔗 رابط العرض:\n{short_branded_link}",
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

def send_telegram_msg(text, image=None, target_chat_ids=None):
    """يبعت العرض بصورة المنتج دائماً (سواء برابط مباشر أو بتحميل الصورة ورفعها لتليجرام أو file_id)."""
    img_url = clean_image_url(image)
    is_tg_file_id = bool(image and isinstance(image, str) and not image.startswith("http") and len(image) > 20)
    destinations = target_chat_ids if target_chat_ids is not None else CHAT_IDS
    for chat_id in destinations:
        try:
            resp = None
            if img_url or is_tg_file_id:
                photo_val = img_url if img_url else image
                # 1. محاولة إرسال الصورة بالرابط المباشر أو file_id
                resp = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    json={"chat_id": chat_id, "photo": photo_val, "caption": text, "parse_mode": "HTML"},
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
                            resp = requests.post(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                                data={"chat_id": chat_id, "caption": text, "parse_mode": "HTML"},
                                files={"photo": ("product.jpg", img_r.content, "image/jpeg")},
                                timeout=25,
                            )
                    except Exception as img_e:
                        print(f"تعذر رفع صورة المنتج كملف: {img_e}")
            if resp is None or not resp.ok:
                resp = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                          "disable_web_page_preview": True},
                    timeout=10,
                )
            if resp.ok:
                print(f"تم إرسال العرض إلى تليجرام ({chat_id}) بنجاح.")
            else:
                print(f"Telegram API error ({chat_id}, {resp.status_code}): {resp.text}")
        except Exception as e:
            print(f"Error sending message to {chat_id}: {e}")

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
    """يفتح صفحة المنتج لجلب البائع، الماركة، التقييمات، المميزات، تعليقات المشترين، الصورة، وعروض دمج الخصومات وروابطها."""
    page = await context.new_page()
    seller, brand, pdp_rating, pdp_reviews, features, image, reviews_list, promos_list, promo_links = None, None, None, None, [], None, [], [], []
    try:
        await page.goto(link, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2000)
        title = await page.title()
        if is_blocked_title(title) or await page.query_selector('form[action*="validateCaptcha"]'):
            print(f"صفحة منتج أمازون محجوبة ({title[:40]}) - هنكتفي ببيانات الكارت.")
            return None, None, None, None, None, None, [], [], []
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.65)")
        await page.wait_for_timeout(1200)
        data = await page.evaluate("""() => {
            const q = s => document.querySelector(s)?.innerText?.trim();
            const seller = q('#sellerProfileTriggerId')
                || q('#merchantInfoFeature_feature_div .offer-display-feature-text-message')
                || q('#merchant-info a') || q('#merchant-info');
            let brand = q('tr.po-brand td.a-span9') || q('#bylineInfo');
            if (brand) {
                brand = brand
                    .replace(/^(زيارة متجر|العلامة التجارية:|الماركة:|Visit the|Brand:)\\s*/i, '')
                    .replace(/\\s*Store$/i, '')
                    .trim();
            }
            const ratingTxt = document.querySelector('#acrPopover')?.getAttribute('title') || q('#acrPopover .a-size-base');
            const reviewsTxt = q('#acrCustomerReviewText');
            const feats = [...document.querySelectorAll('#feature-bullets li span.a-list-item')]
                .map(e => e.innerText.trim()).filter(x => x.length > 10);
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
            return {seller, brand, ratingTxt, reviewsTxt, feats, image, promos: promos.slice(0, 10), promo_links: promo_links.slice(0, 2), revs};
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
    except Exception as e:
        print(f"تعذر جلب تفاصيل المنتج: {e}")
    finally:
        await page.close()
    return seller, brand, pdp_rating, pdp_reviews, features, image, reviews_list, promos_list, promo_links

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

    # فحص أقسام وبراندات مختارة (مثل أنكر وآي لوك و UGREEN وتورنيدو وفريش وفيليبس وبراون) + أقسام الأجهزة والهاردوير
    brands_to_check = [
        (b_lbl, f"https://www.amazon.eg/s?k={quote_plus(kw_list[0])}")
        for b_lbl, kw_list in (HOT_BRANDS[(_brand_rot_idx + i) % len(HOT_BRANDS)] for i in range(6))
    ]
    cats_to_check = [
        AMAZON_CATEGORY_SEARCHES[(_amz_cat_rot_idx + i) % len(AMAZON_CATEGORY_SEARCHES)]
        for i in range(5)
    ]
    _amz_cat_rot_idx = (_amz_cat_rot_idx + 5) % len(AMAZON_CATEGORY_SEARCHES)

    for section_label, search_url in (brands_to_check + cats_to_check):
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
                has_promo_txt = any(w in card_txt for w in ("وفر ", "مع الكوبون", "كوبون", "عند الدفع", "عرض ترويجي", "اشترِ", "اشتري"))
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

            has_card_promo = any(w in text_content for w in ("متاح عرض ترويجي", "مع الكوبون", "كوبون خصم", "وفر ", "عند الدفع", "اشترِ", "اشتري"))
            if discount <= 0 and has_card_promo:
                egp_m = re.search(r'وفر\s+(\d+(?:\.\d+)?)\s*(?:جنيه|ج\.م)', clean(text_content))
                if egp_m and info["price"] > float(egp_m.group(1)):
                    saving_v = float(egp_m.group(1))
                    info["list_price"] = info["price"]
                    discount = (saving_v / info["price"]) * 100
                else:
                    discount = 15.0
            if discount <= 0:
                continue

            prev_min, max_p, min_p = record_price(full_link, info["price"])
            freebie = is_almost_free(info["price"], info["list_price"], badge_disc)
            famous = has_famous_brand(info["title"])
            saving_egp = (info["list_price"] - info["price"]) if (info["list_price"] and info["list_price"] > info["price"]) else 0

            # للبراندات المشهورة (مثل أنكر، آي لوك، تورنيدو، فريش، فيليبس، براون...) نقبل خصم من 14% (أو 10% لو معاه كوبون أو توفير >= 50 جنيه)
            if famous:
                qualifies = (discount >= 14) or (discount >= 10 and (has_card_promo or saving_egp >= 50)) or freebie
            else:
                qualifies = (discount >= 25) or (discount >= 18 and has_card_promo) or freebie

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
            seller, brand, pdp_rating, pdp_reviews, features, image, rev_snippets, page_promos, promo_links = None, None, None, None, [], None, [], [], []
            if consecutive_blocks < 3 and pdp_Lookups < 28:
                pdp_Lookups += 1
                seller, brand, pdp_rating, pdp_reviews, features, image, rev_snippets, page_promos, promo_links = await amazon_product_details(page.context, full_link)
                if features is None:
                    consecutive_blocks += 1
                    features = []
                else:
                    consecutive_blocks = 0

            rating = info["rating"] or pdp_rating
            reviews = info["reviews"] or pdp_reviews
            if not is_trusted_product(info["title"], brand=brand, rating=rating, reviews=reviews):
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
            ok_send, update_reason = should_send_deal(full_link, info["title"], eff_price, promo_sig)
            if not ok_send:
                continue

            mark_deal_sent(full_link, info["title"], eff_price, promo_sig)
            amazon_sent += 1

            msg = build_message(
                "Amazon", info["title"], info["price"], info["list_price"], discount, full_link,
                seller=seller, rating=rating, reviews=reviews, features=features,
                prev_min=prev_min, max_price=max_p, min_price=min_p,
                review_snippets=rev_snippets, bought_badge=info.get("bought"),
                stack_promos=stack_promos, stack_howto=stack_howto, section_note=update_reason,
                extra_pct=extra_pct, extra_egp=extra_egp, extra_label=extra_label, promo_links=promo_links,
                brand=brand,
            )
            is_free_now = is_almost_free(eff_price, info["list_price"], discount)
            await pace_and_send(msg, image=image or card.get("img"), is_freebie=is_free_now)
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
    """يفتح صفحة المنتج في نون لجلب الاسم الكامل، الماركة، البائع، المميزات، التعليقات، العروض الإضافية، والصورة."""
    page = await context.new_page()
    full_title, brand, seller, features, image, promos, reviews_list = None, None, None, [], None, [], []
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
            return None, None, None, None, None, [], []
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
            const promos = container
                ? [...container.querySelectorAll('[class*="coupon" i], [class*="voucher" i], [class*="promo" i], [data-qa*="coupon" i], [class*="cashback" i]')]
                    .map(e => e.innerText.trim()).filter(x => x.length > 6 && x.length < 220)
                : [];
            const revs = [...document.querySelectorAll('[class*="reviewComment" i], [class*="reviewDesc" i], [data-qa*="review" i] p')]
                .map(e => e.innerText.trim()).filter(x => x.length > 15 && x.length < 220).slice(0, 2);
            return {full_title, brand, seller, feats, image, promos: promos.slice(0, 5), revs};
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
    except Exception as e:
        print(f"تعذر جلب تفاصيل منتج نون: {e}")
    finally:
        await page.close()
    return full_title, brand, seller, features, image, promos, reviews_list

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

    # إضافة بحث مباشر عن البراندات الساخنة (مثل أنكر وآي لوك و UGREEN وتورنيدو وفريش وفيليبس وبراون) في نون
    brand_urls = []
    for i in range(6):
        b_label, kw_list = HOT_BRANDS[(_brand_rot_idx + i) % len(HOT_BRANDS)]
        brand_urls.append((b_label, f"https://www.noon.com/egypt-ar/search/?q={quote_plus(kw_list[0])}"))
    _brand_rot_idx = (_brand_rot_idx + 6) % len(HOT_BRANDS)

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
                        if b_hint and not c.get("brand"):
                            c["brand"] = b_hint
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
                qualifies = (discount >= 14) or (discount >= 10 and (has_card_promo or saving_egp >= 50)) or freebie
            else:
                qualifies = (discount >= 25) or (discount >= 18 and has_card_promo) or freebie

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
            full_title, pdp_brand, seller, features, image, page_promos, rev_snippets = None, None, None, [], None, [], []
            if consecutive_blocks < 3 and pdp_lookups < 28:
                pdp_lookups += 1
                full_title, pdp_brand, seller, features, image, page_promos, rev_snippets = await noon_product_details(page.context, full_link)
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
            msg = build_message(
                "Noon", title, info["price"], info["list_price"], discount, full_link,
                seller=seller, rating=info["rating"], reviews=info["reviews"], features=features,
                prev_min=prev_min, max_price=max_p, min_price=min_p,
                review_snippets=rev_snippets, bought_badge=info.get("bought"),
                stack_promos=stack_promos, stack_howto=stack_howto, section_note=update_reason,
                extra_pct=extra_pct, extra_egp=extra_egp, extra_label=extra_label, promo_links=promo_links,
                brand=brand,
            )
            is_free_now = is_almost_free(eff_price, info["list_price"], discount)
            await pace_and_send(msg, image=image or card.get("img"), is_freebie=is_free_now)
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

def _strip_foreign_affiliate_params(url):
    """يحذف أي كود أفلييت أو باراميتر تتبع خاص بقنوات أخرى من الرابط."""
    if not url:
        return url
    s = short_link(url)
    if s != url:
        return s
    if "amazon." in url.lower() or "noon.com" in url.lower():
        return url.split("?")[0].split("#")[0]
    return url

async def resolve_original_url(context, raw_url):
    """يفك أي رابط مختصر (مثل amzn.eu أو sal7.ly أو is.gd أو bit.ly) ويجيب الرابط الأصلي الصافي للمنتج."""
    u = (raw_url or "").strip()
    if not u:
        return u
    direct = short_link(u)
    if direct != u and ("/dp/" in direct or "/p/" in direct):
        return direct

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ar-EG,ar;q=0.9,en;q=0.8",
    }
    try:
        r = await asyncio.to_thread(
            requests.get, u, headers=headers, allow_redirects=True, timeout=15
        )
        final_u = r.url or u
        s = short_link(final_u)
        if "/dp/" in s or "/p/" in s:
            return s
        # فحص محتوى الصفحة لو فيه تحويل بالـ HTML أو JavaScript
        body = r.text or ""
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

    # لو الرابط المختصر بيستخدم تحويل JavaScript أو Cloudflare، نفتحه بالمتصفح
    if context is not None:
        page = await context.new_page()
        try:
            await page.goto(u, wait_until="domcontentloaded", timeout=35000)
            for _ in range(8):
                cur = page.url
                s = short_link(cur)
                if "/dp/" in s or "/p/" in s:
                    return s
                if ("amazon." in cur.lower() or "noon.com" in cur.lower()) and cur != u:
                    await page.wait_for_timeout(1000)
                    return _strip_foreign_affiliate_params(page.url)
                await page.wait_for_timeout(700)
            return _strip_foreign_affiliate_params(page.url)
        except Exception as e:
            print(f"تعذر فك الرابط بالمتصفح ({u}): {e}")
        finally:
            await page.close()
    return _strip_foreign_affiliate_params(u)

def _parse_fallback_message_info(text):
    """يستخرج الاسم والسعر القديم والجديد احتياطياً لو المستخدم محوّل بوست جاهز وصفحة المنتج محجوبة."""
    t = clean(text or "")
    old_m = re.search(r'(?:السعر القديم|بدلاً من|بدل من|سعر القائمه|كان)\s*:?\s*([\d,]+(?:\.\d+)?)', t)
    new_m = re.search(r'(?:السعر الجديد|السعر النهائي|سعر العرض|بسعر|السعر)\s*:?\s*([\d,]+(?:\.\d+)?)', t)
    if not new_m:
        new_m = re.search(r'([\d,]+(?:\.\d+)?)\s*(?:ج\.م|جنيه)', t)
    disc_m = re.search(r'(\d+)\s*%', t)
    title_cand = None
    for line in [l.strip() for l in t.split('\n') if l.strip()]:
        clean_l = re.sub(r'^[📦🔥🟡🚨🏷️✨•\-]+\s*', '', line).strip()
        if (
            len(clean_l) >= 12
            and not clean_l.startswith("http")
            and not any(w in clean_l for w in ("السعر", "إجمالي الخصم", "الخصم:", "البائع:", "التقييم:", "على أمازون", "على نون", "رابط العرض", "ملحوظة:"))
        ):
            title_cand = clean_l[:140]
            break
    return {
        "title": title_cand,
        "price": to_float(new_m.group(1)) if new_m else None,
        "list_price": to_float(old_m.group(1)) if old_m else None,
        "discount": float(disc_m.group(1)) if disc_m else 0.0,
    }

async def scrape_single_product(context, raw_url, fallback_text="", fallback_image=None):
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
                    '#corePrice_feature_div .a-price .a-offscreen',
                    '#apex_desktop .priceToPay .a-offscreen',
                    '#priceblock_dealprice',
                    '#priceblock_ourprice',
                    '#price_inside_buybox',
                    '#tp_price_block_total_price_ww .a-offscreen',
                    '#ppd .a-price .a-offscreen',
                ];
                let priceTxt = priceSelectors.map(q).find(x => x && /\\d/.test(x)) || null;
                if (!priceTxt) {
                    const whole = q('#corePriceDisplay_desktop_feature_div .priceToPay .a-price-whole');
                    const frac = q('#corePriceDisplay_desktop_feature_div .priceToPay .a-price-fraction') || '00';
                    if (whole) priceTxt = whole.replace(/[^0-9,]/g, '') + '.' + frac.replace(/[^0-9]/g, '');
                }
                const listSelectors = [
                    '#corePriceDisplay_desktop_feature_div .basisPrice .a-offscreen',
                    '#corePriceDisplay_desktop_feature_div span[data-a-strike="true"] .a-offscreen',
                    '#apex_desktop .basisPrice .a-offscreen',
                    '.basisPrice .a-offscreen',
                    '#price .a-text-price .a-offscreen',
                ];
                const listTxt = listSelectors.map(q).find(x => x && /\\d/.test(x)) || null;
                const savingsTxt = q('#corePriceDisplay_desktop_feature_div .savingsPercentage') || q('.savingsPercentage');
                const bought = q('#social-proofing-faceout-title-tk_bought');
                const seller = q('#sellerProfileTriggerId')
                    || q('#merchantInfoFeature_feature_div .offer-display-feature-text-message')
                    || q('#merchant-info a') || q('#merchant-info');
                let brand = q('tr.po-brand td.a-span9') || q('#bylineInfo');
                if (brand) {
                    brand = brand
                        .replace(/^(زيارة متجر|العلامة التجارية:|الماركة:|Visit the|Brand:)\\s*/i, '')
                        .replace(/\\s*Store$/i, '')
                        .trim();
                }
                const ratingTxt = document.querySelector('#acrPopover')?.getAttribute('title') || q('#acrPopover .a-size-base');
                const reviewsTxt = q('#acrCustomerReviewText');
                const feats = [...document.querySelectorAll('#feature-bullets li span.a-list-item')]
                    .map(e => e.innerText.trim()).filter(x => x.length > 10);
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
                return {title, priceTxt, listTxt, savingsTxt, bought, seller, brand, ratingTxt, reviewsTxt, feats, image, promos: promos.slice(0, 10), promo_links: promo_links.slice(0, 2), revs};
            }""")
        finally:
            await page.close()

        raw_t = data.get("title") or ""
        title = (raw_t if raw_t and not is_blocked_title(raw_t) else fb["title"]) or "منتج مميز على أمازون مصر"
        p_m = re.search(r'([\d,]+(?:\.\d+)?)', clean(data.get("priceTxt") or ""))
        l_m = re.search(r'([\d,]+(?:\.\d+)?)', clean(data.get("listTxt") or ""))
        price = to_float(p_m.group(1)) if p_m else fb["price"]
        list_price = to_float(l_m.group(1)) if l_m else fb["list_price"]
        s_m = re.search(r'(\d+)\s*%', clean(data.get("savingsTxt") or ""))
        discount = float(s_m.group(1)) if s_m else (fb["discount"] or 0.0)
        if price and list_price and list_price > price:
            discount = (1 - price / list_price) * 100
        elif price and discount > 0 and not list_price:
            list_price = round(price / (1 - discount / 100.0), 2)

        r_m = re.search(r'(\d\.\d)', clean(data.get("ratingTxt") or ""))
        rating = r_m.group(1) if r_m else None
        rv_m = re.search(r'([\d,]+)', clean(data.get("reviewsTxt") or ""))
        reviews = rv_m.group(1) if rv_m else None
        brand = data.get("brand")
        seller = data.get("seller")
        features = data.get("feats") or []
        image = clean_image_url(data.get("image")) or fallback_image
        promos_list = data.get("promos") or []
        promo_links = data.get("promo_links") or []
        rev_snippets = data.get("revs") or []
        bought_badge = data.get("bought")

        prev_min, max_p, min_p = record_price(canonical_url, price) if price else (None, None, None)
        stack_promos, stack_howto, extra_pct, extra_egp, extra_label, promo_links = detect_stacking_promos(
            fallback_text, promos_list, promo_links
        )
        eff_price = price
        if eff_price and extra_pct > 0:
            eff_price = round(eff_price * (1 - extra_pct / 100.0), 2)
        elif eff_price and extra_egp > 0 and eff_price > extra_egp:
            eff_price = round(eff_price - extra_egp, 2)

        msg = build_message(
            "Amazon", title, price, list_price, discount, canonical_url,
            seller=seller, rating=rating, reviews=reviews, features=features,
            prev_min=prev_min, max_price=max_p, min_price=min_p,
            review_snippets=rev_snippets, bought_badge=bought_badge,
            stack_promos=stack_promos, stack_howto=stack_howto,
            extra_pct=extra_pct, extra_egp=extra_egp, extra_label=extra_label, promo_links=promo_links,
            brand=brand,
        )
        return msg, image, canonical_url, branded_url(canonical_url), title, eff_price, "|".join(stack_promos)

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
                if (brand) brand = brand.replace(/[>›]/g, '').split('\\n')[0].trim();
                const priceNow = document.querySelector('[data-qa="div-price-now"], [class*="priceNow" i]')?.innerText || ldPrice;
                const priceWas = document.querySelector('[data-qa="div-price-was"], [class*="priceWas" i], [class*="oldPrice" i]')?.innerText || null;
                const savingTxt = document.querySelector('[data-qa="div-price-saving"], [class*="priceSaving" i], [class*="profit" i]')?.innerText || null;
                const ratingTxt = ldRating || document.querySelector('[data-qa*="rating" i], [class*="ratingValue" i]')?.innerText || null;
                const reviewsTxt = ldReviews || document.querySelector('[data-qa*="review-count" i], [class*="count" i]')?.innerText || null;
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
                const promos = container
                    ? [...container.querySelectorAll('[class*="coupon" i], [class*="voucher" i], [class*="promo" i], [data-qa*="coupon" i], [class*="cashback" i]')]
                        .map(e => e.innerText.trim()).filter(x => x.length > 6 && x.length < 220)
                    : [];
                const revs = [...document.querySelectorAll('[class*="reviewComment" i], [class*="reviewDesc" i], [data-qa*="review" i] p')]
                    .map(e => e.innerText.trim()).filter(x => x.length > 15 && x.length < 220).slice(0, 2);
                return {full_title, brand, seller, priceNow, priceWas, savingTxt, ratingTxt, reviewsTxt, feats, image, promos: promos.slice(0, 5), revs};
            }""")
        finally:
            await page.close()

        raw_t = data.get("full_title") or ""
        title = (raw_t if raw_t and not is_blocked_title(raw_t) else fb["title"]) or "منتج مميز على نون مصر"
        p_m = re.search(r'([\d,]+(?:\.\d+)?)', clean(data.get("priceNow") or ""))
        l_m = re.search(r'([\d,]+(?:\.\d+)?)', clean(data.get("priceWas") or ""))
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
        stack_promos, stack_howto, extra_pct, extra_egp, extra_label, promo_links = detect_stacking_promos(
            fallback_text, promos_list
        )
        eff_price = price
        if eff_price and extra_pct > 0:
            eff_price = round(eff_price * (1 - extra_pct / 100.0), 2)
        elif eff_price and extra_egp > 0 and eff_price > extra_egp:
            eff_price = round(eff_price - extra_egp, 2)

        msg = build_message(
            "Noon", title, price, list_price, discount, canonical_url,
            seller=seller, rating=rating, reviews=reviews, features=features,
            prev_min=prev_min, max_price=max_p, min_price=min_p,
            review_snippets=rev_snippets,
            stack_promos=stack_promos, stack_howto=stack_howto,
            extra_pct=extra_pct, extra_egp=extra_egp, extra_label=extra_label, promo_links=promo_links,
            brand=brand,
        )
        return msg, image, canonical_url, branded_url(canonical_url), title, eff_price, "|".join(stack_promos)

    return None, None, canonical_url, branded_url(canonical_url), None, None, ""

_last_tg_offset = None

async def poll_private_chat_once(context):
    """يتحقق من رسائل الشات الخاص مع البوت لتحويل أي رابط مرسل إلى رابط أفلييت القناة ونشره."""
    global _last_tg_offset
    params = {"timeout": 0, "allowed_updates": json.dumps(["message"])}
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

    for upd in updates:
        upd_id = upd.get("update_id", 0)
        _last_tg_offset = upd_id + 1
        msg = upd.get("message")
        if not msg:
            continue
        chat = msg.get("chat") or {}
        if chat.get("type") != "private":
            continue
        user_chat_id = chat.get("id")
        text = (msg.get("text") or msg.get("caption") or "").strip()

        if text.startswith("/start"):
            welcome_reply = (
                "👋 <b>أهلاً بيك في بوت قناة «لقطة» (@loqta78)!</b>\n\n"
                "🔗 ابعتلي أي <b>لينك منتج</b> من أمازون مصر أو نون مصر (أو اعمل <b>Forward</b> لأي بوست عرض من أي قناة تانية حتى لو الرابط مختصر)، "
                "وهقوم فوراً بـ:\n"
                "1️⃣ فك الاختصار واستخراج <b>الرابط الأصلي الصافي</b> للمنتج (وحذف أي كود أفلييت قديم).\n"
                "2️⃣ إضافة <b>كود الأفلييت الخاص بينا</b> واختصاره باسم القناة (<code>is.gd/loqta_...</code>).\n"
                "3️⃣ سحب تفاصيل المنتج كاملة وإرسال بوست العرض جاهز في الشات ونشره في القناة! 🚀💰"
            )
            await asyncio.to_thread(send_telegram_msg, welcome_reply, None, [user_chat_id])
            continue

        if user_chat_id != OWNER_CHAT_ID:
            continue

        urls = extract_urls_from_message(msg)
        if not urls:
            await asyncio.to_thread(
                send_telegram_msg,
                "⚠️ مبعتليش رابط في الرسالة! ابعت أي رابط منتج من أمازون أو نون (أو اعمل Forward لبوست فيه رابط) وهحوله للينك الأفلييت بتاعنا فوراً.",
                None,
                [user_chat_id],
            )
            continue

        target_url = urls[0]
        photos = msg.get("photo") or []
        fallback_img_id = photos[-1].get("file_id") if photos else None

        await asyncio.to_thread(
            send_telegram_msg,
            "⏳ <i>جاري فتح الرابط واستخراج اللينك الأصلي وتحويله للأفلييت الخاص بينا وتجهيز العرض...</i>",
            None,
            [user_chat_id],
        )

        try:
            deal_msg, deal_img, orig_url, our_short_url, title, eff_p, promo_sig = await scrape_single_product(
                context, target_url, fallback_text=text, fallback_image=fallback_img_id
            )
            if deal_msg:
                if title:
                    mark_deal_sent(orig_url, title, eff_p, promo_sig)
                # 1) نشر الرسالة الكاملة في القناة
                await asyncio.to_thread(send_telegram_msg, deal_msg, deal_img, CHAT_IDS)
                # 2) إرسال نسخة لصاحب البوت في الشات الخاص (لو الشات الخاص مش مضاف أصلاً في CHAT_IDS)
                if str(user_chat_id) not in CHAT_IDS:
                    await asyncio.to_thread(send_telegram_msg, deal_msg, deal_img, [user_chat_id])
                summary_txt = (
                    "✅ <b>تم تحويل الرابط ونشر العرض في القناة بنجاح!</b>\n\n"
                    f"🔗 <b>الرابط الأصلي الصافي:</b>\n{html.escape(orig_url)}\n\n"
                    f"💰 <b>رابط الأفلييت الخاص بينا:</b>\n{html.escape(our_short_url)}"
                )
                await asyncio.to_thread(send_telegram_msg, summary_txt, None, [user_chat_id])
            else:
                # لو الرابط لصفحة عامة في أمازون/نون مش منتج مفرد
                summary_txt = (
                    "✅ <b>تم استخراج الرابط الأصلي وتحويله لكود الأفلييت الخاص بينا:</b>\n\n"
                    f"🔗 <b>الرابط الأصلي:</b>\n{html.escape(orig_url)}\n\n"
                    f"💰 <b>رابط الأفلييت المختصر:</b>\n{html.escape(our_short_url)}"
                )
                await asyncio.to_thread(send_telegram_msg, summary_txt, None, [user_chat_id])
        except Exception as e:
            print(f"خطأ أثناء تحويل الرابط من الشات الخاص: {e}")
            await asyncio.to_thread(
                send_telegram_msg,
                f"❌ حصل خطأ أثناء فحص الرابط: {html.escape(str(e)[:120])}",
                None,
                [user_chat_id],
            )

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
        listener_task = asyncio.create_task(private_chat_listener_loop(context, stop_event))
        if listen_only_seconds > 0:
            await asyncio.sleep(listen_only_seconds)
        else:
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
