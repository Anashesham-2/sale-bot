import io
import json
import os
import re
import threading
import requests

# ---------------------------------------------------------------------------
# 1. قاموس شامل لأشهر الماركات العالمية والمحلية في أمازون مصر ونون مصر (350+ ماركة)
#    يضمن كتابة الماركة دائماً بالإنجليزية الصحيحة والنظيفة في كل الرسائل.
# ---------------------------------------------------------------------------
_GENERIC_BRAND_SET = {
    "generic", "عام", "أخرى", "اخرى", "other", "others", "no brand", "unbranded",
    "بدون ماركة", "بدون علامة تجارية", "غير محدد", "n/a", "oem", "none", "unknown",
    "جينيريك", "جينريك", "متنوع", "متعدد", "brand",
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
    "اي لوك": "iLock", "آي لوك": "iLock", "اى لوك": "iLock", "ilock": "iLock", "i-lock": "iLock",
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
    "ترافل": "Travel", "travel": "Travel",
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
    "أكانه": "Akane", "اكانه": "Akane", "akane": "Akane",
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
    "ميبيلين": "Maybelline", "maybelline": "Maybelline",
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
}

NORM_BRAND_EN_MAP = {}
for _k, _v in RAW_BRAND_EN_MAP.items():
    NORM_BRAND_EN_MAP[norm_ar_token(_k)] = _v
    NORM_BRAND_EN_MAP[_k.lower().strip()] = _v

# كلمات تقنية لا نعتبرها أسماء ماركات عند البحث عن اسم لاتيني
_NON_BRAND_LATIN = {
    "usb", "led", "lcd", "oled", "amole", "amoled", "qled", "uhd", "fhd", "hd", "ips",
    "pro", "max", "plus", "mini", "lite", "ultra", "air", "neo", "tws", "anc", "enc",
    "rgb", "wifi", "bluetooth", "gps", "nfc", "pd", "gan", "qc", "type", "aux", "hdmi",
    "vga", "lan", "ssd", "hdd", "ram", "rom", "cpu", "gpu", "fps", "dpi", "mah", "watt",
    "egp", "new", "for", "with", "and", "the", "pack", "pcs", "set", "kit", "box", "bag",
    "car", "home", "smart", "fast", "super", "power", "water", "series", "gen", "model",
}

_AR_TRANSLIT_TABLE = {
    'ا': 'a', 'أ': 'a', 'إ': 'e', 'آ': 'a', 'ب': 'b', 'ت': 't', 'ث': 'th',
    'ج': 'g', 'ح': 'h', 'خ': 'kh', 'د': 'd', 'ذ': 'z', 'ر': 'r', 'ز': 'z',
    'س': 's', 'ش': 'sh', 'ص': 's', 'ض': 'd', 'ط': 't', 'ظ': 'z', 'ع': 'a',
    'غ': 'gh', 'ف': 'f', 'ق': 'q', 'ك': 'k', 'ل': 'l', 'م': 'm', 'ن': 'n',
    'ه': 'h', 'ة': 'a', 'و': 'o', 'ي': 'y', 'ى': 'a', 'ئ': 'e', 'ؤ': 'o', 'ء': '',
}

def transliterate_ar_to_en(text):
    """تحويل صوتي احتياطي لأي اسم ماركة عربي غير معروف إلى حروف إنجليزية نظيفة."""
    words = []
    for w in re.split(r'\s+', (text or "").strip()):
        if not w:
            continue
        if not re.search(r'[\u0600-\u06FF]', w):
            words.append(w)
            continue
        w_clean = re.sub(r'^ال', 'Al-', w)
        out = []
        for ch in w_clean:
            if ch in _AR_TRANSLIT_TABLE:
                out.append(_AR_TRANSLIT_TABLE[ch])
            elif re.match(r'[A-Za-z0-9\-]', ch):
                out.append(ch)
        s = "".join(out)
        s = re.sub(r'(.)\1{2,}', r'\1\1', s)
        if s:
            words.append(s.capitalize())
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

def translate_ar_to_en_fast(text, timeout=3.5):
    """ترجمة سريعة ومخزنة مؤقتاً لتحويل أي اسم منتج أو ماركة عربي إلى إنجليزي نظيف."""
    q = re.sub(r'\s+', ' ', (text or "")).strip()[:160]
    if not q or not re.search(r'[\u0600-\u06FF]', q):
        return q
    with _tr_lock:
        if q in _tr_cache:
            return _tr_cache[q]
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "ar", "tl": "en", "dt": "t", "q": q},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
        )
        if r.ok:
            data = r.json()
            res = "".join(seg[0] for seg in (data[0] or []) if seg and seg[0]).strip()
            res = re.sub(r'\s+', ' ', res)
            if res and not re.search(r'[\u0600-\u06FF]', res):
                with _tr_lock:
                    _tr_cache[q] = res
                    if len(_tr_cache) % 25 == 0:
                        try:
                            with open(_TR_CACHE_FILE, "w", encoding="utf-8") as f:
                                json.dump(_tr_cache, f, ensure_ascii=False)
                        except Exception:
                            pass
                return res
    except Exception:
        pass
    return ""

def save_tr_cache():
    with _tr_lock:
        try:
            with open(_TR_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_tr_cache, f, ensure_ascii=False)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# استخراج وتوحيد الماركة بالإنجليزية دائماً
# ---------------------------------------------------------------------------
COMPAT_SPLIT_RE = re.compile(
    r'\b(?:متوافق(?:ة)?\s*مع|مناسب(?:ة)?\s*لـ?|مخصص(?:ة)?\s*لـ?|مصمم(?:ة)?\s*لـ?|بديل(?:ة)?\s*لـ?|'
    r'لأجهزة|لاجهزة|لهواتف|لموبايل|لجهاز|لباور\s*بانك|'
    r'compatible\s+with|designed\s+for|fit\s+for|made\s+for|replacement\s+for|case\s+for|cover\s+for|strap\s+for)\b',
    re.IGNORECASE,
)

def normalize_brand_english(brand_raw, title="", extra_text="", allow_network=True):
    """
    يرجع دائماً اسم الماركة بالإنجليزية النظيفة فقط (مثل Philips, Xiaomi, ATA, Samsung, UGREEN).
    لا يرجع أبداً حروفاً عربية أو عبارات متجر مثل 'قم بزيارة متجر ...'.
    """
    t_full = f"{title or ''} {extra_text or ''}".strip()
    t_primary = COMPAT_SPLIT_RE.split(title or "", maxsplit=1)[0]

    # 1. تنظيف الماركة الخام من عبارات المتجر
    b = _STORE_BRAND_NOISE_RE.sub("", str(brand_raw or "")).strip()
    b = re.sub(r'[>›«»]', '', b).strip()
    if b.lower() in _GENERIC_BRAND_SET:
        b = ""

    # حالة التصحيح الخاص لترجمة أمازون الحرفية لـ Philips ('كتاب فيليب')
    if norm_ar_token(b) == norm_ar_token("كتاب فيليب") or "فيليبس" in t_primary:
        if norm_ar_token(b) == norm_ar_token("كتاب فيليب"):
            return "Philips"

    if b:
        # أ) لو الماركة فيها صيغة "عربي (English)" مثل "فريش (Fresh)" أو "Redragon (ريدراجون)"
        paren_m = re.findall(r'[A-Za-z][A-Za-z0-9\+\-\'&\.\s]{1,28}', b)
        # ب) لو الماركة مركبة بشرطة مائلة مثل "فيليبس / براون" نختار المذكورة فعلاً في العنوان
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

        # لو كان فيها جزء إنجليزي صريح ونظيف بين قوسين مثل "فريش (Fresh)"
        if paren_m and re.search(r'[\u0600-\u06FF]', b):
            cand = paren_m[0].strip()
            if cand.lower() not in _GENERIC_BRAND_SET:
                return NORM_BRAND_EN_MAP.get(cand.lower(), cand)

        # لو الماركة أصلاً بالإنجليزي بالكامل
        if not re.search(r'[\u0600-\u06FF]', b):
            # الحفاظ على حالة الأحرف الرسمية إن كانت كلها حروف صغيرة
            if b.islower() and len(b) > 3:
                return b.title()
            return b[:40]

    # 2. البحث عن الماركة داخل الجزء الأساسي من العنوان (قبل متوافق مع) أو صيغة "من <ماركة>"
    if t_primary:
        tp_norm = norm_ar_token(t_primary)
        # فحص صيغة "من <ماركة>" الشائعة جداً في أمازون ونون (مثل: من فيليبس، من تروفال، من كاستويف)
        for m_from in re.finditer(r'\bمن\s+([\w\u0600-\u06FF]+(?:\s+[\w\u0600-\u06FF]+)?)', t_primary):
            phrase = m_from.group(1).strip()
            for candidate in (phrase, phrase.split()[0]):
                cn = norm_ar_token(candidate)
                if cn in NORM_BRAND_EN_MAP:
                    return NORM_BRAND_EN_MAP[cn]

        # فحص أول 6 كلمات من العنوان الأساسي
        head_words = norm_ar_token(" ".join(t_primary.split()[:7]))
        # نرتب المفاتيح الأطول أولاً لمنع التداخل الجزئي (مثل لوريال باريس قبل لوريال)
        for k_norm in sorted(NORM_BRAND_EN_MAP.keys(), key=len, reverse=True):
            if len(k_norm) < 2:
                continue
            if re.search(r'(?:^|\s)' + re.escape(k_norm) + r'(?:\s|$)', head_words):
                return NORM_BRAND_EN_MAP[k_norm]

    # 3. لو الماركة المعطاة بالعربي ولم نجدها في القاموس: نحولها لإنجليزي نظيف
    if b and re.search(r'[\u0600-\u06FF]', b):
        # هل الاسم اللاتيني للماركة مكتوب أصلاً داخل العنوان؟ (مثل: أكانه صانعة القهوة akane)
        b_translit = transliterate_ar_to_en(b)
        for lat in re.findall(r'[A-Za-z][A-Za-z0-9\+\-]{2,20}', t_primary):
            if lat.lower() not in _NON_BRAND_LATIN and not re.search(r'\d', lat):
                if b_translit and lat.lower()[:2] == b_translit.lower()[:2]:
                    return lat if not lat.islower() else lat.title()

        if allow_network:
            tr_b = translate_ar_to_en_fast(b, timeout=2.5)
            tr_b = _STORE_BRAND_NOISE_RE.sub("", tr_b).strip()
            if tr_b and not re.search(r'[\u0600-\u06FF]', tr_b) and len(tr_b) <= 35:
                return tr_b.title() if tr_b.islower() else tr_b
        return b_translit[:35]

    return ""


# ---------------------------------------------------------------------------
# 2. محرك الرؤية الحاسوبية (CLIP Vision Zero-Shot عبر ONNX Runtime الخفيف والسريع)
#    يفحص صورة المنتج الحقيقية ليتعرف على ماهية المنتج بصرياً ويمنع أي تعارض مع النص!
# ---------------------------------------------------------------------------
VISION_PROMPTS = [
    ("kettle", "a product photo of an electric water kettle"),
    ("stand_fan", "a product photo of a standing pedestal fan or electric cooling fan"),
    ("tv_stick", "a product photo of an HDMI TV stick streaming media dongle with remote"),
    ("smart_tv", "a product photo of a wide flat screen television or computer monitor"),
    ("security_camera", "a product photo of a home WiFi security surveillance camera"),
    ("charging_cable", "a product photo of a USB charging cable wire cord"),
    ("wall_charger", "a product photo of a USB wall charger power adapter plug"),
    ("car_charger", "a product photo of a car cigarette lighter USB charger adapter"),
    ("wireless_charger", "a product photo of a magnetic wireless charging pad or stand"),
    ("power_bank", "a product photo of a portable power bank battery pack"),
    ("power_strip", "a product photo of an electrical power strip extension socket outlets"),
    ("usb_hub", "a product photo of a multi-port USB-C hub docking adapter"),
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
    ("cushion_chair", "a product photo of a seat cushion pillow or back support pad"),
    ("baby_chair", "a product photo of a baby high chair or stroller"),
    ("tools", "a product photo of hand tools pliers wire cutter screwdriver wrench drill hardware tool"),
    ("usb_hub", "a product photo of a multiport USB-C hub docking station adapter"),
    ("detergent", "a product photo of laundry detergent pods washing powder cleaning liquid bottle"),
    ("skin_care", "a product photo of skincare cream bottle serum lotion shower gel cosmetics"),
    ("perfume", "a product photo of a glass perfume cologne fragrance spray bottle"),
    ("diapers", "a product photo of a baby diapers jumbo pack"),
    ("tissues", "a product photo of facial tissue box or paper towel rolls"),
    ("clothing", "a product photo of clothing t-shirt pants jacket apparel"),
    ("grocery", "a product photo of food grocery jar coffee pack snack bottle"),
    ("_other_medical", "a product photo of a pill cutter medical box pharmacy accessory"),
    ("_other_hardware", "a product photo of industrial spare parts cutting blades spray can"),
    ("_other_general", "a product photo of a small household retail item accessory"),
]

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

    ("usb_hub", r'(?:\bموزع\b|محول\s*متعدد\s*المنافذ|usb(?:-?c)?\s*hub|type-?c\s*hub|\d+\s*-?\s*port\s*hub|\bhub\s*(?:lite|pro|\d)|docking\s*station|multi-?port\s*(?:hub|adapter))',
     "موزع منافذ USB-C متعدد", "Multi-Port USB-C Hub",
     "موزع منافذ متعدد عالي السرعة يوسّع مداخل اللابتوب والموبايل لتوصيل الشاشات والفلاشات والشحن السريع في وقت واحد."),

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

    ("power_strip", r'(?:مشترك\s*كهربائ?ي?|مشترك\s*(?:مضيئ|مضيء|ذكي|سلك|بمنافذ|حماية)|وصلة\s*مشترك|power\s*strip|extension\s*(?:socket|cord|lead)|surge\s*protector)',
     "مشترك كهربائي", "Power Strip Extension",
     "مشترك كهربائي آمن ومتين بمنافذ متعددة وخامات مقاومة للحرارة مع حماية متكاملة للأجهزة من تذبذب التيار والماس الكهربائي."),

    ("power_bank", r'(?:باور\s*بانك|شاحن\s*متنقل|بطارية\s*(?:متنقلة|احتياطية|محمولة)|شاحن\s*محمول|power\s*bank|portable\s*(?:charger|power))',
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

    ("wall_charger", r'(?:شاحن\s*(?:حائط|جداري|سريع|منزلي|مكتبي|أصلي|تايب\s*سي|من\s+\w+|بمنفذ|بقوة|بقدرة|gan)|راس\s*شاحن|رأس\s*شاحن|شاحن\s*r\d+|wall\s*charger|fast\s*charger|gan\s*charger|usb-?c\s*charger)',
     "شاحن سريع", "Fast Wall Charger",
     "شاحن حائط سريع يدعم تقنيات الشحن الذكي لتزويد هاتفك وأجهزتك بأعلى سرعة شحن آمنة مع حماية ضد السخونة."),

    ("audio_cable", r'(?:كابل\s*(?:صوت|aux|ستيريو)|وصلة\s*(?:صوت|aux)|سلك\s*aux|aux\s*cable|audio\s*cable|3\.5\s*mm\s*.*?\bcable\b)',
     "كابل صوت AUX", "AUX Stereo Audio Cable",
     "كابل صوت AUX مضفر عالي النقاء لنقل الصوت بوضوح تام بدون تشويش بين الموبايل والسيارة والسماعات."),

    ("hdmi_cable", r'(?:كابل\s*hdmi|وصلة\s*hdmi|سلك\s*hdmi|hdmi\s*(?:2\.\d\s*)?cable)',
     "كابل عرض HDMI", "High-Speed HDMI Cable",
     "كابل HDMI فائق السرعة لنقل الصورة والصوت بدقة عالية وثبات تام بين الشاشات والريسيفر والكمبيوتر وأجهزة الألعاب."),

    ("charging_cable", r'(?:كابل\s*(?:شحن|شاحن|بيانات|تايب\s*سي|ماج|usb|type-?c|lightning|سريع|متعدد|مضفر|r\d+)|مجموعة\s*كابل|سلك\s*شحن|وصلة\s*شحن|(?:usb-?c?|type-?c|lightning|data(?:\s*transfer)?|charging)\s*(?:to\s*[\w\-]+\s*)?cable\b)',
     "كابل شحن ونقل بيانات", "Fast Charging & Data Cable",
     "كابل شحن ونقل بيانات متين ومضفر يدعم الشحن السريع ومقاوم للثني والقطع للاستخدام اليومي المكثف."),

    ("stand_holder", r'(?:حامل\s*(?:موبايل|هاتف|لابتوب|تابلت|شاشة|سيارة|مكتب|ثلاثي|ترايبود)|ستاند\s*(?:موبايل|هاتف|لابتوب|تابلت|مكتب|تصوير)|laptop\s*stand|phone\s*(?:stand|holder|mount)|car\s*(?:mount|holder)|tablet\s*stand|\btripod\b)',
     "حامل وستاند تثبيت", "Adjustable Stand Holder",
     "حامل تثبيت متين وقابل للتعديل بزوايا مريحة وثبات عالي لوضع الموبايل أو اللابتوب في مستوى النظر المريح."),

    ("laptop", r'(?:\bلابتوب\b|لاب\s*توب|حاسوب\s*محمول|كمبيوتر\s*محمول|\blaptop\b|\bnotebook\b|\bvivobook\b|\bzenbook\b|\bideapad\b|\bthinkpad\b|\blegion\b|\bmacbook\b|\bloqs?\b|\btuf\s*gaming\b)',
     "لابتوب", "Laptop",
     "لابتوب قوي الأداء يجمع بين سرعة المعالجة والشاشة المريحة والبطارية الاعتمادية لإنجاز الدراسة والعمل والألعاب بكفاءة."),

    ("tablet", r'(?:\bتابلت\b|جهاز\s*لوحي|\bآيباد\b|\bايباد\b|\bipad\b|\btablet\b|galaxy\s*tab\b|redmi\s*pad\b|matepad\b|honor\s*pad\b)',
     "تابلت ذكي", "Smart Tablet",
     "تابلت ذكي بشاشة واسعة عالية الوضوح وأداء سلس للدراسة والترفيه وتصفح التطبيقات مع بطارية تدوم طوال اليوم."),

    ("smartwatch", r'(?:ساعة\s*[^\n،,]{0,25}?\b(?:ذكية|الذكية|سمارت)\b|ساعة\s*(?:ريدمي|شاومي|أبل|ابل|سامسونج|جالكسي|هواوي|هونر|أورايمو|اورايمو|هاينو|تتبع|رياضية)|ووتش\s*\d|smart\s*watch|\bsmartwatch\b|redmi\s*watch|apple\s*watch|galaxy\s*watch|huawei\s*watch|\bt800\b.*?\b(?:ساعة|watch)\b)',
     "ساعة ذكية", "Smartwatch",
     "ساعة ذكية أنيقة بشاشة واضحة لمتابعة الإشعارات والمكالمات والنشاط الرياضي ونبضات القلب مع بطارية طويلة العمر."),

    ("wristwatch", r'(?:ساعة\s*(?:يد|رجالي|رجالية|حريمي|نسائية|كوارتز|كلاسيك|أنالوج|انالوج|كاسيو|نافيفورس)|casio\s*.*?\bwatch\b|quartz\s*watch|analog\s*watch|chronograph\s*watch)',
     "ساعة يد أنيقة", "Wristwatch",
     "ساعة يد أنيقة بتصميم عصري وخامات متينة مقاومة للخدش تمنحك مظهراً راقياً ودقة عالية في التوقيت."),

    ("gaming_monitor", r'(?:شاشة\s*(?:ألعاب|العاب|كمبيوتر|منحنية|جيمنج)|gaming\s*monitor|curved\s*monitor|\b\d{2}\s*(?:انش|بوصة|inch)\s*\d{2,3}\s*hz\b|\bmonitor\b)',
     "شاشة كمبيوتر وألعاب", "Gaming & PC Monitor",
     "شاشة عرض عالية الدقة بمعدل تحديث سريع وألوان غنية وزوايا رؤية واسعة لتجربة ألعاب وعمل احترافية مريحة للعين."),

    ("smart_tv", r'(?:\bتلفزيون\b|\bتلفاز\b|شاشة\s*(?:تلفزيون|سمارت|ذكية\s*\d{2}|عرض\s*ذكية)|smart\s*tv|qled\s*tv|oled\s*tv|uhd\s*tv|google\s*tv|android\s*tv\s*\d{2})',
     "شاشة تلفزيون ذكية", "Smart TV",
     "شاشة تلفزيون ذكية بدقة فائقة وألوان نابضة بالحياة مع نظام ذكي مدمج لتشغيل تطبيقات المشاهدة وصوت نقي غامر."),

    ("smartphone", r'(?:\bموبايل\b|هاتف\s*(?:ذكي|محمول)|\bجوال\b|\bsmartphone\b|\biphone\s*1\d\b|موبايل\s*(?:سامسونج|شاومي|أبل|ابل|ريلمي|أوبو|اوبو|إنفينيكس|انفينكس|هونر|فيفو))',
     "موبايل ذكي", "Smartphone",
     "هاتف ذكي متكامل بمعالج قوي وشاشة سريعة الوضوح وكاميرات عالية الدقة مع بطارية كبيرة تدعم الشحن السريع."),

    ("gaming_headset", r'(?:سماعات?\s*(?:رأس\s*)?(?:ألعاب|العاب|الألعاب|للألعاب|جيمنج)|سماعة\s*رأس\s*.*?\b للألعاب\b|gaming\s*headset)',
     "سماعة رأس للألعاب", "Gaming Headset",
     "سماعة رأس احترافية للألعاب بصوت محيطي دقيق لتحديد الاتجاهات وميكروفون نقي للتواصل ووسائد أذن مريحة جداً."),

    ("headphones", r'(?:سماعات?\s*(?:رأس|راس)|فوق\s*الأذن|على\s*الأذن|over-?ear\s*headphones|wireless\s*headphones|\bheadphones\b|\bheadset\b)',
     "سماعة رأس", "Over-Ear Headphones",
     "سماعة رأس مريحة بصوت غني وواضح وعزل ممتاز للضوضاء مع وسائد ناعمة للاستماع المريح لفترات طويلة."),

    ("wired_earphones", r'(?:سماعات?\s*(?:أذن\s*|اذن\s*)?\bسلكية\b|wired\s*(?:in-?ear\s*)?(?:earphones|earbuds))',
     "سماعة أذن سلكية", "Wired In-Ear Earphones",
     "سماعة أذن سلكية، بصوت نقي وباس متوازن وميكروفون مدمج للمكالمات الواضحة مع سلك متين وتصميم مريح للأذن."),

    ("earbuds", r'(?:سماعات?\s*(?:أذن|اذن|بلوتوث|لاسلكية|ايربودز?|إيربودز?)|earbuds|airpods|true\s*wireless|\btws\b|freeclips|spacebuds)',
     "سماعة أذن لاسلكية", "True Wireless Earbuds",
     "سماعة أذن لاسلكية بصوت نقي غني بالباس وميكروفون واضح للمكالمات مع بطارية تدوم طويلاً وعلبة شحن مدمجة."),

    ("soundbar", r'(?:ساوند\s*بار|\bsoundbar\b|sound\s*bar)',
     "مكبر صوت ساوند بار", "Soundbar Speaker",
     "ساوند بار قوي يمنحك تجربة صوت سينمائي محيطي واضح وعميق للتلفزيون والأفلام والألعاب مع توصيل لاسلكي وسلكي سهل."),

    ("speaker", r'(?:مكبر\s*صوت|صب\s*بلوتوث|\bسبيكر\b|bluetooth\s*speaker|portable\s*speaker|wireless\s*speaker|party\s*speaker|\bspeaker\b)',
     "مكبر صوت بلوتوث", "Bluetooth Speaker",
     "مكبر صوت محمول بصوت قوي ونقي وباس عميق مع اتصال بلوتوث سريع وبطارية ممتازة للاستخدام في المنزل والرحلات."),

    ("stand_fan", r'(?:مروحة\s*(?:ستاند|عمود|عمودية|أرضية)|stand\s*fan|pedestal\s*fan)',
     "مروحة ستاند عمودية", "Stand Pedestal Fan",
     "مروحة ستاند قوية بتدفق هواء منعش وسرعات متعددة مع توزيع تلقائي للهواء وتشغيل هادئ وموفر للطاقة."),

    ("fan", r'(?:مروحة\s*(?:سقف|حائط|مكتب|بوكس|صندوق|تبريد|يد|محمولة)|\bمروحة\b|ceiling\s*fan|wall\s*fan|desk\s*fan|\bfan\b)',
     "مروحة تهوية وتبريد", "Cooling Fan",
     "مروحة تهوية عملية بتدفق هواء قوي وهادئ وتصميم متين لتلطيف الأجواء بكفاءة عالية."),

    ("air_conditioner", r'(?:\bتكييف\b|مكيف\s*(?:هواء|سبليت|صحراوي)|air\s*conditioner|air\s*cooler)',
     "جهاز تكييف وتبريد", "Air Conditioner",
     "جهاز تكييف وتبريد عالي الكفاءة لتبريد سريع ومثالي للغرفة مع توزيع متوازن للهواء وتوفير في استهلاك الكهرباء."),

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

    ("kettle", r'(?:\bغلاية\b|\bكاتل\b|سخان\s*مياه\s*كهربائي|electric\s*kettle|water\s*kettle|\bkettle\b)',
     "غلاية مياه كهربائية", "Electric Water Kettle",
     "غلاية مياه كهربائية سريعة الغليان بعنصر تسخين ستانلس ستيل آمن وفصل تلقائي عند الغليان وجفاف المياه."),

    ("steam_cleaner", r'(?:منظف\s*[\u200b\s]*بخاري?|جهاز\s*تنظيف\s*بالبخار|ممسحة\s*بخار|steam\s*cleaner|steam\s*mop)',
     "جهاز تنظيف بالبخار", "Handheld Steam Cleaner",
     "جهاز تنظيف بالبخار المضغوط عالي الحرارة لإذابة الدهون العنيدة وتعقيم الأسطح والمطابخ والمفروشات بدون كيماويات."),

    ("steam_iron", r'(?:\bمكواة\b|\bكواية\b|مكواة\s*بخار|بخار\s*عمودية\s*للملابس|steam\s*iron|garment\s*steamer|\biron\b)',
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

    ("clothing", r'(?:\bتيشيرت\b|\bقميص\b|\bبنطلون\b|\bبوكسر\b|\bجاكيت\b|\bترنج\b|\bسوت\b|\bفستان\b|\bبيجام[ةه]\b|\bشورت\b|\bجوارب\b|\bشراب\b|طقم\s*(?:قصة|بوكسر|ملابس|داخلي)|t-?shirt|hoodie|jacket|boxer\s*briefs)',
     "ملابس وأزياء", "Apparel & Clothing",
     "ملابس بخامات قطنية ناعمة ومريحة وقصة عملية متقنة تحافظ على رونقها وألوانها مع الغسيل والاستخدام اليومي."),

    ("perfume", r'(?:\bعطر\b|\bبرفان\b|بودي\s*(?:سبلاش|ميست)|بخاخ\s*(?:للجسم|بودي)|مزيل\s*(?:عرق|للعرق)|سبراي\s*مزيل|eau\s*de\s*(?:parfum|toilette)|body\s*(?:splash|mist|spray)|\bdeodorant\b)',
     "عطر وبخاخ للجسم", "Perfume & Body Fragrance",
     "عطر وبخاخ منعش برائحة جذابة وثبات مميز يمنحك انتعاشاً وثقة طوال اليوم."),

    ("oral_care", r'(?:معجون\s*أسنان|فرشاة\s*أسنان|غسول\s*فم|خيط\s*أسنان|toothpaste|toothbrush|mouthwash)',
     "عناية بالأسنان والفم", "Toothpaste & Oral Care",
     "منتج عناية يومية بالفم والأسنان لتنظيف فعال وحماية اللثة والأسنان مع نفس منعش يدوم طويلاً."),

    ("hair_care", r'(?:\bشامبو\b|\bبلسم\b|حمام\s*كريم|ماسك\s*شعر|زيت\s*(?:شعر|للشعر)|سيروم\s*(?:شعر|للشعر)|كريم\s*(?:شعر|تصفيف)|\bshampoo\b|\bconditioner\b|hair\s*(?:mask|serum|oil))',
     "شامبو وعناية بالشعر", "Hair Care Shampoo & Treatment",
     "تركيبة مغذية للعناية بالشعر وتنظيف فروة الرأس بلطف لتقوية الشعر ومنحه نعومة ولمعاناً صحياً."),

    ("skin_care", r'(?:غسول\s*(?:وجه|للوجه|بشرة)|جل\s*هيدرو|لتنظيف\s*الوجه|كريم\s*(?:مرطب|للوجه|لليدين|بشرة)|لوشن\s*مرطب|واقي\s*شمس|صن\s*بلوك|سيروم\s*(?:للوجه|فيتامين|هيالورونيك)|جل\s*استحمام|شاور\s*جل|صابون\s*(?:سائل|استحمام|وجه)|cleanser|face\s*wash|moisturizer|sunscreen|shower\s*gel|body\s*wash|\bserum\b)',
     "عناية بالبشرة والجسم", "Skincare & Body Wash",
     "منتج عناية لطيف وفعال ينظف ويرطب البشرة بعمق ليمنحها نضارة ونعومة وحماية يومية متكاملة."),

    ("diapers", r'(?:\bحفاضات\b|\bحفاضة\b|بامبرز\s*أطفال|مناديل\s*مبللة\s*للأطفال|\bdiapers\b|baby\s*wipes)',
     "حفاضات أطفال", "Baby Diapers Pack",
     "حفاضات أطفال فائقة الامتصاص بطبقة ناعمة لطيفة على بشرة الطفل وحواجز مانعة للتسرب لراحة وجفاف طوال اليوم."),

    ("tissues", r'(?:\bمناديل\b|\bمنديل\b|ورق\s*(?:تواليت|مطبخ|حمام)|بكرة\s*مناديل|رول\s*مطبخ|facial\s*tissues|toilet\s*paper|kitchen\s*(?:towel|rolls))',
     "مناديل ورقية", "Facial Tissues & Paper Rolls",
     "مناديل ورقية ناعمة وعالية الامتصاص بعدة طبقات متينة وموفرة للاستخدام اليومي في المنزل والمطبخ."),

    ("detergent", r'(?:مسحوق\s*غسيل|منظف\s*(?:غسيل|الغسيل|اوتوماتيك|أوتوماتيك|أطباق|أرضيات|حمامات|زجاج|مراحيض)|جل\s*(?:منظف|غسيل)|سائل\s*(?:غسيل|أطباق)|كبسولات\s*غسيل|أقراص\s*غسالة|منعم\s*أقمشة|مزيل\s*بقع|معطر\s*جو|عبوة\s*إعادة\s*تعبئة|مبيد\s*حشرات|laundry\s*detergent|dishwashing|fabric\s*softener|air\s*freshener|stain\s*remover)',
     "منظفات وعناية منزلية", "Home Cleaning & Laundry Detergent",
     "تركيبة تنظيف قوية وفعالة تزيل البقع والدهون الصعبة بسهولة وتترك رائحة منعشة ونظافة فائقة."),

    ("supplements", r'(?:واي\s*بروتين|\bبروتين\b|مكمل\s*(?:غذائي|مركز)|أوميجا\s*3|اوميجا\s*3|زيت\s*السمك|\bفيتامين\b|فيتامينات|\bكولاجين\b|\bكرياتين\b|whey\s*protein|mass\s*gainer|omega[\s\-]*3|fish\s*oil|multivitamin)',
     "مكمل غذائي وفيتامينات", "Nutritional Supplement & Vitamins",
     "مكمل غذائي عالي الجودة بتركيبة مركزة لدعم الطاقة والنشاط البدني والاحتياجات الغذائية اليومية."),

    ("coffee_drink", r'(?:قهوة\s*(?:فورية|سريعة\s*التحضير|تركية|عربي|مطحونة|من\s+\w+|بحبيبات|اسبريسو\s*مطحونة)|برطمان\s*قهوة|كبسولات\s*(?:قهوة|نسبرسو)|مبيض\s*قهوة|كوفي[\s\-]*ميت|\bشاي\b|نسكافيه\s*(?:جولد|كلاسيك|3\s*في\s*1)|instant\s*coffee|ground\s*coffee|coffee\s*beans|coffee\s*capsules|tea\s*bags)',
     "قهوة ومشروبات", "Coffee & Beverages",
     "قهوة ومشروبات بمذاق غني ورائحة محمصة مميزة تمنحك كوباً متوازناً ومنعشاً في كل صباح."),

    ("grocery", r'(?:زيت\s*(?:دوار\s*الشمس|ذرة|زيتون|طهي|قلي|مخلوط|جوز\s*الهند)|\bسمن\b|\bزبدة\b|كريمة\s*فول\s*سوداني|زبدة\s*فول\s*سوداني|\bدقيق\b|\bأرز\b|\bمكرونة\b|\bعسل\b|\bمربى\b|\bشوكولاتة\b|\bبسكويت\b|\bتونة\b|\bصلصة\b|\bمكسرات\b|sunflower\s*oil|cooking\s*oil|olive\s*oil|peanut\s*butter)',
     "منتجات غذائية وسوبرماركت", "Grocery & Food Essentials",
     "منتج غذائي عالي الجودة بمكونات مختارة بعناية ومذاق رائع للاستخدام اليومي في المطبخ."),

    ("auto_care", r'(?:ماء\s*مساحات|زيت\s*محرك|ملمع\s*(?:تابلوه|إطارات)|منفاخ\s*إطارات|مساحات\s*زجاج|شامبو\s*سيارات|motor\s*oil|windshield\s*washer)',
     "عناية ومستلزمات سيارات", "Car Care & Automotive",
     "منتج عملي للعناية بالسيارة والحفاظ على كفاءة التشغيل والنظافة بأداء موثوق."),
]

CATEGORY_BY_KEY = {row[0]: row for row in SMART_CATEGORIES}

# الفئات المعرضة للالتباس النصي لو ذُكرت ككلمة فرعية في آخر العنوان (تراجعها الرؤية الحاسوبية بقوة)
_AMBIGUOUS_TEXT_CATS = {
    "charging_cable", "wall_charger", "stand_holder", "smart_tv",
    "smartphone", "power_bank", "food_chopper", "cushion_chair",
}

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


def _clean_for_cat_match(text):
    if not text:
        return ""
    s = _NEGATED_NOUN_RE.sub(" ", str(text))
    s = re.sub(r'[\u200b-\u200f\xa0]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def _score_text_categories(title, en_slug="", breadcrumbs="", features_text=""):
    """
    يحسب نقاط كل فئة بذكاء سياقي كامل:
    - مسار الفئة في المتجر (Breadcrumbs): وزن 45 نقطة
    - بداية العنوان قبل (متوافق مع / مع / بدون): وزن 40 نقطة + مكافأة الكلمات الأولى (+25)
    - الاسم الإنجليزي الرسمي (en_slug): وزن 32 نقطة للبداية و14 للباقي
    - باقي العنوان قبل (متوافق مع): وزن 12 نقطة
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
            sc += 45.0
            head_matched_cats.add(cat_key)

        if c_head:
            m = re.search(pat, c_head, re.IGNORECASE)
            if m:
                # مكافأة كبيرة لو الكلمة المفتاحية في أول 35 حرف من العنوان (اسم المنتج الحقيقي)
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
    # 1) مشغل الوسائط TV Stick يلغي التلفزيون Smart TV تماماً
    if "tv_stick" in scores:
        scores["tv_stick"] += 40.0
        scores.pop("smart_tv", None)
    # 2) مروحة ستاند أو عجان ستاند أو مكواة ستاند تلغي حامل الموبايل Stand Holder تماماً
    if any(k in scores for k in ("stand_fan", "fan", "stand_mixer", "steam_iron", "baby_chair")):
        scores.pop("stand_holder", None)
    # 3) الساعة الذكية وسوار الساعة يلغيان الموبايل والشاشة الذكية
    if "watch_strap" in head_matched_cats:
        scores["watch_strap"] += 35.0
        scores.pop("smartwatch", None)
        scores.pop("smartphone", None)
    elif "smartwatch" in scores and "smartwatch" in head_matched_cats:
        scores["smartwatch"] += 30.0
        scores.pop("smartphone", None)
        scores.pop("smart_tv", None)
        scores.pop("gaming_monitor", None)
    # 4) جراب الحماية ولاصقة الشاشة في بداية العنوان يلغيان الجهاز المتوافق معه (موبايل/تابلت/باور بانك/لابتوب)
    for acc_k in ("protective_case", "screen_protector", "laptop_bag", "laptop_cooler", "laptop_charger"):
        if acc_k in head_matched_cats:
            scores[acc_k] += 35.0
            for dev_k in ("smartphone", "tablet", "power_bank", "laptop", "earbuds"):
                if dev_k not in head_matched_cats:
                    scores.pop(dev_k, None)
    # 5) كابل شحن صريح في أول العنوان يلغي الشاحن الجداري (مثل: كابل شاحن سريع 66W)
    if "charging_cable" in head_matched_cats and "wall_charger" in scores:
        if not re.search(r'^\s*(?:[\w\u0600-\u06FF]+\s+)?(?:شاحن|مجموعة\s*شاحن|راس\s*شاحن|wall\s*charger)', c_head, re.I):
            scores.pop("wall_charger", None)
    # 6) سماعة الرأس للألعاب أو فوق الأذن تلغي إيربودز الأذن
    if any(k in head_matched_cats for k in ("gaming_headset", "headphones", "wired_earphones")):
        scores.pop("earbuds", None)
    # 7) القهوة سريعة التحضير/الحبيبات بدون كلمة "ماكينة/صانعة" تلغي ماكينة القهوة
    if "coffee_drink" in scores and "coffee_maker" not in head_matched_cats:
        scores.pop("coffee_maker", None)

    return scores, head_matched_cats


# ---------------------------------------------------------------------------
# 4. استخراج المواصفات الدقيقة وبناء الاسم العربي والإنجليزي والوصف الذكي
# ---------------------------------------------------------------------------
def _extract_rich_specs(title, en_slug="", specs_text="", cat_key="", brand_en=""):
    """يستخرج الموديل والأرقام الجوهرية المناسبة لنوع المنتج بدقة بدون حشو عشوائي."""
    combined = f"{title or ''} {re.sub(r'[-_]+', ' ', en_slug or '')} {specs_text or ''}"
    primary = COMPAT_SPLIT_RE.split(title or "", maxsplit=1)[0]
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
            # يدعم "جالاكسي اس S25 الترا" و "Galaxy A55" و "Tab S9 FE"
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

    # 2. اللابتوب
    if cat_key == "laptop":
        m_lap = re.search(r'\b(Vivobook\s*\w*|Zenbook\s*\w*|IdeaPad\s*(?:Gaming\s*)?\w*|ThinkPad\s*\w*|LOQ\s*\w*|Legion\s*\w*|Inspiron\s*\w*|Vostro\s*\w*|Victus\s*\w*|Pavilion\s*\w*|OmniBook\s*\w*|TUF\s*Gaming\s*\w*|ROG\s*\w*|MacBook\s*(?:Air|Pro)\s*(?:M\d)?|Aspire\s*\w*|Nitro\s*\w*)\b', combined, re.I)
        if m_lap:
            v = re.sub(r'\s+', ' ', m_lap.group(1)).strip()
            spec_ar.append(v)
            spec_en.append(v)
        m_cpu = re.search(r'\b(Core\s*(?:Ultra\s*)?i?[3579](?:-\d{4,5}[A-Z]*)?|Ryzen\s*[3579](?:\s*\d{4}[A-Z]*)?|Apple\s*M[1-5](?:\s*Pro|\s*Max)?)\b', combined, re.I)
        if m_cpu:
            c = re.sub(r'\s+', ' ', m_cpu.group(1)).strip()
            spec_ar.append(c)
            spec_en.append(c)
        m_ram = re.search(r'\b(8|12|16|24|32|64)\s*(?:GB\s*RAM|جيجا\s*رام)\b', combined, re.I)
        if m_ram:
            spec_ar.append(f"{m_ram.group(1)} جيجا رام")
            spec_en.append(f"{m_ram.group(1)}GB RAM")
        m_ssd = re.search(r'\b(256|512)\s*(?:GB\s*SSD|جيجا\s*SSD)\b|\b(1|2)\s*TB\s*SSD\b', combined, re.I)
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

    # 4. الساعات الذكية
    if cat_key == "smartwatch":
        m_sw = re.search(r'(?:Redmi\s*Watch\s*\d+\s*(?:Lite|Active)?|Watch\s*\d+\s*(?:Active|Lite|Pro|Ultra)?|ووتش\s*\d+\s*(?:اكتيف|لايت|برو)?|ريدمي\s*(?:ووتش\s*)?\d+\s*(?:لايت|اكتيف)?|Band\s*\d+\s*(?:Pro|Active)?|\bT800\s*(?:Ultra)?\b)', combined, re.I)
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
        return spec_ar, spec_en

    # 6. استخراج رقم/اسم الموديل العام (مثل Tapo C202, C530WS, OTW-323, R50i, HD9314, fx-570ES, Go 4, FreeClips, Zeus H510)
    m_named = re.search(
        r'\b(Tapo\s*[A-Z]?\d{2,4}[A-Z]*|OneBlade|FreeClips|SpaceBuds(?:\s*Neo)?|Zeus\s*(?:H\d+)?|'
        r'Go\s*[34]|Flip\s*[56]|Charge\s*5|Wave\s*(?:Beam|Buds|Flex)|Life\s*[APQ]\d\w*|Liberty\s*\d\w*|'
        r'R50i|P20i|K20i|OEP[\s\-]?\d{3}|OTW[\s\-]?\d{3}|OCF[\s\-]?\d{3}[A-Z]?|'
        r'[Ff][Xx][\s\-]?\d{2,4}[A-Za-z]+|HD\d{4}(?:/\d{2})?|KM\d{4,5}[A-Z]?|'
        r'C\d{3}[A-Z]{1,3}|TC\d{2,3}|GS\d{3}|H\d{3}|M\d{3}|VC\d{3})\b',
        primary + " " + re.sub(r'[-_]+', ' ', en_slug or ""),
        re.I,
    )
    if m_named:
        mv = re.sub(r'\s+', ' ', m_named.group(1)).strip()
        if re.match(r'^fx', mv, re.I):
            mv = "fx-" + re.sub(r'^[Ff][Xx][\s\-]*', '', mv).upper()
        elif re.match(r'^(?:R50i|P20i|K20i)$', mv, re.I):
            mv = mv[0].upper() + mv[1:-1] + "i"
        elif re.match(r'^(?:OEP|OTW|OCF|HD|KM|TC|GS|VC|C\d)', mv, re.I):
            mv = mv.upper()
        else:
            _casing_map = {
                "freeclips": "FreeClips", "spacebuds": "SpaceBuds", "oneblade": "OneBlade",
                "tapo": "Tapo", "zeus": "Zeus", "neo": "Neo", "liberty": "Liberty",
                "wave": "Wave", "beam": "Beam", "buds": "Buds", "flex": "Flex",
                "life": "Life", "charge": "Charge", "flip": "Flip", "go": "Go",
            }
            mv = " ".join(_casing_map.get(tok.lower(), tok.upper() if re.match(r'^[A-Za-z]\d+[A-Za-z]*$', tok) else tok) for tok in mv.split())
        if mv.lower() != (brand_en or "").lower():
            spec_ar.append(mv)
            spec_en.append(mv)

    # دقة الكاميرات الأمنية
    if cat_key == "security_camera":
        for cam_q in ("4K", "3K", "2K", "5MP", "4MP", "3MP", "1080P"):
            if re.search(rf'\b{cam_q}\b', combined, re.I) and len(spec_en) < 3:
                spec_ar.append(cam_q)
                spec_en.append(cam_q)

    # سعة اللتر / المل / الجرام / الكجم / المقاس / عدد القطع حسب الفئة
    if cat_key in ("kettle", "air_fryer", "stand_mixer", "blender", "microwave", "coffee_maker", "food_chopper", "cookware", "detergent", "grocery"):
        m_lit = re.search(r'(?<![\d.])(\d{1,2}(?:\.\d)?)\s*(?:لتر|لترات|L\b|Liter)', primary + " " + (en_slug or "").replace("-", " "), re.I)
        if m_lit and 0.2 <= float(m_lit.group(1)) <= 60:
            spec_ar.append(f"سعة {m_lit.group(1)} لتر" if cat_key not in ("detergent", "grocery") else f"{m_lit.group(1)} لتر")
            spec_en.append(f"{m_lit.group(1)}L")

    if cat_key in ("washing_machine", "grocery", "detergent", "supplements", "weights_fitness"):
        m_kg = re.search(r'(?<![\d.])(\d{1,3}(?:\.\d)?)\s*(?:كجم|كيلو(?:\s*جرام)?|kg\b)', primary, re.I)
        if m_kg:
            spec_ar.append(f"{m_kg.group(1)} كجم")
            spec_en.append(f"{m_kg.group(1)}kg")

    if cat_key in ("hair_care", "skin_care", "perfume", "oral_care", "grocery", "coffee_drink"):
        m_ml = re.search(r'\b(\d{2,4})\s*(?:مل(?:لي(?:لتر)?)?|ml\b)', primary, re.I)
        if m_ml:
            spec_ar.append(f"{m_ml.group(1)} مل")
            spec_en.append(f"{m_ml.group(1)}ml")
        else:
            m_gm = re.search(r'\b(\d{2,4})\s*(?:جم|جرام|g\b|gm\b)', primary, re.I)
            if m_gm:
                spec_ar.append(f"{m_gm.group(1)} جم")
                spec_en.append(f"{m_gm.group(1)}g")

    if cat_key == "diapers":
        m_dsz = re.search(r'(?:مقاس\s*(?:حفاضة\s*)?|حجم\s*\w+\s*|حديثي\s*الولادة\s*|حديثى\s*الولاده\s*)([1-7])\b|\b([1-7])\s*-\s*\d{2}\b', primary)
        if m_dsz:
            sz = m_dsz.group(1) or m_dsz.group(2)
            spec_ar.append(f"مقاس {sz}")
            spec_en.append(f"Size {sz}")
        m_dcnt = re.search(r'\b(\d{2,3})\s*(?:حفاضة|حفاضه|قطعة|قطعه)\b|\b[1-7]\s*-\s*(\d{2,3})\b', primary)
        if m_dcnt:
            cnt = m_dcnt.group(1) or m_dcnt.group(2)
            spec_ar.append(f"({cnt} حفاضة)")
            spec_en.append(f"({cnt} Count)")

    if cat_key == "tissues":
        m_tcnt = re.search(r'\b(\d{1,4})\s*(?:منديل|بكرة|لفة|رول|قطعة)\b', primary)
        if m_tcnt:
            val = m_tcnt.group(1)
            unit_ar = "بكرة" if any(u in m_tcnt.group(0) for u in ("بكرة", "لفة", "رول")) else "منديل"
            unit_en = "Rolls" if unit_ar == "بكرة" else "Sheets"
            spec_ar.append(f"({val} {unit_ar})")
            spec_en.append(f"({val} {unit_en})")

    if cat_key in ("stand_fan", "fan"):
        m_fsz = re.search(r'\b(14|16|18|20|26|30)\s*(?:بوصة|انش|inch)\b|\b(40|45|50)\s*(?:سم|cm)\b', primary, re.I)
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
        "hair_styler", "speaker", "soundbar",
    ):
        m_w = re.search(r'(?<![A-Za-z0-9])(\d{1,4})\s*(?:وات|واط|W\b|Watt)', primary + " " + (en_slug or "").replace("-", " "), re.I)
        if m_w and 5 <= int(m_w.group(1)) <= 3500:
            # تجاهل "5W" الوهمي لباور بانك عندما يكون هناك واط أعلى أو مللي أمبير
            w_val = int(m_w.group(1))
            if not (cat_key == "power_bank" and w_val < 15):
                spec_ar.append(f"{w_val}W")
                spec_en.append(f"{w_val}W")

    if cat_key == "power_bank":
        m_mah = re.search(r'(\d{4,6})\s*(?:مللي\s*أمبير|مللي\s*امبير|mAh\b)', combined.replace(",", ""), re.I)
        if m_mah:
            spec_ar.append(f"سعة {m_mah.group(1)}mAh")
            spec_en.append(f"{m_mah.group(1)}mAh")

    if cat_key in ("power_strip", "usb_hub", "wall_charger", "car_charger"):
        m_ports = re.search(r'\b(\d{1,2})\s*(?:منافذ|مخارج|مخرج|مداخل|ports?|outlets?)\b', primary, re.I)
        if m_ports and 2 <= int(m_ports.group(1)) <= 16:
            p_cnt = m_ports.group(1)
            spec_ar.append(f"{p_cnt} منافذ")
            spec_en.append(f"{p_cnt}-Port")

    if cat_key in ("charging_cable", "audio_cable", "hdmi_cable", "power_strip"):
        m_len = re.search(r'(?<![\d.])(\d(?:\.\d)?)\s*(?:متر|م\b|m\b|meter)', primary, re.I)
        if m_len and 0.2 <= float(m_len.group(1)) <= 15:
            spec_ar.append(f"طول {m_len.group(1)}م")
            spec_en.append(f"{m_len.group(1)}m")
        if cat_key == "charging_cable" and re.search(r'usb-?c|type-?c|تايب\s*سي|نوع\s*سي', primary, re.I):
            if "USB-C" not in " ".join(spec_en):
                spec_ar.append("USB-C")
                spec_en.append("USB-C")

    # إضافة الهدف المتوافق معه باختصار أنيق للجرابات ولاصقات الشاشة والأساور فقط
    if cat_key in ("protective_case", "screen_protector", "watch_strap"):
        parts = COMPAT_SPLIT_RE.split(title or "", maxsplit=1)
        if len(parts) > 1:
            compat_tail = parts[1].strip()
            # استخراج اسم الجهاز المتوافق باختصار (أول 3-4 كلمات مفيدة)
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


def _clean_en_slug_title(en_slug, brand_en=""):
    if not en_slug:
        return ""
    s = en_slug.strip()
    if "://" in s:
        # استخراج الـ slug من روابط نون أو أمازون الإنجليزية
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
    words = s.split()[:9]
    titled = []
    for w in words:
        if w.upper() in ("USB", "HDMI", "LED", "LCD", "QLED", "OLED", "UHD", "FHD", "HD", "ANC", "ENC", "TWS", "RGB", "SSD", "RAM", "5G", "4K", "3K", "2K", "PD", "GAN"):
            titled.append(w.upper())
        elif re.match(r'^\d+(?:gb|tb|mah|w|l|ml|kg|hz|mp)$', w, re.I):
            titled.append(w.upper().replace("MAH", "mAh").replace("ML", "ml").replace("KG", "kg").replace("HZ", "Hz"))
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
    use_vision=True,
    allow_network_translate=True,
):
    """
    المحلل الذكي المتكامل للمنتج:
    يجمع بين العنوان الكامل + الوصف والمواصفات + مسار الفئة + الرابط الإنجليزي + الرؤية الحاسوبية للصورة (CLIP Vision)
    لإنتاج:
      - brand_en: الماركة بالإنجليزية دائماً
      - cat_key: الفئة الدقيقة للمنتج
      - name_ar: اسم عربي ذكي ودقيق ومطابق للصورة والمنتج
      - name_en: اسم إنجليزي نظيف 100% بدون أي حروف عربية أو أرقام عشوائية
      - description: وصف عربي دقيق ومفهوم يشرح المنتج الفعلي
    """
    t_clean = re.sub(r'\s+', ' ', str(title or "")).strip()
    feats_list = [str(f).strip() for f in (features or []) if f and str(f).strip()]
    specs_list = [str(s).strip() for s in (specs or []) if s and str(s).strip()]
    crumbs_str = " > ".join(breadcrumbs) if isinstance(breadcrumbs, (list, tuple)) else str(breadcrumbs or "")
    full_context_text = " | ".join(feats_list + specs_list + ([str(extra_desc)] if extra_desc else []))

    # 1. استخراج الماركة بالإنجليزية دائماً
    brand_en = normalize_brand_english(
        brand, title=t_clean, extra_text=f"{en_slug or ''} {full_context_text}", allow_network=allow_network_translate
    )

    # 2. التقييم النصي الشامل (العنوان + الوصف الكامل + مسار الفئة + الـ Slug الإنجليزي)
    scores, head_matched = _score_text_categories(
        t_clean, en_slug=en_slug or "", breadcrumbs=crumbs_str, features_text=full_context_text
    )

    ranked_text = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_text_cat = ranked_text[0][0] if ranked_text else None
    best_text_score = ranked_text[0][1] if ranked_text else 0.0

    # 3. التحقق البصري عبر صورة المنتج (Computer Vision)
    # يعمل دائماً عندما تكون الفئة النصية غامضة أو معرضة للخطأ أو ضعيفة أو عندما لا يوجد عنوان واضح
    vision_res = None
    should_check_vision = use_vision and bool(image_url) and (
        best_text_cat is None
        or best_text_cat in _AMBIGUOUS_TEXT_CATS
        or best_text_score < 52.0
        or best_text_cat not in head_matched
    )
    if should_check_vision:
        vision_res = classify_product_image(image_url)

    chosen_cat = best_text_cat
    is_placeholder_title = (
        not t_clean
        or len(t_clean) < 8
        or any(ph in t_clean for ph in ("منتج على نون", "منتج على أمازون", "منتج مميز على"))
    )
    if vision_res:
        v_cat = vision_res["top_cat"]
        v_prob = vision_res["top_prob"]
        v_cos = vision_res.get("max_cos", 0.0)

        # تعزيز النقاط السياقية للفئات المرشحة نصياً فقط (لمنع اختلاق فئة عشوائية لمنتج غير مصنف)
        for vc_k, vc_p in vision_res["probs"].items():
            if vc_p >= 0.08 and vc_k in scores and vc_k in CATEGORY_BY_KEY:
                scores[vc_k] = scores[vc_k] + (vc_p * 38.0)

        # قاعدة التصحيح البصري الصارم (Visual Sanity Override):
        if v_cat in CATEGORY_BY_KEY and v_cat != best_text_cat:
            if best_text_cat is None:
                # إذا كان العنوان مفقوداً أو عاماً، أو كانت الصورة واضحة بثقة فائقة جداً (>88%)
                if (is_placeholder_title and v_prob >= 0.48) or (v_prob >= 0.88 and v_cos >= 0.28):
                    chosen_cat = v_cat
            elif best_text_cat in _AMBIGUOUS_TEXT_CATS and v_prob >= 0.45:
                # لا نلغي جراب الحماية أو الكابل لو مكتوب صراحةً كأول كلمة في العنوان
                explicit_head_guard = (
                    (best_text_cat == "protective_case" and re.match(r'^\s*(?:[\w\u0600-\u06FF]+\s+)?(?:جراب|كفر|حافظة)', t_clean))
                    or (best_text_cat == "charging_cable" and re.match(r'^\s*(?:[\w\u0600-\u06FF]+\s+)?(?:كابل|سلك|وصلة)\s*(?:شحن|تايب|بيانات|usb|type)', t_clean, re.I))
                )
                if not explicit_head_guard:
                    chosen_cat = v_cat
            elif scores:
                new_ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                if new_ranked:
                    chosen_cat = new_ranked[0][0]

    # 4. بناء الاسم العربي والاسم الإنجليزي بذكاء ودقة
    specs_ar_list, specs_en_list = _extract_rich_specs(
        t_clean, en_slug=en_slug or "", specs_text=" ".join(specs_list), cat_key=chosen_cat or "", brand_en=brand_en
    )
    spec_ar_str = " ".join(specs_ar_list).strip()
    spec_en_str = " ".join(specs_en_list).strip()

    slug_en_title = _clean_en_slug_title(en_slug, brand_en=brand_en)

    if chosen_cat and chosen_cat in CATEGORY_BY_KEY:
        _, _, cat_ar, cat_en, cat_fallback_desc = CATEGORY_BY_KEY[chosen_cat]

        # الاسم بالعربي: نوع المنتج الدقيق بالعربي + الماركة بالإنجليزي + الموديل والمواصفات
        if brand_en and brand_en.lower() not in spec_ar_str.lower() and brand_en.lower() not in cat_ar.lower():
            name_ar = f"{cat_ar} {brand_en} {spec_ar_str}".strip()
        else:
            name_ar = f"{cat_ar} {spec_ar_str}".strip()

        # الاسم بالإنجليزي: إذا توفر عنوان إنجليزي رسمي أنيق من المتجر وكان متطابقاً أو غنياً نستخدمه أو نبني اسماً قياسياً نظيفاً
        if brand_en and brand_en.lower() not in spec_en_str.lower() and brand_en.lower() not in cat_en.lower():
            built_en = f"{brand_en} {spec_en_str} {cat_en}".strip()
        else:
            built_en = f"{spec_en_str} {cat_en}".strip()

        # لو العنوان الأصلي نفسه مكتوب بالإنجليزي بالكامل ونظيف (مثل Adidas Lightshift 2.0 Shoes) نحتفظ بموديله الحقيقي
        if not re.search(r'[\u0600-\u06FF]', t_clean) and len(t_clean) >= 8 and not spec_en_str:
            short_orig_en = " ".join(t_clean.split()[:8]).strip(" ,.-")
            if brand_en and brand_en.lower() not in short_orig_en.lower():
                built_en = f"{brand_en} {short_orig_en}"
            else:
                built_en = short_orig_en
        elif slug_en_title and not spec_en_str and len(slug_en_title) >= 12:
            built_en = slug_en_title

        name_en = built_en
    else:
        cat_fallback_desc = None
        if re.search(r'[\u0600-\u06FF]', t_clean):
            name_ar = _clean_natural_ar_fallback(t_clean, brand_en=brand_en)
        else:
            # العنوان إنجليزي فقط لمنتج غير مصنف -> نترجمه للعربي لبداية واضحة
            tr_to_ar = ""
            if allow_network_translate and t_clean:
                try:
                    r_ar = requests.get(
                        "https://translate.googleapis.com/translate_a/single",
                        params={"client": "gtx", "sl": "en", "tl": "ar", "dt": "t", "q": t_clean[:120]},
                        timeout=3.0,
                    )
                    if r_ar.ok:
                        tr_to_ar = "".join(seg[0] for seg in (r_ar.json()[0] or []) if seg and seg[0]).strip()
                except Exception:
                    pass
            name_ar = _clean_natural_ar_fallback(tr_to_ar or t_clean, brand_en=brand_en)

        if slug_en_title:
            name_en = slug_en_title
        elif not re.search(r'[\u0600-\u06FF]', t_clean) and len(t_clean) >= 6:
            short_en = " ".join(t_clean.split()[:8]).strip(" ,.-")
            name_en = f"{brand_en} {short_en}".strip() if (brand_en and brand_en.lower() not in short_en.lower()) else short_en
        else:
            tr_en = translate_ar_to_en_fast(name_ar, timeout=3.0) if allow_network_translate else ""
            if tr_en:
                name_en = f"{brand_en} {tr_en}".strip() if (brand_en and brand_en.lower() not in tr_en.lower()) else tr_en
            else:
                name_en = f"{brand_en} Featured Product".strip() if brand_en else "Quality Featured Deal"

    # تنظيف صارم يضمن عدم وجود أي حرف عربي أو رقم منفرد في السطر الإنجليزي أبداً
    name_en = re.sub(r'[\u0600-\u06FF]+', ' ', name_en)
    name_en = re.sub(r'\s+', ' ', name_en).strip(" -—,:;.")
    if len(re.findall(r'[A-Za-z]{2,}', name_en)) == 0:
        name_en = f"{brand_en} Quality Product".strip() if brand_en else "Featured Deal Product"

    name_ar = re.sub(r'\s+', ' ', name_ar).strip(" -—,:;.")[:88]
    name_en = name_en[:88]

    # 5. بناء الوصف العربي الدقيق المتوافق تماماً مع المنتج الحقيقي
    description = build_smart_description(
        t_clean,
        features=feats_list,
        extra_desc=extra_desc,
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
                r'\s+(?=(?:بشاشة|بصوت|بتصميم|بتدفق|بتبريد|ببرامج|بمعالج|بمحرك|بشفرات|بوعاء|بسرعات|بدقة|بمعدل|بتركيبة|بخامات|بقوة|بسعة|يدعم|تدعم|يمنحك|تمنحك|تتميز|يتميز|يجمع|تجمع|تستخلص|لتحضير|لتنظيف|لتصفيف|لتبريد|لتشغيل|لنقل|لوضع|لحماية|لفرم))',
                cat_fallback_desc,
            )
            if m_clause and 6 <= m_clause.start() <= 60:
                return cat_fallback_desc[:m_clause.start()] + b_suffix + cat_fallback_desc[m_clause.start():]
            return f"{cat_fallback_desc.rstrip('.')} ({brand_en})."
        return cat_fallback_desc

    clean_t = _clean_natural_ar_fallback(title, brand_en="")
    return f"منتج عملي عالي الجودة والاعتمادية{b_suffix} ({clean_t})، مصمم بخامات متينة لتقديم أداء ممتاز وقيمة حقيقية مقابل السعر."
