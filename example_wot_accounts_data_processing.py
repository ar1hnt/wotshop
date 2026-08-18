import asyncio
import json
import math
import random

from copy import deepcopy
from datetime import datetime

from pathlib import Path
from typing import Dict, List, Any
from collections import OrderedDict

import pandas as pd

from core.api.lolz_api import LztMarketAPI
from core.config import TEMPLATE, LIMIT_FOR_CATEGORY, MARGIN_COST, COMMISSION, TZ, ADDITIONAL_DESCRIPTIONS, asset_path

UNIQUE_TOPS: Dict[str, int] = json.loads(asset_path("json", "unique_goods.json").read_text(
    encoding="utf-8"))["unique_tops_tanks_wot"]

CATS_XLSX = asset_path("xlsx", "categories_tanks.xlsx")

_cat_df = (pd.read_excel(CATS_XLSX)
             .rename(columns=lambda c: c.strip().lower()))

CAT_LOOKUP: Dict[str, int] = {
    row["модель танка, слово, синоним"].strip().lower(): int(row["категория playntrade"])
    for _, row in _cat_df.iterrows()
}

def _fmt_date(ts: int | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, tz=TZ).strftime("%d.%m.%Y")

def _days_ago(ts: int | None) -> int:
    if not ts:
        return 0
    now = datetime.now(tz=TZ)
    days = (now - datetime.fromtimestamp(ts, tz=TZ)).days
    return days

def get_tanks_list(acc):
    tanks: List[str] = []
    for t in sorted((acc.get("wotTanks") or {}).values(),
                    key=lambda t: (-t["tier"], t["short_name"])):
        if int(t['tier']) == 1:
            continue
        name = t["short_name"]
        if t.get("is_premium"):
            name += " (Премиум)"
        tanks.append(f"({t['tier']}) —> {name}")
    return tanks

def make_tanks_description(acc: Dict[str, Any], product_type: str) -> str:
    """
    1. HTML-описание (если есть)
    2. Список танков (10) —> Name [Премиум]
    3. Сервис-блок (почта, телефон, даты)
    """
    parts: List[str] = []

    # 1. базовые маркеры
    parts.append(f"Регион: Россия (Lesta Games, {'Мир Танков' if product_type == 'wot' else 'Tanks Blitz'})")

    email_access = is_full_email_access(acc)
    if email_access:
        parts.append("Есть доступ к почте")

    if acc.get("wot_mobile") == 0:
        parts.append("Телефон не привязан")

    desc = acc.get("descriptionHtml", "").strip()
    if desc and email_access:
        parts.append(f"Описание:\n{desc}")

    # 2. список танков
    tanks = get_tanks_list(acc)

    if tanks:
        parts.append("Танки в ангаре:\n"+"\n".join(tanks))

    # 3. даты
    reg = _fmt_date(acc.get("wot_register_date"))
    act = _fmt_date(acc.get("wot_last_activity"))
    ago = _days_ago(acc.get("wot_last_activity"))
    parts.append(f"Дата регистрации: {reg}")

    if int(ago) >= 60:
        parts.append(f"Последняя активность: {act} ({ago} дн. назад)")

    parts.append("***")
    parts.append(
        "📝 Если Вам нужен аккаунт с определенными характеристиками (количество топов, премиум-танков, золота, серебра), или же аккаунт с полной перепривязкой — напишите мне в ЛС и я подберу для Вас оптимальный вариант.")

    for desc in ADDITIONAL_DESCRIPTIONS:
        parts.append(desc)

    return "\n\n".join(parts)

def calc_our_price(acc: Dict[str, Any], product_type: str) -> int:
    top_cnt = acc.get("wot_top_tanks", 0)
    prem_cnt = acc.get("wot_premium_tanks", 0)
    top_prem_cnt = acc.get("wot_top_premium_tanks", 0)

    if product_type == "wot":
        price = top_cnt * 15 # было 15
        price += math.ceil(prem_cnt / 10) * 15        # было 15
        price += top_prem_cnt * 5 # было 5

        # бонусы за «уникальные» топы
        all_names = {
            *(t["short_name"] for t in (acc.get("wotTopTanks") or {}).values()),
            *(t["short_name"] for t in (acc.get("wotTopPremiumTanks") or {}).values()),
        }
        for uniq_name, bonus in UNIQUE_TOPS.items():
            if uniq_name in all_names:
                price += bonus - 5                   # снимаем уже добавленные 5 ₽

        # *15 ₽ за полный доступ к почте
        if is_full_email_access(acc):
            price *= 15
        else:
            ago = _days_ago(acc.get("wot_last_activity"))

            # if ago >= 530:
            #     price *= 4
            # elif ago >= 330:
            #     price *= 3.5
            # elif ago >= 230:
            #     price *= 3
            # elif ago >= 130:
            #     price *= 2.5
            if ago >= 530:
                price *= 3
            elif ago >= 330:
                price *= 2.5
            elif ago >= 230:
                price *= 2
            elif ago >= 130:
                price *= 1.5
    else:
        price = top_cnt * 14  # было 15
        price += math.ceil(prem_cnt / 10) * 14  # было 15
        price += top_prem_cnt * 4  # было 5

        # бонусы за «уникальные» топы
        all_names = {
            *(t["short_name"] for t in (acc.get("wotTopTanks") or {}).values()),
            *(t["short_name"] for t in (acc.get("wotTopPremiumTanks") or {}).values()),
        }
        for uniq_name, bonus in UNIQUE_TOPS.items():
            if uniq_name in all_names:
                price += bonus - 4  # снимаем уже добавленные 5 ₽

        # *15 ₽ за полный доступ к почте
        if is_full_email_access(acc):
            price *= 15
        else:
            ago = _days_ago(acc.get("wot_last_activity"))

            # if ago >= 530:
            #     price *= 4
            # elif ago >= 330:
            #     price *= 3.5
            # elif ago >= 230:
            #     price *= 3
            # elif ago >= 130:
            #     price *= 2.5
            if ago >= 530:
                price *= 3
            elif ago >= 330:
                price *= 2.5
            elif ago >= 230:
                price *= 2
            elif ago >= 130:
                price *= 1.5

    return math.ceil(price)

def is_full_email_access(acc: Dict[str, Any]) -> int:
    """1 — если аккаунт идёт вместе с почтой, иначе 0."""
    # самый надёжный маркер на LZT — email_type ≠ ''
    return 1 if acc.get("email_type") else 0

def _days_since(ts: int | None) -> int:
    if not ts:
        return 0
    return (datetime.now(tz=TZ) - datetime.fromtimestamp(ts, TZ)).days

def have_tier_11(acc: Dict[str, Any]) -> bool:
    tanks_data = list((acc.get("wotTanks") or {}).values())
    tier11 = [t["short_name"] for t in tanks_data if t["tier"] == 11]
    if tier11:
        return True
    return False


def _plural_top(n: int) -> str:
    # 1 ТОП, 2-4 ТОПА, 5+ ТОПОВ
    if 11 <= n % 100 <= 14:
        return "ТОПОВ"
    if n % 10 == 1:
        return "ТОП"
    if 2 <= n % 10 <= 4:
        return "ТОПА"
    return "ТОПОВ"

def build_product_name(acc: Dict[str, Any]) -> str:
    """
    ⚡️ [почта] ⚡️ [неактив] ⚡️ <Top> ТОП(ОВ), <Prem> ПРЕМИУМ ⚡️ [ЕСТЬ 11 УР.] ⚡️ <6-10 танков> ⚡️
    """
    top_cnt  = acc.get("wot_top_tanks", 0)
    prem_cnt = acc.get("wot_premium_tanks", 0)

    parts: List[str] = []

    if is_full_email_access(acc):
        parts.append("Доступ к почте")

    idle = _days_since(acc.get("wot_last_activity"))
    if idle >= 60:
        parts.append(f"Неактив {idle} дн.")

    tanks_data = list((acc.get("wotTanks") or {}).values())

    tier11 = [t["short_name"] for t in tanks_data if t["tier"] == 11]
    tier10 = [t["short_name"] for t in tanks_data if t["tier"] == 10]

    prem_lower = [t["short_name"] for t in tanks_data
                  if t["is_premium"] and t["tier"] < 10]
    regular_lower = [t["short_name"] for t in tanks_data
                     if not t["is_premium"] and t["tier"] < 10]

    chosen = tier11 or tier10
    need = random.randint(6, 9)

    if tier11:
        parts.append("ЕСТЬ 11 УР.")
        random.shuffle(tier10)
        chosen.extend(tier10[:max(0, need - len(chosen))])

    parts.append(f"{top_cnt} {_plural_top(top_cnt)}, {prem_cnt} ПРЕМИУМ")

    random.shuffle(prem_lower)
    chosen.extend(prem_lower[:max(0, need - len(chosen))])

    if len(chosen) < need:
        random.shuffle(regular_lower)
        chosen.extend(regular_lower[:need - len(chosen)])

    tanks_txt = ", ".join(list(OrderedDict.fromkeys(chosen))[:10])
    parts.append(tanks_txt)

    return "⚡️ " + " ⚡️ ".join(parts) + " ⚡️"

def categories_for_account(acc: Dict[str, Any], product_type: str) -> List[int]:
    """
    Возвращает список ID категорий для данного аккаунта:
      1. WoT : 11209 + категории танков
      2. Blitz: только 11239
    """
    if product_type != 'wot':
        return [11239]

    cat_ids = {11209}

    for tank in (acc.get("wotTanks") or {}).values():
        name = tank["short_name"].strip().lower()
        for syn, cat_id in CAT_LOOKUP.items():
            if syn == name:
                cat_ids.add(cat_id)

    return sorted(cat_ids)

def convert_to_item(
        acc: Dict[str, Any],
        idx: int,
        product_type: str
) -> Dict[str, Any] | None:
    """
    Преобразует карточку LZT → словарь для mass-upload.
    Пропускает, если маржа (с учётом комиссии COMMISSION%) < MARGIN_COST руб.
    """
    supplier_price = int(float(acc["price"]))          # закупка
    our_price = math.ceil(calc_our_price(acc, product_type) / COMMISSION)  # цена продажи

    margin = our_price * COMMISSION - supplier_price

    if margin < MARGIN_COST:
        return None

    item = deepcopy(TEMPLATE)
    item.update({
        "accid": str(idx),
        "Название товара": build_product_name(acc).upper(),
        "Стоимость": str(our_price),
        "Описание": make_tanks_description(acc, product_type),
        "Доступ": is_full_email_access(acc),
        "Категории": ", ".join(
            map(str, categories_for_account(acc, product_type))
        ),
        "resell_link":  f'https://lzt.market/{acc["item_id"]}/',
        "supplier_link": f'https://lolz.live/members/{acc["seller"]["user_id"]}/',
        "supplier_price": str(supplier_price),

        # Информация для Google Sheets ---------------------------------------------------------------------------------
        "tops": acc.get("wot_top_tanks", 0),
        "prems": acc.get("wot_premium_tanks", 0),
        "last_activity": _days_since(acc.get("wot_last_activity")),
        "email_access": "Есть" if is_full_email_access(acc) else "Нет",
        "tier_11": have_tier_11(acc),
        "register_date": _fmt_date(acc.get("wot_register_date")),
        "phone": "Телефон не привязан" if acc.get("wot_mobile") == 0 else "Телефон привязан",
        "description": acc.get("descriptionHtml", "").strip(),
        "tanks_list": "\n".join(get_tanks_list(acc))
        # --------------------------------------------------------------------------------------------------------------
    })
    return item

async def data_processing(*, product_type: str, limit: int = LIMIT_FOR_CATEGORY
                          ) -> List[Dict[str, Any]]:
    """
    Качаем страницы LZT, пока не соберём limit допущенных аккаунтов
    или пока страницы не кончатся. Дубликаты исключаются по item_id.
    """
    collected: List[Dict[str, Any]] = []
    seen_ids: set[int] = set()  # отслеживаем уникальность
    page = 1
    email_mode = True  # только для wot

    while len(collected) < limit:
        if product_type == "wot":
            raw = await LztMarketAPI.get_wot_accounts(
                page=page,
                country='ru',
                email=email_mode
            )
        else:
            raw = await LztMarketAPI.get_wot_blitz_accounts(
                page=page,
                country='ru'
            )

        for acc in raw["items"]: # type: ignore
            acc_id = acc["item_id"]
            if acc_id in seen_ids:
                continue  # пропускаем дубликат

            item = convert_to_item(acc, idx=len(collected), product_type=product_type)
            if item:
                collected.append(item)
                seen_ids.add(acc_id)

                if len(collected) >= limit:
                    break

        # страницы исчерпаны
        if not raw.get("hasNextPage"): # type: ignore
            if product_type == "wot" and email_mode:
                # пробуем без email
                email_mode = False
                page = 1  # сбрасываем на первую страницу
                continue
            else:
                break

        await asyncio.sleep(0.5)
        page += 1

    return collected[:limit]

