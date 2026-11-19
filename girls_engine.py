import hashlib
import html
import re
from urllib.parse import quote_plus
import product_intelligence as pi

# ---------------------------------------------------------------------------
# محرك الذكاء النسائي الخوارزمي (Girls Niche + TikTok Virality Engine)
# مستقل 100% — يختص بمنتجات البنات فقط بدون أي تداخل مع القناة العامة
# ---------------------------------------------------------------------------

GIRLS_ALLOWED_CATS = {
    "makeup",
    "skin_care",
    "perfume",
    "body_splash",
    "hair_care",
    "hair_styler",
    "hair_dryer",
    "sanitary_pads",
    "women_accessories",
}

# ماركات ترند ومحبوبة جداً لدى البنات في مصر (تعطي أعلى تفاعل ومشاهدات على تيك توك)
TRENDING_GIRLS_BRANDS = {
    "maybelline", "l'oreal paris", "loreal", "sheglam", "essence", "cybele", "amanda",
    "bourjois", "flormar", "nyx", "kiko", "catrice", "rimmel", "garnier",
    "la roche-posay", "cerave", "vichy", "eucerin", "bioderma", "the ordinary",
    "cosrx", "anua", "beauty of joseon", "starville", "infinity", "beesline",
    "kolagra", "eva", "bobana", "shan", "clary", "strongville", "bless",
    "karseell", "seropipe", "bath & body works", "victoria's secret", "lattafa",
    "tresemme", "pantene", "elvive", "gliss", "vatika", "nivea", "dove",
    "neutrogena", "eveline cosmetics", "celimax", "rush brush", "babyliss",
    "braun", "philips", "always", "sofy", "kotex", "private", "carefree",
}

# حظر صارم لأي منتجات رجالية أو أطفال أو إلكترونيات أو منزلية خارج نطاق البنات
_NON_GIRLS_BLOCK_RE = re.compile(
    r'(?:للرجال|رجالي|رجالى|للشباب|شبابي|حلاقة\s*(?:الذقن|اللحية|رجالي)|ذقن|لحية|ماكينة\s*حلاقة\s*رجالي|'
    r'للأطفال|للاطفال|بيبي|رضع|حفاضات|بامبرز|تغيير\s*حفاض|'
    r'\bfor\s*men\b|\bmen\'?s\b|\bmens\b|\bman\b|\bhomme\b|\bpour\s*homme\b|\bbeard\b|\baftershave\b|'
    r'\baxe\b|\bold\s*spice\b|nivea\s*men|dove\s*men|gillette\s*(?:mach|fusion|proglide|blue)|'
    r'\bbaby\b|\bkids\b|\bdiapers?\b|\btoddler\b|\binfant\b|'
    r'صابون\s*(?:أطباق|صحون|مواعين|غسيل|ملابس)|منظف\s*(?:أرضيات|حمامات|زجاج|مطبخ|سيارات)|'
    r'غسول\s*يد(?:ين)?\s*(?:ديتول|لايف\s*بوي)|'
    r'شاحن|كابل|باور\s*بانك|راوتر|كيبورد|ماوس|لابتوب|موبايل|تلفزيون|غسالة|ثلاجة|خلاط|مقلاة|شنيور|سيارة)',
    re.IGNORECASE,
)

# كلمات إيجابية مؤكدة لو المنتج سكين كير أو عناية نسائية أو إكسسوار بناتي
_STRONG_GIRLS_SIGNALS_RE = re.compile(
    r'(?:مكياج|ميكب|ماسكارا|ماسكرا|فاونديشن|كونسيلر|بلاشر|آيلاينر|ايلاينر|أحمر\s*شفاه|ملمع\s*شفاه|تنت|هايلايتر|برونزر|'
    r'سيروم|غسول\s*(?:وجه|بشرة|نسائي|حميمي)|واقي\s*شمس|صن\s*بلوك|ماء\s*ميسيلار|تونر|كريم\s*(?:مرطب|ليلي|نهاري|عيون|تفتيح)|'
    r'بودي\s*(?:سبلاش|ميست|لوشن|بتر)|عطر\s*(?:نسائي|حريمي|للسيدات|للبنات)|برفان\s*(?:حريمي|نسائي)|'
    r'فوط\s*(?:صحية|يومية|ليلية|نسائية)|أولويز|اولويز|سوفي|كوتكس|برايفت|كاري\s*فري|'
    r'شامبو|بلسم|حمام\s*كريم|ماسك\s*شعر|مكواة\s*شعر|مجفف\s*شعر|فرشاة\s*حرارية|سشوار|استشوار|بيبي\s*ليس|airwrapper|'
    r'شنط[ةه]\s*(?:يد|كتف|كروس|حريمي|نسائي|مكياج)|حقيب[ةه]\s*(?:يد|حريمي|مكياج)|أقراط|حلق|سلسل[ةه]|انسيال|أسور[ةه]|خاتم|توك\s*شعر|منظم\s*مكياج|'
    r'makeup|lipstick|lip\s*(?:gloss|tint|balm|oil)|mascara|foundation|concealer|blush|eyeliner|highlighter|eyeshadow|'
    r'serum|sunscreen|cleanser|micellar|moisturizer|toner|skincare|body\s*(?:splash|mist|lotion|butter)|'
    r'eau\s*de\s*parfum.*?(?:women|femme|her)|sanitary\s*pads?|panty\s*liners?|kotex|always|sofy|carefree|'
    r'shampoo|conditioner|hair\s*(?:mask|serum|oil|dryer|straightener|styler)|handbag|crossbody|earrings|necklace|bracelet)',
    re.IGNORECASE,
)

# لوحة الألوان البناتية المخصصة لكل فئة (لتصميم تيك توك احترافي ومتناسق بصرياً)
CATEGORY_THEMES = {
    "makeup": {
        "label_ar": "عروض الميكب والجمال",
        "badge_emoji": "💄",
        "bg_top": (255, 228, 240),     # Rose blush
        "bg_bottom": (255, 245, 250),
        "accent": (214, 48, 108),      # Deep raspberry pink
        "accent_soft": (252, 212, 228),
        "dark_text": (48, 20, 36),
        "hashtags": ["#ميكب", "#عروض_ميكب", "#مكياج_بنات"],
    },
    "skin_care": {
        "label_ar": "عروض السكين كير",
        "badge_emoji": "✨",
        "bg_top": (228, 247, 242),     # Soft mint / spa
        "bg_bottom": (247, 253, 251),
        "accent": (20, 145, 125),      # Emerald teal
        "accent_soft": (206, 240, 231),
        "dark_text": (18, 46, 42),
        "hashtags": ["#سكين_كير", "#عناية_بالبشرة", "#روتين_البشرة"],
    },
    "perfume": {
        "label_ar": "عروض البرفيوم النسائي",
        "badge_emoji": "🌸",
        "bg_top": (240, 230, 255),     # Soft lavender
        "bg_bottom": (251, 247, 255),
        "accent": (124, 58, 178),      # Royal violet
        "accent_soft": (228, 212, 250),
        "dark_text": (38, 20, 56),
        "hashtags": ["#برفيوم", "#عطور_نسائية", "#برفانات"],
    },
    "body_splash": {
        "label_ar": "بودي سبلاش وعناية بالجسم",
        "badge_emoji": "🌷",
        "bg_top": (255, 232, 244),     # Pink blossom
        "bg_bottom": (255, 247, 251),
        "accent": (196, 45, 128),
        "accent_soft": (250, 214, 236),
        "dark_text": (50, 18, 38),
        "hashtags": ["#بودي_سبلاش", "#عناية_بالجسم", "#عطور_بنات"],
    },
    "hair_care": {
        "label_ar": "عروض العناية بالشعر",
        "badge_emoji": "💆‍♀️",
        "bg_top": (255, 237, 224),     # Warm peach
        "bg_bottom": (255, 249, 244),
        "accent": (204, 88, 42),       # Terracotta peach
        "accent_soft": (253, 222, 202),
        "dark_text": (54, 28, 18),
        "hashtags": ["#عناية_بالشعر", "#روتين_الشعر", "#شعر_صحي"],
    },
    "hair_styler": {
        "label_ar": "مصففات ومكاوي الشعر",
        "badge_emoji": "✨",
        "bg_top": (254, 234, 234),     # Coral rose
        "bg_bottom": (255, 248, 248),
        "accent": (198, 52, 86),
        "accent_soft": (252, 214, 222),
        "dark_text": (52, 20, 28),
        "hashtags": ["#تصفيف_الشعر", "#عناية_بالشعر", "#للبنات"],
    },
    "hair_dryer": {
        "label_ar": "مجففات ومصففات الشعر",
        "badge_emoji": "💨",
        "bg_top": (254, 234, 234),
        "bg_bottom": (255, 248, 248),
        "accent": (198, 52, 86),
        "accent_soft": (252, 214, 222),
        "dark_text": (52, 20, 28),
        "hashtags": ["#تصفيف_الشعر", "#عناية_بالشعر", "#للبنات"],
    },
    "sanitary_pads": {
        "label_ar": "العناية الشخصية للبنات",
        "badge_emoji": "🎀",
        "bg_top": (232, 240, 255),     # Soft sky / cotton
        "bg_bottom": (248, 250, 255),
        "accent": (72, 102, 198),
        "accent_soft": (214, 226, 252),
        "dark_text": (22, 32, 62),
        "hashtags": ["#عناية_شخصية", "#اساسيات_البنات", "#عروض_التوفير"],
    },
    "women_accessories": {
        "label_ar": "إكسسوارات وشنط بنات",
        "badge_emoji": "👜",
        "bg_top": (252, 241, 225),     # Champagne gold
        "bg_bottom": (255, 251, 245),
        "accent": (168, 108, 40),      # Warm gold-bronze
        "accent_soft": (246, 228, 202),
        "dark_text": (48, 32, 14),
        "hashtags": ["#اكسسوارات_بنات", "#شنط_حريمي", "#فاشون_بنات"],
    },
}

# استعلامات بحث مخصصة لعروض البنات فقط (أمازون مصر + نون مصر)
GIRLS_SEARCH_QUERIES = [
    # مكياج
    ("مكياج ميبيلين", "ميبيلين ماسكارا روج كونسيلر"),
    ("مكياج شيجلام", "شيجلام بلاشر تنت ميكب"),
    ("مكياج إيسنس ولوريال", "ايسنس لوريال ميكب"),
    ("مكياج سيبيل وبورجوا", "سيبيل بورجوا فلورمار ميكب"),
    # سكين كير
    ("سكين كير سيرافي ولاروش", "سيرافي لاروش بوزيه غسول سيروم"),
    ("سكين كير غارنييه ونيفيا", "غارنييه واقي شمس سيروم فيتامين سي"),
    ("سكين كير مصري ترند", "ستارفيل انفينيتي بوبانا ايفا سكين كير"),
    ("سكين كير كوري", "كوسركس بيوتي اوف جوسون انوا سيروم"),
    # برفيوم وبودي سبلاش
    ("بودي سبلاش نسائي", "بودي سبلاش حريمي باث اند بودي فيكتوريا سيكريت"),
    ("برفيوم نسائي", "عطر نسائي او دو بارفان حريمي"),
    # عناية بالشعر ومصففات
    ("عناية بالشعر", "شامبو بلسم حمام كريم كارسيل بليس لوريال الفيف"),
    ("مكواة ومصفف شعر", "رش براش مكواة شعر بيبي ليس سشوار"),
    # فوط صحية وعناية نسائية
    ("فوط صحية أولويز وسوفي", "فوط صحية اولويز سوفي كوتكس برايفت"),
    ("فوط يومية وغسول نسائي", "كاري فري فوط يومية غسول نسائي"),
    # إكسسوارات وشنط حريمي
    ("شنط حريمي", "شنطة يد حريمي كروس حريمي"),
    ("إكسسوارات ومجوهرات بنات", "اكسسوارات بنات حلق سلسلة اسورة ستانلس"),
    ("منظم مكياج وفرش", "منظم مكياج فرش مكياج بيوتي بلندر"),
]

# صفحات أقسام الجمال والعناية النسائية المباشرة على أمازون ونون
GIRLS_AMAZON_DEAL_URLS = [
    "https://www.amazon.eg/s?i=beauty&rh=p_n_deal_type%3A26901043031",
    "https://www.amazon.eg/s?k=%D9%85%D9%83%D9%8A%D8%A7%D8%AC+%D9%85%D8%A7%D8%B3%D9%83%D8%A7%D8%B1%D8%A7+%D8%B1%D9%88%D8%AC&rh=p_n_deal_type%3A26901043031",
    "https://www.amazon.eg/s?k=%D8%B3%D9%8A%D8%B1%D9%88%D9%85+%D8%BA%D8%B3%D9%88%D9%84+%D9%88%D8%AC%D9%87+%D9%88%D8%A7%D9%82%D9%8A+%D8%B4%D9%85%D8%B3",
    "https://www.amazon.eg/s?k=%D9%81%D9%88%D8%B7+%D8%B5%D8%AD%D9%8A%D8%A9+%D8%A7%D9%88%D9%84%D9%88%D9%8A%D8%B2+%D8%B3%D9%88%D9%81%D9%8A+%D9%83%D9%88%D8%AA%D9%83%D8%B3",
    "https://www.amazon.eg/s?k=%D8%A8%D9%88%D8%AF%D9%8A+%D8%B3%D8%A8%D9%84%D8%A7%D8%B4+%D8%B9%D8%B7%D8%B1+%D9%86%D8%B3%D8%A7%D8%A6%D9%8A",
]

GIRLS_NOON_DEAL_URLS = [
    "https://www.noon.com/egypt-ar/beauty-and-health/beauty/makeup/?sort[by]=discount&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/beauty-and-health/beauty/skin-care/?sort[by]=discount&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/beauty-and-health/beauty/fragrance/women/?sort[by]=discount&sort[dir]=desc",
    "https://www.noon.com/egypt-ar/beauty-and-health/beauty/hair-care/?sort[by]=discount&sort[dir]=desc",
]


def is_girls_product_text_safe(title, en_title="", breadcrumbs=None):
    """فلتر سريع أولي يمنع دخول أي منتج رجالي أو أطفال أو إلكترونيات قبل فتح صفحة المنتج."""
    ctx = f"{title or ''} {en_title or ''} {' '.join(breadcrumbs or [])}"
    if _NON_GIRLS_BLOCK_RE.search(ctx):
        return False
    return True


def classify_girls_product(
    title,
    brand=None,
    features=None,
    en_title="",
    en_brand="",
    en_slug="",
    breadcrumbs=None,
    en_breadcrumbs=None,
    specs=None,
    image_url=None,
    price=None,
    product_url=None,
    use_vision=False,
):
    """
    يحلل المنتج بالكامل عبر product_intelligence ويتأكد 100% أنه منتج بناتي نقي،
    ويرجع dict شامل بالاسم والماركة والفئة والثيم البصري، أو None إذا كان خارج تخصص البنات.
    """
    full_ctx = f"{title or ''} {en_title or ''} {brand or ''} {en_brand or ''} {' '.join(breadcrumbs or [])} {' '.join(en_breadcrumbs or [])}"
    if _NON_GIRLS_BLOCK_RE.search(full_ctx):
        return None

    intel = pi.analyze_product(
        title=title,
        brand=brand,
        features=features,
        en_slug=en_slug,
        breadcrumbs=breadcrumbs,
        specs=specs,
        image_url=image_url,
        price=price,
        use_vision=use_vision,
        product_url=product_url,
        en_title=en_title,
        en_brand=en_brand,
        en_breadcrumbs=en_breadcrumbs,
    )

    cat_key = intel.get("cat_key") or ""
    # التأكد أن الفئة ضمن فئات البنات المسموحة فقط
    if cat_key not in GIRLS_ALLOWED_CATS:
        # استثناء ذكي: لو العنوان فيه إشارة بناتية قوية جداً (مثلاً منظم مكياج) نصنفه women_accessories
        if _STRONG_GIRLS_SIGNALS_RE.search(f"{title or ''} {en_title or ''}") and any(
            w in f"{title or ''} {en_title or ''}".lower()
            for w in ("مكياج", "ميكب", "حريمي", "نسائي", "بناتي", "makeup", "cosmetic", "women")
        ):
            cat_key = "women_accessories"
        else:
            return None

    # تصفية إضافية للعطور: نتأكد أنه ليس عطر رجالي أو للجنسين بصبغة رجالية
    if cat_key == "perfume":
        if re.search(r'(?:رجالي|للرجال|men|homme|intense\s*man|sport\s*men)', full_ctx, re.I):
            return None

    # تصفية إضافية للسكين كير: نتأكد أنه ليس صابون يدين عادي أو جيرم سوب منزلي
    if cat_key == "skin_care":
        if re.search(r'(?:صابون\s*يدين|غسول\s*يدين|hand\s*wash|hand\s*soap|ديتول|لايف\s*بوي|dettol|lifebuoy)', full_ctx, re.I):
            return None

    intel["girls_cat"] = cat_key
    intel["theme"] = CATEGORY_THEMES.get(cat_key, CATEGORY_THEMES["makeup"])
    return intel


def score_girls_virality(
    girls_cat,
    brand_en,
    discount,
    price,
    list_price=None,
    rating=None,
    reviews=None,
    store="Amazon",
    has_promo=False,
):
    """
    درجة الانتشار الخوارزمي (0–100) لترتيب أفضل العروض التي تخطف عين البنات على تيك توك.
    """
    score = 0.0
    # 1. قوة الخصم (حتى 35 نقطة)
    score += min(float(discount or 0), 70.0) * 0.5

    # 2. التوفير بالجنيه (حتى 15 نقطة)
    saving = (list_price - price) if (list_price and price and list_price > price) else 0
    if saving >= 300:
        score += 15
    elif saving >= 150:
        score += 11
    elif saving >= 70:
        score += 7
    elif saving >= 30:
        score += 4

    # 3. شهرة الماركة لدى البنات في مصر (حتى 22 نقطة)
    b_low = (brand_en or "").strip().lower()
    if b_low in TRENDING_GIRLS_BRANDS:
        score += 22
    elif b_low:
        score += 8

    # 4. التقييم والموثوقية (حتى 12 نقطة)
    try:
        r_val = float(str(rating or "0").replace(",", "."))
        if r_val >= 4.5:
            score += 12
        elif r_val >= 4.1:
            score += 8
        elif r_val >= 3.8:
            score += 4
    except Exception:
        pass

    # 5. جاذبية الفئة بصرياً على تيك توك (توازن ذكي بدون إهمال أي فئة بناتية)
    if girls_cat in ("makeup", "skin_care", "perfume", "body_splash"):
        score += 8
    elif girls_cat in ("hair_styler", "hair_dryer", "women_accessories", "hair_care"):
        score += 6
    elif girls_cat == "sanitary_pads":
        score += 5

    # 6. أفضلية خفيفة لأمازون (مصدر ربح الأفلييت المباشر)
    if str(store).lower() == "amazon":
        score += 8

    if has_promo:
        score += 5

    return round(min(score, 100.0), 1)


def _pick_deterministic(options, seed_str):
    idx = int(hashlib.md5((seed_str or "x").encode("utf-8")).hexdigest()[:8], 16) % len(options)
    return options[idx]


def build_tiktok_copy(
    name_ar,
    name_en,
    brand_en,
    girls_cat,
    price,
    list_price,
    discount,
    description,
    features=None,
    rating=None,
    reviews=None,
    store="Amazon",
    tg_channel_username="@loqta78",
):
    """
    يبني نصوص السلايدات الـ 3 (Hook + تفاصيل + CTA) + كابشن TikTok SEO وهاشتاجات ذكية مركّزة.
    """
    theme = CATEGORY_THEMES.get(girls_cat, CATEGORY_THEMES["makeup"])
    saving = int(round(list_price - price)) if (list_price and price and list_price > price) else 0
    disc_i = int(round(float(discount or 0)))
    br_disp = brand_en or "البراند ده"
    store_ar = "أمازون" if str(store).lower() == "amazon" else "نون"
    seed = f"{name_ar}|{price}|{disc_i}"

    # 1. هوك السلايد الأولى (مصمم لوقف الـ Scroll في أول 0.8 ثانية)
    if disc_i >= 50:
        hooks = [
            f"يا بنات الحقوا! خصم {disc_i}% على {br_disp} قبل ما يخلص!",
            f"نص السعر حرفياً! لقطة بنات اليوم على {store_ar}",
            f"مش معقول السعر ده! خصم {disc_i}% على {br_disp}",
        ]
    elif girls_cat == "makeup":
        hooks = [
            f"يا بنات الحقوا عرض الميكب ده من {br_disp}!",
            f"لقطة ميكب نارية! خصم {disc_i}% على {br_disp}",
            f"لو بتحبي {br_disp}.. السعر ده ما يتفوّتش!",
        ]
    elif girls_cat == "skin_care":
        hooks = [
            f"عشاق السكين كير الحقوا خصم {br_disp} النهارده!",
            f"لقطة روتين البشرة! وفّري {saving} ج.م على {br_disp}",
            f"أرخص سعر لـ {br_disp} على {store_ar} دلوقتي!",
        ]
    elif girls_cat in ("perfume", "body_splash"):
        hooks = [
            f"ريحة تجنن وبخصم {disc_i}%! الحقوا {br_disp}",
            f"عشاق البرفيوم والسبلاش.. لقطة اليوم من {br_disp}!",
            f"وفّري {saving} ج.م على {br_disp} قبل ما العرض يخلص!",
        ]
    elif girls_cat == "sanitary_pads":
        hooks = [
            f"لقطة التوفير للبنات! خصم {disc_i}% على {br_disp}",
            f"يا بنات العرض ده موفر جداً على {store_ar}!",
            f"الحقي عرض التوفير على {br_disp} قبل ما يرجع لسعره!",
        ]
    elif girls_cat == "women_accessories":
        hooks = [
            f"شياكة بخصم {disc_i}%! شوفي اللقطة دي على {store_ar}",
            f"إكسسوار تحفة وبسعر لقطة يا بنات!",
            f"الحقيها قبل ما تخلص.. خصم {disc_i}% على {store_ar}!",
        ]
    else:
        hooks = [
            f"يا بنات الحقوا عرض {br_disp} بخصم {disc_i}%!",
            f"لقطة عناية بالشعر من {br_disp} بسعر خرافي!",
            f"وفّري {saving} ج.م على {br_disp} النهارده!",
        ]
    hook_title = _pick_deterministic(hooks, seed)

    # 2. نقاط القيمة للسلايد الثانية (3 نقاط قصيرة وسريعة القراءة)
    bullet_points = []
    for f in (features or []):
        fc = re.sub(r'\s+', ' ', str(f)).strip()
        if 15 <= len(fc) <= 95 and re.search(r'[\u0600-\u06FF]', fc):
            if not any(w in fc for w in ("حول هذه السلعة", "بلد المنشأ", "رقم الموديل", "أبعاد", "تاريخ توفر")):
                bullet_points.append(fc)
        if len(bullet_points) >= 3:
            break

    if not bullet_points and description:
        parts = [p.strip(" .،؛") for p in re.split(r'[؛،.]', description) if len(p.strip()) >= 14]
        bullet_points = parts[:3]

    if not bullet_points:
        bullet_points = [
            f"منتج أصلي وموثوق من {br_disp}",
            f"خصم حقيقي {disc_i}% على {store_ar} مصر",
            "جودة ممتازة وتقييمات عالية من المشترين",
        ]

    # 3. هاشتاجات خوارزمية مركّزة (5–6 هاشتاجات فقط حسب توصيات TikTok SEO)
    tags = ["#عروض_مصر", "#بنات_مصر"] + list(theme["hashtags"][:2])
    if brand_en:
        b_tag = re.sub(r'[^A-Za-z0-9\u0600-\u06FF]+', '', brand_en)
        if 2 <= len(b_tag) <= 18:
            tags.append(f"#{b_tag}")
    tags.append("#لقطة_بنات")
    tags = list(dict.fromkeys(tags))[:6]

    ch_raw = str(tg_channel_username or "").strip()
    if ch_raw.startswith("http://") or ch_raw.startswith("https://"):
        tg_url = ch_raw.replace("https://", "").replace("http://", "")
        tg_handle = ch_raw
    else:
        tg_handle = ch_raw if ch_raw.startswith("@") else f"@{ch_raw}"
        tg_url = f"t.me/{tg_handle.lstrip('@')}"

    price_line = f"السعر بعد الخصم: {int(round(price)):,} ج.م" if price == int(price) else f"السعر بعد الخصم: {price:,.2f} ج.م"
    old_line = f" (بدل {int(round(list_price)):,} ج.م — وفّرتي {saving:,} ج.م!)" if (list_price and list_price > price) else ""

    cta_comment = _pick_deterministic(
        [
            "اكتبي «اللينك» في الكومنتات واعملي Save للبوست عشان ترجعيله!",
            "احفظي البوست (Save) واكتبي «تم» لو عايزة عروض أكتر من البراند ده!",
            "اعملي Save للبوست وفولو عشان تلحقي عروض البنات يومياً قبل ما تخلص!",
        ],
        seed + "|cta",
    )

    # عنوان تيك توك القصير (Photo Mode Title - max 90 chars)
    tiktok_title = f"{theme['badge_emoji']} {name_ar[:60]} — خصم {disc_i}%"[:88]

    # كابشن تيك توك الكامل (SEO + وصف + قناة التليجرام + هاشتاجات)
    caption_lines = [
        f"{theme['badge_emoji']} {hook_title}",
        f"✨ {name_ar}",
        f"💰 {price_line}{old_line}",
        f"📝 {description[:180]}" if description else "",
        f"⭐ التقييم: {rating}/5" + (f" ({reviews} تقييم)" if reviews else "") if rating else "",
        "",
        f"⚡ العروض دي بتخلص بسرعة! اللينك المباشر + كل لقطات البنات لايف أول بأول في قناة التليجرام (الرابط في البايو): {tg_handle} ({tg_url})",
        f"💗 {cta_comment}",
        "",
        " ".join(tags),
    ]
    tiktok_caption = "\n".join(ln for ln in caption_lines if ln is not None).strip()
    tiktok_caption = re.sub(r'\n{3,}', '\n\n', tiktok_caption)[:2000]

    return {
        "hook_title": hook_title,
        "tiktok_title": tiktok_title,
        "tiktok_caption": tiktok_caption,
        "bullet_points": bullet_points[:3],
        "hashtags": tags,
        "theme": theme,
        "saving": saving,
        "disc_i": disc_i,
        "tg_handle": tg_handle,
        "tg_url": tg_url,
    }


def build_girls_telegram_message(
    store,
    intel,
    price,
    list_price,
    discount,
    buy_url,
    seller=None,
    rating=None,
    reviews=None,
    stack_promos=None,
    tg_channel_username="@loqta78",
    noon_coupon="",
):
    """يبني بوست قناة تليجرام البنات المستقلة بأسلوب أنيق وراقي + زر شراء مباشر (بدون إظهار رابط الأفلييت)."""
    store_ar = "أمازون" if str(store).lower() == "amazon" else "نون"
    theme = intel.get("theme") or CATEGORY_THEMES["makeup"]
    badge = theme["badge_emoji"]
    name_ar = intel["name_ar"]
    name_en = intel["name_en"]
    brand_en = intel.get("brand_en") or ""
    desc = intel.get("description") or ""
    disc_i = int(round(float(discount or 0)))
    saving = (list_price - price) if (list_price and price and list_price > price) else 0

    def _fmt(v):
        return f"{int(v):,}" if float(v).is_integer() else f"{float(v):,.2f}"

    if disc_i >= 50:
        header = f"🎀🚨 لقطة بنات بنص السعر على {store_ar}! (خصم {disc_i}%)"
    elif disc_i >= 30:
        header = f"{badge}✨ عرض بنات قوي على {store_ar}! (خصم {disc_i}%)"
    else:
        header = f"{badge}💗 ترشيح بنات مميز على {store_ar} — {theme['label_ar']}"

    lines = [
        f"<b>{html.escape(header)}</b>",
        "",
        f"🛍️ <b>{html.escape(name_ar)}</b>",
        f"🇬🇧 <b>{html.escape(name_en)}</b>",
        "",
    ]
    if list_price and list_price > (price or 0):
        lines.append(f"❌ السعر القديم: <s>{_fmt(list_price)} ج.م</s>")
    if price is not None:
        lines.append(f"💰 السعر الجديد: <b>{_fmt(price)} ج.م</b>")
    if saving > 0 and 1 <= disc_i < 90:
        lines.append(f"📉 إجمالي الخصم: <b>{disc_i}%</b> (وفّرتي {_fmt(saving)} ج.م)")
    if str(store).lower() == "noon" and noon_coupon:
        lines.append(f"🎟️ <b>كود خصم نون الإضافي:</b> <code>{html.escape(noon_coupon)}</code>")
    if brand_en:
        lines.append(f"🏷️ الماركة: <b>{html.escape(brand_en)}</b>")
    if seller:
        lines.append(f"🏪 البائع: {html.escape(str(seller)[:40])}")
    if rating:
        lines.append(f"⭐ التقييم: {rating}" + (f" ({reviews} تقييم)" if reviews else ""))

    if stack_promos:
        lines += ["", "🎁 <b>عروض إضافية على المنتج:</b>"]
        for sp in stack_promos[:2]:
            lines.append(f"• {html.escape(sp)}")

    if desc:
        lines += ["", f"📝 <b>ليه بنرشحلك المنتج ده:</b>\n{html.escape(desc)}"]

    tags_str = " ".join(theme["hashtags"][:2] + ["#عروض_بنات", "#لقطة_بنات"])
    lines += [
        "",
        "👇 <i>اضغطي على الزر بالأسفل لطلب العرض مباشرةً من المتجر</i>",
        "",
        tags_str,
    ]

    btn_txt = "🛍️ اطلبي العرض من أمازون الآن" if str(store).lower() == "amazon" else "🛍️ اطلبي العرض من نون الآن"
    ch_raw = str(tg_channel_username or "").strip()
    full_ch_url = ch_raw if (ch_raw.startswith("http://") or ch_raw.startswith("https://")) else f"https://t.me/{ch_raw.lstrip('@')}"
    share_url = "https://t.me/share/url?url=" + quote_plus(full_ch_url) + "&text=" + quote_plus("أقوى عروض الميكب والسكين كير والبنات يومياً 🎀✨")
    reply_markup = {
        "inline_keyboard": [
            [{"text": btn_txt, "url": buy_url}],
            [{"text": "💗 شاركي القناة مع صاحباتك", "url": share_url}],
        ]
    }
    return "\n".join(lines), reply_markup
