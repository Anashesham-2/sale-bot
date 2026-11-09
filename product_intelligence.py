import html
import io
import json
import os
import re
import threading
import requests

# ---------------------------------------------------------------------------
# 1. قاموس شامل لأشهر الماركات العالمية والمحلية في أمازون مصر ونون مصر (420+ ماركة)
#    يضمن كتابة الماركة دائماً بالإنجليزية الصحيحة والنظيفة في كل الرسائل.
# ---------------------------------------------------------------------------
_GENERIC_BRAND_SET = {
    "generic", "عام", "أخرى", "اخرى", "other", "others", "no brand", "unbranded",
    "بدون ماركة", "بدون علامة تجارية", "غير محدد", "n/a", "oem", "none", "unknown",
    "جينيريك", "جينريك", "متنوع", "متعدد", "brand", "travel", "traveling",
    "outdoor", "household", "portable", "universal", "classic", "fashion",
    # كلمات نتجت سابقاً عن الترجمة الحرفية الخاطئة لأسماء الماركات العربية
    "firstly", "nationalism", "the bride", "bride", "fish", "featured", "quality",
    "product", "deal", "store", "official", "original", "egypt",
}

# ماركات إكسسوارات وصوتيات وطرفيات لا تصنع موبايلات أو تابلت أو لابتوب أو تلفزيونات أو ثلاجات
_NO_MAJOR_DEVICE_BRANDS = {
    "UGREEN", "Anker", "Soundcore", "Baseus", "Joyroom", "Oraimo", "iLock", "LDNIO",
    "Belkin", "Promate", "Spigen", "Ringke", "ESR", "Sekai", "Havit", "Onikuma",
    "Fantech", "JBL", "Logitech", "HyperX", "SanDisk", "Kingston", "Lexar", "Memo",
    "Niimbot", "Choetech", "Arselo", "G-Power", "X-Fast", "Cellularline", "Hama",
    "AULA", "ATTACK SHARK", "Redragon", "Razer", "Cooler Master", "Corsair", "DeepCool",
}

_STORE_BRAND_NOISE_RE = re.compile(
    r'^(?:قم\s+بزيارة\s+متجر|زيارة\s+متجر|العلامة\s+التجارية\s*:?|الماركة\s*:?|متجر|'
    r'visit\s+the|brand\s*:?)\s*|\s*(?:official\s+store|store|المتجر\s+الرسمي)$',
    re.IGNORECASE,
)

def norm_ar_token(text):
    """توحيد الحروف العربية والإنجليزية للمطابقة الدقيقة."""
    if not text:
        return ""
    t = str(text).lower()
    t = re.sub(r'[أإآا]', 'ا', t)
    t = re.sub(r'[ةه]', 'ه', t)
    t = re.sub(r'[يى]', 'ي', t)
    t = re.sub(r'[\u064B-\u065F\u0640\u200b-\u200f]', '', t)
    t = re.sub(r'[^\w\s\+\-\']', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

# المفتاح: عربي أو إنجليزي -> القيمة: الاسم الرسمي المعتمد بالإنجليزية (Canonical English Brand)
RAW_BRAND_EN_MAP = {
    # شواحن، كابلات، صوتيات، إلكترونيات وهاردوير
    "انكر": "Anker", "أنكر": "Anker", "anker": "Anker",
    "ساوند كور": "Soundcore", "ساوندكور": "Soundcore", "soundcore": "Soundcore",
    "يوفي": "Eufy", "eufy": "Eufy",
    "اي لوك": "iLock", "آي لوك": "iLock", "اى لوك": "iLock", "أيلوك": "iLock", "ايلوك": "iLock", "آيلوك": "iLock", "ilock": "iLock", "i-lock": "iLock",
    "يوجرين": "UGREEN", "يوغرين": "UGREEN", "يو جرين": "UGREEN", "ugreen": "UGREEN",
    "بيسوس": "Baseus", "باسيوس": "Baseus", "baseus": "Baseus",
    "جوي روم": "Joyroom", "جوي رووم": "Joyroom", "جويروم": "Joyroom", "joyroom": "Joyroom",
    "اورايمو": "Oraimo", "أورايمو": "Oraimo", "oraimo": "Oraimo",
    "لدنيو": "LDNIO", "ال دي نيو": "LDNIO", "ldnio": "LDNIO",
    "تشويتك": "Choetech", "choetech": "Choetech",
    "ارسيلو": "Arselo", "أرسيلو": "Arselo", "arselo": "Arselo",
    "توليب هوم": "Tulip Home", "tulip home": "Tulip Home",
    "هاينو تيكو": "Haino Teko", "هاينو تيكو ألمانيا": "Haino Teko", "هاينو تيكو المانيا": "Haino Teko", "haino teko": "Haino Teko",
    "تيكزون": "Techzone", "techzone": "Techzone",
    "نيمبوت": "Niimbot", "niimbot": "Niimbot",
    "بيلكن": "Belkin", "بيلكين": "Belkin", "belkin": "Belkin",
    "بروميت": "Promate", "promate": "Promate",
    "هاما": "Hama", "hama": "Hama",
    "انرجايزر": "Energizer", "إنرجايزر": "Energizer", "energizer": "Energizer",
    "دوراسيل": "Duracell", "duracell": "Duracell",
    "جي- بور": "G-Power", "جي باور": "G-Power", "g-power": "G-Power",
    "اكس فاست": "X-Fast", "x-fast": "X-Fast",
    "سيلولار لاين": "Cellularline", "cellularline": "Cellularline",
    "ميمو": "Memo", "memo": "Memo",
    "هافيت": "Havit", "havit": "Havit",
    "اونيكوما": "Onikuma", "أونيكوما": "Onikuma", "onikuma": "Onikuma",
    "ريدراجون": "Redragon", "ريد دراجون": "Redragon", "redragon": "Redragon",
    "لوجيتك": "Logitech", "لوجيتيك": "Logitech", "logitech": "Logitech",
    "ريزر": "Razer", "razer": "Razer",
    "هايبر اكس": "HyperX", "hyperx": "HyperX",
    "فانتك": "Fantech", "fantech": "Fantech",
    "لانجتو": "Langtu", "langtu": "Langtu",
    "تي بي لينك": "TP-Link", "tp-link": "TP-Link", "tplink": "TP-Link",
    "تابو": "Tapo", "tapo": "Tapo",
    "ميركوسيس": "Mercusys", "mercusys": "Mercusys",
    "دي لينك": "D-Link", "d-link": "D-Link",
    "ايمو": "Imou", "إيمو": "Imou", "imou": "Imou",
    "هيكفيجن": "Hikvision", "hikvision": "Hikvision",
    "ezviz": "EZVIZ", "ايزفيز": "EZVIZ",
    "سانديسك": "SanDisk", "sandisk": "SanDisk",
    "كينجستون": "Kingston", "kingston": "Kingston",
    "ليكسر": "Lexar", "lexar": "Lexar",
    "ويسترن ديجيتال": "WD", "wd": "WD", "western digital": "WD",
    "سيجيت": "Seagate", "seagate": "Seagate",
    "كروشال": "Crucial", "crucial": "Crucial",
    "هولي لاند": "Hollyland", "hollyland": "Hollyland",
    "فوجي فيلم": "Fujifilm", "fujifilm": "Fujifilm", "instax": "Instax",
    "كانون": "Canon", "canon": "Canon",
    "نيكون": "Nikon", "nikon": "Nikon",
    "إبسون": "Epson", "ابسون": "Epson", "epson": "Epson",
    "كاسيو": "Casio", "casio": "Casio",
    "فاسينيشن": "Fascination", "fascination": "Fascination",
    "سيكاي": "Sekai", "sekai": "Sekai",
    "وهووب": "Whoop", "ووب": "Whoop", "whoop": "Whoop",
    "لافيتنو": "Lavento", "لافينتو": "Lavento", "lavento": "Lavento",
    "ميدياتيك": "MediaTech", "ميديا تيك": "MediaTech", "mediatech": "MediaTech",
    "بيوتي بيست": "Beauty Beast", "بيوتى بيست": "Beauty Beast", "beauty beast": "Beauty Beast",
    "سيسيجاد": "Sisigad", "sisigad": "Sisigad",
    "اسبيجن": "Spigen", "سبيجن": "Spigen", "spigen": "Spigen",
    "رينجكي": "Ringke", "ringke": "Ringke",
    "إي إس آر": "ESR", "اي اس ار": "ESR", "esr": "ESR",
    "أكس-سكوت": "X-Scot", "اكس سكوت": "X-Scot", "اكس-سكوت": "X-Scot", "أكس سكوت": "X-Scot", "aks-skot": "X-Scot", "x-scot": "X-Scot",
    "جولدن ماسك": "Golden Mask", "golden mask": "Golden Mask",
    "فو ميالتكنولوجيا المحدودة": "Fomi", "فومي": "Fomi", "fomi": "Fomi",
    "امازون": "Amazon", "أمازون": "Amazon", "amazon": "Amazon", "amazon basics": "Amazon Basics",
    "كيندل": "Kindle", "kindle": "Kindle",
    "ادهوماكس": "Edhomax", "edhomax": "Edhomax",
    "جيبيربز": "JEPEErbz", "jepeerbz": "JEPEErbz",

    # موبايلات، لابتوبات، شاشات وصوتيات كبرى
    "سامسونج": "Samsung", "samsung": "Samsung",
    "ابل": "Apple", "أبل": "Apple", "آبل": "Apple", "apple": "Apple",
    "شاومي": "Xiaomi", "xiaomi": "Xiaomi",
    "ريدمي": "Redmi", "redmi": "Redmi",
    "بوكو": "POCO", "poco": "POCO",
    "هواوي": "Huawei", "huawei": "Huawei",
    "هونر": "Honor", "هونور": "Honor", "اونر": "Honor", "أونر": "Honor", "honor": "Honor",
    "ريلمي": "Realme", "realme": "Realme",
    "اوبو": "OPPO", "أوبو": "OPPO", "oppo": "OPPO",
    "فيفو": "Vivo", "vivo": "Vivo",
    "انفينكس": "Infinix", "إنفينيكس": "Infinix", "انفينيكس": "Infinix", "infinix": "Infinix",
    "تكنو": "Tecno", "tecno": "Tecno",
    "نوكيا": "Nokia", "nokia": "Nokia",
    "موتورولا": "Motorola", "motorola": "Motorola",
    "سوني": "Sony", "sony": "Sony",
    "جي بي ال": "JBL", "جي بي إل": "JBL", "جيه بي ال": "JBL", "jbl": "JBL",
    "بوز": "Bose", "bose": "Bose",
    "سنهايزر": "Sennheiser", "sennheiser": "Sennheiser",
    "إديفاير": "Edifier", "اديفاير": "Edifier", "edifier": "Edifier",
    "ديل": "Dell", "dell": "Dell",
    "اتش بي": "HP", "إتش بي": "HP", "hp": "HP",
    "لينوفو": "Lenovo", "lenovo": "Lenovo",
    "اسوس": "ASUS", "أسوس": "ASUS", "اسس": "ASUS", "asus": "ASUS",
    "أيسر": "Acer", "ايسر": "Acer", "acer": "Acer",
    "msi": "MSI", "ام اس اي": "MSI",
    "جيجابايت": "Gigabyte", "gigabyte": "Gigabyte",
    "ال جي": "LG", "إل جي": "LG", "lg": "LG",
    "توشيبا": "Toshiba", "toshiba": "Toshiba",
    "شارب": "Sharp", "sharp": "Sharp",
    "هايسينس": "Hisense", "هايسنس": "Hisense", "hisense": "Hisense",
    "هاير": "Haier", "haier": "Haier",
    "اي تي اي": "ATA", "أي تي إيه": "ATA", "اى تى اى": "ATA", "ata": "ATA",
    "سابل": "Sable", "sable": "Sable",

    # أجهزة منزلية، مطبخ، عدد وأدوات
    "فيليبس": "Philips", "كتاب فيليب": "Philips", "philips": "Philips",
    "براون": "Braun", "braun": "Braun",
    "تورنيدو": "Tornado", "تورنادو": "Tornado", "tornado": "Tornado",
    "فريش": "Fresh", "fresh": "Fresh",
    "ميانتا": "Mienta", "مينتا": "Mienta", "mienta": "Mienta",
    "مولينكس": "Moulinex", "moulinex": "Moulinex",
    "تيفال": "Tefal", "tefal": "Tefal",
    "كينوود": "Kenwood", "kenwood": "Kenwood",
    "ديلونجي": "DeLonghi", "delonghi": "DeLonghi",
    "كروبس": "Krups", "krups": "Krups",
    "نسبرسو": "Nespresso", "نيسبريسو": "Nespresso", "نسبريسو": "Nespresso", "nespresso": "Nespresso",
    "نيوتري كوك": "Nutricook", "نيوتريكوك": "Nutricook", "nutricook": "Nutricook",
    "بلاك اند ديكر": "Black+Decker", "بلاك + ديكر": "Black+Decker", "black+decker": "Black+Decker", "black & decker": "Black+Decker",
    "بوش": "Bosch", "bosch": "Bosch",
    "بيكو": "Beko", "beko": "Beko",
    "ميديا": "Midea", "مديا": "Midea", "midea": "Midea",
    "باناسونيك": "Panasonic", "panasonic": "Panasonic",
    "كاريير": "Carrier", "carrier": "Carrier",
    "يونيون إير": "Unionaire", "يونيون اير": "Unionaire", "unionaire": "Unionaire",
    "أريستون": "Ariston", "اريستون": "Ariston", "ariston": "Ariston",
    "أوليمبيك": "Olympic", "اوليمبيك": "Olympic", "olympic": "Olympic",
    "زانوسي": "Zanussi", "zanussi": "Zanussi",
    "هوفر": "Hoover", "hoover": "Hoover",
    "بيسيل": "Bissell", "bissell": "Bissell",
    "كارشر": "Karcher", "karcher": "Karcher",
    "فيليدا": "Vileda", "vileda": "Vileda",
    "تانك": "Tank", "tank": "Tank",
    "كولداير": "Coldair", "coldair": "Coldair",
    "يورك": "York", "york": "York",
    "سوكاني": "Sokany", "sokany": "Sokany",
    "سوناي": "Sonai", "sonai": "Sonai",
    "راف": "RAF", "raf": "RAF",
    "أكانه": "Akane", "اكانه": "Akane", "أكاني": "Akane", "اكاني": "Akane", "akane": "Akane",
    "هوم جاليري": "Home Gallery", "hom galyry": "Home Gallery", "home gallery": "Home Gallery",
    "توتال": "Total", "total": "Total",
    "توتال انرجيز": "TotalEnergies", "totalenergies": "TotalEnergies",
    "إنجكو": "Ingco", "انجكو": "Ingco", "ingco": "Ingco",
    "ايه بي تي": "APT", "apt": "APT",
    "وودفو": "Wadfow", "wadfow": "Wadfow",
    "انيرجي الحداد": "Energy Elhadad", "energy elhadad": "Energy Elhadad",
    "سيفتي تيك": "Safety Tech", "safety tech": "Safety Tech",
    "كاستويف": "Castwave", "castwave": "Castwave",
    "كينج سميث": "KingSmith", "kingsmith": "KingSmith",
    "جرانزيا": "Granzia", "granzia": "Granzia",
    "تروفال": "Truval", "truval": "Truval",
    "زينوكس": "Zinox", "zinox": "Zinox",
    "نوفال": "Nouval", "nouval": "Nouval",
    "زهران": "Zahran", "zahran": "Zahran",
    "لومينارك": "Luminarc", "luminarc": "Luminarc",
    "بايركس": "Pyrex", "pyrex": "Pyrex",
    "ايكيا": "IKEA", "إيكيا": "IKEA", "ikea": "IKEA",
    "سنوز": "Snooze", "snooze": "Snooze",
    "هابي هوم": "Happy Home", "happy home": "Happy Home",
    "مودرن هوم": "Modern Home", "modern home": "Modern Home",
    "ديان هاوس": "Diane House", "diane house": "Diane House",
    "تى ام هوم": "TM Home", "تي ام هوم": "TM Home", "tm home": "TM Home",
    "لايف ستايل": "Lifestyle", "lifestyle": "Lifestyle",
    "تريس كاسا": "Tres Casa", "tres casa": "Tres Casa",
    "كيتشينو": "Kitcheno", "kitcheno": "Kitcheno",
    "توب شيف": "Top Chef", "top chef": "Top Chef",
    "فكرة": "Fikra", "fikra": "Fikra",
    "تريدو ايجيبت": "Trado Egypt", "ترادو": "Trado Egypt", "trado": "Trado Egypt",
    "سيمبل ديلوكس": "Simple Deluxe", "simple deluxe": "Simple Deluxe",
    "ديلي": "Deli", "deli": "Deli",
    "كيديليو": "Kidilo", "kidilo": "Kidilo",
    "تانجبلب": "Tangplp", "tangplp": "Tangplp",
    "جانفيثا": "Janvitha", "janvitha": "Janvitha",
    "أنيوي": "Anyway", "انيوي": "Anyway", "anyway": "Anyway",

    # عناية شخصية، تجميل، أطفال، منظفات، سوبرماركت، أزياء
    "راش براش": "Rush Brush", "rush brush": "Rush Brush",
    "بيبي ليس": "BaByliss", "babyliss": "BaByliss",
    "كيمي": "Kemei", "كامي": "Kemei", "kemei": "Kemei",
    "في جي ار": "VGR", "في جي آر": "VGR", "vgr": "VGR",
    "دوركو": "Dorco", "dorco": "Dorco",
    "جيليت": "Gillette", "gillette": "Gillette",
    "أورال بي": "Oral-B", "اورال بي": "Oral-B", "oral-b": "Oral-B",
    "نيفيا": "Nivea", "nivea": "Nivea",
    "لوريال": "L'Oreal Paris", "لوريال باريس": "L'Oreal Paris", "loreal": "L'Oreal Paris", "l'oreal": "L'Oreal Paris",
    "غارنييه": "Garnier", "جارنييه": "Garnier", "garnier": "Garnier",
    "دوف": "Dove", "دوف سبراي": "Dove", "dove": "Dove",
    "سيرافي": "CeraVe", "cerave": "CeraVe",
    "لاروش": "La Roche-Posay", "لا روش بوزيه": "La Roche-Posay", "la roche": "La Roche-Posay", "la roche-posay": "La Roche-Posay",
    "يوسيرين": "Eucerin", "eucerin": "Eucerin",
    "بيوديرما": "Bioderma", "بايوديرما": "Bioderma", "bioderma": "Bioderma",
    "فيتشي": "Vichy", "فيشي": "Vichy", "vichy": "Vichy",
    "إيفا": "Eva", "ايفا": "Eva", "eva": "Eva",
    "بيزلين": "Beesline", "بيزلاين": "Beesline", "beesline": "Beesline",
    "بوباى": "Bobai", "بوباي": "Bobai", "bobai": "Bobai",
    "كابيكسي": "Capixy", "capixy": "Capixy",
    "فاكيشين": "Vacation", "فاكيشن": "Vacation", "vacation": "Vacation",
    "سانوسان": "Sanosan", "sanosan": "Sanosan",
    "بندولين": "Penduline", "بيندولين": "Penduline", "penduline": "Penduline",
    "فاتيكا": "Vatika", "فاتيكا ناتشرالز": "Vatika Naturals", "vatika": "Vatika",
    "بيوكسين": "Bioxcin", "bioxcin": "Bioxcin",
    "دابور": "Dabur", "dabur": "Dabur",
    "صانسيلك": "Sunsilk", "sunsilk": "Sunsilk",
    "كلير": "Clear", "clear": "Clear",
    "بانتين": "Pantene", "pantene": "Pantene",
    "هيد اند شولدرز": "Head & Shoulders", "head & shoulders": "Head & Shoulders",
    "تريسمي": "TRESemme", "tresemme": "TRESemme",
    "كارسيل": "Karseell", "karseell": "Karseell",
    "ميبيلين": "Maybelline", "ميبلين": "Maybelline", "maybelline": "Maybelline",
    "سيجنال": "Signal", "signal": "Signal",
    "سنسوداين": "Sensodyne", "sensodyne": "Sensodyne",
    "ليسترين": "Listerine", "listerine": "Listerine",
    "كاماي": "Camay", "camay": "Camay",
    "جونسون": "Johnson's", "جونسون اند جونسون": "Johnson & Johnson", "johnson": "Johnson's",
    "شور": "Sure", "sure": "Sure",
    "اكس": "Axe", "أكس": "Axe", "axe": "Axe",
    "ريكسونا": "Rexona", "rexona": "Rexona",
    "فوج": "Fogg", "fogg": "Fogg",
    "افنان": "Afnan", "أفنان": "Afnan", "afnan": "Afnan",
    "دافيدوف": "Davidoff", "davidoff": "Davidoff",
    "فكتوريا سيكريت": "Victoria's Secret", "victoria's secret": "Victoria's Secret",
    "دولتشي اند غابانا": "Dolce & Gabbana", "dolce & gabbana": "Dolce & Gabbana",
    "ديفا": "Diva", "diva": "Diva",
    "مولفيكس": "Molfix", "molfix": "Molfix",
    "بامبرز": "Pampers", "pampers": "Pampers",
    "بيبي جوي": "Babyjoy", "babyjoy": "Babyjoy",
    "فاين": "Fine", "fine": "Fine",
    "فاين بيبي": "Fine Baby", "fine baby": "Fine Baby",
    "بابيا": "Papia", "papia": "Papia",
    "فاميليا": "Familia", "familia": "Familia",
    "زينة": "Zeina", "zeina": "Zeina",
    "وايت": "White", "white": "White",
    "باهي": "Bahi", "bahi": "Bahi",
    "اريال": "Ariel", "أريال": "Ariel", "ايريال": "Ariel", "ariel": "Ariel",
    "برسيل": "Persil", "persil": "Persil",
    "تايد": "Tide", "tide": "Tide",
    "او اكس اي": "OXI", "أو إكس آي": "OXI", "اوكسي": "OXI", "oxi": "OXI",
    "داوني": "Downy", "downy": "Downy",
    "بريل": "Pril", "pril": "Pril",
    "فيبا": "Feba", "feba": "Feba",
    "فينش": "Finish", "فينيش": "Finish", "finish": "Finish",
    "فانيش": "Vanish", "فانش": "Vanish", "vanish": "Vanish",
    "هاربيك": "Harpic", "harpic": "Harpic",
    "ديتول": "Dettol", "dettol": "Dettol",
    "كلوركس": "Clorox", "clorox": "Clorox",
    "جليد": "Glade", "غليد": "Glade", "glade": "Glade",
    "ريد": "Raid", "raid": "Raid",
    "دايفرسي": "Diversey", "diversey": "Diversey",
    "نسكافيه": "Nescafe", "nescafe": "Nescafe",
    "كوفي-ميت": "Coffee-mate", "كوفي ميت": "Coffee-mate", "coffee-mate": "Coffee-mate",
    "لافازا": "Lavazza", "lavazza": "Lavazza",
    "ليبتون": "Lipton", "lipton": "Lipton",
    "أحمد تي": "Ahmad Tea", "احمد تي": "Ahmad Tea", "ahmad tea": "Ahmad Tea",
    "ابو عوف": "Abu Auf", "أبو عوف": "Abu Auf", "abu auf": "Abu Auf",
    "فيتراك": "Vitrac", "vitrac": "Vitrac",
    "ريتش ماكس": "Rich Mix", "ريتش ميكس": "Rich Mix", "rich mix": "Rich Mix",
    "سوكرادورف": "Sukradorf", "sukradorf": "Sukradorf",
    "عافية": "Afia", "afia": "Afia",
    "سلايت": "Slite", "slite": "Slite",
    "كريستال": "Crystal", "crystal": "Crystal",
    "قليه": "Qalya", "قلية": "Qalya", "qalya": "Qalya",
    "روابي": "Rawabi", "rawabi": "Rawabi",
    "جهينه": "Juhayna", "جهينة": "Juhayna", "juhayna": "Juhayna",
    "إيتاليانو": "Italiano", "ايتاليانو": "Italiano", "italiano": "Italiano",
    "سنبلة الفرات": "Sunbulat Al Furat",
    "حلوة": "Helwa", "helwa": "Helwa",
    "كيت كات": "KitKat", "kitkat": "KitKat",
    "ترايدنت": "Trident", "trident": "Trident",
    "بون": "Bon", "bon": "Bon",
    "دولفين": "Dolphin", "dolphin": "Dolphin",
    "سيمبا": "Simba", "simba": "Simba",
    "ليميتليس": "Limitless", "ليميتليس ناتشورالز": "Limitless Naturals", "limitless": "Limitless",
    "تشالنجر نيوترشن": "Challenger Nutrition", "تشالنجر نيوتريشن": "Challenger Nutrition", "challenger nutrition": "Challenger Nutrition",
    "اوبتيموم نوتريشن": "Optimum Nutrition", "optimum nutrition": "Optimum Nutrition",
    "سينتروم": "Centrum", "centrum": "Centrum",
    "نوفوجين": "Novogen", "novogen": "Novogen",
    "اديداس": "Adidas", "أديداس": "Adidas", "adidas": "Adidas",
    "نايكي": "Nike", "نايك": "Nike", "nike": "Nike",
    "بوما": "Puma", "puma": "Puma",
    "ريبوك": "Reebok", "reebok": "Reebok",
    "سكيتشرز": "Skechers", "skechers": "Skechers",
    "ديفاكتو": "DeFacto", "defacto": "DeFacto",
    "ال سي وايكيكي": "LC Waikiki", "lc waikiki": "LC Waikiki",
    "قطونيل": "Cottonil", "cottonil": "Cottonil",
    "دايس": "Dice", "dice": "Dice",
    "سيزار": "Cesar", "cesar": "Cesar",
    "تيستا تورو": "Testa Toro", "testa toro": "Testa Toro",
    "نافيفورس": "Naviforce", "نافي فورس": "Naviforce", "naviforce": "Naviforce",
    "لاكوست": "Lacoste", "lacoste": "Lacoste",
    "راي بان": "Ray-Ban", "ray-ban": "Ray-Ban",
    "هوت شوبينج": "Hot Shopping", "hot shopping": "Hot Shopping",
    "سبورت كيو": "Sport Q", "sport q": "Sport Q",
    "ابلس": "Aplus", "aplus": "Aplus",
    "جوهار": "Johar", "johar": "Johar",
    # ماركات محلية وعالمية إضافية لمنع أي ترجمة حرفية خاطئة (مثل العروسة / الوطنية / برافو / AULA)
    "العروسة": "El Arosa", "شاي العروسة": "El Arosa", "el arosa": "El Arosa", "elarosa": "El Arosa",
    "الوطنية": "El Wataniya", "وطنية": "El Wataniya", "el wataniya": "El Wataniya",
    "ايزي كير": "Easy Care", "إيزي كير": "Easy Care", "ايزى كير": "Easy Care", "easy care": "Easy Care", "ayzd kyr": "Easy Care",
    "برافو": "Bravo", "bravo": "Bravo", "brafo": "Bravo",
    "أولا": "AULA", "أولاً": "AULA", "اولا": "AULA", "aula": "AULA",
    "أتاك شارك": "ATTACK SHARK", "اتاك شارك": "ATTACK SHARK", "attack shark": "ATTACK SHARK",
    "كامينا": "Kamina", "kamina": "Kamina",
    "لوق": "Looq", "looq": "Looq",
    "بيتي": "Byty", "بيتى": "Byty", "byty": "Byty",
    "نيوب": "Neop", "neop": "Neop",
    "ليسيد": "Leseed", "leseed": "Leseed",
    "كولر ماستر": "Cooler Master", "cooler master": "Cooler Master",
    "كورسير": "Corsair", "corsair": "Corsair",
    "ديب كول": "DeepCool", "deepcool": "DeepCool",
    "ثرمالتيك": "Thermaltake", "thermaltake": "Thermaltake",
    "ان زد اكس تي": "NZXT", "nzxt": "NZXT",
    "روتو": "Roto", "roto": "Roto",
    "فابير كاستل": "Faber-Castell", "فابر كاستل": "Faber-Castell", "faber-castell": "Faber-Castell",
    "بيك": "BIC", "bic": "BIC",
    "بريما": "Prima", "prima": "Prima",
    "فيبكس": "Vebix", "vebix": "Vebix",
    "ستارفيل": "Starville", "ستاركي": "Starville", "starville": "Starville",
    "شان": "Shaan", "shaan": "Shaan",
    "كليو": "Cleo", "cleo": "Cleo",
    "درمينا": "Dermina", "dermina": "Dermina",
    "أفين": "Avene", "افين": "Avene", "avene": "Avene",
    "ذا اورديناري": "The Ordinary", "the ordinary": "The Ordinary",
    "هاينز": "Heinz", "heinz": "Heinz",
    "كنور": "Knorr", "knorr": "Knorr",
    "ماجي": "Maggi", "maggi": "Maggi",
    "المراعي": "Almarai", "almarai": "Almarai",
    "الضحى": "El Doha", "el doha": "El Doha",
    "ريتش بيك": "Rich Bake", "rich bake": "Rich Bake",
    "امتنان": "Imtenan", "إمتنان": "Imtenan", "imtenan": "Imtenan",
    "كادبوري": "Cadbury", "cadbury": "Cadbury",
    "نستله": "Nestle", "نسلة": "Nestle", "nestle": "Nestle",
}

NORM_BRAND_EN_MAP = {}
for _k, _v in RAW_BRAND_EN_MAP.items():
    NORM_BRAND_EN_MAP[norm_ar_token(_k)] = _v
    NORM_BRAND_EN_MAP[_k.lower().strip()] = _v

# كلمات تقنية لا نعتبرها أسماء ماركات عند البحث عن اسم لاتيني
_NON_BRAND_LATIN = {
    "usb", "led", "lcd", "oled", "amole", "amoled", "qled", "uhd", "fhd", "hd", "ips",
    "pro", "max", "plus", "mini", "lite", "ultra", "air", "neo", "tws", "anc", "enc",
    "rgb", "argb", "pwm", "wifi", "bluetooth", "gps", "nfc", "pd", "gan", "qc", "type", "aux", "hdmi",
    "vga", "lan", "ssd", "hdd", "ram", "rom", "cpu", "gpu", "fps", "dpi", "mah", "watt",
    "egp", "new", "for", "with", "and", "the", "pack", "pcs", "set", "kit", "box", "bag",
    "car", "home", "smart", "fast", "super", "power", "water", "series", "gen", "model",
    "travel", "traveling", "outdoor", "household", "portable", "universal", "classic",
    "fashion", "women", "men", "kids", "baby", "storage", "clothing", "white", "black",
}

_AR_TRANSLIT_TABLE = {
    'ا': 'a', 'أ': 'a', 'إ': 'e', 'آ': 'a', 'ب': 'b', 'ت': 't', 'ث': 'th',
    'ج': 'g', 'ح': 'h', 'خ': 'kh', 'د': 'd', 'ذ': 'z', 'ر': 'r', 'ز': 'z',
    'س': 's', 'ش': 'sh', 'ص': 's', 'ض': 'd', 'ط': 't', 'ظ': 'z', 'ع': 'a',
    'غ': 'gh', 'ف': 'f', 'ق': 'q', 'ك': 'k', 'ل': 'l', 'م': 'm', 'ن': 'n',
    'ه': 'h', 'ة': 'a', 'و': 'o', 'ي': 'y', 'ى': 'a', 'ئ': 'e', 'ؤ': 'o', 'ء': '',
    'ڤ': 'v', 'پ': 'p', 'چ': 'ch', 'گ': 'g',
}

def transliterate_ar_to_en(text):
    """تحويل صوتي احتياطي لأي اسم ماركة عربي غير معروف إلى حروف إنجليزية نظيفة (بدون ترجمة دلالية خاطئة)."""
    words = []
    for w in re.split(r'\s+', (text or "").strip()):
        if not w:
            continue
        if not re.search(r'[\u0600-\u06FF]', w):
            words.append(w)
            continue
        has_al = bool(re.match(r'^ال', w)) and len(w) > 3
        w_core = re.sub(r'^ال', '', w) if has_al else w
        out = []
        for ch in w_core:
            if ch in _AR_TRANSLIT_TABLE:
                out.append(_AR_TRANSLIT_TABLE[ch])
            elif re.match(r'[A-Za-z0-9\-]', ch):
                out.append(ch)
        s = "".join(out)
        s = re.sub(r'(.)\1{2,}', r'\1\1', s)
        if s:
            cap = s.capitalize()
            if has_al:
                words.append(f"El {cap}")
            else:
                words.append(cap)
    return " ".join(words).strip()

_tr_cache = {}
_tr_lock = threading.Lock()
_TR_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".en_tr_cache.json")
if os.path.exists(_TR_CACHE_FILE):
    try:
        with open(_TR_CACHE_FILE, "r", encoding="utf-8") as _tf:
            _tr_cache = json.load(_tf)
    except Exception:
        _tr_cache = {}

# تصحيح الكلمات العربية المشتركة لفظياً قبل الترجمة لمنع أخطاء مثل (فيش -> Fish)
_AR_PRE_TRANSLATE_FIXES = [
    (re.compile(r'\bفيش(?:ة|ه)?\b'), "قابس كهربائي"),
    (re.compile(r'\bمشترك\b'), "مشترك كهربائي"),
    (re.compile(r'\bكبة\b'), "مفرمة طعام"),
    (re.compile(r'\bمنشر\b'), "حامل تجفيف ملابس"),
]

def translate_ar_to_en_fast(text, timeout=3.5):
    """ترجمة سريعة ومخزنة مؤقتاً لتحويل اسم منتج عربي إلى إنجليزي نظيف مع بديل احتياطي مجاني."""
    q = re.sub(r'\s+', ' ', (text or "")).strip()[:160]
    if not q or not re.search(r'[\u0600-\u06FF]', q):
        return q
    for rx_fix, repl_ar in _AR_PRE_TRANSLATE_FIXES:
        q = rx_fix.sub(repl_ar, q)
    with _tr_lock:
        if q in _tr_cache:
            return _tr_cache[q]

    res = ""
    # 1) المحرك الأساسي: Google Translate GTX
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "ar", "tl": "en", "dt": "t", "q": q},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
        )
        if r.ok:
            data = r.json()
            cand = "".join(seg[0] for seg in (data[0] or []) if seg and seg[0]).strip()
            cand = re.sub(r'\s+', ' ', cand)
            if cand and not re.search(r'[\u0600-\u06FF]', cand):
                res = cand
    except Exception:
        pass

    # 2) المحرك الاحتياطي المجاني: MyMemory API (يمنع ظهور Featured Product عند ضغط الطلبات)
    if not res:
        try:
            r2 = requests.get(
                "https://api.mymemory.translated.net/get",
                params={"q": q[:140], "langpair": "ar|en"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=timeout,
            )
            if r2.ok:
                cand2 = html.unescape((r2.json().get("responseData") or {}).get("translatedText") or "").strip()
                cand2 = re.sub(r'\s+', ' ', cand2)
                if cand2 and not re.search(r'[\u0600-\u06FF]', cand2) and "MYMEMORY WARNING" not in cand2.upper():
                    res = cand2
        except Exception:
            pass

    if res:
        with _tr_lock:
            _tr_cache[q] = res
            if len(_tr_cache) % 25 == 0:
                try:
                    with open(_TR_CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(_tr_cache, f, ensure_ascii=False)
                except Exception:
                    pass
        return res
    return ""

def save_tr_cache():
    with _tr_lock:
        try:
            with open(_TR_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_tr_cache, f, ensure_ascii=False)
        except Exception:
            pass
    save_en_meta_cache()

# ---------------------------------------------------------------------------
# 1-ب. جلب بيانات المنتج الرسمية بالإنجليزية من المتجر (/-/en/dp/<ASIN>)
#      تكتشف فوراً أي ترجمة عربية آلية خاطئة من أمازون (مثل تسمية شاحن UGREEN X516 كابلاً!)
# ---------------------------------------------------------------------------
_en_meta_cache = {}
_en_meta_lock = threading.Lock()
_EN_META_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".en_meta_cache.json")
if os.path.exists(_EN_META_CACHE_FILE):
    try:
        with open(_EN_META_CACHE_FILE, "r", encoding="utf-8") as _emf:
            _en_meta_cache = json.load(_emf)
    except Exception:
        _en_meta_cache = {}

def save_en_meta_cache():
    with _en_meta_lock:
        try:
            with open(_EN_META_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_en_meta_cache, f, ensure_ascii=False)
        except Exception:
            pass

def extract_amazon_asin(url_or_text):
    if not url_or_text:
        return None
    s = str(url_or_text).strip()
    if re.fullmatch(r'[A-Z0-9]{10}', s):
        return s
    m = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})\b', s, re.I)
    return m.group(1).upper() if m else None

def fetch_amazon_en_metadata(url_or_asin, timeout=5.0):
    """
    يجلب العنوان الرسمي باللغة الإنجليزية والماركة ومسار الفئة من صفحة أمازون الإنجليزية:
    https://www.amazon.eg/-/en/dp/<ASIN>
    سريع جداً (~0.3 ثانية) ومخزن مؤقتاً لمنع تكرار الطلبات لنفس المنتج.
    """
    asin = extract_amazon_asin(url_or_asin)
    if not asin:
        return {}
    with _en_meta_lock:
        if asin in _en_meta_cache:
            return _en_meta_cache[asin]

    en_url = f"https://www.amazon.eg/-/en/dp/{asin}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = requests.get(en_url, headers=headers, timeout=timeout)
        if not r.ok or len(r.text) < 2000:
            return {}
        raw = r.text
        if "validateCaptcha" in raw or "Robot Check" in raw:
            return {}

        # 1) العنوان الرسمي بالإنجليزية (#productTitle)
        en_title = ""
        m_t = re.search(r'<span[^>]*id=["\']productTitle["\'][^>]*>(.*?)</span>', raw, re.S | re.I)
        if m_t:
            en_title = html.unescape(re.sub(r'<[^>]+>', ' ', m_t.group(1)))
            en_title = re.sub(r'\s+', ' ', en_title).strip()
        if not en_title:
            m_mt = re.search(r'<title[^>]*>(.*?)</title>', raw, re.S | re.I)
            if m_mt:
                cand_t = html.unescape(re.sub(r'<[^>]+>', ' ', m_mt.group(1)))
                cand_t = re.split(r'\s*:\s*(?:Buy Online|Amazon\.eg)|\s*\|\s*Amazon\.eg', cand_t, maxsplit=1, flags=re.I)[0]
                cand_t = re.sub(r'^Amazon\.eg\s*:\s*', '', cand_t, flags=re.I).strip()
                if len(cand_t) >= 6 and "Page Not Found" not in cand_t and "Sorry!" not in cand_t:
                    en_title = re.sub(r'\s+', ' ', cand_t).strip()

        # 2) الماركة الرسمية بالإنجليزية (po-brand أو #bylineInfo)
        en_brand = ""
        m_pb = re.search(r'<tr[^>]*\bpo-brand\b[^>]*>.*?<td[^>]*\ba-span9\b[^>]*>(.*?)</td>', raw, re.S | re.I)
        if m_pb:
            en_brand = html.unescape(re.sub(r'<[^>]+>', ' ', m_pb.group(1)))
        if not en_brand:
            m_by = re.search(r'<a[^>]*id=["\']bylineInfo["\'][^>]*>(.*?)</a>', raw, re.S | re.I)
            if m_by:
                en_brand = html.unescape(re.sub(r'<[^>]+>', ' ', m_by.group(1)))
        if en_brand:
            en_brand = re.sub(r'\s+', ' ', en_brand).strip()
            en_brand = re.sub(r'^(?:Visit the|Brand\s*:?)\s*', '', en_brand, flags=re.I)
            en_brand = re.sub(r'\s*Store$', '', en_brand, flags=re.I).strip()

        # 3) مسار الفئة الرسمي بالإنجليزية (Breadcrumbs)
        en_breadcrumbs = []
        m_bc_div = re.search(
            r'id=["\']wayfinding-breadcrumbs_feature_div["\'][^>]*>(.*?)</div>',
            raw,
            re.S | re.I,
        )
        if m_bc_div:
            for a_txt in re.findall(r'<a[^>]*>(.*?)</a>', m_bc_div.group(1), re.S | re.I):
                c_item = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', a_txt))).strip()
                if c_item:
                    en_breadcrumbs.append(c_item)

        if not en_title and not en_brand and not en_breadcrumbs:
            return {}

        meta = {
            "en_title": en_title,
            "en_brand": en_brand,
            "en_breadcrumbs": en_breadcrumbs,
        }
        with _en_meta_lock:
            _en_meta_cache[asin] = meta
            if len(_en_meta_cache) % 20 == 0:
                try:
                    with open(_EN_META_CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(_en_meta_cache, f, ensure_ascii=False)
                except Exception:
                    pass
        return meta
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# استخراج وتوحيد الماركة بالإنجليزية دائماً (بدون ترجمة دلالية لأسماء العلم!)
# ---------------------------------------------------------------------------
COMPAT_SPLIT_RE = re.compile(
    r'(?:\b(?:متوافق(?:ة)?\s*مع|مناسب(?:ة)?\s*لـ?|مخصص(?:ة)?\s*لـ?|مصمم(?:ة)?\s*لـ?|بديل(?:ة)?\s*لـ?|'
    r'لأجهزة|لاجهزة|لهواتف|لموبايل|للموبايل|لهاتف|للهاتف|لجهاز|لباور\s*بانك|'
    r'compatible\s+with|designed\s+for|fit\s+for|made\s+for|replacement\s+for|case\s+for|cover\s+for|strap\s+for)\b|'
    r'\bل(?=ايفون|آيفون|أيفون|ايباد|آيباد|سامسونج|جالكسي|جالاكسي|شاومي|ريدمي|هواوي)|'
    r'\bfor(?=\s+(?:iphone|ipad|ipod|macbook|airpods|apple\s*watch|samsung|galaxy|xiaomi|redmi|huawei|honor|oppo|realme|vivo|infinix|laptop|ps[45]|xbox)\b))',
    re.IGNORECASE,
)

def _clean_latin_brand_candidate(cand):
    if not cand:
        return ""
    c = _STORE_BRAND_NOISE_RE.sub("", str(cand)).strip()
    c = re.sub(r'[>›«»™®©]', '', c).strip(" -—,:;.|/")
    if not c or c.lower() in _GENERIC_BRAND_SET:
        return ""
    cn = norm_ar_token(c)
    if cn in NORM_BRAND_EN_MAP:
        return NORM_BRAND_EN_MAP[cn]
    if c.lower() in NORM_BRAND_EN_MAP:
        return NORM_BRAND_EN_MAP[c.lower()]
    if not re.search(r'[\u0600-\u06FF]', c) and re.search(r'[A-Za-z]{2,}', c):
        if c.islower() and len(c) > 3:
            return c.title()[:40]
        return c[:40]
    return ""

def normalize_brand_english(brand_raw, title="", extra_text="", en_brand="", en_title="", allow_network=True):
    """
    يرجع دائماً اسم الماركة بالإنجليزية النظيفة فقط (مثل Philips, Xiaomi, AULA, El Arosa, UGREEN).
    لا يترجم أسماء الماركات ترجمة دلالية أبداً (فلا يكتب The bride أو Nationalism أو Firstly!).
    """
    t_full = f"{title or ''} {en_title or ''} {extra_text or ''}".strip()
    t_primary = COMPAT_SPLIT_RE.split(title or "", maxsplit=1)[0]
    en_primary = COMPAT_SPLIT_RE.split(en_title or "", maxsplit=1)[0]

    # 0. الأولوية القصوى: الماركة الرسمية من النسخة الإنجليزية للمتجر (إن وجدت)
    clean_en_b = _clean_latin_brand_candidate(en_brand)
    if clean_en_b:
        return clean_en_b

    # 1. تنظيف الماركة الخام من عبارات المتجر
    b = _STORE_BRAND_NOISE_RE.sub("", str(brand_raw or "")).strip()
    b = re.sub(r'[>›«»™®©]', '', b).strip()
    if b.lower() in _GENERIC_BRAND_SET:
        b = ""

    # حالة التصحيح الخاص لترجمة أمازون الحرفية لـ Philips ('كتاب فيليب')
    if norm_ar_token(b) == norm_ar_token("كتاب فيليب"):
        return "Philips"

    if b:
        paren_m = re.findall(r'[A-Za-z][A-Za-z0-9\+\-\'&\.\s]{1,28}', b)
        if "/" in b or "|" in b:
            parts = [p.strip() for p in re.split(r'[/\|]', b) if p.strip()]
            matched_part = None
            t_norm = norm_ar_token(t_full)
            for p in parts:
                pn = norm_ar_token(p)
                en_mapped = NORM_BRAND_EN_MAP.get(pn) or NORM_BRAND_EN_MAP.get(p.lower())
                if (pn and pn in t_norm) or (en_mapped and en_mapped.lower() in t_full.lower()):
                    matched_part = en_mapped or p
                    break
            b = matched_part or parts[0]

        bn = norm_ar_token(b)
        if bn in NORM_BRAND_EN_MAP:
            return NORM_BRAND_EN_MAP[bn]
        if b.lower() in NORM_BRAND_EN_MAP:
            return NORM_BRAND_EN_MAP[b.lower()]

        if paren_m and re.search(r'[\u0600-\u06FF]', b):
            cand = paren_m[0].strip()
            if cand.lower() not in _GENERIC_BRAND_SET:
                return NORM_BRAND_EN_MAP.get(cand.lower(), cand)

        if not re.search(r'[\u0600-\u06FF]', b):
            if b.lower() not in _GENERIC_BRAND_SET:
                if b.islower() and len(b) > 3:
                    return b.title()
                return b[:40]
            b = ""

    # 2. البحث عن الماركة داخل العنوان الإنجليزي الرسمي أولاً ثم العنوان العربي الأساسي
    for src_primary in (en_primary, t_primary):
        if not src_primary:
            continue
        for m_from in re.finditer(r'\b(?:من|by)\s+([\w\u0600-\u06FF]+(?:\s+[\w\u0600-\u06FF]+)?)', src_primary, re.I):
            phrase = m_from.group(1).strip()
            for candidate in (phrase, phrase.split()[0]):
                cn = norm_ar_token(candidate)
                if cn in NORM_BRAND_EN_MAP:
                    return NORM_BRAND_EN_MAP[cn]

        head_words = norm_ar_token(" ".join(src_primary.split()[:7]))
        for k_norm in sorted(NORM_BRAND_EN_MAP.keys(), key=len, reverse=True):
            if len(k_norm) < 2:
                continue
            if re.search(r'(?:^|\s)' + re.escape(k_norm) + r'(?:\s|$)', head_words):
                return NORM_BRAND_EN_MAP[k_norm]

    # لو لدينا عنوان إنجليزي رسمي يبدأ باسم ماركة لاتيني واضح (مثل Looq Strawberry Fluff...)
    if en_primary:
        first_tok = re.sub(r'[^\w\+\-&]', '', en_primary.split()[0]) if en_primary.split() else ""
        if (
            len(first_tok) >= 3
            and re.match(r'^[A-Z][A-Za-z0-9\+\-&]{2,18}$', first_tok)
            and first_tok.lower() not in _NON_BRAND_LATIN
            and first_tok.lower() not in _GENERIC_BRAND_SET
            and not re.search(r'^\d', first_tok)
        ):
            # نتحقق أنه ليس مجرد صفة أو رقم مقاس (مثل Foldable / Portable / Wireless / Adjustable / Heavy)
            _en_adj_not_brand = {
                "foldable", "portable", "wireless", "adjustable", "electric", "digital",
                "rechargeable", "magnetic", "stainless", "waterproof", "multifunctional",
                "automatic", "professional", "original", "mini", "large", "small", "pack",
                "set", "pair", "men", "mens", "women", "womens", "kids", "baby", "cotton",
            }
            if first_tok.lower() not in _en_adj_not_brand:
                return NORM_BRAND_EN_MAP.get(first_tok.lower(), first_tok)

    # 3. لو الماركة المعطاة بالعربي ولم نجدها في القاموس: نحولها صوتياً بدون ترجمة دلالية أبداً!
    if b and re.search(r'[\u0600-\u06FF]', b):
        b_translit = transliterate_ar_to_en(b)
        for lat in re.findall(r'[A-Za-z][A-Za-z0-9\+\-]{2,20}', f"{en_primary} {t_primary}"):
            if lat.lower() not in _NON_BRAND_LATIN and lat.lower() not in _GENERIC_BRAND_SET and not re.search(r'\d', lat):
                if b_translit and lat.lower()[:2] == b_translit.lower()[:2]:
                    return lat if not lat.islower() else lat.title()
        return b_translit[:35]

    return ""


# ---------------------------------------------------------------------------
# 2. محرك الرؤية الحاسوبية (CLIP Vision Zero-Shot عبر ONNX Runtime الخفيف والسريع)
#    يفحص صورة المنتج الحقيقية ليتعرف على ماهية المنتج بصرياً ويمنع أي تعارض مع النص!
# ---------------------------------------------------------------------------
VISION_PROMPTS = [
    ("kettle", "a product photo of an electric water kettle"),
    ("stand_fan", "a product photo of a standing pedestal fan or electric cooling fan"),
    ("pc_cooler", "a product photo of a PC case cooling fan with RGB LED ring or CPU heatsink"),
    ("tv_stick", "a product photo of an HDMI TV stick streaming media dongle with remote"),
    ("smart_tv", "a product photo of a wide flat screen television or computer monitor"),
    ("security_camera", "a product photo of a home WiFi security surveillance camera"),
    ("charging_cable", "a product photo of a USB charging cable wire cord"),
    ("wall_charger", "a product photo of a USB wall charger power adapter plug"),
    ("plug_adapter", "a product photo of a multi-plug electrical wall socket adapter"),
    ("car_charger", "a product photo of a car cigarette lighter USB charger adapter"),
    ("wireless_charger", "a product photo of a magnetic wireless charging pad or stand"),
    ("power_bank", "a product photo of a portable power bank battery pack"),
    ("storage_drive", "a product photo of an external portable SSD drive, hard drive or flash drive"),
    ("water_heater", "a product photo of a domestic water heater mounted on the wall"),
    ("power_strip", "a product photo of an electrical power strip extension socket outlets"),
    ("usb_hub", "a product photo of a multi-port USB-C hub docking station adapter"),
    ("stand_holder", "a product photo of an empty desk phone stand or laptop holder mount"),
    ("stand_mixer", "a product photo of a kitchen stand mixer machine with mixing bowl"),
    ("blender", "a product photo of a kitchen blender jar or hand immersion blender"),
    ("food_chopper", "a product photo of a kitchen electric food chopper bowl with blades"),
    ("juicer", "a product photo of a citrus juicer fruit squeezer machine"),
    ("air_fryer", "a product photo of a digital air fryer kitchen appliance"),
    ("microwave", "a product photo of a microwave oven or electric toaster oven"),
    ("coffee_maker", "a product photo of an electric coffee maker or espresso machine"),
    ("milk_frother", "a product photo of a handheld electric milk frother wand"),
    ("steam_iron", "a product photo of a clothes steam iron or garment steamer"),
    ("ironing_board", "a product photo of a standing foldable ironing board"),
    ("drying_rack", "a product photo of a foldable metal clothes drying rack laundry airer"),
    ("steam_cleaner", "a product photo of a handheld pressurized steam cleaner machine"),
    ("vacuum", "a product photo of a vacuum cleaner appliance"),
    ("washing_machine", "a product photo of a front-load or top-load washing machine"),
    ("cookware", "a product photo of cooking pots frying pan cookware set"),
    ("earbuds", "a product photo of wireless in-ear earbuds with charging case"),
    ("wired_earphones", "a product photo of wired in-ear earphones with audio jack cord"),
    ("headphones", "a product photo of over-ear headphones or gaming headset with mic"),
    ("speaker", "a product photo of a portable bluetooth speaker"),
    ("soundbar", "a product photo of a long horizontal TV soundbar speaker"),
    ("smartphone", "a product photo of a smartphone mobile phone screen and camera"),
    ("protective_case", "a product photo of an empty protective phone or device silicone case cover"),
    ("smartwatch", "a product photo of a wristwatch or digital smartwatch on wrist"),
    ("watch_strap", "a product photo of a replacement watch band strap without watch"),
    ("laptop", "a product photo of an open laptop notebook computer with keyboard"),
    ("tablet", "a product photo of a tablet screen or Kindle e-reader"),
    ("mouse", "a product photo of a computer mouse or gaming mouse"),
    ("keyboard", "a product photo of a computer keyboard"),
    ("shaver", "a product photo of an electric hair clipper trimmer or shaver"),
    ("scale", "a product photo of a flat digital bathroom or kitchen weighing scale"),
    ("lantern", "a product photo of an LED camping lantern or handheld flashlight"),
    ("shoes", "a product photo of sneakers running shoes or sandals"),
    ("bag_organizer", "a product photo of a backpack laptop bag or zipper organizer pouch"),
    ("storage_organizer", "a product photo of a plastic storage organizer box rack or laundry basket"),
    ("cushion_chair", "a product photo of a seat cushion pillow or back support pad"),
    ("baby_chair", "a product photo of a baby high chair or stroller"),
    ("tools", "a product photo of hand tools pliers wire cutter screwdriver wrench drill hardware tool"),
    ("stationery", "a product photo of ballpoint pens markers notebooks office stationery"),
    ("detergent", "a product photo of laundry detergent pods washing powder cleaning liquid bottle"),
    ("skin_care", "a product photo of skincare cream bottle serum lotion hand wash cosmetics"),
    ("perfume", "a product photo of a glass perfume cologne fragrance spray bottle"),
    ("diapers", "a product photo of a baby diapers jumbo pack"),
    ("tissues", "a product photo of facial tissue box or paper towel rolls"),
    ("clothing", "a product photo of clothing t-shirt pants jacket apparel"),
    ("grocery", "a product photo of food grocery jar coffee pack snack bottle"),
    ("_other_medical", "a product photo of a pill cutter medical box pharmacy accessory"),
    ("_other_hardware", "a product photo of industrial spare parts cutting blades spray can"),
    ("_other_general", "a product photo of a small household retail item accessory"),
]

# فئات ذات شكل بصري هندسي مميز جداً يمكن لـ CLIP حسْمها حتى لو كان النص العربي تالفاً أو عاماً
_HIGH_PRECISION_VISION_CATS = {
    "kettle", "water_heater", "storage_drive", "stand_fan", "pc_cooler", "tv_stick", "smart_tv", "security_camera",
    "charging_cable", "wall_charger", "car_charger", "power_bank", "power_strip",
    "stand_mixer", "blender", "food_chopper", "air_fryer", "microwave", "coffee_maker",
    "steam_iron", "ironing_board", "drying_rack", "vacuum", "washing_machine",
    "cookware", "earbuds", "headphones", "speaker", "smartphone", "smartwatch",
    "laptop", "mouse", "keyboard", "shaver", "shoes",
}

_clip_lock = threading.Lock()
_clip_state = {"ready": False, "failed": False, "vis_sess": None, "txt_embeds": None}
_img_vision_cache = {}

def _init_clip_vision():
    with _clip_lock:
        if _clip_state["ready"] or _clip_state["failed"]:
            return _clip_state["ready"]
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
            from huggingface_hub import hf_hub_download

            repo = "Xenova/clip-vit-base-patch32"
            tok_path = hf_hub_download(repo, "tokenizer.json")
            vis_path = hf_hub_download(repo, "onnx/vision_model_quantized.onnx")
            txt_path = hf_hub_download(repo, "onnx/text_model_quantized.onnx")

            tokenizer = Tokenizer.from_file(tok_path)
            tokenizer.enable_padding(pad_id=49407, pad_token="<|endoftext|>", length=77)
            tokenizer.enable_truncation(max_length=77)

            vis_sess = ort.InferenceSession(vis_path, providers=["CPUExecutionProvider"])
            txt_sess = ort.InferenceSession(txt_path, providers=["CPUExecutionProvider"])

            prompts = [p[1] for p in VISION_PROMPTS]
            enc = tokenizer.encode_batch(prompts)
            input_ids = np.array([e.ids for e in enc], dtype=np.int64)
            txt_in = {"input_ids": input_ids}
            if any(i.name == "attention_mask" for i in txt_sess.get_inputs()):
                txt_in["attention_mask"] = np.array([e.attention_mask for e in enc], dtype=np.int64)
            txt_embeds = txt_sess.run(["text_embeds"], txt_in)[0]
            txt_embeds = txt_embeds / np.linalg.norm(txt_embeds, axis=-1, keepdims=True)

            _clip_state["vis_sess"] = vis_sess
            _clip_state["txt_embeds"] = txt_embeds
            _clip_state["ready"] = True
            return True
        except Exception as e:
            print(f"ℹ️ Vision CLIP fallback (text+context mode): {e}")
            _clip_state["failed"] = True
            return False

_ensure_vision_loaded = _init_clip_vision

def classify_product_image(image_source, timeout=6.0):
    """
    يحلل صورة المنتج بصرياً ويرجع قاموس الاحتمالات وأعلى فئة مرئية.
    يدعم رابط URL للصورة أو بايتات الصورة مباشرة.
    """
    if not image_source:
        return None
    cache_key = image_source if isinstance(image_source, str) else None
    if cache_key and cache_key in _img_vision_cache:
        return _img_vision_cache[cache_key]
    if isinstance(image_source, str) and not image_source.startswith("http"):
        return None
    if not _init_clip_vision():
        return None

    try:
        import numpy as np
        from PIL import Image

        if isinstance(image_source, str):
            r = requests.get(
                image_source,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=timeout,
            )
            if not r.ok or len(r.content) < 500:
                return None
            raw_bytes = r.content
        else:
            raw_bytes = image_source

        img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
        w, h = img.size
        if w < 30 or h < 30:
            return None
        scale = 224.0 / min(w, h)
        nw, nh = int(round(w * scale)), int(round(h * scale))
        img = img.resize((nw, nh), Image.BICUBIC)
        left, top = (nw - 224) // 2, (nh - 224) // 2
        img = img.crop((left, top, left + 224, top + 224))

        mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32).reshape(3, 1, 1)
        std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32).reshape(3, 1, 1)
        arr = (np.transpose(np.asarray(img, dtype=np.float32) / 255.0, (2, 0, 1)) - mean) / std
        px = arr[None, ...]

        img_embeds = _clip_state["vis_sess"].run(["image_embeds"], {"pixel_values": px})[0]
        img_embeds = img_embeds / np.linalg.norm(img_embeds, axis=-1, keepdims=True)
        cos_sims = (img_embeds @ _clip_state["txt_embeds"].T)[0]
        max_cos = float(np.max(cos_sims))
        logits = 100.0 * cos_sims
        exps = np.exp(logits - np.max(logits))
        probs = exps / np.sum(exps)

        prob_map = {}
        for idx, (ckey, _) in enumerate(VISION_PROMPTS):
            val = float(probs[idx])
            if val > prob_map.get(ckey, 0.0):
                prob_map[ckey] = val

        ranked = sorted(prob_map.items(), key=lambda x: x[1], reverse=True)
        res = {
            "top_cat": ranked[0][0],
            "top_prob": ranked[0][1],
            "max_cos": max_cos,
            "second_cat": ranked[1][0] if len(ranked) > 1 else None,
            "second_prob": ranked[1][1] if len(ranked) > 1 else 0.0,
            "probs": prob_map,
        }
        if cache_key:
            if len(_img_vision_cache) > 2500:
                _img_vision_cache.clear()
            _img_vision_cache[cache_key] = res
        return res
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 3. تصنيف وفهم المنتج الشامل (العنوان الكامل + الوصف + المواصفات + مسار الفئة + الصورة)
# ---------------------------------------------------------------------------
# كل عنصر: (cat_key, regex_pattern, ar_label, en_label, fallback_ar_desc)
SMART_CATEGORIES = [
    ("capture_card", r'\b(?:كابتشر\s*كارد|كرت\s*تسجيل|بطاقة\s*التقاط|video\s*capture|capture\s*card)\b',
     "كابتشر كارد لتسجيل الفيديو", "Video Capture Card",
     "كارت تسجيل وبث فيديو احترافي ينقل ويسجل الصورة بدقة فائقة وسرعة عالية بدون تأخير، مثالي للبث المباشر وصناع المحتوى والألعاب."),

    ("tv_stick", r'(?:tv\s*stick|fire\s*tv|streaming\s*(?:stick|media|player|device)|android\s*(?:tv\s*)?box|tv\s*box|chromecast|مشغل\s*(?:وسائط|بث)|جهاز\s*بث|أجهزة\s*فك\s*التشفير|ريسيفر\s*ذكي)',
     "مشغل وسائط ذكي للتلفزيون", "Smart TV Streaming Media Player",
     "مشغل وسائط ذكي يحول التلفزيون العادي إلى شاشة سمارت متكاملة بدقة فائقة مع دعم تطبيقات المشاهدة والبث الصوتي والمرئي بسلاسة."),

    ("ereader", r'\b(?:كيندل|kindle|paperwhite|قارئ\s*كتب\s*إلكتروني)\b',
     "جهاز قراءة إلكتروني Kindle", "Kindle E-Reader",
     "قارئ كتب إلكتروني بشاشة مريحة للعين تشبه الورق الحقيقي بدون توهج، مع بطارية تدوم لأسابيع ومساحة واسعة لآلاف الكتب."),

    ("security_camera", r'(?:كاميرا\s*(?:أمان|امان|مراقبة|داخلية|خارجية|واي\s*فاي|ذكية|لاسلكية|امنية|أمنية)|كاميرات\s*مراقبة|security\s*camera|surveillance\s*camera|ip\s*camera|\btapo\s*c\d+|\bc\d{3}ws\b|\btc\d{2}\b)',
     "كاميرا مراقبة ذكية", "Smart Security Camera",
     "كاميرا مراقبة ذكية بدقة تصوير عالية ورؤية ليلية واضحة، مع كشف ذكي للحركة وتنبيهات فورية على الموبايل لحماية المنزل والمكتب."),

    ("camera_photo", r'(?:كاميرا\s*(?:فورية|رقمية|تصوير|فوتوغرافية)|instax\s*mini|digital\s*camera|action\s*camera)',
     "كاميرا تصوير", "Instant & Digital Camera",
     "كاميرا تصوير عملية تلتقط صوراً ومقاطع عالية الوضوح بألوان غنية وتفاصيل دقيقة لتوثيق أجمل اللحظات بسهولة."),

    ("wireless_mic", r'(?:\bميكروفون\b|\bمايك\b|مايكروفون|\bmicrophone\b|lavalier\s*mic|\blark\s*m\d)',
     "ميكروفون احترافي", "Wireless & Studio Microphone",
     "ميكروفون عالي النقاء بعزل ذكي للضوضاء المحيطة، يمنحك تسجيلاً صوتياً واضحاً واحترافياً لتصوير الفيديوهات والبث والاجتماعات."),

    ("thermal_printer", r'(?:طابعة\s*(?:حرارية|ملصقات|محمولة|جيب|فورية|صغيرة)|mini\s*printer|thermal\s*printer|label\s*(?:maker|printer)|pocket\s*printer)',
     "طابعة حرارية محمولة", "Portable Thermal Label Printer",
     "طابعة حرارية ذكية تعمل بدون حبر عبر البلوتوث مع الموبايل مباشرة لطباعة الملصقات والملاحظات والصور بسرعة وسهولة."),

    ("office_printer", r'(?:\bطابعة\b|\bبرنتر\b|inkjet\s*printer|laser\s*printer|\bprinter\b)',
     "طابعة مكتبية", "Printer",
     "طابعة عملية عالية الدقة والسرعة لطباعة المستندات والملفات بجودة واضحة وتكلفة تشغيل اقتصادية للمنزل والمكتب."),

    ("mouse_pad", r'(?:ماوس\s*باد|بساط\s*(?:ماوس|فأرة|للفأرة)|لوحة\s*ماوس|mouse\s*pad|desk\s*mat)',
     "ماوس باد", "Gaming & Desk Mouse Pad",
     "ماوس باد بسطح ناعم عالي الدقة وقاعدة مطاطية ثابتة مضادة للانزلاق لتحكم سلس ومريح في الألعاب والعمل."),

    ("gaming_mouse", r'(?:ماوس\s*(?:ألعاب|العاب|جيمنج|للألعاب)|فأرة\s*(?:ألعاب|العاب)|gaming\s*mouse)',
     "ماوس ألعاب احترافي", "Gaming Mouse",
     "ماوس ألعاب احترافي بمستشعر فائق الدقة وسرعة استجابة فورية مع أزرار قابلة للبرمجة وتصميم مريح لليد لساعات اللعب الطويلة."),

    ("mouse", r'(?:\bماوس\b|\bفأرة\b|optical\s*mouse|wireless\s*mouse|\bmouse\b)',
     "ماوس كمبيوتر", "Wireless & Optical Mouse",
     "ماوس كمبيوتر عملي ومريح لليد باستجابة دقيقة وحركة انسيابية ناعمة لإنجاز المهام اليومية والعمل المكتبي بكفاءة."),

    ("gaming_keyboard", r'(?:كيبورد\s*(?:ألعاب|العاب|جيمنج|ميكانيك|ميكانيكي)|لوحة\s*مفاتيح\s*(?:ألعاب|العاب|ميكانيكية)|gaming\s*keyboard|mechanical\s*keyboard)',
     "كيبورد ألعاب ميكانيكي", "Mechanical Gaming Keyboard",
     "كيبورد ألعاب ميكانيكي بمفاتيح سريعة الاستجابة وإضاءة جذابة وهيكل متين يمنحك أفضل أداء في الألعاب والكتابة السريعة."),

    ("keyboard", r'(?:\bكيبورد\b|لوحة\s*مفاتيح|\bkeyboard\b)',
     "لوحة مفاتيح (كيبورد)", "Computer Keyboard",
     "لوحة مفاتيح مريحة وهادئة بأزرار متينة سريعة الاستجابة لتجربة كتابة سلسة ومريحة طوال اليوم."),

    ("usb_hub", r'(?:\bموزع\b|محول\s*متعدد\s*المنافذ|محور\s*usb|محول\s*usb\s*متعدد|usb(?:-?c)?\s*hub|type-?c\s*hub|\d+\s*-?\s*port\s*hub|\bhub\s*(?:lite|pro|\d)|docking\s*station|multi-?port\s*(?:hub|adapter))',
     "موزع منافذ USB-C متعدد", "Multi-Port USB-C Hub",
     "موزع منافذ متعدد عالي السرعة يوسّع مداخل اللابتوب والموبايل لتوصيل الشاشات والفلاشات والشحن السريع في وقت واحد."),

    ("phone_cooler", r'(?:مبرد\s*(?:موبايل|هاتف|جوال|مغناطيسي)|مروحة\s*تبريد\s*(?:للموبايل|للهاتف|موبايل)|mobile\s*(?:phone\s*)?cooler|phone\s*cooler|magnetic\s*cooler)',
     "مبرد موبايل للألعاب", "Magnetic Mobile Phone Cooler",
     "مبرد موبايل مغناطيسي قوي بتبريد فوري سريع يحافظ على برودة الهاتف وثبات الفريمات أثناء الألعاب الثقيلة."),

    ("laptop_cooler", r'(?:قاعدة\s*تبريد|مبرد\s*لابتوب|مروحة\s*تبريد\s*لابتوب|cooling\s*pad|laptop\s*cooler)',
     "قاعدة تبريد لابتوب", "Laptop Cooling Pad",
     "قاعدة تبريد للابتوب بمراوح قوية وهادئة تحافظ على حرارة الجهاز منخفضة أثناء الألعاب والعمل الثقيل مع زوايا ارتفاع مريحة."),

    ("laptop_bag", r'(?:شنطة\s*(?:ظهر\s*)?لابتوب|حقيبة\s*(?:ظهر\s*)?لابتوب|جراب\s*لابتوب|laptop\s*(?:bag|backpack|sleeve))',
     "حقيبة لابتوب", "Laptop Backpack & Bag",
     "حقيبة لابتوب مبطنة ومتينة مقاومة للصدمات والمياه، بجيوب منظمة لحمل اللابتوب والشاحن والملحقات بأمان وأناقة."),

    ("bag_organizer", r'(?:شنطة\s*(?:تنظيم|سفر|ظهر|يد|كتف|خصر|رياضية)|حقيبة\s*(?:تنظيم|تخزين|سفر|ظهر|يد|كتف|إلكترونيات)|organizer\s*(?:bag|pouch)|travel\s*(?:pouch|bag)|\bbackpack\b)',
     "حقيبة وشنطة تنظيم", "Organizer & Travel Bag",
     "حقيبة عملية مقسمة بذكاء من خامات متينة مقاومة للمياه لتنظيم وحفظ مقتنياتك وإلكترونياتك بترتيب وسهولة في السفر والتنقل."),

    ("protective_case", r'(?:\bجراب\b|\bكفر\b|غطاء\s*حماية|حافظة\s*(?:حماية|سيليكون)|جراب\s*حماية|protective\s*case|phone\s*case|silicone\s*(?:case|cover)|shockproof\s*case|magsafe\s*case)',
     "جراب وحافظة حماية", "Protective Case Cover",
     "جراب حماية متين مقاوم للصدمات والخدوش بحواف مرتفعة لحماية الجهاز والكاميرا مع ملمس مريح وتصميم أنيق."),

    ("screen_protector", r'(?:لاصقة\s*حماية|سكرين\s*بروتكتور|واقي\s*شاشة|حامي\s*شاشة|زجاج\s*مقوى|screen\s*protector|tempered\s*glass)',
     "لاصقة حماية شاشة زجاجية", "Tempered Glass Screen Protector",
     "لاصقة حماية زجاجية مقواة عالية الشفافية تحمي الشاشة من الخدوش والصدمات مع الحفاظ الكامل على حساسية اللمس."),

    ("watch_strap", r'(?:\bسوار\b|\bأستيك\b|\bاستيك\b|حزام\s*ساعة|watch\s*(?:band|strap)|replacement\s*(?:band|strap))',
     "سوار ساعة ذكية", "Smartwatch Band Strap",
     "سوار معصم مريح ومتين بخامات لطيفة على الجلد ومقاومة للتعرق، سهل التركيب وتعديل المقاس للاستخدام الرياضي واليومي."),

    ("power_strip", r'(?:مشترك\s*كهربائ?ي?|توصيل[ةه]\s*(?:كهربائية|كهرباء)|مشترك\s*(?:مضيئ|مضيء|ذكي|سلك|توصيل|بمنافذ|حماية|اي\s*لوك|آي\s*لوك|أيلوك|ايلوك|ilock|لدنيو|ldnio)|مشترك\b[^\n،,]{0,35}?\b(?:منافذ|مخارج|فيش|3500|2500)|وصلة\s*مشترك|power\s*strip|extension\s*(?:socket|cord|lead)|multi[\s\-]*socket|surge\s*protector)',
     "مشترك كهربائي", "Power Strip Extension",
     "مشترك كهربائي آمن ومتين بمنافذ متعددة وخامات مقاومة للحرارة مع حماية متكاملة للأجهزة من تذبذب التيار والماس الكهربائي."),

    ("plug_adapter", r'(?:محول\s*(?:قابس|فيش[ةه]?|ثلاثي|ثنائي|كهرباء|سفر\s*عالمي)|فيش[ةه]?\s*(?:مشترك|ثلاثي[ةه]?|ثنائي[ةه]?|ذكي[ةه]?|كهرباء|حائط|أيلوك|ايلوك|اي\s*لوك|آي\s*لوك|ilock|ldnio)|قابس\s*(?:كهربائي|ذكي|ثلاثي|حائط|محول)|plug\s*adapter|travel\s*adapter|socket\s*adapter|wall\s*(?:socket|outlet)\s*adapter|universal\s*adapter)',
     "محول وقابس كهربائي", "Electrical Plug & Socket Adapter",
     "محول وقابس كهربائي آمن ومتين من خامات مقاومة للحرارة لتوصيل الأجهزة بثبات وحماية تامة من زيادة التيار."),

    ("power_bank", r'(?:باور\s*بانك|ب[ا]?نك\s*الطاقة|شاحن\s*متنقل|بطارية\s*(?:متنقلة|احتياطية|محمولة|خارجية)|شاحن\s*محمول|power\s*bank|portable\s*(?:charger|power))',
     "باور بانك (شاحن متنقل)", "Portable Power Bank",
     "باور بانك بسعة شحن عملية وتقنيات شحن سريع آمنة لشحن الموبايل والأجهزة بكفاءة أثناء السفر والتنقل."),

    ("car_charger", r'(?:شاحن\s*سيار[ةه]|car\s*charger)',
     "شاحن سيارة سريع", "Fast Car Charger",
     "شاحن سيارة سريع متعدد المنافذ بتصميم مدمج يثبت بإحكام ويشحن هواتفك وأجهزتك بأمان وكفاءة عالية أثناء القيادة."),

    ("wireless_charger", r'(?:شاحن\s*لاسلكي|شاحن\s*مغناطيسي\s*لاسلكي|wireless\s*charger|magsafe\s*charger)',
     "شاحن لاسلكي سريع", "Magnetic Wireless Charger",
     "شاحن لاسلكي ذكي بتثبيت مغناطيسي مريح وشحن مستقر وآمن للأجهزة المتوافقة مع حماية من السخونة الزائدة."),

    ("laptop_charger", r'(?:شاحن\s*لابتوب|laptop\s*(?:charger|adapter)|ac\s*power\s*adapter\s*\d+w)',
     "شاحن لابتوب", "Laptop Power Adapter Charger",
     "شاحن لابتوب عالي الكفاءة بقدرة كهربائية مستقرة وحماية متكاملة ضد زيادة الجهد والحرارة لشحن آمن وسريع."),

    ("wall_charger", r'(?:شاحن\s*(?:[A-Za-z0-9\-]{1,10}\s+)?(?:حائط|جداري|سريع|عالي\s*السرعة|نانو|سفر|ذكي|موبايل|هاتف|منزلي|مكتبي|أصلي|اصلي|تايب\s*سي|usb-?c|pd|من\s+\w+|بمنفذ|بقوة|بقدرة|gan|\d{2,3}\s*(?:وات|واط|w\b))|راس\s*شاحن|رأس\s*شاحن|شاحن\s*r\d+|wall\s*charger|mains\s*charger|fast\s*charger|gan\s*(?:wall\s*)?charger|nano\s*charger|usb-?c\s*(?:wall\s*|fast\s*)?charger)',
     "شاحن سريع", "Fast Wall Charger",
     "شاحن حائط سريع يدعم تقنيات الشحن الذكي لتزويد هاتفك وأجهزتك بأعلى سرعة شحن آمنة مع حماية ضد السخونة."),

    ("ethernet_cable", r'(?:كابل\s*(?:إيثرنت|ايثرنت|انترنت|إنترنت|شبكة|لان|cat\s*[5678])|سلك\s*(?:نت|انترنت|إنترنت|شبكة|لان)|وصلة\s*(?:نت|انترنت|لان)|ethernet\s*(?:network\s*|patch\s*)?cable|\bcat\s*[5678][ae]?\b.*?\bcable\b|\brj45\b.*?\bcable\b|lan\s*cable)',
     "كابل إنترنت وشبكة Ethernet", "High-Speed Ethernet LAN Cable",
     "كابل شبكة إيثرنت عالي السرعة لنقل الإنترنت والبيانات بثبات فائق واستجابة فورية بدون تقطيع للألعاب والراوتر والكمبيوتر."),

    ("audio_cable", r'(?:كابل\s*(?:صوت|aux|ستيريو)|وصلة\s*(?:صوت|aux)|سلك\s*aux|aux\s*cable|audio\s*cable|3\.5\s*mm\s*.*?\bcable\b)',
     "كابل صوت AUX", "AUX Stereo Audio Cable",
     "كابل صوت AUX مضفر عالي النقاء لنقل الصوت بوضوح تام بدون تشويش بين الموبايل والسيارة والسماعات."),

    ("hdmi_cable", r'(?:كابل\s*hdmi|وصلة\s*hdmi|سلك\s*hdmi|hdmi\s*(?:2\.\d\s*)?cable)',
     "كابل عرض HDMI", "High-Speed HDMI Cable",
     "كابل HDMI فائق السرعة لنقل الصورة والصوت بدقة عالية وثبات تام بين الشاشات والريسيفر والكمبيوتر وأجهزة الألعاب."),

    ("charging_cable", r'(?:كابل\s*(?:شحن|شاحن|بيانات|تايب\s*سي|ماج|usb|type-?c|lightning|سريع|متعدد|مضفر|من\s+\w+|r\d+)|مجموعة\s*كابل|سلك\s*شحن|وصلة\s*شحن|(?:usb-?c?|type-?c|lightning|data(?:\s*transfer)?|charging)\s*(?:to\s*[\w\-]+\s*)?cable\b)',
     "كابل شحن ونقل بيانات", "Fast Charging & Data Cable",
     "كابل شحن ونقل بيانات متين ومضفر يدعم الشحن السريع ومقاوم للثني والقطع للاستخدام اليومي المكثف."),

    ("stand_holder", r'(?:حامل\s*(?:موبايل|هاتف|جوال|لابتوب|تابلت|شاشة|سيارة|مكتب|ثلاثي|ترايبود)|ستاند\s*(?:موبايل|هاتف|جوال|لابتوب|تابلت|مكتب|تصوير)|laptop\s*stand|phone\s*(?:stand|holder|mount)|car\s*(?:mount|holder)|tablet\s*stand|\btripod\b)',
     "حامل وستاند تثبيت", "Adjustable Stand Holder",
     "حامل تثبيت متين وقابل للتعديل بزوايا مريحة وثبات عالي لوضع الموبايل أو اللابتوب في مستوى النظر المريح."),

    ("storage_drive", r'(?:\bهارد\s*(?:ssd|خارجي|محمول|داخلي|ميكانيكي|صلب)?\b|\bssd\b|\bnvme\b|\bhdd\b|قرص\s*(?:صلب|تخزين)|وحدة\s*تخزين\s*(?:خارجية|محمولة|داخلية|ssd)|ذاكرة\s*فلاشية|\bفلاش[ةه]\b|فلاش\s*درايف|كارت\s*ميموري|بطاقة\s*ذاكرة|external\s*ssd|portable\s*ssd|internal\s*ssd|solid\s*state\s*drive|external\s*hard\s*drive|\bhard\s*drive\b|\bflash\s*drive\b|\bthumb\s*drive\b|\busb\s*drive\b|\bmemory\s*card\b|\bmicrosd\b|\bsd\s*card\b)',
     "هارد SSD محمول", "External Portable SSD Storage",
     "وحدة تخزين ونقل بيانات فائقة السرعة بتصميم مدمج وعملي لحفظ الملفات والنسخ الاحتياطي بأمان وكفاءة."),

    ("laptop", r'(?:\bلابتوب\b|لاب\s*توب|حاسوب\s*محمول|كمبيوتر\s*محمول|\blaptop\b|\bnotebook\b|\bvivobook\b|\bzenbook\b|\bideapad\b|\bthinkpad\b|\bthinkbook\b|\blegion\b|\bmacbook\b|\bloqs?\b|\btuf\s*gaming\b)',
     "لابتوب", "Laptop",
     "لابتوب قوي الأداء يجمع بين سرعة المعالجة والشاشة المريحة والبطارية الاعتمادية لإنجاز الدراسة والعمل والألعاب بكفاءة."),

    ("tablet", r'(?:\bتابلت\b|جهاز\s*لوحي|\bآيباد\b|\bايباد\b|\bipad\b|\btablet\b|galaxy\s*tab\b|redmi\s*pad\b|matepad\b|honor\s*pad\b)',
     "تابلت ذكي", "Smart Tablet",
     "تابلت ذكي بشاشة واسعة عالية الوضوح وأداء سلس للدراسة والترفيه وتصفح التطبيقات مع بطارية تدوم طوال اليوم."),

    ("smartwatch", r'(?:ساعة\s*[^\n،,]{0,25}?\b(?:ذكية|الذكية|سمارت)\b|ساعة\s*(?:ريدمي|شاومي|أبل|ابل|سامسونج|جالكسي|هواوي|هونر|أورايمو|اورايمو|هاينو|تتبع|رياضية)|سوار\s*ذكي|جهاز\s*قابل\s*للارتداء\s*لتتبع|متتبع\s*(?:اللياقة|الصحة|النشاط)|ووتش\s*\d|smart\s*watch|\bsmartwatch\b|fitness\s*tracker|smart\s*band|redmi\s*watch|apple\s*watch|galaxy\s*watch|huawei\s*(?:watch|band)|\bmi\s*band\s*\d+|\bt800\b.*?\b(?:ساعة|watch)\b)',
     "ساعة وسوار تتبع ذكي", "Smartwatch & Fitness Tracker",
     "ساعة ذكية أنيقة بشاشة واضحة لمتابعة الإشعارات والمكالمات والنشاط الرياضي ونبضات القلب مع بطارية طويلة العمر."),

    ("wristwatch", r'(?:ساعة\s*(?:يد|رجالي|رجالية|حريمي|نسائية|كوارتز|كلاسيك|أنالوج|انالوج|كاسيو|نافيفورس)|casio\s*.*?\bwatch\b|quartz\s*watch|analog\s*watch|chronograph\s*watch)',
     "ساعة يد أنيقة", "Wristwatch",
     "ساعة يد أنيقة بتصميم عصري وخامات متينة مقاومة للخدش تمنحك مظهراً راقياً ودقة عالية في التوقيت."),

    ("gaming_monitor", r'(?:شاشة\s*(?:ألعاب|العاب|كمبيوتر|منحنية|جيمنج)|شاشة\s*[^\n،,]{0,25}?\b(?:22|24|27|32|34)\s*(?:بوصة|انش|إنش|inch)|gaming\s*monitor|curved\s*monitor|\b\d{2}\s*(?:انش|بوصة|inch)\s*\d{2,3}\s*hz\b|\bmonitor\b)',
     "شاشة كمبيوتر وألعاب", "Gaming & PC Monitor",
     "شاشة عرض عالية الدقة بمعدل تحديث سريع وألوان غنية وزوايا رؤية واسعة لتجربة ألعاب وعمل احترافية مريحة للعين."),

    ("smart_tv", r'(?:\bتلفزيون\b|\bتلفاز\b|شاشة\s*(?:تلفزيون|سمارت|ذكية\s*\d{2}|عرض\s*ذكية)|smart\s*(?:led\s*|4k\s*|uhd\s*|vidaa\s*|google\s*|android\s*)?tv|qled\s*tv|oled\s*tv|uhd\s*tv|google\s*tv|vidaa\s*tv|android\s*tv\s*\d{2})',
     "شاشة تلفزيون ذكية", "Smart TV",
     "شاشة تلفزيون ذكية بدقة فائقة وألوان نابضة بالحياة مع نظام ذكي مدمج لتشغيل تطبيقات المشاهدة وصوت نقي غامر."),

    ("smartphone", r'(?:\bموبايل\b|هاتف\s*(?:ذكي|محمول)|\bجوال\b|\bsmartphone\b|\b(?:iphone|آيفون|ايفون)\s*1\d\b|(?:جالكسي|جالاكسي|galaxy)\s*(?:s\d{1,2}|a\d{2}|m\d{2}|z\s*(?:fold|flip))\b|(?:redmi\s*note|ريدمي\s*نوت)\s*\d+\b|(?:ثنائي\s*الشريحة|dual\s*sim).*?\b(?:4g|5g|جيجابايت|\d+gb)\b|موبايل\s*(?:سامسونج|شاومي|أبل|ابل|ريلمي|أوبو|اوبو|إنفينيكس|انفينكس|هونر|فيفو))',
     "موبايل ذكي", "Smartphone",
     "هاتف ذكي متكامل بمعالج قوي وشاشة سريعة الوضوح وكاميرات عالية الدقة مع بطارية كبيرة تدعم الشحن السريع."),

    ("gaming_headset", r'(?:سماعات?\s*(?:رأس\s*)?(?:ألعاب|العاب|الألعاب|للألعاب|جيمنج)|سماعة\s*رأس\s*.*?\bللألعاب\b|gaming\s*headset)',
     "سماعة رأس للألعاب", "Gaming Headset",
     "سماعة رأس احترافية للألعاب بصوت محيطي دقيق لتحديد الاتجاهات وميكروفون نقي للتواصل ووسائد أذن مريحة جداً."),

    ("headphones", r'(?:سماعات?\s*(?:رأس|راس)|فوق\s*الأذن|على\s*الأذن|over-?ear\s*headphones|on-?ear\s*headphones|wireless\s*headphones|\bheadphones\b|\bheadset\b)',
     "سماعة رأس", "Over-Ear Headphones",
     "سماعة رأس مريحة بصوت غني وواضح وعزل ممتاز للضوضاء مع وسائد ناعمة للاستماع المريح لفترات طويلة."),

    ("wired_earphones", r'(?:سماعات?\s*(?:أذن\s*|اذن\s*)?\bسلكية\b|wired\s*(?:in-?ear\s*)?(?:earphones|earbuds))',
     "سماعة أذن سلكية", "Wired In-Ear Earphones",
     "سماعة أذن سلكية بصوت نقي وباس متوازن وميكروفون مدمج للمكالمات الواضحة مع سلك متين وتصميم مريح للأذن."),

    ("earbuds", r'(?:سماعات?\s*(?:أذن|اذن|بلوتوث|لاسلكية|ايربودز?|إيربودز?)|داخل\s*الأذن|in-?ear\s*(?:earphones|earbuds|headphones|wireless)|earbuds|airpods|true\s*wireless|\btws\b|freeclips|spacebuds|freebuds|\b(?:r50i|p20i|p30i|p40i|k20i|a20i|a30i|v20i|c30i|c40i)\b|liberty\s*(?:buds|\d)|wave\s*(?:beam|buds|flex))',
     "سماعة أذن لاسلكية", "True Wireless Earbuds",
     "سماعة أذن لاسلكية بصوت نقي غني بالباس وميكروفون واضح للمكالمات مع بطارية تدوم طويلاً وعلبة شحن مدمجة."),

    ("soundbar", r'(?:ساوند\s*بار|\bsoundbar\b|sound\s*bar)',
     "مكبر صوت ساوند بار", "Soundbar Speaker",
     "ساوند بار قوي يمنحك تجربة صوت سينمائي محيطي واضح وعميق للتلفزيون والأفلام والألعاب مع توصيل لاسلكي وسلكي سهل."),

    ("speaker", r'(?:مكبر\s*صوت|صب\s*بلوتوث|\bسبيكر\b|bluetooth\s*speaker|portable\s*speaker|wireless\s*speaker|party\s*speaker|\bspeaker\b)',
     "مكبر صوت بلوتوث", "Bluetooth Speaker",
     "مكبر صوت محمول بصوت قوي ونقي وباس عميق مع اتصال بلوتوث سريع وبطارية ممتازة للاستخدام في المنزل والرحلات."),

    ("pc_cooler", r'(?:مروحة\s*(?:كيسة|كمبيوتر|معالج|بروسيسور|تبريد\s*(?:كمبيوتر|معالج|كيسة|مائي))|مراوح\s*(?:كيسة|تبريد\s*كمبيوتر|argb|rgb)|تبريد\s*مائي\s*(?:للمعالج|للكمبيوتر)|cpu\s*(?:cooler|fan|liquid\s*cooler)|case\s*fan|pc\s*(?:cooling\s*)?fan|\bargb\b[^\n]{0,35}?\b(?:120\s*mm|140\s*mm|pwm|fan)\b|\bpwm\b[^\n]{0,25}?\bfan\b|aio\s*liquid\s*cooler)',
     "مروحة وتبريد كمبيوتر احترافي", "PC Case & CPU Cooling Fan",
     "مروحة وتبريد احترافي للكمبيوتر بتدفق هواء قوي وتشغيل هادئ مع إضاءة جذابة للحفاظ على برودة المعالج والكيسة تحت الضغط."),

    ("stand_fan", r'(?:مروحة\s*(?:ستاند|عمود|عمودية|أرضية)|stand\s*fan|pedestal\s*fan)',
     "مروحة ستاند عمودية", "Stand Pedestal Fan",
     "مروحة ستاند قوية بتدفق هواء منعش وسرعات متعددة مع توزيع تلقائي للهواء وتشغيل هادئ وموفر للطاقة."),

    ("fan", r'(?:مروحة\s*(?:سقف|حائط|مكتب|بوكس|صندوق|تبريد|يد|محمولة)|\bمروحة\b|ceiling\s*fan|wall\s*fan|desk\s*fan|\bfan\b)',
     "مروحة تهوية وتبريد", "Cooling Fan",
     "مروحة تهوية عملية بتدفق هواء قوي وهادئ وتصميم متين لتلطيف الأجواء بكفاءة عالية."),

    ("air_conditioner", r'(?:\bتكييف\b|مكيف\s*(?:هواء|سبليت|صحراوي)|air\s*conditioner|air\s*cooler)',
     "جهاز تكييف وتبريد", "Air Conditioner",
     "جهاز تكييف وتبريد عالي الكفاءة لتبريد سريع ومثالي للغرفة مع توزيع متوازن للهواء وتوفير في استهلاك الكهرباء."),

    ("appliance_stand", r'(?:قاعدة\s*(?:متحركة\s*|حمل\s*|تثبيت\s*)?(?:للغسالة|غسالة|ثلاجة|للثلاجة|بوتاجاز|أجهزة)|حامل\s*(?:غسالة|ثلاجة|بوتاجاز)|washing\s*machine\s*(?:stand|base)|appliance\s*(?:roller|stand|base))',
     "قاعدة تثبيت وحمل للأجهزة المنزلية", "Heavy-Duty Appliance Base Stand",
     "قاعدة معدنية متينة وقابلة للتعديل لحمل وتثبيت الغسالة والثلاجة وحمايتها من الرطوبة والاهتزاز وسهولة التحريك والتنظيف."),

    ("washing_machine", r'(?:\bغسالة\b|غساله\s*(?:ملابس|أطباق|صحون|فوق|تحميل)|washing\s*machine|dishwasher)',
     "غسالة أوتوماتيك", "Washing Machine",
     "غسالة عالية الكفاءة ببرامج غسيل ذكية متعددة تنظف بعمق مع الحفاظ على الأقمشة وتوفير المياه والكهرباء."),

    ("refrigerator", r'(?:\bثلاجة\b|ديب\s*فريزر|\bفريزر\b|\brefrigerator\b|\bfreezer\b|mini\s*bar)',
     "ثلاجة وفريزر", "Refrigerator & Freezer",
     "ثلاجة بتبريد سريع ومتوزع يحفظ الأطعمة طازجة لأطول فترة مع تقسيم داخلي واسع واستهلاك اقتصادي للكهرباء."),

    ("microwave", r'(?:\bميكروويف\b|\bمايكروويف\b|فرن\s*كهربائي|\bmicrowave\b|electric\s*oven)',
     "فرن وميكروويف كهربائي", "Microwave & Electric Oven",
     "ميكروويف وفرن عملي للتسخين والطهي السريع المتساوي مع مستويات طاقة متعددة ولوحة تحكم سهلة الاستخدام."),

    ("air_fryer", r'(?:قلاية\s*(?:هوائية|بدون\s*زيت|كهربائية)|اير\s*فراير|إير\s*فراير|air\s*fryer)',
     "قلاية هوائية بدون زيت", "Air Fryer",
     "قلاية هوائية صحية لتحضير الأطعمة المقرمشة اللذيذة بأقل نقطة زيت أو بدون زيت مع سلة غير لاصقة سهلة التنظيف."),

    ("stand_mixer", r'(?:\bعجان\b|ستاند\s*مكسر|عجانة|stand\s*mixer)',
     "عجان كهربائي", "Electric Stand Mixer",
     "عجان كهربائي قوي بوعاء واسع وسرعات متعددة لعجن المخبوزات وخفق الكريمة والحلويات بكفاءة وثبات عالي."),

    ("milk_frother", r'(?:رغوة\s*الحليب|خفق\s*(?:اللبن|الحليب)|صنع\s*الرغوة|milk\s*frother)',
     "جهاز خفق الحليب وصنع الرغوة", "Electric Milk Frother",
     "جهاز خفق حليب عملي وسريع يمنحك رغوة كريمية غنية لتحضير الكابتشينو واللاتيه والقهوة المثلجة في ثوانٍ."),

    ("hand_mixer", r'(?:مضرب\s*(?:بيض|يدوي\s*كهربائي)|hand\s*mixer)',
     "مضرب بيض كهربائي", "Electric Hand Mixer",
     "مضرب كهربائي خفيف وقوي بسرعات متعددة لخفق البيض والكريمة وخليط الكيك بسرعة وسهولة."),

    ("blender", r'(?:\bخلاط\b|هاند\s*بلندر|خلاط\s*يدوي|\bblender\b)',
     "خلاط كهربائي", "Electric Blender",
     "خلاط كهربائي بمحرك قوي وشفرات ستانلس ستيل حادة لخلط العصائر والسموذي والمكونات الصلبة بنعومة فائقة."),

    ("juicer", r'(?:\bعصارة\b|عصاره\s*(?:فواكه|حمضيات|برتقال)|citrus\s*juicer|\bjuicer\b)',
     "عصارة فواكه وحمضيات كهربائية", "Electric Citrus & Fruit Juicer",
     "عصارة كهربائية عملية تستخلص أقصى كمية من العصير الطازج بسرعة وسهولة مع أجزاء قابلة للفك والتنظيف السريع."),

    ("food_chopper", r'(?:\bمفرمة\b|\bكبة\b|محضر(?:ة)?\s*طعام|قطاعة\s*(?:خضروات|طعام)|\bchopper\b|food\s*processor|meat\s*grinder)',
     "كبة ومفرمة كهربائية", "Electric Food Chopper",
     "كبة ومفرمة قوية بشفرات حادة من الستانلس ستيل لفرم اللحوم وتقطيع الخضروات والمكسرات في ثوانٍ معدودة."),

    ("coffee_maker", r'(?:ماكينة\s*(?:تحضير\s*|صنع\s*)?(?:ال)?(?:قهوة|إسبريسو|اسبريسو|كابتشينو)|صانعة\s*(?:ال)?قهوة|كنكة\s*قهوة\s*كهربائية|coffee\s*(?:maker|machine)|espresso\s*machine|turkish\s*coffee\s*maker)',
     "ماكينة تحضير قهوة", "Coffee & Espresso Machine",
     "ماكينة تحضير قهوة سريعة وعملية تمنحك قهوة غنية المذاق برغوة مثالية وقوام مضبوط بضغطة زر واحدة."),

    ("kettle", r'(?:\bغلاية\b|\bكاتل\b|electric\s*kettle|water\s*kettle|\bkettle\b)',
     "غلاية مياه كهربائية", "Electric Water Kettle",
     "غلاية مياه كهربائية سريعة الغليان بعنصر تسخين ستانلس ستيل آمن وفصل تلقائي عند الغليان وجفاف المياه."),

    ("water_heater", r'(?:سخان\s*(?:مياه\s*)?(?:غاز|كهربائي|كهرباء|فوري|ديجيتال|مركزي|أتوماتيك|اتوماتيك|بدون\s*مدخنة|بمدخنة|تورنيدو|فريش|أوليمبيك|اوليمبيك|اريستون|أريستون|زانوسي)?|gas\s*water\s*heater|electric\s*water\s*heater|instant\s*water\s*heater|tankless\s*water\s*heater|water\s*heater)',
     "سخان مياه", "Water Heater",
     "سخان مياه عملي وآمن بتقنيات تسخين متطورة وموفرة للطاقة مع أنظمة حماية متكاملة لتدفئة فورية ومستقرة للمياه."),

    ("steam_cleaner", r'(?:منظف\s*[\u200b\s]*بخاري?|جهاز\s*تنظيف\s*بالبخار|ممسحة\s*بخار|steam\s*cleaner|steam\s*mop)',
     "جهاز تنظيف بالبخار", "Handheld Steam Cleaner",
     "جهاز تنظيف بالبخار المضغوط عالي الحرارة لإذابة الدهون العنيدة وتعقيم الأسطح والمطابخ والمفروشات بدون كيماويات."),

    ("drying_rack", r'(?:منشر\s*(?:غسيل|ملابس|داخلي|معدني|قابل\s*للطي)?|رف\s*تجفيف(?:\s*ملابس)?|حامل\s*تجفيف\s*(?:ملابس|غسيل)|مجفف\s*ملابس\s*قابل\s*للطي|clothes\s*(?:drying\s*rack|airer|horse)|drying\s*rack|laundry\s*(?:drying\s*)?rack)',
     "منشر وحامل تجفيف ملابس", "Foldable Clothes Drying Rack",
     "منشر وحامل تجفيف ملابس متين وقابل للطي بعدة مستويات يوفر مساحة واسعة لتجفيف الملابس في المنزل والبلكونة بسهولة."),

    ("ironing_board", r'(?:طاولة\s*(?:كي|مكواة|كوي)|ترابيزة\s*(?:مكواة|كي|كوي)|لوح\s*كي|ironing\s*board)',
     "طاولة كي ملابس قابلة للطي", "Foldable Ironing Board",
     "طاولة كي عملية ومبطنة بطبقة مقاومة للحرارة مع أرجل معدنية ثابتة وقابلة للطي لتوفير المساحة وسهولة الاستخدام."),

    ("steam_iron", r'(?:\bمكواة\b|\bكواية\b|مكواة\s*بخار|بخار\s*عمودية\s*للملابس|(?:steam|dry|travel|cordless|clothes|garment)\s*iron\b|garment\s*steamer)',
     "مكواة بخار للملابس", "Steam Iron & Garment Steamer",
     "مكواة بخار قوية تنزلق بسلاسة لإزالة التجاعيد الصعبة بسرعة وأمان على جميع أنواع الأقمشة."),

    ("vacuum", r'(?:\bمكنسة\b|مكنسه\s*كهربائية|vacuum\s*cleaner|robot\s*vacuum)',
     "مكنسة كهربائية", "Vacuum Cleaner",
     "مكنسة كهربائية بقوة شفط عالية لتنظيف السجاد والأرضيات والأركان بعمق مع فلاتر تنقية فعالة للغبار."),

    ("water_filter", r'(?:فلتر\s*مياه|شمعة\s*فلتر|شمعات\s*فلتر|water\s*(?:filter|purifier))',
     "فلتر تنقية مياه", "Water Filter & Cartridges",
     "فلتر مياه عالي الكفاءة لتنقية مياه الشرب من الشوائب والكلور والروائح والحصول على مياه نقية وصحية."),

    ("cookware", r'(?:طقم\s*(?:أواني|اواني|حلل|طهي|توزيع)|مقلاة|طاسة\s*قلي|حلة\s*(?:ضغط|طهي)|سلة\s*مقلاة|صينية\s*فرن|\bcookware\b|frying\s*pan|pressure\s*cooker|\bsaucepan\b)',
     "أواني ومقلاة طهي", "Cookware Pots & Pans",
     "أواني طهي متينة بتوزيع حراري متساوٍ وطبقة عالية الجودة مقاومة للالتصاق لطهي صحي وتنظيف سهل."),

    ("shaver_blade", r'(?:شفرات?\s*(?:حلاقة|ون\s*بليد|بديلة)|ماكينة\s*حلاقة\s*(?:يدوية|فينوس|جيليت|دوركو)|oneblade|replacement\s*blade|razor\s*blades|\brazors?\b)',
     "شفرات وماكينة حلاقة", "Razor & Replacement Blades",
     "شفرات حلاقة حادة ولطيفة على البشرة تمنحك حلاقة ناعمة ودقيقة بدون تهيج مع عمر استخدام طويل."),

    ("shaver", r'(?:ماكينة\s*(?:حلاقة|تشذيب|إزالة\s*الشعر|قص\s*الشعر)|hair\s*(?:clipper|trimmer)|beard\s*trimmer|electric\s*shaver|\bshaver\b|\bclipper\b|\btrimmer\b)',
     "ماكينة حلاقة وتشذيب كهربائية", "Electric Hair Clipper & Shaver",
     "ماكينة حلاقة وتشذيب دقيقة بشفرات حادة آمنة على البشرة وبطارية قابلة للشحن لتحديد وحلاقة سهلة في أي وقت."),

    ("hair_styler", r'(?:مكواة\s*شعر|بيبي\s*ليس|فرشاة\s*(?:شعر\s*)?حرارية|مجفف\s*شعر|\bسشوار\b|\bاستشوار\b|بخاخ\s*بخار\s*نانو.*?\bشعر\b|hair\s*(?:dryer|straightener|curler|styler))',
     "مصفف ومجفف شعر", "Hair Dryer & Straightener",
     "جهاز تصفيف وتجفيف شعر احترافي بتوزيع حراري متوازن يمنح الشعر نعومة ولمعاناً طبيعياً مع حماية من التلف."),

    ("scale", r'(?:\bميزان\b|bathroom\s*scale|kitchen\s*scale|smart\s*scale|body\s*(?:fat\s*)?scale)',
     "ميزان رقمي", "Digital Smart Scale",
     "ميزان رقمي عالي الدقة بشاشة واضحة وحساسات قياس دقيقة وتصميم متين وأنيق للاستخدام اليومي."),

    ("blood_pressure", r'(?:قياس\s*ضغط\s*الدم|جهاز\s*(?:ضغط|قياس\s*السكر|نبض|استنشاق|نيبولايزر)|blood\s*pressure|glucometer|nebulizer|oximeter)',
     "جهاز طبي منزلي", "Home Medical Monitor",
     "جهاز قياس طبي دقيق وسهل الاستخدام في المنزل بشاشة رقمية واضحة لمتابعة المؤشرات الصحية باطمئنان."),

    ("lantern", r'(?:\bفانوس\b|\bكشاف\b|مصباح\s*(?:طوارئ|يدوي|تخييم|رحلات|قابل\s*لإعادة\s*الشحن)|\blantern\b|\bflashlight\b|camping\s*light)',
     "كشاف وفانوس إضاءة LED", "Rechargeable LED Lantern & Flashlight",
     "كشاف وفانوس إضاءة LED قوي ببطارية قابلة لإعادة الشحن وإضاءة ساطعة موفرة للطاقة للطوارئ والرحلات والمنزل."),

    ("tools", r'(?:طقم\s*(?:مفكات|عدد|أدوات|مفاتيح)|مفك\s*(?:كهربائي|براغي)|\bشنيور\b|\bمثقاب\b|\bصاروخ\b|\bكماش[ةه]\b|\bزرادية\b|\bبنز\b|قاطع\s*(?:أسلاك|اسلاك|كابلات)|قطاعة\s*(?:أسلاك|اسلاك)|تعرية\s*(?:الأسلاك|الاسلاك)|شفرات\s*قطع|مفتاح\s*(?:ربط|إنجليزي|فرنساوي)|منظف\s*(?:إلكترونيات|الكترونيات)|رافعة\s*هيدروليكي|خرطوم\s*تمدد|ماجيك\s*هوز|screwdriver|power\s*drill|tool\s*set|hydraulic\s*jack|\bpliers\b|wire\s*(?:cutter|stripper)|cutting\s*blades|\bwrench\b|contact\s*cleaner)',
     "عدد وأدوات صيانة", "Hardware Tools & Equipment",
     "أدوات ومعدات صيانة عالية الصلابة والاعتمادية مصممة لإنجاز أعمال التركيب والصيانة المنزلية والإلكترونية بسهولة."),

    ("safe_box", r'(?:\bخزنة\b|خزنه\s*(?:رقمية|حديدية|مصفحة)|safe\s*box|digital\s*safe|security\s*safe)',
     "خزنة رقمية مصفحة", "Digital Security Safe Box",
     "خزنة أمان فولاذية متينة بقفل رقمي ذكي ومفاتيح طوارئ لحفظ الأموال والمستندات والمقتنيات الثمينة بأمان تام."),

    ("calculator", r'(?:آلة\s*حاسبة|الة\s*حاسبة|scientific\s*calculator|\bcalculator\b)',
     "آلة حاسبة علمية", "Scientific Calculator",
     "آلة حاسبة علمية أصلية بشاشة واضحة ووظائف حسابية وهندسية متكاملة مثالية لطلاب المدارس والجامعات والمحاسبين."),

    ("stationery", r'(?:قلم\s*(?:حبر|جاف|رصاص|تحديد|ماركر|سبورة|ملون|جل)|أقلام\s*(?:حبر|جاف|رصاص|تلوين|تحديد|ماركر|جل)|علبة\s*أقلام|دفتر\s*(?:ملاحظات|سلك|محاضرات)|كشكول|كراسة|ورق\s*تصوير\s*a4|أدوات\s*مكتبية|دباسة\s*ورق|ballpoint\s*pens?|\bpens?\s*(?:pack|box|set)\b|gel\s*pens?|highlighters?|permanent\s*markers?|pencil\s*(?:case|set)|notebook\s*a[45]|a4\s*copy\s*paper|\bstationery\b)',
     "أقلام وأدوات مكتبية ومدرسية", "Pens & Office Stationery",
     "أقلام وأدوات مكتبية عالية الجودة بخط انسيابي واضح وتصميم مريح للكتابة اليومية في الدراسة والعمل."),

    ("books", r'(?:(?<!فيليب\s)\bكتاب\b(?!\s*فيليب)|\bرواية\b|مجموعة\s*قصصية|قصص\s*أطفال|موسوعة|\bpaperback\b|\bhardcover\b)',
     "كتاب وقراءة", "Book",
     "كتاب مميز بطباعة واضحة ومحتوى ثري ومفيد للقراءة والمعرفة."),

    ("storage_organizer", r'(?:منظم\s*(?:أدراج|ادراج|مكتب|مكياج|ملابس|أحذية|احذية|خزانة|دولاب|مطبخ|ثلاجة|حمام|سيارة|أسلاك|كابلات|متعدد)|اورجانيزر|أورجانيزر|صندوق\s*(?:تخزين|تنظيم)|سلة\s*(?:تخزين|غسيل|ملابس|مهملات|قمامة)|علاقة\s*(?:ملابس|مفاتيح|حائط)|شماعة\s*ملابس|حامل\s*(?:أحذية|مناديل|تنظيم|توابل|أطباق)|رف\s*(?:تخزين|تنظيم|حمام|مطبخ|أحذية)|storage\s*(?:box|basket|organizer|rack|bin)|drawer\s*organizer|desk\s*organizer|laundry\s*basket|shoe\s*rack|trash\s*(?:can|bin))',
     "منظم ووحدة تخزين وترتيب", "Home & Desk Storage Organizer",
     "وحدة تنظيم وتخزين عملية ومتينة تساعدك على ترتيب الأغراض واستغلال المساحات في المنزل والمكتب بشكل أنيق."),

    ("baby_chair", r'(?:كرسي\s*(?:مرتفع\s*|طعام\s*|سيارة\s*)?للأطفال|عربة\s*أطفال|مشاية\s*أطفال|سرير\s*أطفال|high\s*chair|baby\s*(?:stroller|walker|car\s*seat))',
     "كرسي ومستلزمات أطفال", "Baby High Chair & Gear",
     "كرسي أطفال مريح وآمن بخامات متينة سهلة التنظيف وأحزمة تثبيت لحماية الطفل وراحته أثناء الطعام والجلوس."),

    ("cushion_chair", r'(?:مسند\s*(?:ظهر|الظهر|طبي)|وسادة\s*(?:ظهر|مقعد|جلوس|طبية)|مخدة\s*طبية|back\s*support\s*cushion|seat\s*cushion|lumbar\s*support)',
     "وسادة ومسند ظهر طبي", "Orthopedic Back & Seat Cushion",
     "وسادة ومقعد دعم طبي مصمم لتخفيف الضغط عن أسفل الظهر والعمود الفقري، مثالي لكرسي المكتب والسيارة والمنزل."),

    ("bedding", r'(?:كيس\s*وساد[ةه]|ملاية\s*سرير|طقم\s*(?:ملايات|سرير)|لحاف|\bمفرش\b|\bبطانية\b|\bفوطة\b|\bبشكير\b|pillowcase|bed\s*sheet|comforter|blanket)',
     "مفروشات ومنسوجات منزلية", "Home Bedding & Pillowcase",
     "مفروشات منزلية بخامات ناعمة عالية الجودة ومريحة للبشرة تمنحك نوماً هادئاً ومظهراً أنيقاً لغرفة النوم."),

    ("weights_fitness", r'(?:طقم\s*أوزان|رفع\s*الأثقال|\bدامبل\b|\bدمبل\b|مشاية\s*(?:رياضية|كهربائية)|جهاز\s*مشي|حبل\s*قفز|أثقال|dumbbell|barbell|walking\s*pad|treadmill)',
     "أدوات اللياقة والأوزان الرياضية", "Fitness Weights & Gym Equipment",
     "معدات لياقة وتدريب منزلي متينة وقابلة للتعديل لبناء القوة البدنية وممارسة التمارين الرياضية اليومية بكفاءة."),

    ("shoes", r'(?:\bحذاء\b|\bأحذية\b|\bاحذية\b|\bكوتشي\b|\bصندل\b|\bصنادل\b|\bشبشب\b|\bsneakers\b|\bshoes\b|\bsandals\b|running\s*shoes)',
     "حذاء مريح", "Sneakers & Footwear",
     "حذاء أنيق ومريح بنعل مرن يمتص الصدمات وخامات خفيفة تسمح بتهوية القدم لراحة مثالية في المشي والاستخدام اليومي."),

    ("clothing", r'(?:\bتيشيرت\b|\bقميص\b|\bبنطلون\b|\bبوكسر\b|\bجاكيت\b|\bترنج\b|\bسوت\b|\bفستان\b|\bبيجام[ةه]\b|\bشورت\b|\bجوارب\b|\bشراب\b|طقم\s*(?:قصة|بوكسر|داخلي)|(?<!تجفيف\s)(?<!منشر\s)(?<!سلة\s)(?<!منظم\s)(?<!علاقة\s)(?<!شماعة\s)طقم\s*ملابس|t-?shirt|hoodie|jacket|boxer\s*briefs|pajama\s*set)',
     "ملابس وأزياء", "Apparel & Clothing",
     "ملابس بخامات قطنية ناعمة ومريحة وقصة عملية متقنة تحافظ على رونقها وألوانها مع الغسيل والاستخدام اليومي."),

    ("perfume", r'(?:(?<!ب)\bعطر\b|\bبرفان\b|بودي\s*(?:سبلاش|ميست)|بخاخ\s*(?:للجسم|بودي)|مزيل\s*(?:عرق|للعرق)|سبراي\s*مزيل|eau\s*de\s*(?:parfum|toilette)|body\s*(?:splash|mist|spray)|\bdeodorant\b)',
     "عطر وبخاخ للجسم", "Perfume & Body Fragrance",
     "عطر وبخاخ منعش برائحة جذابة وثبات مميز يمنحك انتعاشاً وثقة طوال اليوم."),

    ("oral_care", r'(?:معجون\s*أسنان|فرشاة\s*أسنان|غسول\s*فم|خيط\s*أسنان|toothpaste|toothbrush|mouthwash)',
     "عناية بالأسنان والفم", "Toothpaste & Oral Care",
     "منتج عناية يومية بالفم والأسنان لتنظيف فعال وحماية اللثة والأسنان مع نفس منعش يدوم طويلاً."),

    ("hair_care", r'(?:\bشامبو\b|\bبلسم\b|حمام\s*كريم|ماسك\s*شعر|زيت\s*(?:شعر|للشعر)|سيروم\s*(?:شعر|للشعر)|كريم\s*(?:شعر|تصفيف)|\bshampoo\b|\bconditioner\b|hair\s*(?:mask|serum|oil))',
     "شامبو وعناية بالشعر", "Hair Care Shampoo & Treatment",
     "تركيبة مغذية للعناية بالشعر وتنظيف فروة الرأس بلطف لتقوية الشعر ومنحه نعومة ولمعاناً صحياً."),

    ("skin_care", r'(?:غسول\s*(?:وجه|للوجه|بشرة|لليدين|يدين|يد|جسم|للجسم)|صابون\s*(?:لليدين|يدين|يد|سائل|استحمام|وجه|طبي|مرطب)|رغوة\s*(?:استحمام|للوجه|تنظيف)|جل\s*هيدرو|لتنظيف\s*الوجه|كريم\s*(?:مرطب|للوجه|لليدين|بشرة)|لوشن\s*مرطب|واقي\s*شمس|صن\s*بلوك|سيروم\s*(?:للوجه|فيتامين|هيالورونيك)|جل\s*استحمام|شاور\s*جل|ماء\s*ميسيلار|مرطب\s*شفاه|hand\s*wash|liquid\s*(?:hand\s*)?soap|shower\s*(?:gel|foam)|bath\s*foam|cleanser|face\s*wash|moisturizer|sunscreen|body\s*wash|micellar\s*water|\bserum\b)',
     "عناية بالبشرة والجسم", "Skincare & Hand/Body Wash",
     "منتج عناية لطيف وفعال ينظف ويرطب البشرة بعمق ليمنحها نضارة ونعومة وحماية يومية متكاملة."),

    ("diapers", r'(?:\bحفاضات\b|\bحفاضة\b|بامبرز\s*أطفال|مناديل\s*مبللة\s*للأطفال|\bdiapers\b|baby\s*wipes)',
     "حفاضات أطفال", "Baby Diapers Pack",
     "حفاضات أطفال فائقة الامتصاص بطبقة ناعمة لطيفة على بشرة الطفل وحواجز مانعة للتسرب لراحة وجفاف طوال اليوم."),

    ("tissues", r'(?:\bمناديل\b|\bمنديل\b|ورق\s*(?:تواليت|مطبخ|حمام)|بكرة\s*مناديل|رول\s*مطبخ|facial\s*tissues|toilet\s*paper|kitchen\s*(?:towel|rolls))',
     "مناديل ورقية", "Facial Tissues & Paper Rolls",
     "مناديل ورقية ناعمة وعالية الامتصاص بعدة طبقات متينة وموفرة للاستخدام اليومي في المنزل والمطبخ."),

    ("detergent", r'(?:مسحوق\s*(?:ال)?غسيل|منظف\s*(?:ال)?(?:غسيل|اوتوماتيك|أوتوماتيك|أطباق|صحون|أرضيات|حمامات|زجاج|مراحيض|متعدد\s*الأغراض|أسطح)|جل\s*(?:منظف|غسيل|الغسيل)|سائل\s*(?:تنظيف|غسيل|الغسيل|أطباق|الأطباق|صحون)|كبسولات\s*(?:ال)?غسيل|أقراص\s*غسالة|معقم\s*ومطهر|مطهر\s*(?:أرضيات|أسطح|ومنظف)|مبيض\s*ملابس|منعم\s*(?:ال)?أقمشة|مزيل\s*(?:ال)?بقع|معطر\s*جو|عبوة\s*إعادة\s*تعبئة|مبيد\s*حشرات|laundry\s*detergent|washing\s*powder|dishwashing|dishwasher\s*(?:tablets|pods|gel|salt)|all[\s\-]*purpose\s*cleaner|surface\s*cleaner|disinfectant|fabric\s*softener|air\s*freshener|stain\s*remover)',
     "منظفات وعناية منزلية", "Home Cleaning & Laundry Detergent",
     "تركيبة تنظيف قوية وفعالة تزيل البقع والدهون الصعبة بسهولة وتترك رائحة منعشة ونظافة فائقة."),

    ("supplements", r'(?:واي\s*بروتين|\bبروتين\b|مكمل\s*(?:غذائي|مركز)|أوميجا\s*3|اوميجا\s*3|زيت\s*السمك|\bفيتامين\b|فيتامينات|\bكولاجين\b|\bكرياتين\b|whey\s*protein|mass\s*gainer|omega[\s\-]*3|fish\s*oil|multivitamin)',
     "مكمل غذائي وفيتامينات", "Nutritional Supplement & Vitamins",
     "مكمل غذائي عالي الجودة بتركيبة مركزة لدعم الطاقة والنشاط البدني والاحتياجات الغذائية اليومية."),

    ("tea_drink", r'(?:\bشاي\b|أكياس\s*شاي|فتلة\s*شاي|ينسون|بابونج|نعناع\s*طبيعي|كركديه|أعشاب\s*طبيعية|black\s*tea|green\s*tea|tea\s*bags|herbal\s*(?:tea|infusion)|\btea\b\s*\d+\s*(?:g|gm|bags))',
     "شاي ومشروبات طبيعية", "Tea & Herbal Infusion",
     "شاي ومشروبات طبيعية مختارة بعناية بمذاق أصيل ونكهة غنية ومنعشة في كل كوب."),

    ("coffee_drink", r'(?:قهوة\s*(?:فورية|سريعة\s*التحضير|تركية|عربي|مطحونة|من\s+\w+|بحبيبات|اسبريسو\s*مطحونة)|برطمان\s*قهوة|كبسولات\s*(?:قهوة|نسبرسو)|مبيض\s*قهوة|كوفي[\s\-]*ميت|نسكافيه\s*(?:جولد|كلاسيك|3\s*في\s*1)|instant\s*coffee|ground\s*coffee|coffee\s*beans|coffee\s*capsules)',
     "قهوة ومشروبات", "Coffee & Beverages",
     "قهوة ومشروبات بمذاق غني ورائحة محمصة مميزة تمنحك كوباً متوازناً ومنعشاً في كل صباح."),

    ("grocery", r'(?:زيت\s*(?:دوار\s*الشمس|ذرة|زيتون|طهي|قلي|مخلوط|جوز\s*الهند)|\bسمن\b|\bزبدة\b|كريمة\s*فول\s*سوداني|زبدة\s*فول\s*سوداني|\bدقيق\b|\bأرز\b|\bمكرونة\b|\bعسل\b|\bمربى\b|\bشوكولاتة\b|\bبسكويت\b|\bتونة\b|\bصلصة\b|\bمكسرات\b|sunflower\s*oil|cooking\s*oil|olive\s*oil|peanut\s*butter)',
     "منتجات غذائية وسوبرماركت", "Grocery & Food Essentials",
     "منتج غذائي عالي الجودة بمكونات مختارة بعناية ومذاق رائع للاستخدام اليومي في المطبخ."),

    ("auto_care", r'(?:ماء\s*مساحات|زيت\s*محرك|ملمع\s*(?:تابلوه|إطارات)|منفاخ\s*إطارات|مساحات\s*زجاج|شامبو\s*سيارات|motor\s*oil|windshield\s*washer)',
     "عناية ومستلزمات سيارات", "Car Care & Automotive",
     "منتج عملي للعناية بالسيارة والحفاظ على كفاءة التشغيل والنظافة بأداء موثوق."),

    ("sandwich_maker", r'(?:صانعة?\s*(?:ساندوتش(?:ات)?|ساندويتش(?:ات)?|وافل)|محضرة\s*الوجبات\s*الخفيفة.*?ساندو[ي]?تش|\bتوستر\b|محمصة\s*خبز|شواية\s*كهربائية|جريل\s*كهربائي|sandwich\s*(?:maker|grill)|waffle\s*maker|\btoaster\b|contact\s*grill|health\s*grill)',
     "صانعة ساندوتشات وشواية كهربائية", "Sandwich Maker & Electric Grill",
     "صانعة ساندوتشات وشواية كهربائية بألواح غير لاصقة سهلة التنظيف وتسخين سريع متساوٍ لتحضير أشهى الساندوتشات والمشويات."),

    ("electric_stove", r'(?:طبق\s*تسخين|مسطح\s*(?:كهربائي|بلت|غاز|سيراميك)|\bبوتاجاز\b|شعلة\s*كهربائية|عين\s*كهربائية|ceramic\s*heating\s*plate|hot\s*plate|electric\s*(?:cooktop|stove|burner))',
     "مسطح وسخان طهي كهربائي", "Electric Hot Plate & Cooktop",
     "مسطح وسخان طهي عملي بتسخين سريع وتحكم مريح في درجات الحرارة لطهي وتسخين الطعام بكفاءة وأمان."),

    ("scooter_hoverboard", r'(?:هوفر\s*بورد|سكوتر\s*(?:كهربائي|ذكي|توازن|ركلة|أطفال)|\bhoverboard\b|self[\s\-]*balancing\s*scooter|electric\s*scooter|kick\s*scooter)',
     "سكوتر وهوفر بورد ذكي", "Smart Hoverboard & Scooter",
     "سكوتر وهوفر بورد عصري بتوازن ذكي وحركة سلسة وهيكل متين يمنح تجربة قيادة ممتعة وآمنة."),

    ("batteries", r'(?:بطاري[ةه]\s*(?:ليثيوم|قلوية|قلم|ألكالاين|الكالاين|عملة)|\bبطاريات\s*(?:قلم|ليثيوم|قلوية|ألكالاين|قابلة\s*للشحن)\b|\bcr20(?:32|25|16)\b|\b(?:aa|aaa)\s*batter|lithium\s*(?:coin\s*)?battery|alkaline\s*batter)',
     "بطاريات طاقة", "Alkaline & Lithium Batteries",
     "بطاريات طاقة أصلية طويلة العمر بتفريغ مستقر وآمن لتشغيل الريموت والساعات والأجهزة الإلكترونية بكفاءة."),

    ("home_decor", r'(?:لوح[ةه]\s*(?:فنية|حائط|جدارية|كانفاس|مطبوعة)|لوحات\s*(?:فنية|حائط|جدارية)|تابلوه|بوهو\s*مرسومة|ديكور\s*(?:منزلي|حائط)|wall\s*art|printed\s*canvas|home\s*gallery\s*set)',
     "لوحات وديكور منزلي", "Wall Art & Home Decor",
     "لوحات وديكور جداري أنيق بطباعة عالية الوضوح وألوان جذابة تضيف لمسة فنية راقية لغرف المعيشة والمكاتب."),

    ("makeup", r'(?:أحمر\s*شفاه|ملمع\s*شفاه|ماسكارا|ماسكرا|كريم\s*أساس|فاونديشن|كونسيلر|آيلاينر|ايلاينر|بلاشر|مكياج|طلاء\s*أظافر|lipstick|lip\s*gloss|mascara|foundation|concealer|eyeliner|\bmakeup\b)',
     "مستحضرات تجميل ومكياج", "Makeup & Cosmetics",
     "مستحضر تجميل بتركيبة ناعمة وثبات مميز يمنحك إطلالة جذابة وطبيعية طوال اليوم."),

    ("mop_cleaning_tool", r'(?:طقم\s*(?:دلو\s*و)?ممسحة|ممسحة\s*(?:دوارة|أرضيات|مايكروفايبر)|جردل\s*وممسحة|مساحة\s*أرضيات|floor\s*mop|spin\s*mop|mop\s*bucket)',
     "طقم ممسحة وتنظيف أرضيات", "Spin Floor Mop & Bucket Set",
     "طقم ممسحة أرضيات عملي برأس مايكروفايبر فائق الامتصاص وعصر مريح لتنظيف جميع الأسطح بسهولة وسرعة."),
]

CATEGORY_BY_KEY = {row[0]: row for row in SMART_CATEGORIES}

# الفئات المعرضة للالتباس النصي أو للترجمات العربية الآلية الخاطئة (تراجعها النسخة الإنجليزية والرؤية الحاسوبية بقوة)
_AMBIGUOUS_TEXT_CATS = {
    "charging_cable", "wall_charger", "stand_holder", "smart_tv",
    "smartphone", "tablet", "laptop", "power_bank", "food_chopper",
    "cushion_chair", "clothing", "perfume", "fan", "steam_iron",
}

# قاموس تصنيف مسار الفئة الإنجليزي الرسمي للمتجر (Leaf Breadcrumb Taxonomy)
# يعطي دليلاً قاطعاً من كتالوج أمازون/نون الرسمي (مثل Mains Chargers -> wall_charger)
_EN_BREADCRUMB_CAT_MAP = [
    (r'\bmains\s*chargers?\b|\bwall\s*chargers?\b', "wall_charger"),
    (r'\bcar\s*chargers?\b', "car_charger"),
    (r'\bwireless\s*chargers?\b', "wireless_charger"),
    (r'\bportable\s*power\s*banks?\b|\bpower\s*banks?\b', "power_bank"),
    (r'\bexternal\s*hard\s*drives?\b|\bexternal\s*solid\s*state\s*drives?\b|\bdata\s*storage\b|\bsolid\s*state\s*drives?\b|\binternal\s*solid\s*state\s*drives?\b|\busb\s*flash\s*drives?\b|\bflash\s*drives?\b|\bmemory\s*cards?\b|\bmicro\s*sd\s*cards?\b', "storage_drive"),
    (r'\bwater\s*heaters?(?:\s*&\s*parts)?\b|\bgas\s*water\s*heaters?\b|\belectric\s*water\s*heaters?\b', "water_heater"),
    (r'\bpower\s*strips?\b|\bsurge\s*protectors?\b|\bextension\s*cords?\b', "power_strip"),
    (r'\btravel\s*adapters?\b|\bsocket\s*adapters?\b|\bpower\s*converters?\b', "plug_adapter"),
    (r'\bethernet\s*cables?\b|\bcat\s*[5678]\s*cables?\b', "ethernet_cable"),
    (r'\bhdmi\s*cables?\b', "hdmi_cable"),
    (r'\busb\s*cables?\b|\blightning\s*cables?\b', "charging_cable"),
    (r'\busb\s*hubs?\b|\bdocking\s*stations?\b', "usb_hub"),
    (r'\bbasic\s*cases?\b|\bphone\s*cases?\b|\bwallet\s*cases?\b|\bsleeves?\b', "protective_case"),
    (r'\bscreen\s*protectors?\b', "screen_protector"),
    (r'\bsmartwatch\s*bands?\b|\bwatch\s*bands?\b', "watch_strap"),
    (r'\bsmartwatches\b|\bactivity\s*&\s*fitness\s*trackers?\b|\bfitness\s*trackers?\b', "smartwatch"),
    (r'\bin-ear\s*headphones\b|\bearbud\s*headphones\b', "earbuds"),
    (r'\bover-ear\s*headphones\b|\bon-ear\s*headphones\b', "headphones"),
    (r'\bpc\s*gaming\s*headsets?\b|\bgaming\s*headsets?\b', "gaming_headset"),
    (r'\bportable\s*bluetooth\s*speakers?\b|\bbluetooth\s*speakers?\b', "speaker"),
    (r'\bsoundbars?\b', "soundbar"),
    (r'\bstreaming\s*media\s*players?\b', "tv_stick"),
    (r'\bsmart\s*tvs?\b|\bled\s*&\s*lcd\s*tvs?\b|\btelevisions\b', "smart_tv"),
    (r'\bmonitors\b', "gaming_monitor"),
    (r'\btraditional\s*laptops?\b|\b2\s*in\s*1\s*laptops?\b', "laptop"),
    (r'\bgaming\s*keyboards?\b', "gaming_keyboard"),
    (r'\bgaming\s*mice\b', "gaming_mouse"),
    (r'\bmouse\s*pads?\b', "mouse_pad"),
    (r'\bcpu\s*cooling\s*fans?\b|\bwater\s*cooling\s*systems?\b|\bcase\s*fans?\b', "pc_cooler"),
    (r'\blaptop\s*cooling\s*pads?\b', "laptop_cooler"),
    (r'\bclothes\s*drying\s*racks?\b|\bdrying\s*racks?\b', "drying_rack"),
    (r'\bironing\s*boards?\b', "ironing_board"),
    (r'\bgarment\s*steamers?\b|\bsteam\s*irons?\b|\birons\b', "steam_iron"),
    (r'\bhand\s*wash\b|\bbody\s*wash\b|\bfacial\s*cleansers?\b|\bface\s*moisturizers?\b|\bsunscreens?\b', "skin_care"),
    (r'\bshampoos?\b|\bhair\s*conditioners?\b|\bhair\s*oils?\b|\bhair\s*masks?\b', "hair_care"),
    (r'\beau\s*de\s*(?:parfum|toilette)\b|\bbody\s*sprays?\b|\bdeodorants?\b', "perfume"),
    (r'\blaundry\s*detergent\b|\bliquid\s*detergent\b|\bpowder\s*detergent\b|\bdishwashing\b|\bhousehold\s*cleaners?\b', "detergent"),
    (r'\belectric\s*kettles?\b', "kettle"),
    (r'\bair\s*fryers?\b', "air_fryer"),
    (r'\bstand\s*mixers?\b', "stand_mixer"),
    (r'\bcountertop\s*blenders?\b|\bhand\s*blenders?\b|\bblenders?\b', "blender"),
    (r'\bfood\s*processors?\b|\bmini\s*choppers?\b|\bchoppers?\b', "food_chopper"),
    (r'\bespresso\s*machines?\b|\bcoffee\s*machines?\b|\bdrip\s*coffee\b', "coffee_maker"),
    (r'\bvacuum\s*cleaners?\b|\brobot\s*vacuums?\b', "vacuum"),
    (r'\bpedestal\s*fans?\b', "stand_fan"),
    (r'\bballpoint\s*pens?\b|\bgel\s*ink\s*pens?\b|\bhighlighters?\b', "stationery"),
]

# إزالة تراكيب النفي (مثل: بدون سلك، بدون زيت، بدون أسلاك، بدون حبر، بدون سكر) قبل فحص الفئات!
_NEGATED_NOUN_RE = re.compile(
    r'(?:بدون\s+(?:سلك|أسلاك|اسلاك|كابل|زيت|حبر|سكر|كحول|عطر|امونيا|أمونيا|سلوفان)|'
    r'بلا\s+(?:سلك|أسلاك|زيت|حبر)|'
    r'without\s+(?:cord|wire|wires|cable|oil|ink|sugar)|cordless|oil[\s\-]*free)',
    re.IGNORECASE,
)

# فصل الجملة الرأسية (المنتج الفعلي) عن الجملة الوصفية اللاحقة (مع كابل / مزود بـ / بشاشة...)
_MODIFIER_SPLIT_RE = re.compile(
    r'\b(?:مزود(?:ة)?\s*بـ?|شامل(?:ة)?|يشمل|يتضمن|يأتي\s*مع|تأتي\s*مع|مع\s+(?:كابل|سلك|شاحن|حامل|قاعدة|شنطة|جراب|محول|شاشة)|'
    r'بشاشة\s+عرض|مع\s+جهاز\s+تحكم|featuring|including|includes|comes\s+with|\bwith\s+(?:a\s+|usb|cable|charger|adapter|stand|case))\b',
    re.IGNORECASE,
)

# إزالة عبارات التوافق ومصادر الطاقة المشروطة (متوافق مع تابلت / يعمل بـ باور بانك / designed for / compatible with...)
# حتى لا تُصنف السلعة الأساسية خطأً باسم الملحق أو الجهاز المتوافق معه!
_COMPATIBILITY_CLAUSE_RE = re.compile(
    r'(?:'
    r'\b(?:compatible\s+with|compatibility|designed\s+for|works\s+with|suitable\s+for|operates\s+via|powered\s+by|supported\s+by)\b[^\n,;،|()]*|'
    r'(?:متوافق\s*(?:مع)?|مناسب\s*(?:لـ|مع)?|مخصص\s*(?:لـ)?|يعمل\s*(?:بـ|مع|بواسطة|عبر)?|يمكن\s*تشغيل[هة]\s*(?:بـ|عبر|بواسطة)?|مزود\s*بخاصية\s*التشغيل\s*عبر|خاص\s*بـ|معد\s*لـ)[^\n,;،|()]*'
    r')',
    re.IGNORECASE,
)


def _clean_for_cat_match(text):
    if not text:
        return ""
    s = _NEGATED_NOUN_RE.sub(" ", str(text))
    s = _COMPATIBILITY_CLAUSE_RE.sub(" ", s)
    s = re.sub(r'[\u200b-\u200f\xa0]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def _has_accessory_breadcrumb(breadcrumbs_str):
    """يتحقق مما إذا كان مسار الفئة يشير فعلاً لقسم إكسسوارات فرعي (مع استثناء اسم القسم العام للكمبيوتر في أمازون!)."""
    if not breadcrumbs_str:
        return False
    cleaned_bc = re.sub(
        r'computers,?\s*components\s*(?:&|and)\s*accessories|الكمبيوتر\s*ومكوناته\s*وملحقاته',
        ' ',
        str(breadcrumbs_str),
        flags=re.I,
    )
    # لو الفئة النهائية في المسار هي جهاز رئيسي صريح (Laptops / Smartphones / Tablets / TVs)، فليست إكسسواراً أبداً
    parts = [p.strip() for p in re.split(r'[>/›»]', str(breadcrumbs_str)) if p.strip()]
    if parts and re.search(r'^(?:traditional\s*laptops|2\s*in\s*1\s*laptops|laptops|notebooks|smartphones|mobile\s*phones|tablets|smart\s*tvs|tvs|أجهزة\s*اللابتوب|الهواتف\s*الذكية|التلفزيونات)$', parts[-1], re.I):
        return False
    return bool(re.search(r'\b(?:accessories|ملحقات|اكسسوارات|إكسسوارات)\b', cleaned_bc, re.I))


def _is_cat_forbidden(cat_key, brand_en="", price=None, breadcrumbs_str="", title_str=""):
    """يتحقق مما إذا كانت الفئة مستحيلة منطقياً للماركة أو السعر أو مسار قسم الإكسسوارات."""
    t_low = f"{title_str or ''} {breadcrumbs_str or ''}".lower()

    # حماية سخانات المياه والأجهزة الكبيرة من التصنيف الخاطئ كباور بانك أو كابل أو حامل
    if cat_key == "power_bank":
        if re.search(r'سخان|heater|غلاية|kettle|بوتاجاز|stove|فرن|oven|غسالة|washing|ثلاجة|fridge|refrigerator|مروحة|pedestal\s*fan', t_low):
            return True
        if price is not None and price >= 3500:
            return True

    # حماية وسائط التخزين والهاردات من التصنيف الخاطئ كأجهزة تابلت
    if cat_key == "tablet":
        if re.search(r'\bssd\b|\bhdd\b|\bnvme\b|هارد|ذاكرة\s*فلاشية|solid\s*state|hard\s*drive|flash\s*drive|flash\s*disk', t_low):
            return True

    # حماية الكابلات والحوامل من التصنيف الخاطئ للأجهزة المنزلية
    if cat_key in ("charging_cable", "stand_holder", "audio_cable"):
        if re.search(r'غلاية|kettle|مروحة|fan\b|سخان|heater|بوتاجاز|stove|فرن|oven|غسالة|ثلاجة', t_low):
            return True
        if price is not None and price >= 1500:
            return True

    if brand_en in _NO_MAJOR_DEVICE_BRANDS and cat_key in ("smartphone", "tablet", "laptop", "smart_tv", "refrigerator", "washing_machine", "air_conditioner"):
        return True
    if _has_accessory_breadcrumb(breadcrumbs_str):
        if cat_key in ("smartphone", "tablet", "laptop", "smart_tv", "refrigerator", "washing_machine", "air_conditioner"):
            return True
    if price is not None and price > 0:
        if price < 1400 and cat_key in ("smartphone", "tablet"):
            return True
        if price < 4500 and cat_key == "laptop":
            return True
        if price < 2500 and cat_key in ("smart_tv", "refrigerator", "washing_machine", "air_conditioner"):
            return True
        if price >= 2500 and cat_key in ("protective_case", "screen_protector", "charging_cable", "audio_cable", "hdmi_cable", "ethernet_cable", "watch_strap", "stand_holder", "phone_cooler", "plug_adapter"):
            return True
    return False


def _score_en_breadcrumbs(en_breadcrumbs):
    """يستخرج الفئة الدقيقة من مسار القسم الإنجليزي الرسمي للمتجر (الأقرب لنهاية المسار هو الأدق)."""
    if not en_breadcrumbs:
        return {}
    crumbs_list = list(en_breadcrumbs) if isinstance(en_breadcrumbs, (list, tuple)) else [s.strip() for s in str(en_breadcrumbs).split(">") if s.strip()]
    if not crumbs_list:
        return {}
    full_bc = " > ".join(crumbs_list)
    has_acc = _has_accessory_breadcrumb(full_bc)
    bc_scores = {}
    # نعطي وزناً أعلى للمستويات الفرعية الأخيرة (Leaf category)
    for depth_idx, item in enumerate(crumbs_list):
        weight = 48.0 if depth_idx == len(crumbs_list) - 1 else (32.0 if depth_idx == len(crumbs_list) - 2 else 18.0)
        for pat, ckey in _EN_BREADCRUMB_CAT_MAP:
            if re.search(pat, item, re.I):
                if has_acc and ckey in ("smartphone", "tablet", "laptop", "smart_tv"):
                    continue
                bc_scores[ckey] = max(bc_scores.get(ckey, 0.0), weight)
        # حالات خاصة للقسم النهائي فقط عندما لا يكون قسم إكسسوارات
        if not has_acc and depth_idx == len(crumbs_list) - 1:
            if re.fullmatch(r'smartphones?|mobile\s*phones?', item.strip(), re.I):
                bc_scores["smartphone"] = max(bc_scores.get("smartphone", 0.0), 48.0)
            elif re.fullmatch(r'tablets?', item.strip(), re.I):
                bc_scores["tablet"] = max(bc_scores.get("tablet", 0.0), 48.0)
            elif re.fullmatch(r'laptops?|notebooks?', item.strip(), re.I):
                bc_scores["laptop"] = max(bc_scores.get("laptop", 0.0), 48.0)
            elif re.fullmatch(r'keyboards?', item.strip(), re.I) and not re.search(r'musical|piano', full_bc, re.I):
                bc_scores["keyboard"] = max(bc_scores.get("keyboard", 0.0), 42.0)
            elif re.fullmatch(r'mice', item.strip(), re.I):
                bc_scores["mouse"] = max(bc_scores.get("mouse", 0.0), 42.0)
    return bc_scores


def _score_text_categories(title, en_slug="", breadcrumbs="", features_text="", brand_en="", price=None):
    """
    يحسب نقاط كل فئة بذكاء سياقي كامل:
    - بداية العنوان قبل (متوافق مع / مع / بدون): وزن 38 نقطة + مكافأة الكلمات الأولى (+28)
    - الاسم الإنجليزي المساعد (en_slug): وزن 30 نقطة للبداية + مكافأة (+20)
    - مسار الفئة في المتجر (Breadcrumbs): وزن مساعد 22 نقطة
    - باقي العنوان قبل (متوافق مع): وزن 14 نقطة
    - الوصف الكامل والمواصفات (Features / Overview / Specs): وزن 15 نقطة
    """
    scores = {}
    head_matched_cats = set()

    t_no_compat = COMPAT_SPLIT_RE.split(title or "", maxsplit=1)[0]
    t_head = _MODIFIER_SPLIT_RE.split(t_no_compat, maxsplit=1)[0]

    en_clean = re.sub(r'[-_/]+', ' ', en_slug or "")
    en_no_compat = COMPAT_SPLIT_RE.split(en_clean, maxsplit=1)[0]
    en_head = _MODIFIER_SPLIT_RE.split(en_no_compat, maxsplit=1)[0]

    c_crumbs = _clean_for_cat_match(breadcrumbs)
    c_head = _clean_for_cat_match(t_head)
    c_body = _clean_for_cat_match(t_no_compat)
    c_en_head = _clean_for_cat_match(en_head)
    c_en_body = _clean_for_cat_match(en_no_compat)
    c_feats = _clean_for_cat_match(features_text)

    for cat_key, pat, _, _, _ in SMART_CATEGORIES:
        sc = 0.0
        if c_crumbs and re.search(pat, c_crumbs, re.IGNORECASE):
            sc += 22.0

        if c_head:
            m = re.search(pat, c_head, re.IGNORECASE)
            if m:
                pos_bonus = 28.0 if m.start() <= 35 else (14.0 if m.start() <= 65 else 4.0)
                sc += 38.0 + pos_bonus
                if m.start() <= 45:
                    head_matched_cats.add(cat_key)

        if c_en_head:
            m_en = re.search(pat, c_en_head, re.IGNORECASE)
            if m_en:
                pos_bonus_en = 20.0 if m_en.start() <= 40 else 8.0
                sc += 30.0 + pos_bonus_en
                if m_en.start() <= 45:
                    head_matched_cats.add(cat_key)

        if not sc and c_body and re.search(pat, c_body, re.IGNORECASE):
            sc += 14.0
        if not sc and c_en_body and re.search(pat, c_en_body, re.IGNORECASE):
            sc += 12.0

        if c_feats and re.search(pat, c_feats, re.IGNORECASE):
            sc += 15.0

        if sc > 0:
            scores[cat_key] = sc

    # قواعد حسم التضارب المنطقي السياقي:
    # 0) قواعد منطق الماركة والسعر وقسم الإكسسوارات
    for k_chk in list(scores.keys()):
        if _is_cat_forbidden(k_chk, brand_en=brand_en, price=price, breadcrumbs_str=c_crumbs, title_str=title):
            scores.pop(k_chk, None)
            head_matched_cats.discard(k_chk)

    # قدرة كهربائية >= 1000W أو مشترك iLock بمنافذ متعددة مستحيل يكون شاحن موبايل حائط -> مشترك كهربائي!
    if "wall_charger" in scores:
        combined_title_slug = f"{title or ''} {en_clean}"
        if re.search(r'\b[1-4]\d{3}\s*(?:وات|واط|w\b|watt)', combined_title_slug, re.I) or (
            brand_en == "iLock" and re.search(r'منافذ|مخارج|ports?|outlets?|3500|2500', combined_title_slug, re.I)
            and "plug_adapter" not in head_matched_cats
        ):
            scores.pop("wall_charger", None)
            scores["power_strip"] = max(scores.get("power_strip", 0.0), 75.0)

    # 1) التمييز الدقيق بين مشغل الوسائط TV Stick وشاشة التلفزيون الفعلية ذات المقاس الكبير (32-85 بوصة)
    has_tv_inch = bool(re.search(r'\b(?:32|40|43|50|55|58|65|70|75|85)\s*(?:بوصة|انش|إنش|inch|\")\b', f"{c_head} {c_en_head}", re.I))
    if "tv_stick" in scores and ("tv_stick" in head_matched_cats or ("smart_tv" not in head_matched_cats and not has_tv_inch)):
        scores["tv_stick"] += 40.0
        scores.pop("smart_tv", None)
    elif "smart_tv" in head_matched_cats and has_tv_inch:
        scores["smart_tv"] += 30.0
        scores.pop("tv_stick", None)

    # 2) مراوح الكمبيوتر والتبريد الاحترافي تلغي مروحة المنزل العادية
    if any(k in head_matched_cats for k in ("pc_cooler", "laptop_cooler", "phone_cooler")):
        scores.pop("fan", None)
        scores.pop("stand_fan", None)
    elif "pc_cooler" in scores and "fan" not in head_matched_cats and "stand_fan" not in head_matched_cats:
        scores.pop("fan", None)

    # 3) منشر الملابس وطاولة الكي ووحدات التخزين والغسالات يلغون تصنيف الملابس الخاطئ!
    if any(k in head_matched_cats for k in ("drying_rack", "ironing_board", "storage_organizer", "washing_machine", "detergent", "steam_iron", "appliance_stand")):
        scores.pop("clothing", None)
    elif any(k in scores for k in ("drying_rack", "ironing_board")) and "clothing" not in head_matched_cats:
        scores.pop("clothing", None)

    if "ironing_board" in head_matched_cats:
        scores["ironing_board"] += 35.0
        scores.pop("steam_iron", None)
    if "appliance_stand" in head_matched_cats:
        scores["appliance_stand"] += 35.0
        scores.pop("washing_machine", None)
        scores.pop("refrigerator", None)
        scores.pop("stand_holder", None)

    # 4) الصابون وغسول اليدين والشامبو والمنظفات في بداية العنوان يلغون تصنيف العطر (بسبب عبارات مثل: بعطر الفراولة)
    if any(k in head_matched_cats for k in ("skin_care", "hair_care", "detergent", "oral_care", "tissues", "diapers")) and "perfume" not in head_matched_cats:
        scores.pop("perfume", None)

    # 5) مروحة ستاند أو عجان ستاند أو مكواة ستاند تلغي حامل الموبايل Stand Holder تماماً
    if any(k in scores for k in ("stand_fan", "fan", "stand_mixer", "steam_iron", "baby_chair", "drying_rack", "ironing_board")):
        scores.pop("stand_holder", None)

    # 6) الساعة الذكية وسوار الساعة يلغيان الموبايل والشاشة الذكية
    if "watch_strap" in scores and "watch_strap" in head_matched_cats:
        scores["watch_strap"] += 35.0
        scores.pop("smartwatch", None)
        scores.pop("smartphone", None)
    elif "smartwatch" in scores and "smartwatch" in head_matched_cats:
        scores["smartwatch"] += 30.0
        scores.pop("smartphone", None)
        scores.pop("smart_tv", None)
        scores.pop("gaming_monitor", None)

    # 7) جراب الحماية ولاصقة الشاشة والمبرد والملحقات في بداية العنوان يلغون الجهاز المتوافق معه
    for acc_k in (
        "protective_case", "screen_protector", "laptop_bag", "laptop_cooler", "phone_cooler",
        "laptop_charger", "ethernet_cable", "hdmi_cable", "audio_cable", "charging_cable",
        "wall_charger", "plug_adapter", "car_charger", "wireless_charger", "stand_holder",
    ):
        if acc_k in scores and acc_k in head_matched_cats:
            scores[acc_k] += 30.0
            for dev_k in ("smartphone", "tablet", "power_bank", "laptop", "earbuds"):
                if dev_k not in head_matched_cats:
                    scores.pop(dev_k, None)

    if "ethernet_cable" in head_matched_cats:
        scores["ethernet_cable"] += 30.0
        scores.pop("charging_cable", None)
    if "plug_adapter" in head_matched_cats and "wall_charger" not in head_matched_cats:
        scores["plug_adapter"] += 25.0
        scores.pop("wall_charger", None)

    if "phone_cooler" in scores:
        scores["phone_cooler"] += 35.0
        for k_rm in ("lantern", "smartphone", "protective_case"):
            if k_rm not in head_matched_cats:
                scores.pop(k_rm, None)
    if "scooter_hoverboard" in scores:
        scores["scooter_hoverboard"] += 40.0
        for k_rm in ("earbuds", "speaker", "lantern"):
            scores.pop(k_rm, None)
    if "batteries" in scores and "batteries" in head_matched_cats:
        scores["batteries"] += 35.0
        scores.pop("power_bank", None)
        scores.pop("smartwatch", None)
    if any(k in head_matched_cats for k in ("food_chopper", "blender", "stand_mixer")):
        scores.pop("milk_frother", None)

    # 8) كابل شحن صريح في أول العنوان يلغي الشاحن الجداري (عندما يكون العنوان متسقاً)
    if "charging_cable" in head_matched_cats and "wall_charger" in scores:
        if not re.search(r'^\s*(?:[\w\u0600-\u06FF]+\s+)?(?:شاحن|مجموعة\s*شاحن|راس\s*شاحن|wall\s*charger|mains\s*charger|gan\s*wall)', f"{c_head} {c_en_head}", re.I):
            scores.pop("wall_charger", None)

    # 9) التمييز الدقيق بين سماعة الأذن اللاسلكية (Earbuds) وسماعة الرأس (Over-Ear Headphones)
    if "earbuds" in scores and "earbuds" in head_matched_cats and not re.search(r'فوق\s*الأذن|على\s*الأذن|over-?ear|on-?ear|gaming\s*headset|سماعة\s*رأس\s*للألعاب', f"{c_head} {c_en_head}", re.I):
        scores["earbuds"] += 25.0
        scores.pop("headphones", None)
    elif any(k in head_matched_cats for k in ("gaming_headset", "headphones", "wired_earphones")):
        scores.pop("earbuds", None)

    # 10) القهوة سريعة التحضير/الحبيبات بدون كلمة "ماكينة/صانعة" تلغي ماكينة القهوة
    if "coffee_drink" in scores and "coffee_maker" not in head_matched_cats:
        scores.pop("coffee_maker", None)
    if "gaming_monitor" in scores and "smart_tv" in head_matched_cats:
        scores.pop("gaming_monitor", None)

    return scores, head_matched_cats


# ---------------------------------------------------------------------------
# 4. استخراج المواصفات الدقيقة وبناء الاسم العربي والإنجليزي والوصف الذكي
# ---------------------------------------------------------------------------
def _extract_rich_specs(title, en_slug="", specs_text="", cat_key="", brand_en="", en_title=""):
    """يستخرج الموديل والأرقام الجوهرية المناسبة لنوع المنتج بدقة بدون حشو عشوائي."""
    en_ref = f"{en_title or ''} {re.sub(r'[-_]+', ' ', en_slug or '')}".strip()
    combined = f"{title or ''} {en_ref} {specs_text or ''}"
    primary = COMPAT_SPLIT_RE.split(title or "", maxsplit=1)[0]
    en_primary = COMPAT_SPLIT_RE.split(en_title or "", maxsplit=1)[0]
    primary_both = f"{primary} {en_primary}".strip()
    spec_ar, spec_en = [], []

    # 1. الهواتف والتابلت: الموديل + المساحة + الرام + 5G
    if cat_key in ("smartphone", "tablet"):
        model_str = None
        m_ap = re.search(r'\b(?:iPhone|iPad|آيفون|ايفون|آيباد|ايباد)\s*(Air|mini|Pro|1[1-9]e?|1[1-9]|X[SR]?|SE|\d{1,2})\s*(Pro\s*Max|Pro|Plus|mini|برو\s*ماكس|برو|بلس|ميني)?\b', combined, re.I)
        if m_ap:
            pref = "iPad" if any(x in m_ap.group(0).lower() for x in ("ipad", "آيباد", "ايباد")) else "iPhone"
            p1 = m_ap.group(1)
            p1 = p1.upper() if p1.upper() in ("SE", "XR", "XS") else p1.capitalize()
            t_raw = (m_ap.group(2) or "").lower()
            t_en = "Pro Max" if ("pro max" in t_raw or "برو ماكس" in t_raw) else ("Pro" if ("pro" in t_raw or "برو" in t_raw) else ("Plus" if ("plus" in t_raw or "بلس" in t_raw) else ("mini" if ("mini" in t_raw or "ميني" in t_raw) else "")))
            model_str = f"{pref} {p1} {t_en}".strip()

        if not model_str:
            m_sam = re.search(r'(?:Galaxy|جالكسي|جالاكسي)?\s*(?:اس\s+|إس\s+|ايه\s+|إيه\s+|ام\s+|تاب\s+)?\b(S2\d|S1\d|Z\s*(?:Fold|Flip)\s*\d*|A\d{2}s?|M\d{2}s?|Tab\s*[SA]\d+(?:\s*Lite)?)\s*(Ultra|Plus|\+|FE|الترا|ألترا|بلس)?\b', combined, re.I)
            if m_sam:
                m_core = re.sub(r'\s+', ' ', m_sam.group(1)).strip()
                if not m_core.lower().startswith("tab"):
                    m_core = m_core.upper().replace(" ", "")
                t_raw = (m_sam.group(2) or "").lower()
                t_en = "Ultra" if any(w in t_raw for w in ("ultra", "الترا", "ألترا")) else ("Plus" if any(w in t_raw for w in ("plus", "بلس", "+")) else ("FE" if "fe" in t_raw else ""))
                model_str = f"Galaxy {m_core} {t_en}".strip()

        if not model_str:
            m_xm = re.search(r'(?:Redmi\s*Note|ريدمي\s*نوت)\s*(\d{1,2}[A-Za-z]?)\s*(Pro\s*\+|Pro|Plus|برو\s*\+|برو)?', combined, re.I)
            if m_xm:
                t_raw = (m_xm.group(2) or "").lower()
                t_en = "Pro+" if ("+" in t_raw) else ("Pro" if ("pro" in t_raw or "برو" in t_raw) else "")
                model_str = f"Redmi Note {m_xm.group(1)} {t_en}".strip()

        if not model_str:
            m_other_ph = re.search(
                r'(?:(?:Redmi|ريدمي)\s*(?:Pad\s*(?:SE|Pro)?|\d{1,2}[A-Za-z]?)|'
                r'(?:POCO|بوكو)\s*[XFM C]\d{1,2}\s*(?:Pro|GT)?|'
                r'(?:Reno|رينو)\s*\d{1,2}\s*(?:Pro\+?|Pro|F)?|'
                r'(?:Realme|ريلمي)\s*(?:C\d{2}[A-Za-z]?|\d{1,2}\s*(?:Pro\+?|Pro)?|Note\s*\d{1,2})|'
                r'\b(?:1[3-7]T)\s*(?:Pro)?\b|'
                r'\b(?:Hot|Note|Smart|Spark|Camon|Magic|Nova|Honor)\s*\d{1,3}\s*(?:Pro\+?|Pro|Plus|Lite)?\b)',
                combined, re.I
            )
            if m_other_ph:
                raw_m = m_other_ph.group(0)
                raw_m = re.sub(r'ريدمي', 'Redmi', raw_m)
                raw_m = re.sub(r'بوكو', 'POCO', raw_m)
                raw_m = re.sub(r'رينو', 'Reno', raw_m)
                raw_m = re.sub(r'ريلمي', 'Realme', raw_m)
                raw_m = re.sub(r'برو', 'Pro', raw_m)
                model_str = re.sub(r'\s+', ' ', raw_m).strip()

        if model_str:
            spec_ar.append(model_str)
            spec_en.append(model_str)

        if re.search(r'\b5G\b|الجيل\s*الخامس', combined, re.I):
            if "5G" not in " ".join(spec_en):
                spec_ar.append("5G")
                spec_en.append("5G")

        m_tb = re.search(r'\b([12])\s*(?:تيرا(?:بايت)?|TB)\b', combined, re.I)
        if m_tb:
            spec_ar.append(f"سعة {m_tb.group(1)}TB")
            spec_en.append(f"{m_tb.group(1)}TB")
        else:
            m_rom = re.search(r'\b(64|128|256|512)\s*(?:جيجا(?:بايت)?|GB)\b', combined, re.I)
            if m_rom:
                spec_ar.append(f"سعة {m_rom.group(1)} جيجا")
                spec_en.append(f"{m_rom.group(1)}GB")

        m_ram = re.search(r'\b(4|6|8|12|16|24)\s*(?:جيجا(?:بايت)?\s*رام|رام|GB\s*RAM)\b|(?:رام|RAM)\s*(4|6|8|12|16|24)\s*(?:جيجا|GB)?', combined, re.I)
        if m_ram:
            rv = m_ram.group(1) or m_ram.group(2)
            spec_ar.append(f"({rv} جيجا رام)")
            spec_en.append(f"({rv}GB RAM)")
        return spec_ar, spec_en

    # 2. اللابتوب (السلسلة الكاملة + المعالج + الرام + الـ SSD)
    if cat_key == "laptop":
        m_lap = re.search(
            r'\b(IdeaPad\s*(?:Slim\s*\d*|Gaming\s*\d*|Pro\s*\d*|Flex\s*\d*|\d+)|'
            r'Vivobook\s*(?:Go\s*\d*|Pro\s*\d*|S\s*\d*|\d*)|Zenbook\s*\w*|'
            r'ThinkPad\s*[A-Z]?\d*|ThinkBook\s*\d*|LOQ\s*\d*|Legion\s*(?:Pro\s*\d*|Slim\s*\d*|\d*)|'
            r'Inspiron\s*\d*|Vostro\s*\d*|Latitude\s*\d*|Victus\s*\d*|Pavilion\s*\w*|OmniBook\s*\w*|'
            r'TUF\s*Gaming\s*[AF]?\d*|ROG\s*(?:Strix|Zephyrus)?\s*\w*|'
            r'MacBook\s*(?:Air|Pro)|Aspire\s*\d*|Nitro\s*[V5]?\s*\d*|MateBook\s*[DX]?\d*)\b',
            combined, re.I
        )
        if m_lap:
            v = re.sub(r'\s+', ' ', m_lap.group(1)).strip()
            spec_ar.append(v)
            spec_en.append(v)
        m_cpu = re.search(
            r'\b(Core\s*Ultra\s*[579]|Core\s*i[3579](?:-\d{4,5}[A-Z]{0,2})?|Core\s*[357]\s*\d{3}[A-Z]?|'
            r'Ryzen\s*[3579](?:\s*\d{4}[A-Z]{0,2})?|Apple\s*M[1-5](?:\s*Pro|\s*Max)?|Celeron\s*N\d+|Intel\s*N\d{2,3})\b',
            combined, re.I
        )
        if m_cpu:
            c = re.sub(r'\s+', ' ', m_cpu.group(1)).strip()
            spec_ar.append(c)
            spec_en.append(c)
        m_ram = re.search(r'\b(8|12|16|24|32|64)\s*(?:GB\s*(?:DDR\d\s*)?RAM|جيجا(?:بايت)?\s*رام|GB\s*Memory)\b', combined, re.I)
        if m_ram:
            spec_ar.append(f"{m_ram.group(1)} جيجا رام")
            spec_en.append(f"{m_ram.group(1)}GB RAM")
        m_ssd = re.search(r'\b(256|512)\s*(?:GB\s*(?:NVMe\s*|M\.2\s*)?SSD|جيجا(?:بايت)?\s*SSD)\b|\b(1|2)\s*TB\s*SSD\b', combined, re.I)
        if m_ssd:
            if m_ssd.group(1):
                spec_ar.append(f"{m_ssd.group(1)}GB SSD")
                spec_en.append(f"{m_ssd.group(1)}GB SSD")
            else:
                spec_ar.append(f"{m_ssd.group(2)}TB SSD")
                spec_en.append(f"{m_ssd.group(2)}TB SSD")
        return spec_ar, spec_en

    # 3. مشغل الوسائط TV Stick
    if cat_key == "tv_stick":
        if re.search(r'tv\s*stick|تي\s*في\s*ستيك', combined, re.I):
            spec_ar.append("TV Stick")
        if re.search(r'\b4K\b', combined, re.I):
            spec_ar.append("4K")
            spec_en.append("4K")
        if re.search(r'2nd\s*gen|الجيل\s*الثاني', combined, re.I):
            spec_ar.append("(الجيل الثاني)")
            spec_en.append("(2nd Gen)")
        return spec_ar, spec_en

    # 4. الساعات الذكية وأساور التتبع
    if cat_key == "smartwatch":
        m_sw = re.search(r'(?:Redmi\s*Watch\s*\d+\s*(?:Lite|Active)?|Watch\s*\d+\s*(?:Active|Lite|Pro|Ultra)?|ووتش\s*\d+\s*(?:اكتيف|لايت|برو)?|ريدمي\s*(?:ووتش\s*)?\d+\s*(?:لايت|اكتيف)?|Smart\s*Band\s*\d+\s*(?:Pro|Active)?|Band\s*\d+\s*(?:Pro|Active)?|\bT800\s*(?:Ultra)?\b)', combined, re.I)
        if m_sw:
            s_val = m_sw.group(0)
            s_val = re.sub(r'ريدمي\s*(?:ووتش)?\s*', 'Redmi Watch ', s_val)
            s_val = re.sub(r'ووتش\s*', 'Watch ', s_val)
            s_val = re.sub(r'اكتيف', 'Active', s_val)
            s_val = re.sub(r'لايت', 'Lite', s_val)
            s_val = re.sub(r'برو', 'Pro', s_val)
            s_val = re.sub(r'\bt800\b', 'T800', s_val, flags=re.I)
            s_val = re.sub(r'\bultra\b', 'Ultra', s_val, flags=re.I)
            s_val = re.sub(r'\bwatch\b', 'Watch', s_val, flags=re.I)
            s_val = re.sub(r'\bband\b', 'Band', s_val, flags=re.I)
            s_val = re.sub(r'\blite\b', 'Lite', s_val, flags=re.I)
            s_val = re.sub(r'\bactive\b', 'Active', s_val, flags=re.I)
            s_val = re.sub(r'\bpro\b', 'Pro', s_val, flags=re.I)
            s_val = re.sub(r'\s+', ' ', s_val).strip()
            spec_ar.append(s_val)
            spec_en.append(s_val)
        return spec_ar, spec_en

    # 5. الشاشات والتلفزيونات
    if cat_key in ("smart_tv", "gaming_monitor"):
        m_sz = re.search(r'\b(22|24|27|32|34|40|43|50|55|58|65|70|75|85)\s*(?:بوصة|انش|إنش|inch|\")\b', combined, re.I)
        if m_sz:
            spec_ar.append(f"{m_sz.group(1)} بوصة")
            spec_en.append(f"{m_sz.group(1)}-inch")
        for res_tok in ("4K", "QLED", "OLED", "FHD"):
            if re.search(rf'\b{res_tok}\b', combined, re.I) and len(spec_en) < 3:
                spec_ar.append(res_tok)
                spec_en.append(res_tok)
        m_hz = re.search(r'\b(100|120|144|165|180|240)\s*Hz\b', combined, re.I)
        if m_hz:
            spec_ar.append(f"{m_hz.group(1)}Hz")
            spec_en.append(f"{m_hz.group(1)}Hz")
        m_tv_mod = re.search(r'\b(\d{2}[A-Z]{1,3}\d{2,4}[A-Z]{0,3})\b', combined)
        if m_tv_mod and len(spec_en) < 4:
            spec_ar.append(m_tv_mod.group(1))
            spec_en.append(m_tv_mod.group(1))
        return spec_ar, spec_en

    # 6. استخراج رقم/اسم الموديل العام (يشمل موديلات الشواحن مثل X516/Nano/Nexode والكيبوردات مثل WIN68 HE والمراوح والصوتيات)
    m_named = re.search(
        r'\b(Tapo\s*[A-Z]?\d{2,4}[A-Z]*|OneBlade|FreeClips|FreeBuds(?:\s*SE\s*\d?)?|SpaceBuds(?:\s*Neo)?|Zeus\s*(?:H\d+)?|'
        r'Go\s*[34]|Flip\s*[56]|Charge\s*5|Select\s*\d\s*(?:Go)?|Motion\s*[A-Z]?\d{3}|Space\s*One|'
        r'Wave\s*(?:Beam|Buds|Flex|\d{3}TWS)|Tune\s*\d{3}(?:BT|NC)?|Life\s*[APQ]\d\w*|Liberty\s*(?:Buds|\d\w*)|'
        r'R50i(?:\s*NC)?|P20i|P30i|P40i|K20i|A20i|A30i|V20i|C30i|C40i|Q20i|H30i|'
        r'WIN\s*6[08]\s*(?:HE)?|F75|F87|F99|K552|K617|G102|G213|G304|G502|M711|M908|'
        r'MR120(?:\s*ARGB)?|X5\d{2}|CD\d{3}|Nexode(?:\s*Pro)?|Zolo|Nano\s*(?:II|\d)?|'
        r'OEP[\s\-]?\d{3}|OTW[\s\-]?\d{3}|OCF[\s\-]?\d{3}[A-Z]?|'
        r'[Ff][Xx][\s\-]?\d{2,4}[A-Za-z]+|HD\d{4}(?:/\d{2})?|KM\d{4,5}[A-Z]?|'
        r'CR20(?:32|25|16)|UC\d{2}|CX\d{2}|XS[\s\-]?655|'
        r'C\d{3}[A-Z]{1,3}|TC\d{2,3}|GS\d{3}|H\d{3}|M\d{3}|VC\d{3})\b',
        f"{primary_both} {en_ref}",
        re.I,
    )
    if m_named:
        mv = re.sub(r'\s+', ' ', m_named.group(1)).strip()
        if re.match(r'^fx', mv, re.I):
            mv = "fx-" + re.sub(r'^[Ff][Xx][\s\-]*', '', mv).upper()
        elif re.match(r'^(?:R50i|P20i|P30i|P40i|K20i|A20i|A30i|V20i|C30i|C40i|Q20i|H30i)(?:\s*NC)?$', mv, re.I):
            parts_m = mv.split()
            base_m = parts_m[0][0].upper() + parts_m[0][1:-1] + "i"
            mv = f"{base_m} NC" if len(parts_m) > 1 else base_m
        elif re.match(r'^(?:OEP|OTW|OCF|HD|KM|TC|GS|VC|CR20|UC|CX|K552|K617|F75|F87|F99|G\d{3}|M\d{3}|MR120|X5\d{2}|CD\d{3}|XS|C\d|WIN)', mv, re.I):
            mv = mv.upper()
        else:
            _casing_map = {
                "freeclips": "FreeClips", "freebuds": "FreeBuds", "se": "SE", "spacebuds": "SpaceBuds", "oneblade": "OneBlade",
                "tapo": "Tapo", "zeus": "Zeus", "neo": "Neo", "liberty": "Liberty",
                "wave": "Wave", "beam": "Beam", "buds": "Buds", "flex": "Flex", "tune": "Tune",
                "life": "Life", "charge": "Charge", "flip": "Flip", "go": "Go", "select": "Select",
                "motion": "Motion", "space": "Space", "one": "One", "nexode": "Nexode", "zolo": "Zolo", "nano": "Nano",
            }
            mv = " ".join(_casing_map.get(tok.lower(), tok.upper() if re.match(r'^[A-Za-z]\d+[A-Za-z]*$', tok) else tok) for tok in mv.split())
        if mv.lower() != (brand_en or "").lower():
            spec_ar.append(mv)
            spec_en.append(mv)

    # تقنية GaN للشواحن الحديثة
    if cat_key in ("wall_charger", "laptop_charger", "power_strip") and re.search(r'\bGaN\b|نيتريد\s*الغاليوم', combined, re.I):
        if "gan" not in " ".join(spec_en).lower():
            spec_ar.append("GaN")
            spec_en.append("GaN")

    # مراوح الكمبيوتر (المقاس وعدد المراوح)
    if cat_key == "pc_cooler":
        m_mm = re.search(r'\b(120|140|240|360)\s*mm\b', combined, re.I)
        if m_mm:
            spec_ar.append(f"{m_mm.group(1)}mm")
            spec_en.append(f"{m_mm.group(1)}mm")
        if re.search(r'\btriple\s*pack\b|\b3[\s\-]*pack\b|3\s*قطع|3\s*مراوح', combined, re.I):
            spec_ar.append("(3 مراوح)")
            spec_en.append("(3-Pack)")

    # الكيبوردات (مقاس 60% / 65% / 75% / TKL)
    if cat_key in ("gaming_keyboard", "keyboard"):
        m_kb_sz = re.search(r'(?<![\d.])(60%|65%|75%|80%|\bTKL\b)', combined, re.I)
        if m_kb_sz:
            kv = m_kb_sz.group(1).upper()
            spec_ar.append(kv)
            spec_en.append(kv)

    # دقة الكاميرات الأمنية
    if cat_key == "security_camera":
        for cam_q in ("4K", "3K", "2K", "5MP", "4MP", "3MP", "1080P"):
            if re.search(rf'\b{cam_q}\b', combined, re.I) and len(spec_en) < 3:
                spec_ar.append(cam_q)
                spec_en.append(cam_q)

    # سعة اللتر / المل / الجرام / الكجم / المقاس / عدد القطع حسب الفئة
    if cat_key in ("kettle", "air_fryer", "stand_mixer", "blender", "microwave", "coffee_maker", "food_chopper", "cookware", "detergent", "grocery"):
        m_lit = re.search(r'(?<![\d.])(\d{1,2}(?:\.\d)?)\s*(?:لتر|لترات|L\b|Liter)', f"{primary_both} {en_ref}", re.I)
        if m_lit and 0.2 <= float(m_lit.group(1)) <= 60:
            spec_ar.append(f"سعة {m_lit.group(1)} لتر" if cat_key not in ("detergent", "grocery") else f"{m_lit.group(1)} لتر")
            spec_en.append(f"{m_lit.group(1)}L")
        elif cat_key in ("food_chopper", "blender"):
            m_ml_ch = re.search(r'\b(\d{3,4})\s*(?:مل(?:لي(?:لتر)?)?|ml\b)', f"{primary_both} {en_ref}", re.I)
            if m_ml_ch and 200 <= int(m_ml_ch.group(1)) <= 2000:
                spec_ar.append(f"سعة {m_ml_ch.group(1)} مل")
                spec_en.append(f"{m_ml_ch.group(1)}ml")

    if cat_key in ("washing_machine", "grocery", "detergent", "supplements", "weights_fitness"):
        m_kg = re.search(r'(?<![\d.])(\d{1,3}(?:\.\d)?)\s*(?:كجم|كيلو(?:\s*جرام)?|kg\b)', primary_both, re.I)
        if m_kg:
            spec_ar.append(f"{m_kg.group(1)} كجم")
            spec_en.append(f"{m_kg.group(1)}kg")

    if cat_key in ("hair_care", "skin_care", "perfume", "oral_care", "grocery", "coffee_drink", "tea_drink"):
        m_ml = re.search(r'\b(\d{2,4})\s*(?:مل(?:لي(?:لتر)?)?|ml\b)', primary_both, re.I)
        if m_ml:
            spec_ar.append(f"{m_ml.group(1)} مل")
            spec_en.append(f"{m_ml.group(1)}ml")
        else:
            m_gm = re.search(r'\b(\d{2,4})\s*(?:جم|جرام|g\b|gm\b)', primary_both, re.I)
            if m_gm:
                spec_ar.append(f"{m_gm.group(1)} جم")
                spec_en.append(f"{m_gm.group(1)}g")

    if cat_key == "diapers":
        m_dsz = re.search(r'(?:مقاس\s*(?:حفاضة\s*)?|حجم\s*\w+\s*|حديثي\s*الولادة\s*|حديثى\s*الولاده\s*|size\s*)([1-7])\b|\b([1-7])\s*-\s*\d{2}\b', primary_both, re.I)
        if m_dsz:
            sz = m_dsz.group(1) or m_dsz.group(2)
            spec_ar.append(f"مقاس {sz}")
            spec_en.append(f"Size {sz}")
        m_dcnt = re.search(r'\b(\d{2,3})\s*(?:حفاضة|حفاضه|قطعة|قطعه|diapers?|count)\b|\b[1-7]\s*-\s*(\d{2,3})\b', primary_both, re.I)
        if m_dcnt:
            cnt = m_dcnt.group(1) or m_dcnt.group(2)
            spec_ar.append(f"({cnt} حفاضة)")
            spec_en.append(f"({cnt} Count)")

    if cat_key == "tissues":
        m_tcnt = re.search(r'\b(\d{1,4})\s*(?:منديل|بكرة|لفة|رول|قطعة|sheets?|rolls?)\b', primary_both, re.I)
        if m_tcnt:
            val = m_tcnt.group(1)
            unit_ar = "بكرة" if any(u in m_tcnt.group(0).lower() for u in ("بكرة", "لفة", "رول", "roll")) else "منديل"
            unit_en = "Rolls" if unit_ar == "بكرة" else "Sheets"
            spec_ar.append(f"({val} {unit_ar})")
            spec_en.append(f"({val} {unit_en})")

    if cat_key == "drying_rack":
        m_tiers = re.search(r'\b([234])\s*(?:أدوار|ادوار|طوابق|مستويات|tier|level)', primary_both, re.I)
        if m_tiers:
            spec_ar.append(f"{m_tiers.group(1)} أدوار")
            spec_en.append(f"{m_tiers.group(1)}-Tier")

    if cat_key in ("stand_fan", "fan"):
        m_fsz = re.search(r'\b(14|16|18|20|26|30)\s*(?:بوصة|انش|inch)\b|\b(40|45|50)\s*(?:سم|cm)\b', primary_both, re.I)
        if m_fsz:
            if m_fsz.group(1):
                spec_ar.append(f"مقاس {m_fsz.group(1)} بوصة")
                spec_en.append(f"{m_fsz.group(1)}-inch")
            else:
                spec_ar.append(f"مقاس {m_fsz.group(2)} سم")
                spec_en.append(f"{m_fsz.group(2)}cm")

    # القدرة بالوات للأجهزة الكهربائية والشواحن والكابلات فقط
    if cat_key in (
        "power_bank", "wall_charger", "car_charger", "wireless_charger", "laptop_charger",
        "charging_cable", "power_strip", "kettle", "air_fryer", "stand_mixer", "blender",
        "food_chopper", "microwave", "coffee_maker", "steam_iron", "steam_cleaner", "vacuum",
        "hair_styler", "speaker", "soundbar", "sandwich_maker", "electric_stove", "phone_cooler",
    ):
        m_w = re.search(r'(?<![A-Za-z0-9])(\d{1,4})\s*(?:وات|واط|W\b|Watt)', f"{primary_both} {en_ref}", re.I)
        if m_w and 5 <= int(m_w.group(1)) <= 3500:
            w_val = int(m_w.group(1))
            if not (cat_key == "power_bank" and w_val < 15):
                spec_ar.append(f"{w_val}W")
                spec_en.append(f"{w_val}W")

    if cat_key == "power_bank":
        m_mah = re.search(r'(\d{4,6})\s*(?:مللي\s*أمبير|مللي\s*امبير|mAh\b)', combined.replace(",", ""), re.I)
        if m_mah:
            spec_ar.append(f"سعة {m_mah.group(1)}mAh")
            spec_en.append(f"{m_mah.group(1)}mAh")

    if cat_key in ("power_strip", "usb_hub", "wall_charger", "car_charger", "plug_adapter"):
        m_ports = re.search(r'\b(\d{1,2})\s*(?:منافذ|مخارج|مخرج|مداخل|ports?|outlets?|way)\b', primary_both, re.I)
        if m_ports and 2 <= int(m_ports.group(1)) <= 16:
            p_cnt = m_ports.group(1)
            spec_ar.append(f"{p_cnt} منافذ")
            spec_en.append(f"{p_cnt}-Port")
        else:
            # اكتشاف صيغة (1x USB-A 1x USB-C) في لغة واحدة فقط لمنع مضاعفة العدد عند وجود عنوانين!
            usb_x_counts = [int(x) for x in re.findall(r'\b(\d)\s*x\s*USB(?:\s*-\s*[AC])?\b', en_primary, re.I)]
            if not usb_x_counts:
                usb_x_counts = [int(x) for x in re.findall(r'\b(\d)\s*x\s*USB(?:\s*-\s*[AC])?\b', primary, re.I)]
            if len(usb_x_counts) >= 2 and 2 <= sum(usb_x_counts) <= 8:
                tot_p = sum(usb_x_counts)
                spec_ar.append(f"{tot_p} منافذ")
                spec_en.append(f"{tot_p}-Port")
            elif re.search(r'\bdual[\s\-]*port\b|منفذين|مخرجين|ثنائي\s*المنفذ', primary_both, re.I):
                spec_ar.append("2 منافذ")
                spec_en.append("2-Port")

    if cat_key == "ethernet_cable":
        m_cat = re.search(r'\b(Cat\s*[5678][ae]?)\b', combined, re.I)
        if m_cat:
            cv = re.sub(r'\s+', '', m_cat.group(1)).capitalize()
            spec_ar.append(cv)
            spec_en.append(cv)

    if cat_key in ("charging_cable", "audio_cable", "hdmi_cable", "ethernet_cable", "power_strip"):
        m_len = re.search(r'(?<![\d.])(\d{1,2}(?:\.\d)?)\s*(?:متر|م\b|m\b|meter)', primary_both, re.I)
        if m_len and 0.2 <= float(m_len.group(1)) <= 50:
            spec_ar.append(f"طول {m_len.group(1)}م")
            spec_en.append(f"{m_len.group(1)}m")
        if cat_key == "charging_cable" and re.search(r'usb-?c|type-?c|تايب\s*سي|نوع\s*سي', primary_both, re.I):
            if "USB-C" not in " ".join(spec_en):
                spec_ar.append("USB-C")
                spec_en.append("USB-C")

    # وحدات التخزين والهاردات والفلاشات (SSD / HDD / Flash Drive / MicroSD)
    if cat_key == "storage_drive":
        m_mod = re.search(r'\b(T300S|T5|T7\s*(?:Shield)?|T9|Extreme\s*(?:Pro)?|E61|E81|Crucial\s*X\d+|ArmorATD|Canvio|My\s*Passport|Elements|Plus\s*Slim|Bar\s*Plus|Ultra\s*Dual|DataTraveler|EVO\s*Plus|Ultra\s*Plus|SN\d{3,4})\b', combined, re.I)
        if m_mod:
            spec_ar.append(m_mod.group(0).strip())
            spec_en.append(m_mod.group(0).strip())
        m_tb = re.search(r'\b([1-8])\s*(?:تيرا(?:بايت)?|TB)\b', combined, re.I)
        if m_tb:
            spec_ar.append(f"سعة {m_tb.group(1)}TB")
            spec_en.append(f"{m_tb.group(1)}TB")
        else:
            m_gb = re.search(r'\b(32|64|128|256|512|960)\s*(?:جيجا(?:بايت)?|GB)\b', combined, re.I)
            if m_gb:
                spec_ar.append(f"سعة {m_gb.group(1)} جيجا")
                spec_en.append(f"{m_gb.group(1)}GB")
        m_spd = re.search(r'\b(\d{3,4})\s*(?:MB/s|ميجابايت/ثانية|ميجابايت)\b', combined, re.I)
        if m_spd:
            spec_ar.append(f"بسرعة {m_spd.group(1)}MB/s")
            spec_en.append(f"up to {m_spd.group(1)}MB/s")

    # سخانات المياه المنزلية (غاز / كهرباء / فوري)
    if cat_key == "water_heater":
        if re.search(r'غاز|gas', combined, re.I):
            spec_ar.append("غاز")
            spec_en.append("Gas")
        elif re.search(r'كهربائ?ي?|electric', combined, re.I):
            spec_ar.append("كهربائي")
            spec_en.append("Electric")
        elif re.search(r'فوري|instant|tankless', combined, re.I):
            spec_ar.append("فوري")
            spec_en.append("Instant Tankless")

        m_liters = re.search(r'\b(5|6|10|15|20|30|40|50|60|80|100)\s*(?:لتر|L(?:iter)?)\b', combined, re.I)
        if m_liters:
            spec_ar.append(f"سعة {m_liters.group(1)} لتر")
            spec_en.append(f"{m_liters.group(1)} Liter")

        if re.search(r'بدون\s*مدخنة|without\s*chimney', combined, re.I):
            spec_ar.append("بدون مدخنة")
            spec_en.append("without Chimney")
        elif re.search(r'بمدخنة|with\s*chimney', combined, re.I):
            spec_ar.append("بمدخنة")
            spec_en.append("with Chimney")
        elif re.search(r'ديجيتال|digital', combined, re.I):
            spec_ar.append("ديجيتال")
            spec_en.append("Digital")

    # إضافة الهدف المتوافق معه باختصار أنيق للجرابات ولاصقات الشاشة والأساور فقط
    if cat_key in ("protective_case", "screen_protector", "watch_strap"):
        parts = COMPAT_SPLIT_RE.split(title or "", maxsplit=1)
        if len(parts) > 1:
            compat_tail = parts[1].strip()
            compat_words = [w for w in re.sub(r'[^\w\u0600-\u06FF\s\+\-]', ' ', compat_tail).split() if w.lower() not in ("من", "مع", "لون", "ماركة")][:4]
            if compat_words:
                short_compat = " ".join(compat_words)
                spec_ar.append(f"(متوافق مع {short_compat})")

    return spec_ar, spec_en


_DANGLING_AR_WORDS = {
    "من", "مع", "في", "على", "إلى", "الى", "عن", "بـ", "لـ", "او", "أو", "و",
    "مزود", "مزودة", "مصنوع", "مصنوعة", "قابلة", "قابل", "متعدد", "متعددة", "ذات", "بها", "خاصية",
}

def _clean_natural_ar_fallback(title, brand_en=""):
    t = re.sub(r'[\(\[\{].*?[\)\]\}]', ' ', title or "")
    t = re.sub(r'[,،؛|]+', ' ', t)
    if brand_en:
        for ar_k, en_v in RAW_BRAND_EN_MAP.items():
            if en_v.lower() == brand_en.lower() and re.search(r'[\u0600-\u06FF]', ar_k):
                t = re.sub(rf'(?:\bمن\s+)?\b{re.escape(ar_k)}\b', ' ', t)
    words = [
        w for w in t.split()
        if len(w) > 1 and w.lower() not in ("أصلي", "اصلي", "جديد", "عرض", "خصم")
    ][:8]
    while words and norm_ar_token(words[-1]) in {norm_ar_token(d) for d in _DANGLING_AR_WORDS}:
        words.pop()
    res = " ".join(words).strip()
    if brand_en and brand_en.lower() not in res.lower():
        res = f"{res} {brand_en}".strip()
    return res[:85]


def _clean_en_official_title(en_title, brand_en=""):
    """ينظف العنوان الإنجليزي الرسمي للمتجر ليكون أنيقاً ومختصراً بدون حشو SEO."""
    if not en_title:
        return ""
    s = re.sub(r'[\u0600-\u06FF]+', ' ', str(en_title))
    s = re.sub(r'\s+', ' ', s).strip()
    if len(s) < 5:
        return ""
    # قص الحشو الدعائي الطويل بعد الفاصلة أو الشرطة إذا كان الجزء الأول وافياً
    clauses = re.split(r'\s*(?:\||–|—|\s-\s|,)\s*', s)
    picked = clauses[0].strip()
    if len(picked.split()) < 4 and len(clauses) > 1:
        picked = f"{picked} {clauses[1].strip()}".strip()
    words = picked.split()[:9]
    while words and words[-1].lower() in ("for", "with", "and", "or", "in", "to", "of", "by", "the", "a", "an"):
        words.pop()
    out = " ".join(words).strip(" ,.-—|")
    if not out:
        return ""
    if brand_en and brand_en.lower() not in out.lower():
        out = f"{brand_en} {out}".strip()
    return out[:85]


def _clean_en_slug_title(en_slug, brand_en=""):
    if not en_slug:
        return ""
    s = en_slug.strip()
    if "://" in s:
        m_noon = re.search(r'noon\.com/[a-z]{2,5}-en/([^/?#]+)/[A-Z0-9]{8,}/p', s, re.I)
        m_amz = re.search(r'amazon\.[a-z.]+/(?:-/en/)?([^/?#]+)/dp/[A-Z0-9]{10}', s, re.I)
        if m_noon:
            s = m_noon.group(1)
        elif m_amz and not re.search(r'%[0-9A-F]{2}', m_amz.group(1), re.I):
            s = m_amz.group(1)
        else:
            return ""
    s = re.sub(r'[-_]+', ' ', s).strip()
    if not s or re.search(r'[\u0600-\u06FF]', s):
        return ""
    words = []
    for raw_w in s.split():
        if not words or words[-1].lower() != raw_w.lower():
            words.append(raw_w)
    words = words[:9]
    titled = []
    for w in words:
        if w.upper() in ("USB", "HDMI", "LED", "LCD", "QLED", "OLED", "UHD", "FHD", "HD", "ANC", "ENC", "TWS", "RGB", "ARGB", "PWM", "SSD", "RAM", "5G", "4K", "3K", "2K", "PD", "GAN"):
            titled.append(w.upper())
        elif re.match(r'^\d+(?:gb|tb|mah|w|l|ml|kg|hz|mp|mm)$', w, re.I):
            titled.append(w.upper().replace("MAH", "mAh").replace("ML", "ml").replace("KG", "kg").replace("HZ", "Hz").replace("MM", "mm"))
        else:
            titled.append(w.capitalize())
    out = " ".join(titled)
    if brand_en and brand_en.lower() not in out.lower():
        out = f"{brand_en} {out}"
    return out[:85].strip()


def analyze_product(
    title,
    brand=None,
    features=None,
    extra_desc=None,
    en_slug=None,
    breadcrumbs=None,
    specs=None,
    image_url=None,
    price=None,
    use_vision=True,
    allow_network_translate=True,
    product_url=None,
    en_title=None,
    en_brand=None,
    en_breadcrumbs=None,
):
    """
    المحلل الذكي ثلاثي المصادر للمنتج (Tri-Modal Consensus V2):
    يجمع ويقارن بين:
      1) النسخة الإنجليزية الرسمية للمتجر (en_title + en_brand + en_breadcrumbs من /-/en/dp/ أو /egypt-en/)
      2) النسخة العربية الكاملة (العنوان + الوصف + المواصفات + مسار الفئة + السعر)
      3) الرؤية الحاسوبية لصورة المنتج الحقيقية (CLIP Vision ONNX)
    فيكتشف فوراً أي ترجمة عربية آلية تالفة في أمازون/نون (مثل تسمية شاحن حائط UGREEN كابلاً!)
    ويمنع تماماً ظهور "Featured Product" أو ترجمة أسماء الماركات دلالياً.
    """
    t_clean = re.sub(r'\s+', ' ', str(title or "")).strip()
    feats_list = [str(f).strip() for f in (features or []) if f and str(f).strip()]
    specs_list = [str(s).strip() for s in (specs or []) if s and str(s).strip()]
    crumbs_str = " > ".join(breadcrumbs) if isinstance(breadcrumbs, (list, tuple)) else str(breadcrumbs or "")
    full_context_text = " | ".join(feats_list + specs_list + ([str(extra_desc)] if extra_desc else []))

    # 0. جلب الحقيقة الرسمية بالإنجليزية من المتجر تلقائياً لأي رابط أمازون مصر عندما لا تكون ممررة مسبقاً
    en_t_clean = re.sub(r'\s+', ' ', str(en_title or "")).strip()
    en_b_clean = str(en_brand or "").strip()
    en_bc_list = list(en_breadcrumbs) if isinstance(en_breadcrumbs, (list, tuple)) else ([en_breadcrumbs] if en_breadcrumbs else [])
    # لو الصفحة الإنجليزية أعادت نصاً عربياً بسبب كوكيز الجلسة نتجاهله ونجلب النسخة الإنجليزية النقية
    if en_t_clean and len(re.findall(r'[\u0600-\u06FF]', en_t_clean)) > len(re.findall(r'[A-Za-z]', en_t_clean)):
        en_t_clean = ""
    if en_b_clean and re.search(r'[\u0600-\u06FF]', en_b_clean):
        en_b_clean = ""
    en_bc_list = [x for x in en_bc_list if x and not re.search(r'[\u0600-\u06FF]', str(x))]

    if not en_t_clean and allow_network_translate:
        asin_src = product_url or en_slug or ""
        if extract_amazon_asin(asin_src):
            amz_en = fetch_amazon_en_metadata(asin_src)
            if amz_en:
                en_t_clean = amz_en.get("en_title") or ""
                if not en_b_clean:
                    en_b_clean = amz_en.get("en_brand") or ""
                if not en_bc_list:
                    en_bc_list = amz_en.get("en_breadcrumbs") or []

    en_crumbs_str = " > ".join(str(x).strip() for x in en_bc_list if x)
    all_crumbs_str = f"{crumbs_str} > {en_crumbs_str}".strip(" >")

    # 1. استخراج الماركة بالإنجليزية دائماً (بأولوية النسخة الإنجليزية الرسمية للمتجر + القاموس الموسع)
    brand_en = normalize_brand_english(
        brand,
        title=t_clean,
        extra_text=f"{en_slug or ''} {full_context_text}",
        en_brand=en_b_clean,
        en_title=en_t_clean,
        allow_network=allow_network_translate,
    )

    slug_en_title = _clean_en_slug_title(en_slug, brand_en=brand_en)
    en_official_clean = _clean_en_official_title(en_t_clean, brand_en=brand_en) or slug_en_title

    # 2-أ. تقييم المصدر الإنجليزي الرسمي بمفرده (غير متأثر بأي ترجمة عربية آلية مكسورة!)
    en_ref_for_cat = en_t_clean or slug_en_title
    en_scores = {}
    en_head_matched = set()
    if en_ref_for_cat or en_bc_list:
        en_scores, en_head_matched = _score_text_categories(
            en_ref_for_cat,
            en_slug="",
            breadcrumbs=en_crumbs_str,
            features_text="",
            brand_en=brand_en,
            price=price,
        )
        for bc_k, bc_v in _score_en_breadcrumbs(en_bc_list).items():
            if not _is_cat_forbidden(bc_k, brand_en=brand_en, price=price, breadcrumbs_str=all_crumbs_str, title_str=t_clean):
                en_scores[bc_k] = en_scores.get(bc_k, 0.0) + bc_v

    ranked_en = sorted(en_scores.items(), key=lambda x: x[1], reverse=True)
    en_best_cat = ranked_en[0][0] if ranked_en else None
    en_best_score = ranked_en[0][1] if ranked_en else 0.0

    # 2-ب. تقييم المصدر العربي بمفرده
    ar_scores, ar_head_matched = _score_text_categories(
        t_clean,
        en_slug="" if en_t_clean else (en_slug or ""),
        breadcrumbs=all_crumbs_str,
        features_text=full_context_text,
        brand_en=brand_en,
        price=price,
    )
    ranked_ar = sorted(ar_scores.items(), key=lambda x: x[1], reverse=True)
    ar_best_cat = ranked_ar[0][0] if ranked_ar else None
    ar_best_score = ranked_ar[0][1] if ranked_ar else 0.0

    # 3. التحقق البصري عبر صورة المنتج (CLIP Vision) وحسم التعارض بين المصادر الثلاثة
    has_ar_en_conflict = bool(en_best_cat and ar_best_cat and en_best_cat != ar_best_cat)
    vision_res = None
    should_check_vision = use_vision and bool(image_url) and (
        has_ar_en_conflict
        or (ar_best_cat is None and en_best_cat is None)
        or (not en_best_cat and (ar_best_cat in _AMBIGUOUS_TEXT_CATS or ar_best_score < 52.0 or ar_best_cat not in ar_head_matched))
    )
    if should_check_vision:
        vision_res = classify_product_image(image_url)

    ar_title_corrupted = False
    chosen_cat = ar_best_cat

    # حسم الإجماع الثلاثي (Tri-Modal Consensus):
    if en_best_cat and en_best_score >= 48.0:
        if ar_best_cat is None:
            chosen_cat = en_best_cat
        elif ar_best_cat == en_best_cat:
            chosen_cat = en_best_cat
        else:
            # تعارض صريح بين العنوان العربي والنسخة الإنجليزية الرسمية (مثل: كابل يوجرين vs UGREEN 30W GaN Wall Charger)!
            v_probs = (vision_res or {}).get("probs") or {}
            v_en = v_probs.get(en_best_cat, 0.0)
            v_ar = v_probs.get(ar_best_cat, 0.0)
            if en_best_score >= 60.0 or v_en > v_ar + 0.08 or ar_best_cat in _AMBIGUOUS_TEXT_CATS:
                chosen_cat = en_best_cat
                ar_title_corrupted = True
            else:
                chosen_cat = ar_best_cat

    # في حال عدم توفر حسم إنجليزي (أو لمزيد من التدقيق البصري عندما يغيب النص الإنجليزي)
    is_placeholder_title = (
        not t_clean
        or len(t_clean) < 8
        or any(ph in t_clean for ph in ("منتج على نون", "منتج على أمازون", "منتج مميز على"))
    )
    if vision_res and not (en_best_cat and en_best_score >= 60.0 and chosen_cat == en_best_cat):
        v_cat = vision_res["top_cat"]
        v_prob = vision_res["top_prob"]
        v_cos = vision_res.get("max_cos", 0.0)
        v_sec_prob = vision_res.get("second_prob", 0.0)
        v_probs = vision_res.get("probs") or {}

        if v_cat in CATEGORY_BY_KEY and not _is_cat_forbidden(v_cat, brand_en, price, all_crumbs_str, title_str=t_clean):
            if chosen_cat is None:
                non_device_ar_hint = bool(re.search(r'كتاب|رواية|قلم|أقلام|شامبو|كريم|غسول|صابون|عطر|شاي|قهوة|زيت|مكرونة|بسكويت', t_clean))
                if (is_placeholder_title and v_prob >= 0.45) or (
                    not non_device_ar_hint
                    and v_cat in _HIGH_PRECISION_VISION_CATS
                    and v_prob >= 0.50
                    and v_cos >= 0.275
                    and v_prob >= max(0.50, v_sec_prob * 2.0)
                ):
                    chosen_cat = v_cat
                    ar_title_corrupted = True
            elif v_cat != chosen_cat and chosen_cat in _AMBIGUOUS_TEXT_CATS and v_prob >= 0.46 and v_cos >= 0.27:
                # الجرابات ولاصقات الحماية تظهر بصرياً كموبايل في صور المتاجر، فلا نلغيها لو مكتوبة صراحةً في أول العنوان
                is_case_or_glass = (
                    chosen_cat in ("protective_case", "screen_protector")
                    and re.match(r'^\s*(?:[\w\u0600-\u06FF]+\s+)?(?:جراب|كفر|حافظة|واقي|لاصقة|سكرين)', t_clean)
                )
                # لو الصورة تؤكد بقوة عالية (>52%) أنها منتج مختلف تماماً (مثل شاحن حائط أو غلاية) واحتمال الفئة النصية في الصورة ضئيل (<12%) -> نصحح الفئة فوراً!
                strong_visual_contradiction = (v_prob >= 0.52 and v_probs.get(chosen_cat, 0.0) < 0.12)
                if not is_case_or_glass and (strong_visual_contradiction or chosen_cat not in ar_head_matched):
                    chosen_cat = v_cat
                    ar_title_corrupted = True

    # 4. بناء الاسم العربي والاسم الإنجليزي بذكاء ودقة (مع استبعاد العنوان العربي التالف من استخراج المواصفات!)
    title_for_specs = "" if ar_title_corrupted else t_clean
    specs_ar_list, specs_en_list = _extract_rich_specs(
        title_for_specs,
        en_slug="" if (ar_title_corrupted or en_t_clean) else (en_slug or ""),
        specs_text="" if ar_title_corrupted else " ".join(specs_list),
        cat_key=chosen_cat or "",
        brand_en=brand_en,
        en_title=en_t_clean or (slug_en_title if ar_title_corrupted else ""),
    )
    spec_ar_str = " ".join(specs_ar_list).strip()
    spec_en_str = " ".join(specs_en_list).strip()

    if chosen_cat and chosen_cat in CATEGORY_BY_KEY:
        _, _, cat_ar, cat_en, cat_fallback_desc = CATEGORY_BY_KEY[chosen_cat]

        if brand_en and brand_en.lower() not in spec_ar_str.lower() and brand_en.lower() not in cat_ar.lower():
            name_ar = f"{cat_ar} {brand_en} {spec_ar_str}".strip()
        else:
            name_ar = f"{cat_ar} {spec_ar_str}".strip()

        if brand_en and brand_en.lower() not in spec_en_str.lower() and brand_en.lower() not in cat_en.lower():
            built_en = f"{brand_en} {spec_en_str} {cat_en}".strip()
        else:
            built_en = f"{spec_en_str} {cat_en}".strip()

        # لو لم نستخرج موديل محدد وكان لدينا عنوان إنجليزي رسمي أنيق من المتجر، نحتفظ به ليكون غنياً ودقيقاً
        if not spec_en_str and en_official_clean and len(en_official_clean) >= 10:
            built_en = en_official_clean
        elif not re.search(r'[\u0600-\u06FF]', t_clean) and len(t_clean) >= 8 and not spec_en_str:
            short_orig_en = " ".join(t_clean.split()[:8]).strip(" ,.-")
            built_en = f"{brand_en} {short_orig_en}".strip() if (brand_en and brand_en.lower() not in short_orig_en.lower()) else short_orig_en

        name_en = built_en
    else:
        cat_fallback_desc = None
        if re.search(r'[\u0600-\u06FF]', t_clean) and not ar_title_corrupted:
            name_ar = _clean_natural_ar_fallback(t_clean, brand_en=brand_en)
        else:
            src_en_for_ar = en_official_clean or t_clean
            tr_to_ar = ""
            if allow_network_translate and src_en_for_ar:
                try:
                    r_ar = requests.get(
                        "https://translate.googleapis.com/translate_a/single",
                        params={"client": "gtx", "sl": "en", "tl": "ar", "dt": "t", "q": src_en_for_ar[:120]},
                        timeout=3.0,
                    )
                    if r_ar.ok:
                        tr_to_ar = "".join(seg[0] for seg in (r_ar.json()[0] or []) if seg and seg[0]).strip()
                except Exception:
                    pass
            name_ar = _clean_natural_ar_fallback(tr_to_ar or src_en_for_ar, brand_en=brand_en)

        if en_official_clean:
            name_en = en_official_clean
        elif not re.search(r'[\u0600-\u06FF]', t_clean) and len(t_clean) >= 6:
            short_en = " ".join(t_clean.split()[:8]).strip(" ,.-")
            name_en = f"{brand_en} {short_en}".strip() if (brand_en and brand_en.lower() not in short_en.lower()) else short_en
        else:
            tr_en = translate_ar_to_en_fast(name_ar, timeout=3.5) if allow_network_translate else ""
            if tr_en:
                name_en = f"{brand_en} {tr_en}".strip() if (brand_en and brand_en.lower() not in tr_en.lower()) else tr_en
            else:
                tr_translit = transliterate_ar_to_en(name_ar)
                name_en = tr_translit if len(tr_translit) >= 5 else (f"{brand_en} Product".strip() if brand_en else "Selected Deal")

    # تنظيف صارم يضمن عدم وجود أي حرف عربي في السطر الإنجليزي أبداً
    name_en = re.sub(r'[\u0600-\u06FF]+', ' ', name_en)
    name_en = re.sub(r'\s+', ' ', name_en).strip(" -—,:;.")
    if len(re.findall(r'[A-Za-z]{2,}', name_en)) == 0:
        name_en = en_official_clean or (f"{brand_en} Product".strip() if brand_en else "Selected Deal")

    name_ar = re.sub(r'\s+', ' ', name_ar).strip(" -—,:;.")[:88]
    name_en = name_en[:88]

    # 5. بناء الوصف العربي الدقيق (مع تجاهل نقاط الوصف العربية إن كان العنوان العربي للصفحة تالفاً)
    safe_feats = [] if ar_title_corrupted else feats_list
    safe_extra = None if ar_title_corrupted else extra_desc
    description = build_smart_description(
        name_ar if ar_title_corrupted else t_clean,
        features=safe_feats,
        extra_desc=safe_extra,
        brand_en=brand_en,
        cat_key=chosen_cat,
        cat_fallback_desc=cat_fallback_desc,
    )

    return {
        "brand_en": brand_en,
        "cat_key": chosen_cat,
        "name_ar": name_ar,
        "name_en": name_en,
        "description": description,
        "vision": vision_res,
        "ar_title_corrupted": ar_title_corrupted,
    }


def build_smart_description(title, features=None, extra_desc=None, brand_en="", cat_key=None, cat_fallback_desc=None):
    """يبني وصفاً عربياً نظيفاً ودقيقاً يشرح المنتج الحقيقي بدون أخطاء تصنيف أو حشو."""
    noise_phrases = (
        "حول هذه السلعة", "بلد المنشأ", "رقم الموديل", "تاريخ توفر", "ضمان",
        "أبعاد", "الوزن:", "وزن السلعة", "العلامة التجارية:", "الماركة:",
        "لو اشتريت منتج من نون", "تقديم التقييم", "نحن نفخر بدعم جميع منتجاتنا",
    )
    clean_ar_feats = []
    for f in (features or []):
        fc = re.sub(r'\s+', ' ', str(f)).strip()
        if any(np in fc for np in noise_phrases):
            continue
        if len(fc) >= 18 and re.search(r'[\u0600-\u06FF]', fc):
            clean_ar_feats.append(fc)

    if clean_ar_feats:
        desc_text = "؛ ".join(clean_ar_feats[:2])
        if len(desc_text) > 220:
            desc_text = desc_text[:220].rsplit(" ", 1)[0]
        if not desc_text.endswith("."):
            desc_text += "."
        return desc_text

    if extra_desc and len(str(extra_desc).strip()) > 18:
        ce = re.sub(r'\s+', ' ', str(extra_desc).strip())
        if re.search(r'[\u0600-\u06FF]', ce) and not any(np in ce for np in noise_phrases):
            if len(ce) > 210:
                ce = ce[:210].rsplit(" ", 1)[0] + "."
            elif not ce.endswith("."):
                ce += "."
            return ce

    b_suffix = f" من {brand_en}" if brand_en else ""
    if not cat_fallback_desc and cat_key and cat_key in CATEGORY_BY_KEY:
        cat_fallback_desc = CATEGORY_BY_KEY[cat_key][4]

    if cat_fallback_desc:
        if brand_en and brand_en.lower() not in cat_fallback_desc.lower():
            first_comma = cat_fallback_desc.find("،")
            if 5 < first_comma < 50:
                return cat_fallback_desc[:first_comma] + b_suffix + cat_fallback_desc[first_comma:]
            m_clause = re.search(
                r'\s+(?=(?:بشاشة|بصوت|بتصميم|بتدفق|بتبريد|ببرامج|بمعالج|بمحرك|بشفرات|بوعاء|بسرعات|بدقة|بمعدل|بتركيبة|بخامات|بقوة|بسعة|يدعم|تدعم|يمنحك|تمنحك|تتميز|يتميز|يجمع|تجمع|تستخلص|لتحضير|لتنظيف|لتصفيف|لتبريد|لتشغيل|لنقل|لوضع|لحماية|لفرم|لحمل|يوفر|تساعدك))',
                cat_fallback_desc,
            )
            if m_clause and 6 <= m_clause.start() <= 60:
                return cat_fallback_desc[:m_clause.start()] + b_suffix + cat_fallback_desc[m_clause.start():]
            return f"{cat_fallback_desc.rstrip('.')} ({brand_en})."
        return cat_fallback_desc

    clean_t = _clean_natural_ar_fallback(title, brand_en="")
    return f"منتج عملي عالي الجودة والاعتمادية{b_suffix} ({clean_t})، مصمم بخامات متينة لتقديم أداء ممتاز وقيمة حقيقية مقابل السعر."
