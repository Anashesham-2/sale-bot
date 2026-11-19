import asyncio
import hashlib
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
GIRLS_CHANNEL_ID = os.getenv("GIRLS_CHANNEL_ID", "").strip()
GIRLS_CHANNEL_USERNAME = os.getenv("GIRLS_CHANNEL_USERNAME", "").strip() or "https://t.me/+toD37sJhssI3ZjJk"
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

GIRLS_TG_MAX_PER_RUN = int(os.getenv("GIRLS_TG_MAX_PER_RUN", "4"))
GIRLS_TIKTOK_MAX_PER_RUN = int(os.getenv("GIRLS_TIKTOK_MAX_PER_RUN", "1"))  # 1 بوست في كل وقت ذروة = 4 يومياً (مثالي للخوارزمية)

# ملفات حالة مستقلة تماماً عن القناة العامة
GIRLS_SENT_TG_FILE = os.path.join(BASE_DIR, "girls_sent_deals.txt")
GIRLS_SENT_TT_FILE = os.path.join(BASE_DIR, "girls_tiktok_sent.txt")
GIRLS_STATE_FILE = os.path.join(BASE_DIR, "girls_state.json")

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٬٫", "0123456789,.")


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
    if os.path.exists(GIRLS_STATE_FILE):
        try:
            with open(GIRLS_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"query_idx": 0, "last_tt_cat": "", "recent_names": {}, "price_history": {}}


def _save_state(st):
    # تقليم السجل القديم لإبقاء الملف خفيفاً
    now = time.time()
    st["recent_names"] = {
        k: v for k, v in (st.get("recent_names") or {}).items()
        if now - v < 86400 * 3
    }
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
# 4. الدورة الرئيسية المستقلة لبوت البنات
# ---------------------------------------------------------------------------
async def run_girls_cycle():
    print(f"\n===== 🎀 بدء دورة بوت البنات المستقل: {time.strftime('%Y-%m-%d %H:%M:%S')} =====")
    sent_tg = _load_set(GIRLS_SENT_TG_FILE)
    sent_tt = _load_set(GIRLS_SENT_TT_FILE)
    state = _load_state()

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
                if nk in (state.get("recent_names") or {}):
                    continue

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
    if not raw_candidates:
        _save_state(state)
        return

    # 1) النشر على قناة تليجرام البنات المستقلة (لو تم تفعيل GIRLS_CHANNEL_ID)
    if GIRLS_CHANNEL_ID:
        tg_sorted = sorted(raw_candidates, key=lambda x: x["v_score"], reverse=True)
        tg_sent_cnt = 0
        used_cats = set()
        for c in tg_sorted:
            if tg_sent_cnt >= GIRLS_TG_MAX_PER_RUN:
                break
            link = c["item"]["link"]
            gcat = c["intel"]["girls_cat"]
            if link in sent_tg or gcat in used_cats:
                continue
            buy_u = make_buy_url(link)
            msg_html, markup = ge.build_girls_telegram_message(
                store=c["item"]["store"],
                intel=c["intel"],
                price=c["item"]["price"],
                list_price=c["item"]["list_price"],
                discount=c["item"]["discount"],
                buy_url=buy_u,
                seller=c["pdp"]["seller"],
                rating=c["item"].get("rating"),
                reviews=c["item"].get("reviews"),
                tg_channel_username=GIRLS_CHANNEL_USERNAME,
                noon_coupon=NOON_COUPON,
            )
            if send_telegram_photo_post(GIRLS_CHANNEL_ID, msg_html, c["pdp"]["image"], reply_markup=markup):
                _append_set(GIRLS_SENT_TG_FILE, sent_tg, link)
                state["recent_names"][c["name_key"]] = time.time()
                used_cats.add(gcat)
                tg_sent_cnt += 1
                print(f"✅ [Girls TG #{tg_sent_cnt}] {c['intel']['name_ar']} (Score={c['v_score']})")
                await asyncio.sleep(5)

    # 2) النشر الخوارزمي التلقائي على تيك توك (أقوى عرض واحد في كل وقت ذروة)
    tt_sorted = sorted(raw_candidates, key=lambda x: x["tt_score"], reverse=True)
    tt_sent_cnt = 0
    for c in tt_sorted:
        if tt_sent_cnt >= GIRLS_TIKTOK_MAX_PER_RUN:
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
            state["recent_names"][c["name_key"]] = time.time()
            tt_sent_cnt += 1
            print(f"🚀 [TikTok Published via {mode}] {c['intel']['name_ar']} (TT Score={c['tt_score']})")
        else:
            # لو لم تُضف مفاتيح تيك توك بعد: نرسل السلايدات الـ 3 المصممة والكابشن الجاهز لصاحب البوت في الخاص
            if mode == "unconfigured":
                if send_tiktok_preview_to_owner(slide_paths, copy_bundle["tiktok_caption"]):
                    _append_set(GIRLS_SENT_TT_FILE, sent_tt, link)
                    state["last_tt_cat"] = c["intel"]["girls_cat"]
                    state["recent_names"][c["name_key"]] = time.time()
                    tt_sent_cnt += 1
                    print(f"📲 [TikTok Ready Preview -> Owner TG] {c['intel']['name_ar']}")

    _save_state(state)
    print("===== ✅ اكتملت دورة بوت البنات المستقل =====")


if __name__ == "__main__":
    asyncio.run(run_girls_cycle())
