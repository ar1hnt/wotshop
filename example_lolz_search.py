import asyncio
import base64

import httpx

from loguru import logger

from core.utils.bot_message import bot_message


class LztMarketAPI:
    API_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzUxMiJ9.eyJzdWIiOjQ0MTQzNzAsImlzcyI6Imx6dCIsImlhdCI6MTc1MTc5NzkwNSwianRpIjoiODEwMzYxIiwic2NvcGUiOiJiYXNpYyByZWFkIHBvc3QgY29udmVyc2F0ZSBwYXltZW50IGludm9pY2UgY2hhdGJveCBtYXJrZXQifQ.SOcKVqpLHqkia43U6T-WWM0BSJU9x3gLgmk10jZInFQtigsTuzYUHwJbv_UbCb7rhvZ0UrIAsRhTKbGj-7TVNIifRTZq44P44pjxSoaS1tvFcAIrvyaQnBAyIeRNOhcJPPnMeZt256KiRVv3iSNWQrwiLnHESg-5XTIDTnTXP10"
    API_URL = "https://prod-api.lzt.market/"
    API_URL_WOT = "https://prod-api.lzt.market/world-of-tanks"
    API_URL_WOT_BLITZ = "https://prod-api.lzt.market/wot-blitz"
    API_URL_CHATGPT = "https://prod-api.lzt.market/chatgpt"
    API_URL_GIFT_TELEGRAM_PREMIUM = "https://prod-api.lzt.market/gifts"
    API_URL_WAR_THUNDER = "https://prod-api.lzt.market/war-thunder"
    API_URL_MINECRAFT = "https://prod-api.lzt.market/minecraft"
    API_URL_UPLAY = "https://prod-api.lzt.market/uplay"
    API_URL_MIHOYO = "https://prod-api.lzt.market/mihoyo"
    API_URL_FORTNITE = "https://prod-api.lzt.market/fortnite"
    API_URL_BATTLENET = "https://prod-api.lzt.market/battlenet"
    API_URL_SUPERCELL = "https://prod-api.lzt.market/supercell"
    API_URL_EA = "https://prod-api.lzt.market/ea"
    API_URL_EPIC_GAMES = "https://prod-api.lzt.market/epicgames"
    API_URL_WARFACE = "https://prod-api.lzt.market/warface"
    API_URL_RIOT = "https://prod-api.lzt.market/riot"

    HEADERS = {
        "accept": "application/json",
        "authorization": f"Bearer {API_TOKEN}"
    }

    RETRIES: int = 10
    DELAY: int = 20
    TIMEOUT: int = 30

    @classmethod
    async def get_me_profile_info(cls) -> dict | None:
        """
        Получение данных профиля Lolz
        :return:
        """
        profile_data_url = "https://prod-api.lzt.market/me"

        async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
            try:
                response = await client.get(profile_data_url)
                logger.debug(
                    f'Статус запроса на получение данных профиля: {response.status_code}')

                if response.status_code == 200:
                    return response.json()

                logger.warning(
                    f"Ошибка получения данных профиля (Статус: {response.status_code}): {response.text}")

            except httpx.RequestError as e:
                logger.exception(f"Сетевая ошибка: {e}")

    @classmethod
    async def get_wot_accounts(cls, page: int, country: str, email: bool) -> dict | None:
        """
        Получение списка аккаунтов Мир Танков на определенной странице Lolz Market'а
        :param page:
        :param country:
        :return:
        """
        if email:
            filter_url = cls.API_URL_WOT + f'?page={page}&pmin=100&pmax=90000&show=active&daybreak=15&not_origin[]=resale&top_min=10&region[]={country}&order_by=pdate_to_down_upload&email_type[]=autoreg&email_type[]=native'
        else:
            filter_url = cls.API_URL_WOT + f'?page={page}&pmin=10&pmax=90000&show=active&daybreak=15&not_origin[]=resale&top_min=10&region[]={country}&order_by=pdate_to_down_upload'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(f'Статус запроса на получение списка аккаунтов Мир Танков (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(f"Ошибка получения списка аккаунтов Мир Танков (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов Мир танков</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_wot_blitz_accounts(cls, page: int, country: str) -> dict | None:
        """
        Получение списка аккаунтов Tanks Blitz на определенной странице Lolz Market'а
        :param page:
        :param country:
        :return:
        """
        filter_url = cls.API_URL_WOT_BLITZ + f'?page={page}&pmin=10&pmax=90000&show=active&daybreak=14&not_origin[]=resale&top_min=5&region[]={country}&order_by=pdate_to_down_upload'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов Tanks Blitz (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов Tanks Blitz (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов Tanks Blitz</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_chatgpt_accounts(cls, page: int) -> dict | None:
        """
        Получение списка аккаунтов ChatGPT на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_CHATGPT + f'?page={page}&show=active&not_origin[]=resale&order_by=pdate_to_down_upload'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов ChatGPT (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов ChatGPT (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов ChatGPT</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_gifts_telegram_premium(cls, page: int) -> dict | None:
        """
        Получение списка гифтов Telegram Premium на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_GIFT_TELEGRAM_PREMIUM + f'?page={page}order_by=pdate_to_down_upload&show=active&not_origin[]=resale&subscription=telegram_premium&subscription_length=3&subscription_period=month'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка гифтов Telegram Premium (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка гифтов Telegram  Premium(Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных гифтов Telegram Premium</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_war_thunder_accounts(cls, page: int) -> dict | None:
        """
        Получение списка аккаунтов War Thunder на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_WAR_THUNDER + f'?page={page}&pmin=100&pmax=90000&order_by=pdate_to_down_upload&show=active&not_origin[]=resale&email_type[]=no&daybreak=10&rank_min=20&elite_units_min=10&launcher[]=gaijin'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов War Thunder (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов War Thunder (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов War Thunder</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_minecraft_accounts(cls, page: int) -> dict | None:
        """
        Получение списка аккаунтов Minecraft на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_MINECRAFT + f'?page={page}&pmin=300&pmax=4000&order_by=pdate_to_down_upload&show=active&not_origin[]=resale&email_login_data=true&change_nickname=yes&hypixel_ban=no&java=yes&bedrock=yes&can_change_details=yes'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов Minecraft (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов Minecraft (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов Minecraft</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_uplay_accounts(cls, page: int) -> dict | None:
        """
        Получение списка аккаунтов Uplay на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_UPLAY + f'?page={page}&pmin=300&pmax=9000&order_by=pdate_to_down_upload&show=active&not_origin[]=resale&gmin=2&daybreak=60&r6_ban=no&xbox_connected=no&psn_connected=no&steam_connected=no'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов Uplay (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов Uplay (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов Uplay</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_mihoyo_accounts(cls, page: int) -> dict | None:
        """
        Получение списка аккаунтов Mihoyo на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_MIHOYO + f'?page={page}&pmin=100&pmax=9000&order_by=pdate_to_down_upload&show=active&daybreak=30&email_type[]=autoreg'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов Mihoyo (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов Mihoyo (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов Mihoyo</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_fortnite_accounts(cls, page: int) -> dict | None:
        """
        Получение списка аккаунтов Fortnite на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_FORTNITE + f'?page={page}&pmin=300&pmax=90000&order_by=pdate_to_down_upload&show=active&platform[]=EpicPC&not_origin[]=resale&email_type[]=autoreg&daybreak=30'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов Fortnite (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов Fortnite (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов Fortnite</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_battlenet_accounts(cls, page: int) -> dict | None:
        """
        Получение списка аккаунтов BattleNet на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_BATTLENET + f'?page={page}&pmin=100&pmax=10000&order_by=pdate_to_down_upload&show=active&not_origin[]=resale&eg=0&daybreak=30&tel=no&edit_btag=yes&changeable_fn=yes&parent_control=no&no_bans=yes'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов BattleNet (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов BattleNet (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов BattleNet</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_supercell_accounts(cls, page: int) -> dict | None:
        """
        Получение списка аккаунтов Supercell на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_SUPERCELL + f'?page={page}&pmin=100&pmax=10000&order_by=pdate_to_down_upload&show=active&not_origin[]=resale&daybreak=30&tel=no'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов Supercell (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов Supercell (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов Supercell</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_ea_accounts(cls, page: int) -> dict | None:
        """
        Получение списка аккаунтов EA на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_EA + f'?page={page}&pmin=100&pmax=10000&order_by=pdate_to_down_upload&show=active&email_type[]=autoreg&email_type[]=native&xbox_connected=no&steam_connected=no&psn_connected=no&has_ban=no'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов EA (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов EA (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов EA</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_epic_games_accounts(cls, page: int) -> dict | None:
        """
        Получение списка аккаунтов Epic Games на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_EPIC_GAMES + f'?page={page}&pmin=100&pmax=10000&order_by=pdate_to_down_upload&show=active&not_origin[]=resale&email_type[]=autoreg&email_type[]=native&daybreak=30'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов Epic Games (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов Epic Games (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов Epic Games</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_warface_accounts(cls, page: int) -> dict | None:
        """
        Получение списка аккаунтов Warface на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_WARFACE + f'?page={page}&pmin=100&pmax=10000&tel=no&daybreak=30'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов Warface (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов Warface (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов Warface</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def get_riot_accounts(cls, page: int) -> dict | None:
        """
        Получение списка аккаунтов Riot на определенной странице Lolz Market'а
        :param page:
        :return:
        """
        filter_url = cls.API_URL_RIOT + f'?page={page}&pmin=100&pmax=10000&not_origin[]=resale&daybreak=60&email=no&tel=no&email_type[]=no'

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(filter_url)
                    logger.debug(
                        f'Статус запроса на получение списка аккаунтов Riot (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка получения списка аккаунтов Riot (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при сборе данных аккаунтов Riot</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def download_product_images(cls, filename, url):
        """
        Загрузка изображения с Lolz Market
        :param filename:
        :param url:
        :return:
        """
        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.get(url)
                    content_type = response.headers.get("Content-Type", "")
                    logger.debug(
                        f'Статус запроса скачивания изображения (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        if content_type.startswith("image/"):
                            return {filename: response.content}
                        elif content_type.startswith("application/json"):
                            try:
                                data = response.json()
                                b64_data = data.get("base64")
                                if b64_data:
                                    return {filename + '.png': base64.b64decode(b64_data)}
                                else:
                                    logger.debug("base64 данных нет в ответе в скачанном изображении.")
                            except Exception as e:
                                logger.debug("Ошибка при разборе JSON скачанного изображения:", e)

                    logger.warning(
                        f"Ошибка скачивания изображения (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                message = (f"<b>Ошибка при скачивании изображения</b>\n\n"
                           f"Не удалось получить данные после {cls.RETRIES} попыток.")
                await bot_message(message=message)
                raise RuntimeError(message)

    @classmethod
    async def check_account_for_validity(cls, item_id: int) -> dict | None:
        """
        Проверка аккаунта на валидность (только проверка логина и пароля) перед покупкой
        :param item_id: ID товара
        :return:
        """
        check_account_url = f"https://prod-api.lzt.market/{item_id}/check-account"

        for attempt in range(1, cls.RETRIES + 1):
            async with httpx.AsyncClient(headers=cls.HEADERS, timeout=cls.TIMEOUT) as client:
                try:
                    response = await client.post(check_account_url)
                    logger.debug(
                        f'Статус запроса на проверку валидности товара (попытка №{attempt}): {response.status_code}')

                    if response.status_code == 200:
                        return response.json()

                    logger.warning(
                        f"Ошибка запроса на проверку валидности товара (Статус: {response.status_code}): {response.text}")
                except httpx.ConnectTimeout:
                    pass
                except httpx.RequestError as e:
                    logger.exception(f"Сетевая ошибка: {e}")

            if attempt < cls.RETRIES:
                await asyncio.sleep(cls.DELAY)
            else:
                raise RuntimeError(f"Не удалось проверить товар на валидность после {cls.RETRIES} попыток")

