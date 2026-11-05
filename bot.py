import asyncio
import html
import json
import os
import re
import sys
import time
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
MAX_PER_CYCLE = 20  # أقصى عدد عروض تتبعت في الدورة الواحدة (الباقي يتبعت في الدورة اللي بعدها)
cycle_sent = 0
HASHTAG = "#عروض_يستاهل"
HISTORY_DAYS = 90
# المدة بين كل فحص والتاني بالثواني (افتراضياً 3 دقايق - فترة العروض)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "180"))

SENT_DEALS_FILE = os.path.join(BASE_DIR, "sent_deals.txt")
HISTORY_FILE = os.path.join(BASE_DIR, "price_history.json")

# ---------------------------------------------------------------------------
# حفظ العروض المرسلة وسجل الأسعار (لمعرفة أقل/أعلى سعر مسجّل)
# ---------------------------------------------------------------------------
sent_deals = set()
if os.path.exists(SENT_DEALS_FILE):
    with open(SENT_DEALS_FILE, "r", encoding="utf-8") as f:
        sent_deals = {line.strip() for line in f if line.strip()}

price_history = {}
if os.path.exists(HISTORY_FILE):
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            price_history = json.load(f)
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
# أدوات مساعدة
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

def build_message(store, title, price, list_price, discount, link,
                  seller=None, rating=None, reviews=None, features=None,
                  prev_min=None, max_price=None, min_price=None):
    store_ar = "أمازون" if store.lower() == "amazon" else ("نون" if store.lower() == "noon" else store)
    icon = "🔥" if store.lower() == "amazon" else "🟡"
    header = f"{icon} على {store_ar}"

    lines = [f"<b>{header}</b>", "", f"📦 <b>{html.escape(title)}</b>", ""]

    if price is not None:
        lines.append(f"💰 السعر الحالي: <b>{fmt(price)} ج.م</b>")
    if list_price:
        lines.append(f"❌ السعر المرجعي: <s>{fmt(list_price)} ج.م</s>")
    if price is not None and list_price and list_price > price:
        lines.append(f"📉 الخصم: <b>{discount:.0f}%</b> (وفّرت {fmt(list_price - price)} ج.م)")
    else:
        lines.append(f"📉 الخصم: <b>{discount:.0f}%</b>")
    if seller:
        lines.append(f"🏪 البائع: {html.escape(seller)}")
    if rating:
        lines.append(f"⭐ التقييم: {rating}" + (f" ({reviews} تقييم)" if reviews else ""))

    if features:
        lines += ["", "✨ <b>المميزات:</b>"]
        lines += [f"• {html.escape(f[:200])}" for f in features[:3]]

    if max_price is not None and min_price is not None and max_price > min_price:
        lines += [
            "",
            f"📊 أعلى سعر مسجّل: {fmt(max_price)} ج.م | أقل سعر: {fmt(min_price)} ج.م",
        ]

    lines += ["", f"🔗 <a href='{link}'>اشتري من هنا</a>", "", HASHTAG]
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
                          "disable_web_page_preview": False},
                    timeout=10,
                )
            if resp.ok:
                print(f"تم إرسال العرض إلى تليجرام ({chat_id}) بنجاح.")
            else:
                print(f"Telegram API error ({chat_id}, {resp.status_code}): {resp.text}")
        except Exception as e:
            print(f"Error sending message to {chat_id}: {e}")

# ---------------------------------------------------------------------------
# أمازون مصر
# ---------------------------------------------------------------------------
def parse_amazon_card(text):
    t = clean(text)
    deal = re.search(r'سعر العرض:+\s*([\d,]+(?:\.\d+)?)', t)
    lst = re.search(r'سعر القائمه:\s*([\d,]+(?:\.\d+)?)', t)
    rating = re.search(r'^\s*(\d\.\d)\s*$', t, re.MULTILINE)
    reviews = re.search(r'\(([\d.,]+\s*(?:ألف|K)?)\s*\)', t)
    lines = [
        l.strip() for l in t.split('\n')
        if len(l.strip()) > 15
        and not any(s in l for s in ("سعر العرض", "سعر القائمه", "تمت المطالبة", "عروض من هذه العلامة"))
    ]
    return {
        "price": to_float(deal.group(1)) if deal else None,
        "list_price": to_float(lst.group(1)) if lst else None,
        "rating": rating.group(1) if rating else None,
        "reviews": reviews.group(1).strip() if reviews else None,
        "title": lines[0][:150] if lines else "منتج على أمازون",
    }

async def amazon_product_details(context, link):
    """يفتح صفحة المنتج لجلب اسم البائع وأهم المميزات."""
    page = await context.new_page()
    seller, features, image = None, [], None
    try:
        await page.goto(link, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2000)
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
            return {seller, feats, image};
        }""")
        seller = data.get("seller")
        features = data.get("feats") or []
        image = data.get("image")
    except Exception as e:
        print(f"تعذر جلب تفاصيل المنتج: {e}")
    finally:
        await page.close()
    return seller, features, image

AMAZON_SCROLLS = int(os.getenv("AMAZON_SCROLLS", "10"))

async def scrape_amazon_eg(page):
    print("جاري فحص عروض أمازون مصر...")
    await page.goto("https://www.amazon.eg/deals", wait_until="domcontentloaded", timeout=60000)
    try:
        await page.wait_for_selector('div[data-testid="product-card"]', timeout=15000)
    except Exception:
        pass

    # القائمة "افتراضية" (الكروت بتختفي لما تنزل)، فبنجمع الكروت بعد كل تمريرة
    products = {}
    for _ in range(AMAZON_SCROLLS):
        cards = await page.evaluate("""() => [...document.querySelectorAll('div[data-testid="product-card"], div[data-testid="deal-card"]')]
            .map(c => ({href: (c.querySelector('a[data-testid="product-card-link"]') || c.querySelector('a'))?.getAttribute('href'),
                        text: c.innerText}))""")
        for c in cards:
            if c["href"]:
                base = c["href"].split('?')[0]
                link = f"https://www.amazon.eg{base}" if base.startswith('/') else base
                products.setdefault(link, c["text"])
        await page.mouse.wheel(0, 1800)
        await page.wait_for_timeout(1200)

    print(f"تم العثور على {len(products)} عرض في صفحة أمازون مصر.")
    amazon_sent = 0

    for full_link, text_content in products.items():
        try:
            match = re.search(r'(\d+)%', text_content)
            if not match:
                continue
            info = parse_amazon_card(text_content)
            discount = int(match.group(1))
            if info["price"] and info["list_price"]:
                discount = (1 - info["price"] / info["list_price"]) * 100

            prev_min, max_p, min_p = (None, None, None)
            if info["price"]:
                prev_min, max_p, min_p = record_price(full_link, info["price"])

            if discount < MIN_DISCOUNT or full_link in sent_deals or amazon_sent >= MAX_PER_CYCLE:
                continue
            mark_deal_sent(full_link)
            amazon_sent += 1

            seller, features, image = await amazon_product_details(page.context, full_link)
            msg = build_message(
                "Amazon", info["title"], info["price"], info["list_price"], discount, full_link,
                seller=seller, rating=info["rating"], reviews=info["reviews"], features=features,
                prev_min=prev_min, max_price=max_p, min_price=min_p,
            )
            send_telegram_msg(msg, image=image)
            await asyncio.sleep(3)  # تجنب حد الإرسال في تليجرام
        except Exception as e:
            print(f"خطأ في كارت أمازون: {e}")
            continue

# ---------------------------------------------------------------------------
# نون مصر (تغطية شاملة للأقسام + تفاصيل المنتج + المميزات + البائع + الصورة)
# ---------------------------------------------------------------------------
def parse_noon_card(text):
    t = clean(text)
    lines = [l.strip() for l in t.split('\n') if l.strip()]
    price = list_price = rating = reviews = None
    if "جنيه" in lines:
        i = lines.index("جنيه")
        nums = [to_float(x) for x in lines[i + 1:i + 3] if re.fullmatch(r'[\d,]+(?:\.\d+)?', x)]
        if nums:
            price = nums[0]
        if len(nums) > 1:
            list_price = nums[1]
    for j, l in enumerate(lines):
        if re.fullmatch(r'\d\.\d', l):
            rating = l
            if j + 1 < len(lines) and re.fullmatch(r'[\d.,]+K?', lines[j + 1]):
                reviews = lines[j + 1]
            break
    return {"price": price, "list_price": list_price, "rating": rating, "reviews": reviews}

# أقسام نون الأساسية (تُفحص في كل دورة)
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

# أقسام نون الإضافية والصفحات التالية (تُفحص بالتناوب لتغطية آلاف المنتجات بدون بطء)
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
    skip = ("أفضل المنتجات", "في ", "باقي", "خصم", "جنيه", "express", "الأكثر مبيعاً")
    for l in clean(text).split('\n'):
        l = l.strip()
        if len(l) > 15 and not any(l.startswith(s) for s in skip) and not l.startswith('#'):
            return l[:150]
    return "منتج على نون"

async def noon_product_details(context, link):
    """يفتح صفحة المنتج في نون لجلب الاسم الكامل، البائع، المميزات، وصورة المنتج."""
    page = await context.new_page()
    full_title, seller, features, image = None, None, [], None
    try:
        await page.goto(link, wait_until="domcontentloaded", timeout=40000)
        try:
            await page.wait_for_selector('h1', timeout=10000)
        except Exception:
            await page.wait_for_timeout(3000)
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
            return {full_title, seller, feats, image};
        }""")
        full_title = data.get("full_title")
        seller = data.get("seller")
        features = data.get("feats") or []
        image = data.get("image")
    except Exception as e:
        print(f"تعذر جلب تفاصيل منتج نون: {e}")
    finally:
        await page.close()
    return full_title, seller, features, image

async def scrape_noon_eg(page):
    global _noon_rot_idx
    print("جاري فحص عروض نون مصر...")
    extra_batch = [
        NOON_EXTRA_URLS[(_noon_rot_idx + i) % len(NOON_EXTRA_URLS)]
        for i in range(4)
    ]
    _noon_rot_idx = (_noon_rot_idx + 4) % len(NOON_EXTRA_URLS)
    urls_to_scan = NOON_CORE_URLS + extra_batch

    products = {}
    for url in urls_to_scan:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_selector('a[href*="/p/"]', timeout=15000)
            except Exception:
                pass
            # التمرير عدة مرات لتحميل منتجات أكثر
            for _ in range(6):
                await page.mouse.wheel(0, 2500)
                await page.wait_for_timeout(800)
            cards = await page.evaluate(
                "() => [...document.querySelectorAll('a[href*=\"/p/\"]')]"
                ".map(a => ({href: a.getAttribute('href'), text: a.innerText}))"
            )
            for c in cards:
                if c["href"]:
                    base = c["href"].split('?')[0]
                    link = f"https://www.noon.com{base}" if base.startswith('/') else base
                    products.setdefault(link, c["text"])
        except Exception as e:
            print(f"تعذر فتح {url}: {e}")
            continue

    print(f"تم العثور على {len(products)} منتج في نون مصر.")

    # استخراج وترتيب عروض نون من الأعلى خصماً للأقل
    candidates = []
    for full_link, card_text in products.items():
        try:
            match = re.search(r'(?:خصم\s*(\d+)%|(\d+)%\s*(?:خصم|OFF))', card_text, re.IGNORECASE)
            if not match:
                continue
            info = parse_noon_card(card_text)
            discount = int(match.group(1) or match.group(2))
            if info["price"] and info["list_price"]:
                discount = (1 - info["price"] / info["list_price"]) * 100

            prev_min, max_p, min_p = (None, None, None)
            if info["price"]:
                prev_min, max_p, min_p = record_price(full_link, info["price"])

            if discount >= MIN_DISCOUNT and full_link not in sent_deals:
                candidates.append((discount, full_link, card_text, info, prev_min, max_p, min_p))
        except Exception:
            continue

    candidates.sort(key=lambda x: x[0], reverse=True)
    print(f"تم العثور على {len(candidates)} عرض قوي جديد في نون مصر (خصم >= {MIN_DISCOUNT}%).")

    noon_sent = 0
    for discount, full_link, card_text, info, prev_min, max_p, min_p in candidates:
        if noon_sent >= MAX_PER_CYCLE:
            break
        try:
            mark_deal_sent(full_link)
            noon_sent += 1

            full_title, seller, features, image = await noon_product_details(page.context, full_link)
            title = full_title or noon_title(card_text)
            if not seller and "express" in card_text.lower():
                seller = "نون (Express)"

            msg = build_message(
                "Noon", title, info["price"], info["list_price"], discount, full_link,
                seller=seller, rating=info["rating"], reviews=info["reviews"], features=features,
                prev_min=prev_min, max_price=max_p, min_price=min_p,
            )
            send_telegram_msg(msg, image=image)
            await asyncio.sleep(3)  # تجنب حد الإرسال في تليجرام
        except Exception as e:
            print(f"خطأ في منتج نون: {e}")
            continue

async def run_cycle(p):
    global cycle_sent
    cycle_sent = 0
    # تشغيل المتصفح خارج حدود الشاشة لتجنب حظر الحماية (Akamai) في نون وأمازون
    browser = await p.chromium.launch(
        headless=False,
        args=[
            "--window-position=-32000,-32000",
            "--disable-blink-features=AutomationControlled",
        ]
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
                # متصفح جديد كل دورة لتفادي تهنيج المتصفح أو امتلاء الذاكرة
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
