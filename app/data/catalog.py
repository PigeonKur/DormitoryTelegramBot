CATALOG = {
    "groceries": {
        "name": "🌾 Бакалея",
        "items": [
            {"id": "pasta_1",    "name": "Макароны Barilla 400г",    "price": 89},
            {"id": "pasta_2",    "name": "Макароны Makfa 400г",       "price": 65},
            {"id": "cereal_1",   "name": "Гречка 900г",               "price": 75},
            {"id": "cereal_2",   "name": "Рис длиннозёрный 900г",     "price": 80},
            {"id": "cereal_3",   "name": "Овсянка 500г",              "price": 55},
            {"id": "spice_1",    "name": "Соль 1кг",                  "price": 30},
            {"id": "spice_2",    "name": "Сахар 1кг",                 "price": 65},
            {"id": "spice_3",    "name": "Перец чёрный молотый 20г",  "price": 40},
        ]
    },
    "drinks": {
        "name": "🥤 Напитки",
        "subcategories": {
            "water": {
                "name": "💧 Вода",
                "items": [
                    {"id": "water_1", "name": "Святой источник 0.5л", "price": 35},
                    {"id": "water_2", "name": "Святой источник 1л",   "price": 55},
                    {"id": "water_3", "name": "Святой источник 5л",   "price": 150},
                    {"id": "water_4", "name": "Архыз 1л",             "price": 60},
                    {"id": "water_5", "name": "BonAqua 0.5л",         "price": 40},
                ]
            },
            "carbonated": {
                "name": "🫧 Газировка",
                "items": [
                    {"id": "carb_1", "name": "Coca-Cola 0.5л",     "price": 90},
                    {"id": "carb_2", "name": "Pepsi 0.5л",         "price": 85},
                    {"id": "carb_3", "name": "Sprite 0.5л",        "price": 85},
                    {"id": "carb_4", "name": "Fanta 0.5л",         "price": 85},
                ]
            },
            "juice": {
                "name": "🧃 Соки",
                "items": [
                    {"id": "juice_1", "name": "Добрый яблоко 1л",   "price": 95},
                    {"id": "juice_2", "name": "Добрый апельсин 1л", "price": 95},
                    {"id": "juice_3", "name": "Rich вишня 1л",      "price": 110},
                ]
            },
            "icetea": {
                "name": "🍵 Холодный чай",
                "items": [
                    {"id": "tea_1", "name": "Lipton лимон 0.5л",  "price": 80},
                    {"id": "tea_2", "name": "Lipton персик 0.5л", "price": 80},
                ]
            },
        }
    },
    "pastries": {
        "name": "🍞 Хлеб и выпечка",
        "items": [
            {"id": "bread_1", "name": "Хлеб белый",          "price": 35},
            {"id": "bread_2", "name": "Хлеб чёрный",         "price": 40},
            {"id": "bread_3", "name": "Батон нарезной",       "price": 45},
            {"id": "bread_4", "name": "Багет французский",    "price": 55},
        ]
    },
    "sweets": {
        "name": "🍬 Сладости",
        "items": [
            {"id": "sweet_1", "name": "Шоколад Milka 90г",       "price": 120},
            {"id": "sweet_2", "name": "Шоколад Alpen Gold 90г",   "price": 90},
            {"id": "sweet_3", "name": "Печенье Орео 95г",         "price": 75},
            {"id": "sweet_4", "name": "Зефир 250г",               "price": 80},
            {"id": "sweet_5", "name": "Вафли 200г",               "price": 60},
        ]
    },
    "frozen": {
        "name": "❄️ Замороженные продукты",
        "items": [
            {"id": "frz_1", "name": "Пельмени Мираторг 800г",   "price": 290},
            {"id": "frz_2", "name": "Вареники с картофелем 800г","price": 180},
            {"id": "frz_3", "name": "Пицца замороженная",        "price": 250},
        ]
    },
    "snacks": {
        "name": "🍿 Снеки",
        "items": [
            {"id": "snack_1", "name": "Чипсы Lay's 150г",      "price": 110},
            {"id": "snack_2", "name": "Чипсы Pringles 165г",   "price": 180},
            {"id": "snack_3", "name": "Сухарики Три корочки",  "price": 45},
            {"id": "snack_4", "name": "Орешки солёные 100г",   "price": 85},
        ]
    },
    "produce": {
        "name": "🥦 Овощи, фрукты, грибы",
        "items": [
            {"id": "veg_1", "name": "Огурцы 1кг",      "price": 90},
            {"id": "veg_2", "name": "Помидоры 1кг",    "price": 120},
            {"id": "veg_3", "name": "Бананы 1кг",      "price": 80},
            {"id": "veg_4", "name": "Яблоки 1кг",      "price": 95},
            {"id": "veg_5", "name": "Шампиньоны 400г", "price": 110},
        ]
    },
}

ITEMS_INDEX: dict = {}

def _build_index():
    for cat_key, cat in CATALOG.items():
        if "items" in cat:
            for item in cat["items"]:
                ITEMS_INDEX[item["id"]] = {**item, "category": cat_key}
        if "subcategories" in cat:
            for sub_key, sub in cat["subcategories"].items():
                for item in sub["items"]:
                    ITEMS_INDEX[item["id"]] = {**item, "category": cat_key, "subcategory": sub_key}

_build_index()
