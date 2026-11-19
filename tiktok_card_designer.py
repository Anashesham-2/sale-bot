import io
import os
import re
import math
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
import arabic_reshaper
from bidi.algorithm import get_display

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "assets", "fonts")

# أبعاد تيك توك Photo Mode المثالية (4:5 — تملأ الشاشة وتترك مساحة مريحة للكابشن)
CANVAS_W = 1080
CANVAS_H = 1350

# إزالة الإيموجي والرموز غير المدعومة في خطوط TTF العادية لمنع ظهور مربعات فارغة
_EMOJI_STRIP_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0000FE00-\U0000FE0F"
    "\u200d"
    "]+",
    flags=re.UNICODE,
)


def _clean_for_font(text):
    s = _EMOJI_STRIP_RE.sub("", str(text or ""))
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _shape_ar(text):
    """يعيد تشكيل النص العربي وضبط اتجاه RTL بشكل سليم 100% لـ Pillow."""
    clean = _clean_for_font(text)
    if not clean:
        return ""
    if re.search(r'[\u0600-\u06FF]', clean):
        try:
            reshaped = arabic_reshaper.reshape(clean)
            return get_display(reshaped)
        except Exception:
            return clean
    return clean


def _load_font(weight=700, size=40):
    """يحمّل خط Amiri العربي الكامل (0 missing glyphs مع arabic_reshaper) مع بدائل مضمونة على Windows و Linux."""
    # Amiri أنحف قليلاً من الخطوط الهندسية فنزيد المقاس قليلاً للوضوح الفائق على شاشات الموبايل
    adj_size = int(round(size * 1.12))
    if weight >= 700:
        candidates = [
            os.path.join(FONTS_DIR, "Amiri-Bold.ttf"),
            os.path.join(FONTS_DIR, "Amiri-Regular.ttf"),
            r"C:\Windows\Fonts\tahomabd.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            os.path.join(FONTS_DIR, "Amiri-Regular.ttf"),
            os.path.join(FONTS_DIR, "Amiri-Bold.ttf"),
            r"C:\Windows\Fonts\tahoma.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for path in candidates:
        if os.path.exists(path):
            try:
                use_sz = adj_size if "Amiri" in os.path.basename(path) else size
                return ImageFont.truetype(path, size=use_sz)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text_lines(text, font, max_width, draw, max_lines=3):
    """يلف النص العربي/الإنجليزي بذكاء قبل إعادة التشكيل حتى لا تتكسر السطور."""
    clean = _clean_for_font(text)
    if not clean:
        return []
    words = clean.split()
    lines = []
    cur = []
    for w in words:
        test = " ".join(cur + [w])
        bbox = draw.textbbox((0, 0), _shape_ar(test), font=font)
        if (bbox[2] - bbox[0]) <= max_width or not cur:
            cur.append(w)
        else:
            lines.append(" ".join(cur))
            cur = [w]
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(" ".join(cur))
    if len(lines) == max_lines and len(" ".join(lines).split()) < len(words):
        last_w = lines[-1].split()
        if len(last_w) > 1:
            lines[-1] = " ".join(last_w[:-1]) + "..."
    return lines


def _draw_centered_text(draw, y, text, font, fill, center_x=CANVAS_W // 2):
    shaped = _shape_ar(text)
    if not shaped:
        return 0
    bbox = draw.textbbox((0, 0), shaped, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((center_x - tw / 2, y - bbox[1]), shaped, font=font, fill=fill)
    return th


def _draw_right_aligned_text(draw, right_x, y, text, font, fill):
    shaped = _shape_ar(text)
    if not shaped:
        return 0
    bbox = draw.textbbox((0, 0), shaped, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((right_x - tw, y - bbox[1]), shaped, font=font, fill=fill)
    return th


def _create_gradient_bg(top_rgb, bottom_rgb, accent_soft):
    """ينشئ خلفية بناتية متدرجة ناعمة مع لمسات إضاءة دائرية جمالية."""
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), top_rgb)
    px = img.load()
    for y in range(CANVAS_H):
        t = y / (CANVAS_H - 1)
        r = int(top_rgb[0] * (1 - t) + bottom_rgb[0] * t)
        g = int(top_rgb[1] * (1 - t) + bottom_rgb[1] * t)
        b = int(top_rgb[2] * (1 - t) + bottom_rgb[2] * t)
        for x in range(CANVAS_W):
            px[x, y] = (r, g, b)

    # دوائر إضاءة ناعمة في الخلفية (Soft Aesthetic Blobs)
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    c1 = (*accent_soft, 110)
    c2 = (255, 255, 255, 130)
    od.ellipse((-140, -120, 420, 440), fill=c1)
    od.ellipse((720, 880, 1260, 1420), fill=c1)
    od.ellipse((680, -80, 1180, 420), fill=c2)
    od.ellipse((-120, 760, 340, 1220), fill=c2)
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=60))
    return Image.alpha_composite(img.convert("RGBA"), overlay)


def _draw_shadow_card(canvas_rgba, box, radius=42, fill=(255, 255, 255, 255), shadow_alpha=36):
    """يرسم كارتاً أبيض بحواف دائرية وظل ناعم احترافي."""
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", canvas_rgba.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x0 + 4, y0 + 14, x1 + 4, y1 + 14), radius=radius, fill=(40, 20, 35, shadow_alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=22))
    out = Image.alpha_composite(canvas_rgba, shadow)
    cd = ImageDraw.Draw(out)
    cd.rounded_rectangle(box, radius=radius, fill=fill)
    return out


def _draw_pill(draw, center_x, y, text, font, bg_color, text_color, pad_x=34, pad_y=14):
    shaped = _shape_ar(text)
    bbox = draw.textbbox((0, 0), shaped, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    w = tw + pad_x * 2
    h = th + pad_y * 2
    x0 = int(center_x - w / 2)
    y0 = int(y)
    draw.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=int(h / 2), fill=bg_color)
    draw.text((center_x - tw / 2, y0 + pad_y - bbox[1]), shaped, font=font, fill=text_color)
    return int(h)


def _draw_star(draw, cx, cy, outer_r, fill):
    pts = []
    inner_r = outer_r * 0.44
    for i in range(10):
        ang = math.radians(i * 36 - 90)
        r = outer_r if i % 2 == 0 else inner_r
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    draw.polygon(pts, fill=fill)


def _draw_slide_dots(draw, active_idx, total, accent, soft_accent, y=CANVAS_H - 40):
    gap = 28
    total_w = (total - 1) * gap
    start_x = CANVAS_W // 2 - total_w // 2
    for i in range(total):
        cx = start_x + i * gap
        if i == active_idx:
            draw.rounded_rectangle((cx - 18, y - 7, cx + 18, y + 7), radius=7, fill=accent)
        else:
            draw.ellipse((cx - 7, y - 7, cx + 7, y + 7), fill=soft_accent)


def _download_product_image(image_url_or_path):
    """يحمل صورة المنتج من رابط أو مسار محلي ويعالجها بخلفية بيضاء نظيفة."""
    if not image_url_or_path:
        return None
    try:
        if os.path.exists(str(image_url_or_path)):
            im = Image.open(image_url_or_path)
        else:
            r = requests.get(
                image_url_or_path,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"},
                timeout=15,
            )
            if not r.ok or len(r.content) < 500:
                return None
            im = Image.open(io.BytesIO(r.content))
        if im.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im_rgba = im.convert("RGBA")
            bg.paste(im_rgba, mask=im_rgba.split()[3])
            return bg.convert("RGB")
        return im.convert("RGB")
    except Exception:
        return None


def _fmt_price(val):
    if val is None:
        return ""
    return f"{int(round(val)):,}" if abs(val - round(val)) < 0.01 else f"{val:,.2f}"


def generate_tiktok_carousel(
    product_image,
    name_ar,
    name_en,
    brand_en,
    price,
    list_price,
    discount,
    copy_bundle,
    store="Amazon",
    rating=None,
    reviews=None,
    out_dir=None,
    prefix="slide",
):
    """
    يصمّم 3 صور Carousel احترافية بمقاس 1080×1350 جاهزة للنشر التلقائي على تيك توك.
    يرجع قائمة بمسارات الصور الـ 3 (JPG عالية الجودة).
    """
    if out_dir is None:
        out_dir = os.path.join(BASE_DIR, "tiktok_out")
    os.makedirs(out_dir, exist_ok=True)

    theme = copy_bundle["theme"]
    accent = theme["accent"]
    accent_soft = theme["accent_soft"]
    dark_text = theme["dark_text"]
    bg_top = theme["bg_top"]
    bg_bottom = theme["bg_bottom"]
    store_ar = "أمازون مصر" if str(store).lower() == "amazon" else "نون مصر"
    disc_i = copy_bundle["disc_i"]
    saving = copy_bundle["saving"]
    tg_handle = copy_bundle["tg_handle"]

    prod_img = _download_product_image(product_image)

    f_pill = _load_font(700, 28)
    f_hook = _load_font(800, 50)
    f_title_ar = _load_font(800, 40)
    f_brand = _load_font(700, 30)
    f_price_big = _load_font(800, 62)
    f_price_old = _load_font(600, 34)
    f_save = _load_font(700, 28)
    f_badge_big = _load_font(800, 40)
    f_badge_sm = _load_font(700, 24)
    f_swipe = _load_font(700, 30)
    f_body = _load_font(600, 33)
    f_subhead = _load_font(800, 42)
    f_cta_big = _load_font(800, 54)
    f_handle = _load_font(800, 52)

    paths = []

    # =====================================================================
    # SLIDE 1: الغلاف الخاطف للعين (Hook + صورة المنتج + بادج الخصم + السعر)
    # =====================================================================
    s1 = _create_gradient_bg(bg_top, bg_bottom, accent_soft)
    d1 = ImageDraw.Draw(s1)

    # شارة الفئة والمتجر
    _draw_pill(d1, CANVAS_W // 2, 54, f"{theme['label_ar']}  |  {store_ar}", f_pill, (255, 255, 255, 235), accent, pad_x=34, pad_y=12)

    # الهوك الخاطف في الأعلى
    hook_lines = _wrap_text_lines(copy_bundle["hook_title"], f_hook, CANVAS_W - 110, d1, max_lines=2)
    hy = 136
    for ln in hook_lines:
        _draw_centered_text(d1, hy, ln, f_hook, dark_text)
        hy += 66

    # كارت صورة المنتج المركزي
    card_top = max(278, hy + 18)
    card_bottom = 865
    s1 = _draw_shadow_card(s1, (74, card_top, CANVAS_W - 74, card_bottom), radius=46)
    d1 = ImageDraw.Draw(s1)

    if prod_img is not None:
        inner_w = (CANVAS_W - 74) - 74 - 90
        inner_h = (card_bottom - card_top) - 76
        fitted = ImageOps.contain(prod_img, (inner_w, inner_h), Image.Resampling.LANCZOS)
        px = (CANVAS_W - fitted.width) // 2
        py = card_top + ((card_bottom - card_top) - fitted.height) // 2
        s1.paste(fitted.convert("RGBA"), (px, py))
        d1 = ImageDraw.Draw(s1)

    # بادج الخصم الدائري البارز في الزاوية العليا اليمنى
    if disc_i >= 5:
        bx, by, br = CANVAS_W - 148, card_top + 78, 76
        d1.ellipse((bx - br - 6, by - br - 6, bx + br + 6, by + br + 6), fill=(255, 255, 255, 255))
        d1.ellipse((bx - br, by - br, bx + br, by + br), fill=accent)
        _draw_centered_text(d1, by - 46, "خصم", f_badge_sm, (255, 255, 255), center_x=bx)
        _draw_centered_text(d1, by - 14, f"{disc_i}%", f_badge_big, (255, 255, 255), center_x=bx)

    # اسم المنتج تحت الصورة
    title_lines = _wrap_text_lines(name_ar, f_title_ar, CANVAS_W - 120, d1, max_lines=2)
    ty = card_bottom + 24
    for ln in title_lines:
        _draw_centered_text(d1, ty, ln, f_title_ar, dark_text)
        ty += 60

    # كارت السعر البارز
    price_card_top = max(1002, ty + 10)
    price_card_bottom = price_card_top + 174
    s1 = _draw_shadow_card(s1, (74, price_card_top, CANVAS_W - 74, price_card_bottom), radius=34, fill=(255, 255, 255, 245))
    d1 = ImageDraw.Draw(s1)

    new_p_txt = f"{_fmt_price(price)} ج.م"
    _draw_centered_text(d1, price_card_top + 12, new_p_txt, f_price_big, accent)

    if list_price and list_price > price:
        old_p_txt = f"السعر القديم: {_fmt_price(list_price)} ج.م"
        shaped_old = _shape_ar(old_p_txt)
        ob = d1.textbbox((0, 0), shaped_old, font=f_price_old)
        ow = ob[2] - ob[0]
        ox = CANVAS_W // 2 - ow / 2
        oy = price_card_top + 104
        d1.text((ox, oy - ob[1]), shaped_old, font=f_price_old, fill=(140, 125, 135))
        # خط شطب أنيق في منتصف النص تماماً
        line_y = oy + (ob[3] - ob[1]) * 0.42
        d1.line((ox - 6, line_y, ox + ow + 6, line_y), fill=(190, 75, 95), width=4)

        if saving >= 15:
            _draw_pill(d1, 215, price_card_top + 54, f"وفّرتي {saving:,} ج.م", f_save, accent_soft, accent, pad_x=22, pad_y=10)

    # شريط السحب لتحفيز الـ Swipe-through Rate
    _draw_pill(d1, CANVAS_W // 2, CANVAS_H - 146, "<<   اسحبي للتفاصيل والوصف   <<", f_swipe, accent, (255, 255, 255), pad_x=42, pad_y=12)
    _draw_slide_dots(d1, 0, 3, accent, accent_soft)

    p1 = os.path.join(out_dir, f"{prefix}_1_cover.jpg")
    s1.convert("RGB").save(p1, "JPEG", quality=93, optimize=True)
    paths.append(p1)

    # =====================================================================
    # SLIDE 2: الوصف والمميزات والتقييم (The Value Slide)
    # =====================================================================
    s2 = _create_gradient_bg(bg_top, bg_bottom, accent_soft)
    d2 = ImageDraw.Draw(s2)

    _draw_pill(d2, CANVAS_W // 2, 54, "ليه المنتج ده لقطة؟", f_pill, accent, (255, 255, 255), pad_x=38, pad_y=12)

    # كارت تعريفي أعلى السلايد (صورة مصغرة + اسم المنتج والماركة)
    s2 = _draw_shadow_card(s2, (74, 140, CANVAS_W - 74, 412), radius=36)
    d2 = ImageDraw.Draw(s2)
    if prod_img is not None:
        thumb = ImageOps.contain(prod_img, (195, 195), Image.Resampling.LANCZOS)
        tx = 104 + (195 - thumb.width) // 2
        ty_img = 178 + (195 - thumb.height) // 2
        s2.paste(thumb.convert("RGBA"), (tx, ty_img))
        d2 = ImageDraw.Draw(s2)

    rx = CANVAS_W - 108
    t2_lines = _wrap_text_lines(name_ar, _load_font(800, 34), 635, d2, max_lines=2)
    cy = 166
    for ln in t2_lines:
        _draw_right_aligned_text(d2, rx, cy, ln, _load_font(800, 34), dark_text)
        cy += 54
    if brand_en:
        _draw_right_aligned_text(d2, rx, cy + 8, f"الماركة: {brand_en}  |  {store_ar}", _load_font(700, 27), accent)
        cy += 52

    # شارة التقييم بالنجوم الذهبية لو موجودة (بمسافة نظيفة أسفل سطر الماركة)
    if rating:
        try:
            rv = float(str(rating).replace(",", "."))
            star_y = max(352, cy + 26)
            for si in range(5):
                sx = rx - 18 - si * 34
                _draw_star(d2, sx, star_y, 13, (245, 176, 20) if si < int(round(rv)) else (225, 220, 225))
            rev_txt = f"{rating}/5" + (f" ({reviews} تقييم)" if reviews else "")
            _draw_right_aligned_text(d2, rx - 185, star_y - 20, rev_txt, _load_font(700, 25), dark_text)
        except Exception:
            pass

    # كارت المميزات والوصف
    s2 = _draw_shadow_card(s2, (74, 438, CANVAS_W - 74, 962), radius=40)
    d2 = ImageDraw.Draw(s2)
    _draw_right_aligned_text(d2, CANVAS_W - 116, 466, "أهم تفاصيل ومميزات المنتج:", f_subhead, accent)
    d2.line((116, 534, CANVAS_W - 116, 534), fill=accent_soft, width=4)

    by_cur = 562
    for idx_b, bp in enumerate(copy_bundle["bullet_points"][:3], 1):
        # دائرة رقم النقطة على اليمين
        cx_dot = CANVAS_W - 142
        d2.ellipse((cx_dot - 24, by_cur + 4, cx_dot + 24, by_cur + 52), fill=accent_soft)
        _draw_centered_text(d2, by_cur + 8, str(idx_b), _load_font(800, 26), accent, center_x=cx_dot)
        bp_lines = _wrap_text_lines(bp, f_body, CANVAS_W - 310, d2, max_lines=2)
        for bl in bp_lines:
            _draw_right_aligned_text(d2, CANVAS_W - 188, by_cur + 4, bl, f_body, dark_text)
            by_cur += 48
        by_cur += 28

    # كارت خلاصة السعر والتوفير
    s2 = _draw_shadow_card(s2, (74, 992, CANVAS_W - 74, 1172), radius=34, fill=(255, 255, 255, 245))
    d2 = ImageDraw.Draw(s2)
    summary_price = f"السعر الآن: {_fmt_price(price)} ج.م"
    if list_price and list_price > price:
        summary_price += f"   (بدل {_fmt_price(list_price)} ج.م)"
    _draw_centered_text(d2, 1020, summary_price, _load_font(800, 40), accent)
    if saving >= 10:
        _draw_centered_text(d2, 1094, f"إجمالي التوفير: {saving:,} ج.م  —  خصم حقيقي {disc_i}%", _load_font(700, 29), dark_text)
    else:
        _draw_centered_text(d2, 1094, f"خصم {disc_i}% لفترة محدودة على {store_ar}", _load_font(700, 29), dark_text)

    _draw_pill(d2, CANVAS_W // 2, CANVAS_H - 146, "<<   اسحبي لطريقة الطلب بالخصم   <<", f_swipe, accent, (255, 255, 255), pad_x=42, pad_y=12)
    _draw_slide_dots(d2, 1, 3, accent, accent_soft)

    p2 = os.path.join(out_dir, f"{prefix}_2_details.jpg")
    s2.convert("RGB").save(p2, "JPEG", quality=93, optimize=True)
    paths.append(p2)

    # =====================================================================
    # SLIDE 3: تحويل المتابعين لقناة التليجرام + تحفيز التفاعل الخوارزمي
    # =====================================================================
    s3 = _create_gradient_bg(bg_top, bg_bottom, accent_soft)
    d3 = ImageDraw.Draw(s3)

    _draw_pill(d3, CANVAS_W // 2, 68, "إزاي تطلبي العرض بالخصم؟", f_pill, (255, 255, 255, 240), accent, pad_x=40, pad_y=14)

    # الكارت الرئيسي لقناة التليجرام في البايو
    s3 = _draw_shadow_card(s3, (74, 168, CANVAS_W - 74, 650), radius=46)
    d3 = ImageDraw.Draw(s3)

    _draw_centered_text(d3, 214, "رابط الشراء المباشر بالخصم", f_cta_big, dark_text)
    _draw_centered_text(d3, 290, "موجود في قناة التليجرام في البايو", _load_font(700, 38), accent)

    # صندوق يوزر قناة التليجرام البارز
    d3.rounded_rectangle((170, 375, CANVAS_W - 170, 495), radius=60, fill=accent)
    _draw_centered_text(d3, 405, f"Telegram:  {tg_handle}", f_handle, (255, 255, 255))

    _draw_centered_text(d3, 536, "ادخلي البايو واضغطي على لينك القناة", _load_font(700, 34), dark_text)
    _draw_centered_text(d3, 588, "هتلاقي كل عروض البنات يومياً بالروابط المباشرة", _load_font(600, 29), (110, 95, 108))

    # 3 بطاقات تحفيز خوارزمي (Save + Comment + Follow)
    cta_rows = [
        ("1", "احفظي البوست (Save) عشان ترجعيله بسهولة"),
        ("2", "اكتبي «اللينك» في الكومنتات وهنرد عليكي فوراً"),
        ("3", "اعملي فولو عشان تلحقي عروض البنات قبل ما تخلص"),
    ]
    ry = 702
    for num, label in cta_rows:
        s3 = _draw_shadow_card(s3, (74, ry, CANVAS_W - 74, ry + 118), radius=30, fill=(255, 255, 255, 245), shadow_alpha=24)
        d3 = ImageDraw.Draw(s3)
        cx_n = CANVAS_W - 140
        d3.ellipse((cx_n - 30, ry + 29, cx_n + 30, ry + 89), fill=accent)
        _draw_centered_text(d3, ry + 39, num, _load_font(800, 34), (255, 255, 255), center_x=cx_n)
        _draw_right_aligned_text(d3, CANVAS_W - 196, ry + 40, label, _load_font(700, 33), dark_text)
        ry += 142

    # تذكير أنيق بالسعر في الأسفل
    _draw_pill(
        d3,
        CANVAS_W // 2,
        CANVAS_H - 148,
        f"السعر الحالي: {_fmt_price(price)} ج.م  (خصم {disc_i}%)",
        _load_font(800, 32),
        accent_soft,
        accent,
        pad_x=44,
        pad_y=14,
    )
    _draw_slide_dots(d3, 2, 3, accent, accent_soft)

    p3 = os.path.join(out_dir, f"{prefix}_3_cta.jpg")
    s3.convert("RGB").save(p3, "JPEG", quality=93, optimize=True)
    paths.append(p3)

    return paths
