"""Автогенерация имён семей: женское имя + 3 случайные цифры."""

from __future__ import annotations

import random

COLONY_NAME_POOL = [
    "Альбина",
    "Амина",
    "Анна",
    "Ася",
    "Вера",
    "Виктория",
    "Галина",
    "Дарья",
    "Елена",
    "Жанна",
    "Зоя",
    "Ирина",
    "Клара",
    "Лариса",
    "Людмила",
    "Мария",
    "Надежда",
    "Ольга",
    "Полина",
    "Раиса",
    "София",
    "Татьяна",
    "Ульяна",
    "Фаина",
    "Хава",
    "Эльвира",
    "Юлия",
    "Яна",
    "Айгуль",
    "Айша",
    "Гульнара",
    "Динара",
    "Зарина",
    "Камила",
    "Лейла",
    "Мадина",
    "Сабина",
    "Fatima",
    "Layla",
    "Amira",
    "Chloe",
    "Claire",
    "Elise",
    "Helene",
    "Juliette",
    "Margot",
    "Noemie",
    "Anika",
    "Priya",
    "Sunita",
    "Mei",
    "Yuki",
    "Hana",
    "Sakura",
    "Min",
    "Lucia",
    "Elena",
    "Carmen",
    "Rosa",
    "Ines",
]


def generate_colony_name(rng: random.Random | None = None) -> str:
    r = rng or random
    base = r.choice(COLONY_NAME_POOL)
    suffix = r.randint(0, 999)
    return f"{base} {suffix:03d}"
