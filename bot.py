import asyncio
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
MIN_DISCOUNT = 30
MAX_PER_CYCLE = 20  # أقصى عدد عروض تتبعت لكل متجر في الدورة الواحدة
HASHTAG = "#عروض_يستاهل"
HISTORY_DAYS = 90
# المدة بين كل فحص والتاني بالثواني (افتراضياً 3 دقايق - فترة العروض)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "180"))

SENT_DEALS_FILE = os.path.join(BASE_DIR, "sent_deals.txt")
HISTORY_FILE = os.path.join(BASE_DIR, "price_history.json")

# أشهر البراندات والأقسام اللي عليها عروض قوية في مصر (بيتم فحصها واكتشاف عروضها المجمعة)
HOT_BRANDS = [
    ("UGREEN (يوغرين)", ["ugreen", "يوغرين", "يوجرين"]),
    ("Redragon (ريدراجون)", ["redragon", "ريدراجون", "ريد دراجون"]),
    ("فيتراك (Vitrac)", ["vitrac", "فيتراك"]),
    ("أبو عوف", ["ابو عوف", "أبو عوف", "abu auf"]),
    ("Fogg (فوج)", ["fogg", "فوج"]),
    ("أنكر (Anker)", ["anker", "انكر", "أنكر", "soundcore", "ساوند كور"]),
    ("أورايمو (Oraimo)", ["oraimo", "أورايمو", "اورايمو"]),
    ("لوجيتك (Logitech)", ["logitech", "لوجيتك"]),
    ("بيسوس / جوي روم", ["baseus", "بيسوس", "joyroom", "جوي روم"]),
    ("نيفيا (Nivea)", ["nivea", "نيفيا"]),
    ("لوريال (L'Oreal)", ["loreal", "l'oreal", "لوريال"]),
    ("أريال (Ariel)", ["ariel", "اريال", "أريال", "ايريال"]),
    ("برسيل (Persil)", ["persil", "برسيل"]),
    ("تورنيدو (Tornado)", ["tornado", "تورنيدو"]),
    ("فريش (Fresh)", ["fresh", "فريش"]),
    ("شاومي (Xiaomi)", ["xiaomi", "شاومي", "redmi", "ريدمي"]),
    ("سامسونج (Samsung)", ["samsung", "سامسونج"]),
    ("أديداس (Adidas)", ["adidas", "اديداس", "أديداس"]),
    ("نسبرسو / نسكافيه", ["nespresso", "nescafe", "نسبرسو", "نسكافيه"]),
]

# أقسام بحث إضافية لعروض الهاردوير والإلكترونيات والسوبرماركت في أمازون
AMAZON_CATEGORY_SEARCHES = [
    ("عروض الهاردوير والكمبيوتر", "https://www.amazon.eg/s?k=%D9%83%D9%8A%D8%A8%D9%88%D8%B1%D8%AF+%D9%85%D9%8A%D9%83%D8%A7%D9%86%D9%8A%D9%83%D9%8A"),
    ("عروض الشواحن السريعة GaN", "https://www.amazon.eg/s?k=%D8%B4%D8%A7%D8%AD%D9%86+%D8%B3%D8%B1%D9%8A%D8%B9+gan"),
    ("عروض السماعات والباور بانك", "https://www.amazon.eg/s?k=%D8%B3%D9%85%D8%A7%D8%B9%D8%A9+%D8%A8%D9%84%D9%88%D8%AA%D9%88%D8%AB&rh=p_n_deal_type%3A26901043031"),
    ("عروض السوبرماركت وفلاش", "https://www.amazon.eg/s?k=%D8%B9%D8%B1%D9%88%D8%B6&i=grocery"),
    ("عروض الإلكترونيات اليومية", "https://www.amazon.eg/s?i=electronics&rh=p_n_deal_type%3A26901043031"),
]
_brand_rot_idx = 0
_amz_cat_rot_idx = 0

# ---------------------------------------------------------------------------
# حفظ العروض المرسلة وسجل الأسعار
# ---------------------------------------------------------------------------
def short_link(link):
    """رابط قصير وثابت للمنتج (بيفضل شغال لما حد ينسخ الرسالة)."""
    m = re.search(r'/dp/([A-Z0-9]{10})', link)
    if m and "amazon" in link:
        return f"https://www.amazon.eg/dp/{m.group(1)}"
    m = re.search(r'/([A-Z0-9]{8,})/p/?', link)
    if m and "noon.com" in link:
        return f"https://www.noon.com/egypt-ar/{m.group(1)}/p/"
    return link

sent_deals = set()
if os.path.exists(SENT_DEALS_FILE):
    with open(SENT_DEALS_FILE, "r", encoding="utf-8") as f:
        sent_deals = {short_link(line.strip()) for line in f if line.strip()}

price_history = {}
if os.path.exists(HISTORY_FILE):
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            price_history = {short_link(k): v for k, v in json.load(f).items()}
    except Exception:
        price_history = {}

def save_history():
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(price_history, f, ensure_ascii=False)

def mark_deal_sent(link):
    sent_deals.add(link)
    with open(SENT_DEALS_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")

def record_price(link, price):
    """يسجّل السعر الحالي ويرجع (أقل سعر سابق، أعلى سعر، أقل سعر) خلال آخر 90 يوم."""
    now = time.time()
    entry = price_history.setdefault(link, {"prices": [], "last_sent": None})
    cutoff = now - HISTORY_DAYS * 86400
    entry["prices"] = [p for p in entry["prices"] if p[0] >= cutoff]
    prev_min = min((p[1] for p in entry["prices"]), default=None)
    entry["prices"].append([now, price])
    all_prices = [p[1] for p in entry["prices"]]
    save_history()
    return prev_min, max(all_prices), min(all_prices)

# ---------------------------------------------------------------------------
# أدوات مساعدة وذكاء العروض
# ---------------------------------------------------------------------------
def clean(text):
    return re.sub(r'[\u200e\u200f\xa0]', ' ', text or "")

def to_float(s):
    try:
        return float(s.replace(',', ''))
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

def is_almost_free(price, list_price):
    """يكتشف العروض اللي تعتبر ببلاش (مثلاً سعرها كان 300+ ونزل تحت 100، أو نزل لـ 20 جنيه وأقل)."""
    if price is None:
        return False
    if list_price and list_price >= 300 and price < 100:
        return True
    if list_price and list_price >= 150 and price <= 25:
        return True
    if price <= 15 and list_price and list_price >= 80:
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

def build_description(title, features=None, extra_desc=None):
    """يكوّن وصف مختصر وواضح للمنتج من المميزات أو من تفاصيل الاسم."""
    if features:
        clean_feats = [re.sub(r'\s+', ' ', f).strip() for f in features if len(f.strip()) > 15]
        if clean_feats:
            return "؛ ".join(clean_feats[:3])[:280]
    if extra_desc and len(extra_desc.strip()) > 20:
        return re.sub(r'\s+', ' ', extra_desc.strip())[:250]
    # استنتاج وصف ذكي من اسم المنتج وتفاصيله لو صفحة المنتج محجوبة
    clean_t = re.sub(r'\s+', ' ', title).strip()
    return f"{clean_t} — منتج متوفر بعرض خاص لفترة محدودة."

def build_review_summary(rating, reviews, review_snippets=None, bought_badge=None):
    """يبني مراجعة وتقييم للمنتج بناءً على تعليقات وتقييمات المشترين."""
    parts = []
    r_val = to_float(rating) if rating else None
    r_cnt = parse_reviews_count(reviews)

    if r_val is not None:
        if r_val >= 4.5 and r_cnt >= 100:
            verdict = "إشادة عالية جداً من المشترين بجودة المنتج وأدائه مقابل السعر"
        elif r_val >= 4.2:
            verdict = "انطباع إيجابي وتجارب شراء ناجحة من أغلب المستخدمين"
        elif r_val >= 3.8:
            verdict = "تقييمات جيدة بشكل عام مع رضا عن القيمة مقابل السعر"
        else:
            verdict = "تقييمات متفاوتة؛ يُنصح بمراجعة تفاصيل المواصفات قبل الشراء"
        cnt_txt = f" من {reviews} مشتري" if reviews else ""
        parts.append(f"حاصل على {rating}/5{cnt_txt} ({verdict}).")

    if bought_badge:
        parts.append(f"معدل الطلب: {bought_badge}.")

    if review_snippets:
        snippet = re.sub(r'\s+', ' ', review_snippets[0]).strip()[:160]
        if len(snippet) > 15:
            parts.append(f"من تعليقات المشترين: «{snippet}»")

    if not parts:
        return "منتج عليه خصم ملحوظ؛ لم تتوفر تعليقات كافية بعد."
    return " ".join(parts)

def detect_stacking_promos(card_text, page_promos=None, promo_links=None):
    """يكتشف فرص دمج الخصومات (كوبونات، أكواد مثل FLASH، خصم برايم التلقائي، وأكواد البنوك) ويحسب الخصم الإضافي."""
    promos = []
    how_to = []
    extra_pct = 0.0
    extra_egp = 0.0
    extra_label = None
    t = clean(card_text or "")

    # 1. فحص نص الكارت (نون وأمازون)
    for line in t.split('\n'):
        l = line.strip()
        if not l:
            continue
        m_egp = re.search(r'خصم\s+(\d+(?:\.\d+)?)\s*(?:جنيه|ج\.م)', l)
        if m_egp:
            val = float(m_egp.group(1))
            if val > extra_egp:
                extra_egp = val
                extra_label = "بعد الخصم الإضافي/الكوبون"
            promos.append(f"كوبون/خصم إضافي على الكارت: {l}")
            how_to.append("فعّل الكوبون أو العرض الإضافي الظاهر تحت السعر في صفحة المنتج قبل الإضافة للسلة.")
        elif "متاح عرض ترويجي بخصم" in l:
            m_pct = re.search(r'(\d+)\s*[%٪]', l)
            if m_pct:
                extra_pct = max(extra_pct, float(m_pct.group(1)))
                extra_label = "بعد العرض الترويجي الإضافي"
            promos.append(l)
            how_to.append("اضغط على (تفعيل العرض الترويجي) تحت السعر في صفحة المنتج أو اكتب الكود في صفحة الدفع.")
        elif any(k in l for k in ("مع الكوبون", "كوبون خصم", "وفر", "اشترِ", "اشتري", "كود خصم", "عرض أول أوردر", "هدية مجانية")):
            if not re.fullmatch(r'خصم\s*\d+%', l) and len(l) < 120:
                promos.append(l)
                m_pct = re.search(r'(\d+)\s*[%٪]', l)
                if m_pct and ("كوبون" in l or "وفر" in l):
                    extra_pct = max(extra_pct, float(m_pct.group(1)))
                    extra_label = "بعد الكوبون"
                if "كوبون" in l:
                    how_to.append("علّم على مربع (تطبيق الكوبون) الموجود تحت السعر مباشرة قبل ما تضيف المنتج للسلة.")
                elif "اشتر" in l:
                    how_to.append("أضف العدد المطلوب من المنتج في السلة وهيتخصم العرض الإضافي تلقائياً عند الدفع.")

    # 2. فحص العروض وأكواد الخصم من صفحة المنتج (بما فيها كود FLASH وخصم برايم التلقائي)
    all_p_lines = []
    for p in (page_promos or []):
        p_no_css = re.sub(r'\.cxcwEmphasisLink\s*\{[^}]*\}', ' ', clean(p))
        for sub in p_no_css.split('\n'):
            s_clean = re.sub(r'^تسجيل الدخول للاستفادة من الكوبون\.?\s*', '', sub).strip()
            s_clean = re.sub(r'\s+', ' ', s_clean)
            if len(s_clean) >= 8 and not s_clean.startswith('{') and "margin-" not in s_clean:
                all_p_lines.append(s_clean)

    page_found_promos = []
    page_found_howto = []
    for p_clean in all_p_lines:
        is_bank = any(b in p_clean.lower() for b in ("visa", "mastercard", "credit card", "بطاقات", "بنك", "bank", "nbe", "qnb", "aaib", "alex"))
        code_m = re.search(r'(?:أدخل الرمز|رمز العرض الترويجي:?|كود|رمز|code)\s*:?\s*([A-Z0-9]{4,20})', p_clean, re.IGNORECASE)
        pct_m = re.search(r'(\d+)\s*[%٪]', p_clean)
        if code_m:
            code = code_m.group(1)
            short_p = p_clean.split("الشروط")[0].replace("تسوق المنتجات", "").strip()[:130]
            if not is_bank and pct_m:
                page_found_promos.insert(0, f"🔥 {short_p} (كود الخصم: {code})")
                extra_pct = max(extra_pct, float(pct_m.group(1)))
                extra_label = f"بعد كود الخصم ({code})"
                page_found_howto.insert(0, f"اكتب كود الخصم ({code}) في خانة الكوبون عند الدفع (أو اضغط تفعيل تحت السعر) علشان ينزل السعر {pct_m.group(1)}% كمان!")
            else:
                page_found_promos.append(f"💳 {short_p} (كود: {code})")
                page_found_howto.append(f"لو معاك البطاقة البنكية الموضحة، اكتب الكود ({code}) في صفحة الدفع لخصم إضافي.")
        elif "التوفير مع خدمة برايم" in p_clean or "خصم تلقائي" in p_clean:
            short_p = p_clean.split("الشروط")[0].replace("تسوق المنتجات", "").strip()[:130]
            page_found_promos.insert(0, f"⚡ {short_p} (خصم تلقائي في الـ Checkout)")
            if pct_m:
                extra_pct = max(extra_pct, float(pct_m.group(1)))
                if not extra_label or "العرض الترويجي" in extra_label:
                    extra_label = "بعد الخصم التلقائي في الـ Checkout"
            page_found_howto.insert(0, "أضف المنتج للسلة وادخل صفحة الدفع (Checkout) هتلاقي الخصم الإضافي اتخصم تلقائياً!")
        elif any(w in p_clean for w in ("كوبون", "خصم", "وفر", "وفِّر", "اشتر", "مجاني", "هدية")):
            short_p = p_clean.split("الشروط")[0].replace("تسوق المنتجات", "").strip()[:130]
            page_found_promos.append(short_p)
            if not is_bank and pct_m and ("كوبون" in short_p or "وفر" in short_p or "وفِّر" in short_p):
                extra_pct = max(extra_pct, float(pct_m.group(1)))
                if not extra_label:
                    extra_label = "بعد الكوبون/العرض الإضافي"
                page_found_howto.append("علّم على مربع الكوبون تحت السعر في صفحة المنتج عشان يتدمج مع الخصم الأساسي.")

    # لو لقينا تفاصيل العرض كاملة من صفحة المنتج نقدمها في الأول قبل النص العام للكارت
    combined_promos = page_found_promos + [p for p in promos if not (page_found_promos and "متاح عرض ترويجي" in p)]
    combined_howto = page_found_howto + how_to

    unique_promos = list(dict.fromkeys(combined_promos))[:3]
    unique_howto = list(dict.fromkeys(combined_howto))[:2]
    if unique_promos and not unique_howto:
        unique_howto.append("فعّل العرض الإضافي من تحت السعر أو في صفحة الدفع لدمجه مع خصم المنتج الأساسي.")
    return unique_promos, unique_howto, extra_pct, extra_egp, extra_label, (promo_links or [])[:1]

def build_message(store, title, price, list_price, discount, link,
                  seller=None, rating=None, reviews=None, features=None,
                  prev_min=None, max_price=None, min_price=None,
                  review_snippets=None, bought_badge=None,
                  stack_promos=None, stack_howto=None, section_note=None,
                  extra_pct=0.0, extra_egp=0.0, extra_label=None, promo_links=None):
    store_ar = "أمازون" if store.lower() == "amazon" else ("نون" if store.lower() == "noon" else store)
    icon = "🔥" if store.lower() == "amazon" else "🟡"

    final_price = None
    if price is not None:
        if extra_pct > 0:
            final_price = round(price * (1 - extra_pct / 100.0), 2)
        elif extra_egp > 0 and price > extra_egp:
            final_price = round(price - extra_egp, 2)

    effective_price = final_price if final_price is not None else price
    freebie = is_almost_free(effective_price, list_price)
    if freebie:
        header = f"🚨🔥 ببلاش حرفياً على {store_ar}! (نزل من {fmt(list_price)} ج.م لـ {fmt(effective_price)} ج.م)"
    else:
        header = f"{icon} على {store_ar}"

    lines = [f"<b>{header}</b>", "", f"📦 <b>{html.escape(title)}</b>", ""]

    if list_price and list_price > (price or 0):
        lines.append(f"❌ السعر القديم: <s>{fmt(list_price)} ج.م</s>")
    if price is not None:
        tag = " 🔥 (ببلاش تقريباً!)" if (freebie and final_price is None) else ""
        lines.append(f"💰 السعر الجديد: <b>{fmt(price)} ج.م</b>{tag}")
    if final_price is not None and final_price < price:
        lbl = extra_label or "بعد دمج الخصم الإضافي"
        lines.append(f"🔥 <b>السعر النهائي {html.escape(lbl)}: {fmt(final_price)} ج.م فقط!</b>")
    if effective_price is not None and list_price and list_price > effective_price:
        eff_disc = (1 - effective_price / list_price) * 100
        lines.append(f"📉 إجمالي الخصم: <b>{eff_disc:.0f}%</b> (وفّرت {fmt(list_price - effective_price)} ج.م)")
    else:
        lines.append(f"📉 الخصم: <b>{discount:.0f}%</b>")

    if seller:
        lines.append(f"🏪 البائع: {html.escape(seller)}")
    if rating:
        lines.append(f"⭐ التقييم: {rating}" + (f" ({reviews} تقييم)" if reviews else ""))

    if section_note:
        lines += ["", f"🏷️ <b>{html.escape(section_note)}</b>"]

    # وصف المنتج
    desc = build_description(title, features)
    if desc:
        lines += ["", f"📝 <b>وصف المنتج:</b>\n{html.escape(desc)}"]

    # مراجعة بناءً على تعليقات المشترين
    rev_summary = build_review_summary(rating, reviews, review_snippets, bought_badge)
    if rev_summary:
        lines += ["", f"💬 <b>مراجعة المشترين:</b>\n{html.escape(rev_summary)}"]

    # دمج الخصومات وطريقة تحقيقه
    if stack_promos:
        lines += ["", "🎁 <b>فرصة دمج خصومات:</b>"]
        for sp in stack_promos[:2]:
            lines.append(f"• {html.escape(sp)}")
        if stack_howto:
            lines.append("💡 <b>إزاي تحقق دمج الخصومات:</b>")
            for idx, step in enumerate(stack_howto, 1):
                lines.append(f"{idx}️⃣ {html.escape(step)}")
        for pl in (promo_links or [])[:1]:
            lines.append(f"🛒 <b>خصم إضافي على منتجات مختلفة من نفس العرض هنا:</b>\n{pl}")

    if max_price is not None and min_price is not None and max_price > min_price:
        lines += [
            "",
            f"📊 أعلى سعر مسجّل: {fmt(max_price)} ج.م | أقل سعر: {fmt(min_price)} ج.م",
        ]

    lines += [
        "",
        "⚠️ <i>ملحوظة: ده مجرد ترشيح للعرض، والتجربة وقرار الشراء عليك.</i>",
        "",
        f"🔗 رابط العرض:\n{link}",
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

def send_telegram_msg(text, image=None):
    """يبعت العرض بصورة المنتج لو متاحة (والكلام تحتها)، وإلا يبعته كرسالة عادية."""
    for chat_id in CHAT_IDS:
        try:
            resp = None
            # تليجرام بيسمح بـ 1024 حرف بس تحت الصورة
            if image and len(re.sub(r'<[^>]+>', '', text)) <= 1024:
                resp = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    json={"chat_id": chat_id, "photo": image, "caption": text, "parse_mode": "HTML"},
                    timeout=20,
                )
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
    """يفتح صفحة المنتج لجلب البائع، المميزات، تعليقات المشترين، وعروض دمج الخصومات وروابطها."""
    page = await context.new_page()
    seller, features, image, reviews_list, promos_list, promo_links = None, [], None, [], [], []
    try:
        await page.goto(link, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2000)
        title = await page.title()
        if is_blocked_title(title) or await page.query_selector('form[action*="validateCaptcha"]'):
            print(f"صفحة منتج أمازون محجوبة ({title[:40]}) - هنكتفي ببيانات الكارت.")
            return None, None, None, [], [], []
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.65)")
        await page.wait_for_timeout(1200)
        data = await page.evaluate("""() => {
            const q = s => document.querySelector(s)?.innerText?.trim();
            const seller = q('#sellerProfileTriggerId')
                || q('#merchantInfoFeature_feature_div .offer-display-feature-text-message')
                || q('#merchant-info a') || q('#merchant-info');
            const feats = [...document.querySelectorAll('#feature-bullets li span.a-list-item')]
                .map(e => e.innerText.trim()).filter(x => x.length > 10);
            const img = document.querySelector('#landingImage');
            const image = img?.getAttribute('data-old-hires') || img?.getAttribute('src')
                || document.querySelector('meta[property="og:image"]')?.content;
            const promos = [...document.querySelectorAll('#promoPriceBlockMessage_feature_div, #couponBadgeRegularVpc, [id*="coupon" i], #sopp_feature_div')]
                .map(e => e.innerText.trim()).filter(x => x && x.length > 5 && x.length < 3000);
            const promo_links = [...new Set(
                [...document.querySelectorAll('#promoPriceBlockMessage_feature_div a[href*="/promotion/psp/"], a[href*="/promotion/psp/"]')]
                    .map(a => a.href.split('&ref=')[0].split('?ref=')[0])
                    .filter(Boolean)
            )];
            const revs = [...document.querySelectorAll('[data-hook="reviewText"], [data-hook="review-collapsed"], .review-text-content')]
                .map(e => e.innerText.trim()).filter(x => x.length > 15).slice(0, 3);
            return {seller, feats, image, promos: promos.slice(0, 5), promo_links: promo_links.slice(0, 2), revs};
        }""")
        seller = data.get("seller")
        features = data.get("feats") or []
        image = data.get("image")
        promos_list = data.get("promos") or []
        promo_links = data.get("promo_links") or []
        reviews_list = data.get("revs") or []
    except Exception as e:
        print(f"تعذر جلب تفاصيل المنتج: {e}")
    finally:
        await page.close()
    return seller, features, image, reviews_list, promos_list, promo_links

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
                products.setdefault(link, c)
        await page.mouse.wheel(0, 1800)
        await page.wait_for_timeout(1200)

    # فحص أقسام وبراندات مختارة (مثل UGREEN و Redragon و Vitrac وأبو عوف و Fogg) + أقسام الهاردوير والسوبرماركت
    brands_to_check = [
        (b_lbl, f"https://www.amazon.eg/s?k={quote_plus(kw_list[0])}")
        for b_lbl, kw_list in (HOT_BRANDS[(_brand_rot_idx + i) % len(HOT_BRANDS)] for i in range(4))
    ]
    cats_to_check = [
        AMAZON_CATEGORY_SEARCHES[(_amz_cat_rot_idx + i) % len(AMAZON_CATEGORY_SEARCHES)]
        for i in range(2)
    ]
    _amz_cat_rot_idx = (_amz_cat_rot_idx + 2) % len(AMAZON_CATEGORY_SEARCHES)

    for section_label, search_url in (brands_to_check + cats_to_check):
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)
            scards = await page.evaluate("""() => [...document.querySelectorAll('div[data-component-type="s-search-result"]')].slice(0, 24).map(c => {
                const asin = c.getAttribute('data-asin');
                const title = c.querySelector('h2')?.innerText?.trim();
                const price = c.querySelector('.a-price .a-offscreen')?.innerText;
                const list_price = c.querySelector('.a-price.a-text-price .a-offscreen')?.innerText;
                const img = c.querySelector('img.s-image')?.src;
                return {asin, title, price, list_price, img, text: c.innerText};
            })""")
            for sc in scards:
                if sc.get("asin") and sc.get("price") and sc.get("list_price"):
                    link = f"https://www.amazon.eg/dp/{sc['asin']}"
                    synth_text = f"سعر العرض: {sc['price']}\nسعر القائمه: {sc['list_price']}\n{sc.get('title') or ''}\n{sc.get('text') or ''}"
                    is_brand = any(section_label == b[0] for b in HOT_BRANDS)
                    products.setdefault(link, {
                        "href": link,
                        "text": synth_text,
                        "img": sc.get("img"),
                        "brand_section": (section_label, search_url) if is_brand else (None, None),
                    })
        except Exception as e:
            print(f"تعذر فحص قسم {section_label} في أمازون: {e}")

    print(f"تم العثور على {len(products)} عرض في أمازون مصر.")

    candidates = []
    brand_clusters = {}
    for full_link, card in products.items():
        try:
            text_content = card["text"]
            info = parse_amazon_card(text_content)
            if not info["price"] or is_blocked_title(info["title"]):
                continue
            match = re.search(r'(\d+)%', text_content)
            discount = int(match.group(1)) if match else 0
            if info["list_price"] and info["list_price"] > info["price"]:
                discount = (1 - info["price"] / info["list_price"]) * 100
            if discount <= 0:
                continue

            prev_min, max_p, min_p = record_price(full_link, info["price"])
            freebie = is_almost_free(info["price"], info["list_price"])
            has_card_promo = any(w in text_content for w in ("متاح عرض ترويجي", "مع الكوبون", "كوبون خصم", "وفر "))

            # تجميع عروض البراندات والأقسام (زي أبو عوف و Fogg و UGREEN و Vitrac)
            b_label = card.get("brand_section", (None, None))[0] or detect_brand(info["title"])
            if b_label and discount >= 20:
                b_url = card.get("brand_section", (None, None))[1] or f"https://www.amazon.eg/s?k={quote_plus(b_label.split()[0])}"
                brand_clusters.setdefault(b_label, {"url": b_url, "items": []})["items"].append({
                    "title": info["title"], "price": info["price"], "list_price": info["list_price"],
                    "discount": discount, "link": full_link, "img": card.get("img")
                })

            if (discount >= MIN_DISCOUNT or freebie or (discount >= 22 and has_card_promo)) and full_link not in sent_deals:
                candidates.append((1 if freebie else 0, discount, full_link, card, info, prev_min, max_p, min_p, b_label))
        except Exception as e:
            print(f"خطأ في كارت أمازون: {e}")
            continue

    # إرسال تنبيه مجمع لو فيه قسم/براند كامل عليه خصومات قوية
    today_key = time.strftime("%Y-%m-%d")
    for b_label, b_data in brand_clusters.items():
        b_items = sorted(b_data["items"], key=lambda x: x["discount"], reverse=True)
        alert_id = f"section:amazon:{b_label}:{today_key}"
        if len(b_items) >= 3 and b_items[0]["discount"] >= 25 and alert_id not in sent_deals:
            mark_deal_sent(alert_id)
            alert_msg = build_section_alert("Amazon", b_label, b_data["url"], b_items)
            send_telegram_msg(alert_msg, image=b_items[0].get("img"))
            await asyncio.sleep(3)

    # ترتيب العروض: عروض "ببلاش" أولاً ثم الأعلى خصماً
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    amazon_sent = 0
    pdp_blocked = False

    for _, discount, full_link, card, info, prev_min, max_p, min_p, b_label in candidates:
        if amazon_sent >= MAX_PER_CYCLE:
            break
        try:
            mark_deal_sent(full_link)
            amazon_sent += 1

            seller, features, image, rev_snippets, page_promos, promo_links = None, [], None, [], [], []
            if not pdp_blocked:
                seller, features, image, rev_snippets, page_promos, promo_links = await amazon_product_details(page.context, full_link)
                if features is None:
                    pdp_blocked = True
                    features = []

            stack_promos, stack_howto, extra_pct, extra_egp, extra_label, promo_links = detect_stacking_promos(
                card["text"], page_promos, promo_links
            )
            sec_note = None
            if b_label and len(brand_clusters.get(b_label, {}).get("items", [])) >= 2:
                sec_note = f"قسم {b_label} عليه خصومات مجمعة حالياً على أمازون!"

            msg = build_message(
                "Amazon", info["title"], info["price"], info["list_price"], discount, full_link,
                seller=seller, rating=info["rating"], reviews=info["reviews"], features=features,
                prev_min=prev_min, max_price=max_p, min_price=min_p,
                review_snippets=rev_snippets, bought_badge=info.get("bought"),
                stack_promos=stack_promos, stack_howto=stack_howto, section_note=sec_note,
                extra_pct=extra_pct, extra_egp=extra_egp, extra_label=extra_label, promo_links=promo_links,
            )
            send_telegram_msg(msg, image=image or card.get("img"))
            await asyncio.sleep(3)
        except Exception as e:
            print(f"خطأ في إرسال عرض أمازون: {e}")
            continue

# ---------------------------------------------------------------------------
# نون مصر (تغطية شاملة + البراندات والأقسام + دمج الخصومات + المراجعات)
# ---------------------------------------------------------------------------
def parse_noon_card(text, price_text=None):
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
    for j, l in enumerate(lines):
        if re.fullmatch(r'\d\.\d', l):
            rating = l
            if j + 1 < len(lines) and re.fullmatch(r'[\d.,]+K?', lines[j + 1]):
                reviews = lines[j + 1]
            break
    rank_badge = next((l for l in lines if l.startswith('#') and 'في ' in l), None)
    return {"price": price, "list_price": list_price, "rating": rating, "reviews": reviews, "bought": rank_badge}

NOON_CORE_URLS = [
    "https://www.noon.com/egypt-ar/electronics-and-mobiles/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/electronics-and-mobiles/mobiles-and-accessories/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/electronics-and-mobiles/computers-and-accessories/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/electronics-and-mobiles/television-and-video/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/home-and-kitchen/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/home-appliances-31235/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/tools-and-home-improvement/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/grocery-store/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/search/?q=deals",
    "https://www.noon.com/egypt-ar/search/?q=خصم",
]

NOON_EXTRA_URLS = [
    "https://www.noon.com/egypt-ar/fashion/men-31225/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/fashion/women-31229/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/health/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/baby-products/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/toys-and-games/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/sports-and-outdoors/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/automotive/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/office-supplies/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/video-games-10181/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/pet-supplies/?sort[by]=discount_percent&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/electronics-and-mobiles/?sort[by]=discount_percent&sort[dir]=desc&page=2",
    "https://www.noon.com/egypt-ar/home-and-kitchen/?sort[by]=discount_percent&sort[dir]=desc&page=2",
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
    """يفتح صفحة المنتج في نون لجلب الاسم الكامل، البائع، المميزات، العروض الإضافية، والصورة."""
    page = await context.new_page()
    full_title, seller, features, image, promos = None, None, [], None, []
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
            return None, None, None, None, []
        data = await page.evaluate("""() => {
            const full_title = (document.querySelector('[data-qa="pdp-product-name"]') || document.querySelector('h1'))?.innerText?.trim();
            const image = document.querySelector('meta[property="og:image"]')?.content;
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
                    .filter(x => x.length > 25 && x.length < 220 && !x.includes('\\n'))
                : [];
            const promos = container
                ? [...container.querySelectorAll('[class*="coupon" i], [class*="voucher" i], [class*="promo" i], [data-qa*="coupon" i]')]
                    .map(e => e.innerText.trim()).filter(x => x.length > 6 && x.length < 180)
                : [];
            return {full_title, seller, feats, image, promos: promos.slice(0, 4)};
        }""")
        full_title = data.get("full_title")
        if is_blocked_title(full_title):
            full_title = None
        seller = data.get("seller")
        features = data.get("feats") or []
        image = data.get("image")
        promos = data.get("promos") or []
    except Exception as e:
        print(f"تعذر جلب تفاصيل منتج نون: {e}")
    finally:
        await page.close()
    return full_title, seller, features, image, promos

NOON_CARDS_JS = """() => [...document.querySelectorAll('a[href*="/p/"]')].map(a => {
    const qaImg = a.querySelector('[data-qa^="productImagePLP_"]');
    return {
        href: a.getAttribute('href'),
        text: a.innerText,
        name: qaImg ? qaImg.getAttribute('data-qa').replace('productImagePLP_', '') : null,
        price_text: a.querySelector('[data-qa="plp-product-box-price"]')?.innerText || null,
        express: !!a.querySelector('[data-qa="product-noon-express"]'),
        img: [...a.querySelectorAll('img')].map(i => i.currentSrc || i.src)
                .find(s => s && s.includes('nooncdn.com/p/')) || null,
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

    # إضافة بحث مباشر عن البراندات الساخنة (مثل أبو عوف و Fogg) في نون
    brand_urls = []
    for i in range(3):
        b_label, kw_list = HOT_BRANDS[(_brand_rot_idx + i) % len(HOT_BRANDS)]
        brand_urls.append((b_label, f"https://www.noon.com/egypt-ar/search/?q={quote_plus(kw_list[0])}"))
    _brand_rot_idx = (_brand_rot_idx + 3) % len(HOT_BRANDS)

    urls_to_scan = [(None, u) for u in (NOON_CORE_URLS + extra_batch)] + brand_urls

    products = {}
    for b_hint, url in urls_to_scan:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_selector('a[href*="/p/"]', timeout=15000)
            except Exception:
                pass
            for _ in range(5):
                await page.mouse.wheel(0, 2500)
                await page.wait_for_timeout(700)
            for c in await page.evaluate(NOON_CARDS_JS):
                if c["href"]:
                    base = c["href"].split('?')[0]
                    link = short_link(f"https://www.noon.com{base}" if base.startswith('/') else base)
                    if b_hint:
                        c["brand_section"] = (b_hint, url)
                    products.setdefault(link, c)
        except Exception as e:
            print(f"تعذر فتح {url}: {e}")
            continue

    print(f"تم العثور على {len(products)} منتج في نون مصر.")

    candidates = []
    brand_clusters = {}
    for full_link, card in products.items():
        try:
            card_text = card["text"]
            match = re.search(r'(?:خصم\s*(\d+)%|(\d+)%\s*(?:خصم|OFF))', card_text, re.IGNORECASE)
            if not match:
                continue
            info = parse_noon_card(card_text, card.get("price_text"))
            if not info["price"]:
                continue
            discount = int(match.group(1) or match.group(2))
            if info["list_price"] and info["list_price"] > info["price"]:
                discount = (1 - info["price"] / info["list_price"]) * 100

            prev_min, max_p, min_p = record_price(full_link, info["price"])
            freebie = is_almost_free(info["price"], info["list_price"])
            c_title = card.get("name") or noon_title(card_text)

            b_label = card.get("brand_section", (None, None))[0] or detect_brand(c_title)
            if b_label and discount >= 20:
                b_url = card.get("brand_section", (None, f"https://www.noon.com/egypt-ar/search/?q={quote_plus(b_label.split()[0])}"))[1]
                brand_clusters.setdefault(b_label, {"url": b_url, "items": []})["items"].append({
                    "title": c_title, "price": info["price"], "list_price": info["list_price"],
                    "discount": discount, "link": full_link, "img": card.get("img")
                })

            if (discount >= MIN_DISCOUNT or freebie) and full_link not in sent_deals:
                candidates.append((1 if freebie else 0, discount, full_link, card, info, prev_min, max_p, min_p, b_label))
        except Exception:
            continue

    # إرسال تنبيه مجمع لو فيه قسم/براند كامل عليه خصومات قوية في نون
    today_key = time.strftime("%Y-%m-%d")
    for b_label, b_data in brand_clusters.items():
        b_items = sorted(b_data["items"], key=lambda x: x["discount"], reverse=True)
        alert_id = f"section:noon:{b_label}:{today_key}"
        if len(b_items) >= 3 and b_items[0]["discount"] >= 25 and alert_id not in sent_deals:
            mark_deal_sent(alert_id)
            alert_msg = build_section_alert("Noon", b_label, b_data["url"], b_items)
            send_telegram_msg(alert_msg, image=b_items[0].get("img"))
            await asyncio.sleep(3)

    # ترتيب العروض: عروض "ببلاش" أولاً ثم الأعلى خصماً
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    print(f"تم العثور على {len(candidates)} عرض قوي جديد في نون مصر.")

    noon_sent = 0
    pdp_blocked = False
    for _, discount, full_link, card, info, prev_min, max_p, min_p, b_label in candidates:
        if noon_sent >= MAX_PER_CYCLE:
            break
        try:
            card_title = card.get("name") or noon_title(card["text"])
            full_title, seller, features, image, page_promos = None, None, [], None, []
            if not pdp_blocked:
                full_title, seller, features, image, page_promos = await noon_product_details(page.context, full_link)
                if features is None:
                    pdp_blocked = True
                    features = []

            title = full_title or card_title
            if not title or is_blocked_title(title):
                continue
            if not seller and card.get("express"):
                seller = "نون (Express)"

            stack_promos, stack_howto, extra_pct, extra_egp, extra_label, promo_links = detect_stacking_promos(
                card["text"], page_promos
            )
            sec_note = None
            if b_label and len(brand_clusters.get(b_label, {}).get("items", [])) >= 2:
                sec_note = f"قسم {b_label} عليه خصومات مجمعة حالياً على نون!"

            mark_deal_sent(full_link)
            noon_sent += 1
            msg = build_message(
                "Noon", title, info["price"], info["list_price"], discount, full_link,
                seller=seller, rating=info["rating"], reviews=info["reviews"], features=features,
                prev_min=prev_min, max_price=max_p, min_price=min_p,
                bought_badge=info.get("bought"),
                stack_promos=stack_promos, stack_howto=stack_howto, section_note=sec_note,
                extra_pct=extra_pct, extra_egp=extra_egp, extra_label=extra_label, promo_links=promo_links,
            )
            send_telegram_msg(msg, image=image or card.get("img"))
            await asyncio.sleep(3)
        except Exception as e:
            print(f"خطأ في منتج نون: {e}")
            continue

async def run_cycle(p):
    launch_args = ["--disable-blink-features=AutomationControlled"]
    if sys.platform == "win32":
        launch_args.append("--window-position=-32000,-32000")
    else:
        launch_args.extend(["--window-position=0,0", "--window-size=1366,768"])
    browser = await p.chromium.launch(
        headless=False,
        args=launch_args
    )
    try:
        context = await browser.new_context(
            locale="ar-EG",
            viewport={"width": 1366, "height": 768}
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()
        for scraper in (scrape_amazon_eg, scrape_noon_eg):
            try:
                await scraper(page)
            except Exception as e:
                print(f"Scraping error ({scraper.__name__}): {e}")
    finally:
        await browser.close()

async def main():
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

            print(f"انتظار {CHECK_INTERVAL // 60} دقيقة قبل الفحص القادم...")
            await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
