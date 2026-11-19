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

import product_intelligence as pi
import girls_engine as ge
import tiktok_card_designer as designer

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

# ---------------------------------------------------------------------------
# إعدادات بوت البنات المستقل 100% (لا يلمس قناة @loqta78 أو ملفاتها أبداً)
# ---------------------------------------------------------------------------
BOT_TOKEN = os.getenv("GIRLS_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID", "6725805788")
GIRLS_CHANNEL_ID = os.getenv("GIRLS_CHANNEL_ID", "").strip() or "-1003921525835"
GIRLS_CHANNEL_USERNAME = os.getenv("GIRLS_CHANNEL_USERNAME", "").strip() or "@Loqta_G"
AMAZON_TAG = os.getenv("AMAZON_TAG", "anashesham-21")
NOON_COUPON = os.getenv("NOON_COUPON", "")

# إعدادات النشر التلقائي على تيك توك (يدعم Upload-Post API المعتمد + TikTok Official API v2 + Webhook)
UPLOAD_POST_API_KEY = os.getenv("UPLOAD_POST_API_KEY", "").strip()
UPLOAD_POST_USER = os.getenv("UPLOAD_POST_USER", "").strip()
TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "").strip()
TIKTOK_REFRESH_TOKEN = os.getenv("TIKTOK_REFRESH_TOKEN", "").strip()
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()
TIKTOK_POST_MODE = os.getenv("TIKTOK_POST_MODE", "DIRECT_POST").strip().upper()  # DIRECT_POST أو MEDIA_UPLOAD
TIKTOK_WEBHOOK_URL = os.getenv("TIKTOK_WEBHOOK_URL", "").strip()
# رابط استضافة صور مؤقتة (مطلوب فقط لـ TikTok Official API v2 إذا استُخدم بدون Upload-Post)
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "").strip()

# معدل النشر الحي على قناة تليجرام البنات (@Loqta_G) — نفس الذكاء والتنظيم بتاع القناة الرئيسية (@loqta78)
GIRLS_TG_MAX_PER_CYCLE = int(os.getenv("GIRLS_TG_MAX_PER_CYCLE", os.getenv("GIRLS_TG_MAX_PER_RUN", "6")))
GIRLS_HOURLY_CAP = int(os.getenv("GIRLS_HOURLY_CAP", "6"))  # حد أقصى 6 عروض عادية بالساعة (الخصومات >= 50% تنزل فوراً!)
GIRLS_QUIET_START = int(os.getenv("GIRLS_QUIET_START", "3"))  # ساعات الهدوء الليلي بتوقيت القاهرة (3–8 صباحاً)
GIRLS_QUIET_END = int(os.getenv("GIRLS_QUIET_END", "8"))
GIRLS_CYCLE_SLEEP_SEC = int(os.getenv("GIRLS_CYCLE_SLEEP_SEC", "360"))  # فحص متجدد كل 6 دقائق لايف
GIRLS_RUN_MINUTES = int(os.getenv("RUN_MINUTES", "0"))  # 0 = دورة واحدة | >0 = تشغيل مستمر على السيرفر
# تيك توك ثابت ومقيد على 4 أوقات ذروة يومياً فقط (1 بوست في كل وقت ذروة = مثالي لخوارزمية تيك توك وجذب متابعين لـ @Loqta_G)
GIRLS_TIKTOK_MAX_PER_SLOT = int(os.getenv("GIRLS_TIKTOK_MAX_PER_RUN", "1"))
FORCE_TIKTOK_ONCE = os.getenv("FORCE_TIKTOK_ONCE", "0").strip() == "1"

# ملفات حالة مستقلة تماماً عن القناة العامة
GIRLS_SENT_TG_FILE = os.path.join(BASE_DIR, "girls_sent_deals.txt")
GIRLS_SENT_TT_FILE = os.path.join(BASE_DIR, "girls_tiktok_sent.txt")
GIRLS_STATE_FILE = os.path.join(BASE_DIR, "girls_state.json")

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٬٫", "0123456789,.")


def _cairo_now():
    """يرجع توقيت القاهرة الحالي (UTC+2)."""
    return time.gmtime(time.time() + 2 * 3600)


def _is_girls_quiet_hours():
    h = _cairo_now().tm_hour
    if GIRLS_QUIET_START < GIRLS_QUIET_END:
        return GIRLS_QUIET_START <= h < GIRLS_QUIET_END
    return h >= GIRLS_QUIET_START or h < GIRLS_QUIET_END


def _count_girls_sent_in_window(state, seconds=3600):
    now = time.time()
    return sum(1 for ts in (state.get("sent_timestamps") or []) if ts > now - seconds)


def _can_post_girls_tg_now(state, discount=0.0):
    """
    نفس نظام Anti-Spam وساعات الهدوء الليلي في القناة الرئيسية (@loqta78):
    - خصومات >= 65% (ببلاش) تنزل فوراً 24/7.
    - خصومات >= 50% (نص السعر) تنزل حتى في ساعات الهدوء الليلي وتتجاوز حد الساعة.
    - العروض العادية تلتزم بحد 6 عروض/ساعة وساعات الهدوء (3–8 صباحاً).
    """
    if discount >= 65.0:
        return True
    if _is_girls_quiet_hours() and discount < 50.0:
        return False
    if discount < 50.0 and _count_girls_sent_in_window(state, 3600) >= GIRLS_HOURLY_CAP:
        return False
    return True


def _get_active_tiktok_slot():
    """
    تيك توك ثابت ومقيد على 4 أوقات ذروة فقط بتوقيت القاهرة (1 بوست في كل وقت = 4 يومياً):
    1:00 ظهراً | 5:00 عصراً | 8:30 مساءً | 11:00 مساءً.
    """
    ct = _cairo_now()
    date_str = f"{ct.tm_year:04d}-{ct.tm_mon:02d}-{ct.tm_mday:02d}"
    h, m = ct.tm_hour, ct.tm_min
    if h == 13:
        return f"{date_str}|13:00"
    if h == 17:
        return f"{date_str}|17:00"
    if (h == 20 and m >= 15) or (h == 21 and m < 30):
        return f"{date_str}|20:30"
    if h == 23:
        return f"{date_str}|23:00"
    return None


def clean_txt(s):
    return re.sub(r'\s+', ' ', (s or "").translate(_AR_DIGITS)).strip()


def to_float(val):
    if not val:
        return None
    m = re.search(r'(\d[\d,]*(?:\.\d+)?)', str(val).translate(_AR_DIGITS))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except Exception:
        return None


def canonical_url(link):
    if not link:
        return ""
    m = re.search(r'/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})', link, re.I)
    if m and ("amazon" in link.lower() or "amzn" in link.lower()):
        return f"https://www.amazon.eg/dp/{m.group(1).upper()}"
    m2 = re.search(r'/([A-Z0-9]{8,})/p/?', link, re.I)
    if m2 and "noon.com" in link.lower():
        return f"https://www.noon.com/egypt-ar/{m2.group(1).upper()}/p/"
    return link.split("?")[0]


def make_buy_url(url):
    u = canonical_url(url)
    if "amazon." in u.lower() and AMAZON_TAG:
        sep = "&" if "?" in u else "?"
        return f"{u}{sep}tag={AMAZON_TAG}&linkCode=ll1"
    return u


def _load_set(path):
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def _append_set(path, s_set, val):
    if val not in s_set:
        s_set.add(val)
        with open(path, "a", encoding="utf-8") as f:
            f.write(val + "\n")


def _load_state():
    st = {}
    if os.path.exists(GIRLS_STATE_FILE):
        try:
            with open(GIRLS_STATE_FILE, "r", encoding="utf-8") as f:
                st = json.load(f) or {}
        except Exception:
            st = {}
    st.setdefault("query_idx", 0)
    st.setdefault("last_tt_cat", "")
    st.setdefault("recent_names", {})
    st.setdefault("price_history", {})
    st.setdefault("sent_timestamps", [])
    st.setdefault("tiktok_slots_sent", [])
    st.setdefault("sent_today_meta", [])
    st.setdefault("last_digest_date", "")
    st.setdefault("tg_update_offset", 0)
    return st


def _save_state(st):
    # تقليم السجل القديم لإبقاء الملف خفيفاً
    now = time.time()
    st["recent_names"] = {
        k: v for k, v in (st.get("recent_names") or {}).items()
        if now - v < 86400 * 3
    }
    st["sent_timestamps"] = [
        int(ts) for ts in (st.get("sent_timestamps") or [])
        if now - ts < 86400
    ]
    st["sent_today_meta"] = [
        m for m in (st.get("sent_today_meta") or [])
        if now - (m.get("ts") or 0) < 86400
    ][-80:]
    st["tiktok_slots_sent"] = (st.get("tiktok_slots_sent") or [])[-32:]
    with open(GIRLS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def _norm_name_key(name_ar):
    s = re.sub(r'[أإآا]', 'ا', (name_ar or "").lower())
    s = re.sub(r'[ةه]', 'ه', s)
    s = re.sub(r'[يى]', 'ي', s)
    s = re.sub(r'[^\w\u0600-\u06FF]+', ' ', s).strip()
    return s[:60]


# ---------------------------------------------------------------------------
# 1. فحص عروض البنات فقط على أمازون مصر ونون مصر
# ---------------------------------------------------------------------------
async def scrape_girls_amazon(page, queries_batch):
    items = {}
    urls = list(ge.GIRLS_AMAZON_DEAL_URLS[:3]) + [
        f"https://www.amazon.eg/s?k={quote_plus(q)}" for _, q in queries_batch
    ]
    for url in urls:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(1800)
            cards = await page.evaluate("""() => [...document.querySelectorAll('div[data-component-type="s-search-result"]')].slice(0, 22).map(c => {
                const asin = c.getAttribute('data-asin');
                const title = c.querySelector('h2')?.innerText?.trim();
                const price = c.querySelector('.a-price:not(.a-text-price) .a-offscreen')?.innerText
                    || c.querySelector('.a-price .a-offscreen')?.innerText;
                const list_price = c.querySelector('.a-price.a-text-price .a-offscreen')?.innerText
                    || c.querySelector('span[data-a-strike="true"] .a-offscreen')?.innerText;
                const rating = c.querySelector('i[class*="a-icon-star"] span.a-icon-alt, span[aria-label*="من 5"]')?.innerText;
                const reviews = c.querySelector('a[href*="#customerReviews"] span, span.s-underline-text')?.innerText;
                const img = c.querySelector('img.s-image')?.src;
                return {asin, title, price, list_price, rating, reviews, img, text: c.innerText};
            })""")
            for sc in cards:
                asin = (sc.get("asin") or "").strip().upper()
                if not asin or not sc.get("title") or not sc.get("price"):
                    continue
                if not ge.is_girls_product_text_safe(sc["title"]):
                    continue
                p = to_float(sc["price"])
                lp = to_float(sc.get("list_price"))
                if not p or p < 20 or not lp or lp <= p:
                    continue
                disc = (1.0 - p / lp) * 100.0
                if disc < 12.0 or disc >= 92.0:
                    continue
                link = f"https://www.amazon.eg/dp/{asin}"
                if link in items:
                    continue
                rm = re.search(r'(\d[.,]\d)', sc.get("rating") or "")
                rat = rm.group(1).replace(",", ".") if rm else None
                rev_m = re.search(r'([\d,]+)', clean_txt(sc.get("reviews") or ""))
                rev = rev_m.group(1) if rev_m else None
                # تحسين جودة صورة أمازون من المصغرة إلى عالية الدقة 1000px
                img_u = sc.get("img") or ""
                if "/images/I/" in img_u:
                    img_u = re.sub(r'\._[A-Za-z0-9_,]+_\.', '._SL1000_.', img_u)
                items[link] = {
                    "store": "Amazon",
                    "link": link,
                    "title": clean_txt(sc["title"]),
                    "price": p,
                    "list_price": lp,
                    "discount": disc,
                    "rating": rat,
                    "reviews": rev,
                    "image": img_u,
                    "card_text": sc.get("text") or "",
                }
        except Exception as e:
            print(f"[Girls Amazon] skip {url[:60]}: {e}")
    return list(items.values())


async def scrape_girls_noon(page, queries_batch):
    items = {}
    urls = list(ge.GIRLS_NOON_DEAL_URLS[:2]) + [
        f"https://www.noon.com/egypt-ar/search/?q={quote_plus(q)}" for _, q in queries_batch[:3]
    ]
    for url in urls:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2400)
            cards = await page.evaluate("""() => [...document.querySelectorAll('a[href*="/p/"]')].slice(0, 26).map(a => {
                const href = a.getAttribute('href') || '';
                const imgEl = a.querySelector('img[src*="nooncdn"], img');
                const img = imgEl ? (imgEl.currentSrc || imgEl.src || '') : '';
                const title = a.querySelector('[data-qa="product-name"]')?.innerText
                    || imgEl?.getAttribute('alt') || '';
                const text = a.innerText || '';
                return {href, img, title, text};
            })""")
            for sc in cards:
                href = sc.get("href") or ""
                if "/p/" not in href:
                    continue
                full_u = canonical_url(f"https://www.noon.com{href}" if href.startswith("/") else href)
                if not full_u or full_u in items:
                    continue
                raw_t = clean_txt(sc.get("title") or "")
                txt = clean_txt(sc.get("text") or "")
                if not raw_t or len(raw_t) < 8:
                    continue
                if not ge.is_girls_product_text_safe(raw_t):
                    continue
                m_disc = re.search(r'(?:خصم\s*(\d+)%|(\d+)%\s*(?:خصم|OFF))', txt, re.I)
                badge_d = int(m_disc.group(1) or m_disc.group(2)) if m_disc else 0
                nums = [to_float(x) for x in re.findall(r'(?:جنيه|ج\.م|EGP)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:جنيه|ج\.م|EGP)', txt, re.I)]
                flat_nums = [to_float(a or b) for a, b in re.findall(r'(?:جنيه|ج\.م|EGP)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:جنيه|ج\.م|EGP)', txt, re.I)]
                flat_nums = [x for x in flat_nums if x and x >= 15]
                if not flat_nums:
                    continue
                p = flat_nums[0]
                lp = flat_nums[1] if len(flat_nums) > 1 and flat_nums[1] > p else (round(p / (1 - badge_d / 100.0), 2) if 15 <= badge_d <= 85 else None)
                if not lp or lp <= p:
                    continue
                disc = (1.0 - p / lp) * 100.0
                if disc < 18.0 or disc >= 90.0:
                    continue
                rat_m = re.search(r'\b([345]\.\d)\b', txt)
                items[full_u] = {
                    "store": "Noon",
                    "link": full_u,
                    "title": raw_t,
                    "price": p,
                    "list_price": lp,
                    "discount": disc,
                    "rating": rat_m.group(1) if rat_m else None,
                    "reviews": None,
                    "image": sc.get("img") or "",
                    "card_text": txt,
                }
        except Exception as e:
            print(f"[Girls Noon] skip {url[:60]}: {e}")
    return list(items.values())


async def fetch_pdp_details(context, item):
    """يجلب التفاصيل الكاملة والصورة الأصلية والوصف الإنجليزي والعربي من صفحة المنتج."""
    page = await context.new_page()
    res = {
        "title": item["title"],
        "brand": "",
        "seller": "Amazon.eg" if item["store"] == "Amazon" else "نون مصر",
        "features": [],
        "image": item.get("image") or "",
        "en_title": "",
        "en_brand": "",
        "breadcrumbs": [],
    }
    try:
        await page.goto(item["link"], wait_until="domcontentloaded", timeout=35000)
        await page.wait_for_timeout(1600)
        if item["store"] == "Amazon":
            data = await page.evaluate("""() => {
                const title = document.querySelector('#productTitle')?.innerText?.trim() || '';
                const brand = document.querySelector('#bylineInfo')?.innerText?.trim() || '';
                const seller = document.querySelector('#sellerProfileTriggerId, #merchant-info a')?.innerText?.trim() || '';
                const feats = [...document.querySelectorAll('#feature-bullets li span.a-list-item')]
                    .map(e => e.innerText.trim()).filter(t => t.length > 10).slice(0, 5);
                const img = document.querySelector('#landingImage')?.getAttribute('data-old-hires')
                    || document.querySelector('#landingImage')?.src || '';
                const crumbs = [...document.querySelectorAll('#wayfinding-breadcrumbs_feature_div li a')]
                    .map(e => e.innerText.trim()).filter(Boolean);
                return {title, brand, seller, feats, img, crumbs};
            }""")
            if data.get("title"):
                res["title"] = clean_txt(data["title"])
            if data.get("brand"):
                res["brand"] = clean_txt(data["brand"])
            if data.get("seller"):
                res["seller"] = clean_txt(data["seller"])
            if data.get("feats"):
                res["features"] = data["feats"]
            if data.get("img"):
                res["image"] = data["img"]
            if data.get("crumbs"):
                res["breadcrumbs"] = data["crumbs"]
        else:
            data = await page.evaluate("""() => {
                const title = document.querySelector('h1')?.innerText?.trim() || '';
                const feats = [...document.querySelectorAll('[class*="highlight"] li, [class*="Highlight"] li')]
                    .map(e => e.innerText.trim()).filter(t => t.length > 10).slice(0, 5);
                let ldBrand = '', ldImg = '';
                for (const sc of document.querySelectorAll('script[type="application/ld+json"]')) {
                    try {
                        const o = JSON.parse(sc.textContent);
                        const arr = Array.isArray(o) ? o : [o];
                        for (const p of arr) {
                            if (p['@type'] === 'Product') {
                                if (p.brand) ldBrand = typeof p.brand === 'string' ? p.brand : (p.brand.name || '');
                                if (p.image) ldImg = Array.isArray(p.image) ? p.image[0] : p.image;
                            }
                        }
                    } catch (e) {}
                }
                return {title, feats, ldBrand, ldImg};
            }""")
            if data.get("title"):
                res["title"] = clean_txt(data["title"])
            if data.get("ldBrand"):
                res["brand"] = clean_txt(data["ldBrand"])
            if data.get("feats"):
                res["features"] = data["feats"]
            if data.get("ldImg"):
                res["image"] = data["ldImg"]
    except Exception as e:
        print(f"[Girls PDP] error {item['link']}: {e}")
    finally:
        await page.close()
    return res


# ---------------------------------------------------------------------------
# 2. النشر على قناة تليجرام البنات المستقلة
# ---------------------------------------------------------------------------
def send_telegram_photo_post(chat_id, caption_html, image_url, reply_markup=None):
    if not BOT_TOKEN or not chat_id:
        return False
    img_bytes = None
    if image_url and image_url.startswith("http"):
        try:
            r = requests.get(image_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if r.ok and len(r.content) > 800:
                img_bytes = r.content
        except Exception:
            pass
    try:
        if img_bytes:
            data = {"chat_id": chat_id, "caption": caption_html[:1000], "parse_mode": "HTML"}
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)
            resp = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data=data,
                files={"photo": ("deal.jpg", img_bytes, "image/jpeg")},
                timeout=25,
            )
            return resp.ok
        else:
            payload = {"chat_id": chat_id, "text": caption_html, "parse_mode": "HTML", "disable_web_page_preview": True}
            if reply_markup:
                payload["reply_markup"] = reply_markup
            resp = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload, timeout=15)
            return resp.ok
    except Exception as e:
        print(f"[Girls TG] send error: {e}")
        return False


def send_tiktok_preview_to_owner(slide_paths, tiktok_caption):
    """يرسل السلايدات الـ 3 المصممة + كابشن تيك توك الجاهز لصاحب البوت في الخاص كمعاينة/نسخة احتياطية."""
    if not BOT_TOKEN or not OWNER_CHAT_ID:
        return False
    try:
        media = []
        files = {}
        for idx, p in enumerate(slide_paths):
            key = f"photo{idx}"
            files[key] = (os.path.basename(p), open(p, "rb"), "image/jpeg")
            entry = {"type": "photo", "media": f"attach://{key}"}
            if idx == 0:
                entry["caption"] = f"🎀 جاهز للنشر على تيك توك (Carousel 3 صور):\n\n{tiktok_caption[:900]}"
            media.append(entry)
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup",
            data={"chat_id": OWNER_CHAT_ID, "media": json.dumps(media)},
            files=files,
            timeout=35,
        )
        for fobj in files.values():
            fobj[1].close()
        return resp.ok
    except Exception as e:
        print(f"[Girls Preview] error: {e}")
        return False


# ---------------------------------------------------------------------------
# 3. النشر التلقائي 100% على تيك توك (Upload-Post API / TikTok Official API v2 / Webhook)
# ---------------------------------------------------------------------------
def _upload_image_for_public_url(local_path):
    """يرفع صورة مؤقتاً لإنشاء رابط HTTPS عام مطلوب لـ TikTok Official API v2 Photo Mode."""
    if IMGBB_API_KEY:
        try:
            with open(local_path, "rb") as f:
                r = requests.post(
                    "https://api.imgbb.com/1/upload",
                    params={"key": IMGBB_API_KEY, "expiration": "3600"},
                    files={"image": f},
                    timeout=25,
                )
            if r.ok:
                return (r.json().get("data") or {}).get("url")
        except Exception:
            pass
    # بديل مجاني بدون مفتاح (catbox litterbox مؤقت لمدة ساعة)
    try:
        with open(local_path, "rb") as f:
            r = requests.post(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data={"reqtype": "fileupload", "time": "1h"},
                files={"fileToUpload": (os.path.basename(local_path), f, "image/jpeg")},
                timeout=25,
            )
        if r.ok and r.text.strip().startswith("http"):
            return r.text.strip()
    except Exception:
        pass
    return None


def _refresh_tiktok_access_token():
    """يجدد TikTok OAuth2 access_token تلقائياً لو توفر refresh_token."""
    if not (TIKTOK_REFRESH_TOKEN and TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET):
        return TIKTOK_ACCESS_TOKEN
    try:
        r = requests.post(
            "https://open.tiktokapis.com/v2/oauth/token/",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": TIKTOK_CLIENT_KEY,
                "client_secret": TIKTOK_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": TIKTOK_REFRESH_TOKEN,
            },
            timeout=20,
        )
        if r.ok and r.json().get("access_token"):
            return r.json()["access_token"]
    except Exception as e:
        print(f"[TikTok OAuth] refresh error: {e}")
    return TIKTOK_ACCESS_TOKEN


def publish_to_tiktok(slide_paths, title, caption):
    """
    ناشر تيك توك التلقائي المتعدد (Photo Mode Carousel 3 صور + موسيقى ترند تلقائية):
    1) Upload-Post API (أسرع نشر تلقائي Public 100% من أول يوم)
    2) TikTok Official Content Posting API v2 (مجاني 100%)
    3) Webhook مخصص (Make.com / Zapier)
    """
    # المسار 1: Upload-Post API المعتمد من تيك توك
    if UPLOAD_POST_API_KEY and UPLOAD_POST_USER:
        try:
            opened = []
            files_list = []
            for p in slide_paths:
                fh = open(p, "rb")
                opened.append(fh)
                files_list.append(("photos[]", (os.path.basename(p), fh, "image/jpeg")))
            r = requests.post(
                "https://api.upload-post.com/api/upload_photos",
                headers={"Authorization": f"Apikey {UPLOAD_POST_API_KEY}"},
                data={
                    "user": UPLOAD_POST_USER,
                    "platform[]": "tiktok",
                    "title": title[:90],
                    "description": caption[:2000],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "auto_add_music": "true",
                    "photo_cover_index": "0",
                },
                files=files_list,
                timeout=60,
            )
            for fh in opened:
                fh.close()
            if r.ok:
                print(f"✅ [TikTok Upload-Post] Published Photo Carousel successfully: {r.text[:160]}")
                return True, "upload-post"
            print(f"⚠️ [TikTok Upload-Post] HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"⚠️ [TikTok Upload-Post] error: {e}")

    # المسار 2: TikTok Official Content Posting API v2 (Photo Mode)
    token = _refresh_tiktok_access_token()
    if token:
        public_urls = []
        for p in slide_paths:
            pu = _upload_image_for_public_url(p)
            if pu:
                public_urls.append(pu)
        if len(public_urls) == len(slide_paths):
            try:
                body = {
                    "post_info": {
                        "title": title[:90],
                        "description": caption[:2000],
                        "disable_comment": False,
                        "privacy_level": "PUBLIC_TO_EVERYONE" if TIKTOK_POST_MODE == "DIRECT_POST" else "SELF_ONLY",
                        "auto_add_music": True,
                    },
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "photo_cover_index": 0,
                        "photo_images": public_urls,
                    },
                    "post_mode": TIKTOK_POST_MODE,
                    "media_type": "PHOTO",
                }
                r = requests.post(
                    "https://open.tiktokapis.com/v2/post/publish/content/init/",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json; charset=UTF-8",
                    },
                    json=body,
                    timeout=30,
                )
                if r.ok and (r.json().get("error") or {}).get("code") in (None, "ok"):
                    print(f"✅ [TikTok Official API] Published ({TIKTOK_POST_MODE}): {r.text[:180]}")
                    return True, f"tiktok-official-{TIKTOK_POST_MODE}"
                print(f"⚠️ [TikTok Official API] HTTP {r.status_code}: {r.text[:250]}")
            except Exception as e:
                print(f"⚠️ [TikTok Official API] error: {e}")

    # المسار 3: Webhook خارجي (Make.com / Zapier)
    if TIKTOK_WEBHOOK_URL:
        public_urls = [_upload_image_for_public_url(p) for p in slide_paths]
        public_urls = [u for u in public_urls if u]
        if public_urls:
            try:
                r = requests.post(
                    TIKTOK_WEBHOOK_URL,
                    json={"title": title, "caption": caption, "photo_urls": public_urls},
                    timeout=25,
                )
                if r.ok:
                    print("✅ [TikTok Webhook] Sent successfully!")
                    return True, "webhook"
            except Exception as e:
                print(f"⚠️ [TikTok Webhook] error: {e}")

    return False, "unconfigured"


# ---------------------------------------------------------------------------
# 4. تقارير الشات الخاص (@Loqta_Girlsbot) + ملخص أقوى 5 لقطات بنات يومياً
# ---------------------------------------------------------------------------
def _send_tg_text(chat_id, text_html, reply_markup=None):
    if not BOT_TOKEN or not chat_id:
        return False
    payload = {
        "chat_id": chat_id,
        "text": text_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload, timeout=15)
        return r.ok
    except Exception as e:
        print(f"[Girls TG text] error: {e}")
        return False


def build_girls_stats_report(state):
    """تقرير حالة حي ومستقل لبوت وقناة البنات (@Loqta_G) عند إرسال /stats في شات @Loqta_Girlsbot."""
    now = time.time()
    ct = _cairo_now()
    today_str = f"{ct.tm_year:04d}-{ct.tm_mon:02d}-{ct.tm_mday:02d}"
    sent_1h = _count_girls_sent_in_window(state, 3600)
    sent_24h = _count_girls_sent_in_window(state, 86400)
    meta_24 = [m for m in (state.get("sent_today_meta") or []) if now - (m.get("ts") or 0) < 86400]
    amz_24 = sum(1 for m in meta_24 if str(m.get("store", "")).lower() == "amazon")
    noon_24 = sum(1 for m in meta_24 if str(m.get("store", "")).lower() != "amazon")
    tt_today = [s.split("|", 1)[1] for s in (state.get("tiktok_slots_sent") or []) if s.startswith(f"{today_str}|")]
    quiet_txt = "🌙 هدوء ليلي (خصم 50%+ فقط)" if _is_girls_quiet_hours() else "☀️ نشر حي مستمر"
    lines = [
        f"🎀📊 <b>تقرير حالة بوت «لقطة بنات» ({GIRLS_CHANNEL_USERNAME})</b>",
        f"🕒 وقت القاهرة: <code>{ct.tm_hour:02d}:{ct.tm_min:02d}</code> | {quiet_txt}",
        "",
        f"📨 <b>عروض قناة البنات آخر 24 ساعة:</b> {sent_24h}",
        f"   • 🔥 أمازون: <b>{amz_24}</b> | 🟡 نون: <b>{noon_24}</b>",
        f"⏱️ <b>آخر ساعة:</b> {sent_1h} / {GIRLS_HOURLY_CAP} (نفس نظام Anti-Spam)",
        f"🎬 <b>تيك توك اليوم (ثابت 4 ذروة):</b> {len(tt_today)} / 4" + (f" ({'، '.join(tt_today)})" if tt_today else ""),
    ]
    if meta_24:
        top3 = sorted(meta_24, key=lambda m: (m.get("v_score") or 0, m.get("discount") or 0), reverse=True)[:3]
        lines += ["", "🏆 <b>أقوى 3 لقطات بنات اليوم:</b>"]
        for idx, m in enumerate(top3, 1):
            st_ar = "أمازون" if str(m.get("store", "")).lower() == "amazon" else "نون"
            pr = m.get("price") or 0
            pr_s = f"{int(round(pr)):,}" if pr == int(pr) else f"{pr:,.2f}"
            lines.append(f"{idx}️⃣ {html.escape(str(m.get('name_ar') or '')[:55])} — <b>{pr_s} ج.م</b> ({m.get('discount', 0):.0f}% على {st_ar})")
    return "\n".join(lines)


def maybe_send_girls_daily_top5_digest(state):
    """ملخص يومي لأقوى 5 لقطات بنات الساعة 9:30 مساءً بتوقيت القاهرة (بعيد عن موعد القناة العامة 9:00 م)."""
    ct = _cairo_now()
    if not (ct.tm_hour == 21 and ct.tm_min >= 25):
        return False
    today_str = f"{ct.tm_year:04d}-{ct.tm_mon:02d}-{ct.tm_mday:02d}"
    if state.get("last_digest_date") == today_str:
        return False
    now = time.time()
    cands = [m for m in (state.get("sent_today_meta") or []) if now - (m.get("ts") or 0) < 86400 and m.get("link") and m.get("name_ar")]
    if len(cands) < 3:
        return False
    cands.sort(key=lambda m: (m.get("v_score") or 0, m.get("discount") or 0), reverse=True)
    top5 = []
    seen_nk = set()
    for m in cands:
        nk = _norm_name_key(m["name_ar"])
        if nk in seen_nk:
            continue
        seen_nk.add(nk)
        top5.append(m)
        if len(top5) >= 5:
            break
    if len(top5) < 3:
        return False

    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    lines = [
        "🎀🏆 <b>ملخص أقوى 5 لقطات بنات اليوم في «لقطة بنات»!</b>",
        "<i>لو فاتك أي عرض النهارده، دي أقوى خصومات الجمال اللي نزلناها:</i>",
        "",
    ]
    kb_rows = []
    for idx, m in enumerate(top5):
        nm = str(m["name_ar"])
        pr = float(m.get("price") or 0)
        lp = float(m.get("list_price") or 0)
        disc = float(m.get("discount") or 0)
        st_ar = "أمازون" if str(m.get("store", "")).lower() == "amazon" else "نون"
        pr_s = f"{int(round(pr)):,}" if pr == int(pr) else f"{pr:,.2f}"
        old_s = f"<s>{int(round(lp)):,}</s> ← " if lp > pr else ""
        disc_s = f" (خصم {disc:.0f}%)" if disc >= 5 else ""
        lines.append(f"{nums[idx]} <b>{html.escape(nm[:62])}</b>\n   💰 {old_s}<b>{pr_s} ج.م</b>{disc_s} — {st_ar}")
        btn_nm = nm[:26].rsplit(" ", 1)[0] if len(nm) > 26 and " " in nm[:26] else nm[:26]
        kb_rows.append([{"text": f"🛍️ {idx+1}. اطلبي {btn_nm} ({pr_s} ج.م)", "url": make_buy_url(m["link"])}])

    ch_raw = str(GIRLS_CHANNEL_USERNAME or "@Loqta_G").strip()
    ch_url = ch_raw if ch_raw.startswith("http") else f"https://t.me/{ch_raw.lstrip('@')}"
    share_url = "https://t.me/share/url?url=" + quote_plus(ch_url) + "&text=" + quote_plus("ملخص أقوى 5 لقطات بنات اليوم على أمازون ونون مصر 🎀🔥")
    kb_rows.append([{"text": "💌 شاركي ملخص اليوم مع صاحباتك", "url": share_url}])
    lines += [
        "",
        "👇 <i>اضغطي على رقم أي عرض بالأسفل للطلب المباشر قبل انتهاء الخصم</i>",
        "",
        "#لقطة_بنات #أقوى_عروض_اليوم",
    ]
    if _send_tg_text(GIRLS_CHANNEL_ID, "\n".join(lines), reply_markup={"inline_keyboard": kb_rows}):
        state["last_digest_date"] = today_str
        print(f"🎀🏆 تم إرسال ملخص أقوى 5 لقطات بنات اليوم ({today_str}) بنجاح!")
        return True
    return False


def poll_girls_private_chat(state):
    """يتابع رسائل الشات الخاص المستقل لبوت @Loqta_Girlsbot (مثل /stats أو /start) لصاحب البوت فقط."""
    if not BOT_TOKEN:
        return
    offset = int(state.get("tg_update_offset") or 0)
    params = {"timeout": 0, "allowed_updates": json.dumps(["message"])}
    if offset > 0:
        params["offset"] = offset
    try:
        r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", params=params, timeout=8)
        if not r.ok:
            return
        updates = r.json().get("result") or []
    except Exception:
        return
    for upd in updates:
        uid = int(upd.get("update_id") or 0)
        if uid >= offset:
            offset = uid + 1
            state["tg_update_offset"] = offset
        msg = upd.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        if str(chat_id) != str(OWNER_CHAT_ID):
            continue
        txt = (msg.get("text") or "").strip()
        if not txt:
            continue
        low = txt.lower()
        if low.startswith("/stats") or txt in ("احصائيات", "إحصائيات", "الاحصائيات", "الإحصائيات"):
            _send_tg_text(chat_id, build_girls_stats_report(state))
        elif low.startswith("/start"):
            _send_tg_text(
                chat_id,
                f"🎀 <b>بوت «لقطة بنات» شغّال لايف ومستقل 100%!</b>\n\n"
                f"📢 القناة: {GIRLS_CHANNEL_USERNAME} (نشر مستمر بنفس معدل القناة الرئيسية)\n"
                f"🎬 تيك توك: ثابت 4 بوستات يومياً في أوقات الذروة (1 ظهراً، 5 عصراً، 8:30 م، 11 م)\n"
                f"📊 ابعت <code>/stats</code> في أي وقت لتقرير الإحصائيات الفوري.",
            )


# ---------------------------------------------------------------------------
# 5. الدورة الرئيسية المستقلة لبوت البنات (تليجرام لايف مستمر + تيك توك 4 ذروات ثابتة)
# ---------------------------------------------------------------------------
async def run_girls_cycle(force_tiktok=False):
    ct = _cairo_now()
    print(f"\n===== 🎀 بدء دورة بوت البنات المستقل (القاهرة {ct.tm_hour:02d}:{ct.tm_min:02d}) =====")
    sent_tg = _load_set(GIRLS_SENT_TG_FILE)
    sent_tt = _load_set(GIRLS_SENT_TT_FILE)
    state = _load_state()
    poll_girls_private_chat(state)

    q_idx = int(state.get("query_idx", 0))
    queries_batch = [
        ge.GIRLS_SEARCH_QUERIES[(q_idx + i) % len(ge.GIRLS_SEARCH_QUERIES)]
        for i in range(5)
    ]
    state["query_idx"] = (q_idx + 5) % len(ge.GIRLS_SEARCH_QUERIES)

    launch_args = ["--disable-blink-features=AutomationControlled"]
    if sys.platform == "win32":
        launch_args.append("--window-position=-32000,-32000")
    else:
        launch_args.extend(["--window-position=0,0", "--window-size=1366,768"])

    raw_candidates = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=launch_args)
        try:
            context = await browser.new_context(locale="ar-EG", viewport={"width": 1366, "height": 768})
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = await context.new_page()

            amz_items = await scrape_girls_amazon(page, queries_batch)
            noon_items = await scrape_girls_noon(page, queries_batch)
            print(f"🔎 تم العثور على {len(amz_items)} عرض بنات مبدئي على أمازون و {len(noon_items)} على نون.")

            # تصفية مبدئية وإزالة المكرر ثم جلب تفاصيل الصفحات لأفضل 18 مرشح
            pool = [it for it in (amz_items + noon_items) if it["link"] not in sent_tg or it["link"] not in sent_tt]
            pool.sort(key=lambda x: (1 if x["store"] == "Amazon" else 0, x["discount"]), reverse=True)

            for item in pool[:18]:
                pdp = await fetch_pdp_details(context, item)
                intel = ge.classify_girls_product(
                    title=pdp["title"],
                    brand=pdp["brand"],
                    features=pdp["features"],
                    en_title=pdp["en_title"],
                    en_brand=pdp["en_brand"],
                    breadcrumbs=pdp["breadcrumbs"],
                    image_url=pdp["image"],
                    price=item["price"],
                    product_url=item["link"],
                    use_vision=False,
                )
                if not intel:
                    continue
                if not pdp["image"]:
                    continue

                nk = _norm_name_key(intel["name_ar"])
                v_score = ge.score_girls_virality(
                    girls_cat=intel["girls_cat"],
                    brand_en=intel.get("brand_en") or "",
                    discount=item["discount"],
                    price=item["price"],
                    list_price=item["list_price"],
                    rating=item.get("rating"),
                    reviews=item.get("reviews"),
                    store=item["store"],
                )
                # بونص خوارزمي لتنويع الفئة على تيك توك (تجنب نشر نفس الفئة مرتين متتاليتين)
                tt_score = v_score + (6.0 if intel["girls_cat"] != state.get("last_tt_cat") else -8.0)

                raw_candidates.append({
                    "item": item,
                    "pdp": pdp,
                    "intel": intel,
                    "v_score": v_score,
                    "tt_score": tt_score,
                    "name_key": nk,
                })
        finally:
            await browser.close()

    print(f"🎀 عروض بنات صافية ومعتمدة بعد الفلترة الذكية: {len(raw_candidates)}")

    # 1) النشر الحي المستمر على قناة تليجرام البنات (@Loqta_G) بنفس معدل ونظام @loqta78
    if GIRLS_CHANNEL_ID and raw_candidates:
        tg_sorted = sorted(raw_candidates, key=lambda x: x["v_score"], reverse=True)
        tg_sent_cnt = 0
        cat_counts = {}
        recent_names = state.get("recent_names") or {}
        for c in tg_sorted:
            if tg_sent_cnt >= GIRLS_TG_MAX_PER_CYCLE:
                break
            link = c["item"]["link"]
            gcat = c["intel"]["girls_cat"]
            disc = float(c["item"]["discount"] or 0)
            if link in sent_tg or c["name_key"] in recent_names:
                continue
            if cat_counts.get(gcat, 0) >= 2 and disc < 65.0:
                continue
            if not _can_post_girls_tg_now(state, discount=disc):
                continue
            buy_u = make_buy_url(link)
            msg_html, markup = ge.build_girls_telegram_message(
                store=c["item"]["store"],
                intel=c["intel"],
                price=c["item"]["price"],
                list_price=c["item"]["list_price"],
                discount=disc,
                buy_url=buy_u,
                seller=c["pdp"]["seller"],
                rating=c["item"].get("rating"),
                reviews=c["item"].get("reviews"),
                tg_channel_username=GIRLS_CHANNEL_USERNAME,
                noon_coupon=NOON_COUPON,
            )
            if send_telegram_photo_post(GIRLS_CHANNEL_ID, msg_html, c["pdp"]["image"], reply_markup=markup):
                now_ts = int(time.time())
                _append_set(GIRLS_SENT_TG_FILE, sent_tg, link)
                state["recent_names"][c["name_key"]] = now_ts
                state["sent_timestamps"].append(now_ts)
                state["sent_today_meta"].append({
                    "ts": now_ts,
                    "link": link,
                    "name_ar": c["intel"]["name_ar"][:85],
                    "price": c["item"]["price"],
                    "list_price": c["item"]["list_price"],
                    "discount": round(disc, 1),
                    "store": c["item"]["store"],
                    "v_score": c["v_score"],
                })
                cat_counts[gcat] = cat_counts.get(gcat, 0) + 1
                tg_sent_cnt += 1
                print(f"✅ [Girls TG #{tg_sent_cnt}] {c['intel']['name_ar']} (Score={c['v_score']})")
                await asyncio.sleep(5)

    # 2) تيك توك ثابت ومقيّد بـ 4 أوقات ذروة يومياً فقط (1 بوست دعائي قوي في كل وقت ذروة لجذب المتابعين لقناة @Loqta_G)
    active_slot = _get_active_tiktok_slot()
    slots_done = set(state.get("tiktok_slots_sent") or [])
    should_post_tiktok = False
    slot_key_to_record = None
    if active_slot and active_slot not in slots_done:
        should_post_tiktok = True
        slot_key_to_record = active_slot
    elif force_tiktok:
        date_str = f"{ct.tm_year:04d}-{ct.tm_mon:02d}-{ct.tm_mday:02d}"
        should_post_tiktok = True
        slot_key_to_record = active_slot or f"{date_str}|manual-{ct.tm_hour:02d}{ct.tm_min:02d}"

    if should_post_tiktok and raw_candidates:
        tt_sorted = sorted(raw_candidates, key=lambda x: x["tt_score"], reverse=True)
        tt_sent_cnt = 0
        for c in tt_sorted:
            if tt_sent_cnt >= GIRLS_TIKTOK_MAX_PER_SLOT:
                break
            link = c["item"]["link"]
            if link in sent_tt:
                continue

            copy_bundle = ge.build_tiktok_copy(
                name_ar=c["intel"]["name_ar"],
                name_en=c["intel"]["name_en"],
                brand_en=c["intel"].get("brand_en") or "",
                girls_cat=c["intel"]["girls_cat"],
                price=c["item"]["price"],
                list_price=c["item"]["list_price"],
                discount=c["item"]["discount"],
                description=c["intel"].get("description") or "",
                features=c["pdp"]["features"],
                rating=c["item"].get("rating"),
                reviews=c["item"].get("reviews"),
                store=c["item"]["store"],
                tg_channel_username=GIRLS_CHANNEL_USERNAME,
            )

            slug_id = hashlib.md5(link.encode("utf-8")).hexdigest()[:8]
            slide_paths = designer.generate_tiktok_carousel(
                product_image=c["pdp"]["image"],
                name_ar=c["intel"]["name_ar"],
                name_en=c["intel"]["name_en"],
                brand_en=c["intel"].get("brand_en") or "",
                price=c["item"]["price"],
                list_price=c["item"]["list_price"],
                discount=c["item"]["discount"],
                copy_bundle=copy_bundle,
                store=c["item"]["store"],
                rating=c["item"].get("rating"),
                reviews=c["item"].get("reviews"),
                prefix=f"girls_{slug_id}",
            )

            ok_tt, mode = publish_to_tiktok(slide_paths, copy_bundle["tiktok_title"], copy_bundle["tiktok_caption"])
            if ok_tt:
                _append_set(GIRLS_SENT_TT_FILE, sent_tt, link)
                state["last_tt_cat"] = c["intel"]["girls_cat"]
                if slot_key_to_record and slot_key_to_record not in state["tiktok_slots_sent"]:
                    state["tiktok_slots_sent"].append(slot_key_to_record)
                tt_sent_cnt += 1
                print(f"🚀 [TikTok Published via {mode} | slot={slot_key_to_record}] {c['intel']['name_ar']} (TT Score={c['tt_score']})")
            elif mode == "unconfigured":
                if send_tiktok_preview_to_owner(slide_paths, copy_bundle["tiktok_caption"]):
                    _append_set(GIRLS_SENT_TT_FILE, sent_tt, link)
                    state["last_tt_cat"] = c["intel"]["girls_cat"]
                    if slot_key_to_record and slot_key_to_record not in state["tiktok_slots_sent"]:
                        state["tiktok_slots_sent"].append(slot_key_to_record)
                    tt_sent_cnt += 1
                    print(f"📲 [TikTok Ready Preview -> Owner TG | slot={slot_key_to_record}] {c['intel']['name_ar']}")
    elif not active_slot:
        print(f"⏳ [TikTok] خارج أوقات الذروة الـ 4 الثابتة (1م / 5م / 8:30م / 11م) — النشر الآن لقناة التليجرام {GIRLS_CHANNEL_USERNAME} فقط.")

    # 3) ملخص أقوى 5 لقطات بنات الساعة 9:30 مساءً
    try:
        maybe_send_girls_daily_top5_digest(state)
    except Exception as de:
        print(f"[Girls Digest] error: {de}")

    _save_state(state)
    try:
        pi.save_tr_cache()
    except Exception:
        pass
    print("===== ✅ اكتملت دورة بوت البنات المستقل =====")


async def run_girls_bot_loop():
    """يدير التشغيل المستمر (مثل بوت القناة العامة) مع متابعة شات @Loqta_Girlsbot الخاص بين الدورات."""
    if GIRLS_RUN_MINUTES <= 0:
        await run_girls_cycle(force_tiktok=FORCE_TIKTOK_ONCE)
        return

    deadline = time.time() + GIRLS_RUN_MINUTES * 60
    first_cycle = True
    while time.time() < deadline:
        try:
            await run_girls_cycle(force_tiktok=(FORCE_TIKTOK_ONCE and first_cycle))
        except Exception as e:
            print(f"⚠️ خطأ في دورة بوت البنات: {e}")
        first_cycle = False

        remaining = deadline - time.time()
        if remaining <= 45:
            break
        sleep_for = min(GIRLS_CYCLE_SLEEP_SEC, remaining - 30)
        end_sleep = time.time() + sleep_for
        while time.time() < end_sleep:
            try:
                st = _load_state()
                prev_off = st.get("tg_update_offset")
                poll_girls_private_chat(st)
                if st.get("tg_update_offset") != prev_off:
                    _save_state(st)
            except Exception:
                pass
            await asyncio.sleep(min(20, max(1, end_sleep - time.time())))


if __name__ == "__main__":
    asyncio.run(run_girls_bot_loop())
