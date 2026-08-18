from aiogram import Router
from aiogram.types import CallbackQuery

from src.i18n import translate
from src.keyboards.callbacks import (
    AccountRefreshSource,
    FavoritesAccountAction,
    FavoritesAccountActionCallback,
    FavoritesAccountDetailCallback,
    FavoritesPageCallback,
)
from src.keyboards.inline import (
    build_favorites_account_detail_markup,
    build_favorites_markup,
)
from src.routers.common.navigation import render_screen_message, show_favorites_screen
from src.routers.user.account_refresh import start_account_purchase, start_account_refresh
from src.schemas.common.menu import Screen, render_menu_view
from src.services.catalog import (
    CatalogAccountNotFoundError,
    CatalogService,
    render_catalog_detail_text,
    render_catalog_favorite_alert,
    render_favorites_text,
)
from src.services.system import BotSettingsService, render_sales_disabled_alert

router = Router(name="user-favorites")
catalog_service = CatalogService()
bot_settings_service = BotSettingsService()


@router.callback_query(FavoritesPageCallback.filter())
async def handle_favorites_page(
    callback: CallbackQuery,
    callback_data: FavoritesPageCallback,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await show_favorites_screen(
        callback.message,
        callback.from_user,
        edit=True,
        page=callback_data.page,
    )
    await callback.answer()


@router.callback_query(FavoritesAccountDetailCallback.filter())
async def handle_favorite_account_detail(
    callback: CallbackQuery,
    callback_data: FavoritesAccountDetailCallback,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    try:
        detail = await catalog_service.get_account_detail(
            callback.from_user,
            account_id=callback_data.account_id,
            detail_page=callback_data.detail_page,
        )
    except CatalogAccountNotFoundError:
        language = await catalog_service.get_user_language(callback.from_user)
        await callback.answer(translate(language, "catalog_account_not_found"), show_alert=True)
        return

    await render_screen_message(
        callback.message,
        text=render_catalog_detail_text(detail),
        reply_markup=build_favorites_account_detail_markup(detail, page=callback_data.page),
        media=render_menu_view(Screen.FAVORITES, detail.language).media,
        edit=True,
    )
    await callback.answer()


@router.callback_query(FavoritesAccountActionCallback.filter())
async def handle_favorite_account_action(
    callback: CallbackQuery,
    callback_data: FavoritesAccountActionCallback,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    if callback_data.action == FavoritesAccountAction.BUY:
        language = await catalog_service.get_user_language(callback.from_user)
        try:
            detail = await catalog_service.get_account_detail(
                callback.from_user,
                account_id=callback_data.account_id,
                detail_page=callback_data.detail_page,
            )
        except CatalogAccountNotFoundError:
            await callback.answer(translate(language, "catalog_account_not_found"), show_alert=True)
            return
        if not await bot_settings_service.is_sales_enabled(detail.game_type):
            await callback.answer(render_sales_disabled_alert(language, detail.game_type), show_alert=True)
            return
        await start_account_purchase(
            callback,
            source=AccountRefreshSource.FAVORITES,
            account_id=callback_data.account_id,
            page=callback_data.page,
            detail_page=callback_data.detail_page,
        )
        return

    if callback_data.action == FavoritesAccountAction.REFRESH:
        await start_account_refresh(
            callback,
            source=AccountRefreshSource.FAVORITES,
            account_id=callback_data.account_id,
            page=callback_data.page,
            detail_page=callback_data.detail_page,
        )
        return

    if callback_data.action in {
        FavoritesAccountAction.PREVIOUS_DETAIL_PAGE,
        FavoritesAccountAction.NEXT_DETAIL_PAGE,
    }:
        target_detail_page = callback_data.detail_page
        if callback_data.action == FavoritesAccountAction.PREVIOUS_DETAIL_PAGE:
            target_detail_page -= 1
        elif callback_data.action == FavoritesAccountAction.NEXT_DETAIL_PAGE:
            target_detail_page += 1

        try:
            detail = await catalog_service.get_account_detail(
                callback.from_user,
                account_id=callback_data.account_id,
                detail_page=target_detail_page,
            )
        except CatalogAccountNotFoundError:
            language = await catalog_service.get_user_language(callback.from_user)
            await callback.answer(translate(language, "catalog_account_not_found"), show_alert=True)
            return

        await render_screen_message(
            callback.message,
            text=render_catalog_detail_text(detail),
            reply_markup=build_favorites_account_detail_markup(detail, page=callback_data.page),
            media=render_menu_view(Screen.FAVORITES, detail.language).media,
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == FavoritesAccountAction.BACK_TO_LIST:
        await show_favorites_screen(
            callback.message,
            callback.from_user,
            edit=True,
            page=callback_data.page,
        )
        await callback.answer()
        return

    try:
        detail, is_added = await catalog_service.toggle_favorite(
            callback.from_user,
            account_id=callback_data.account_id,
        )
    except CatalogAccountNotFoundError:
        language = await catalog_service.get_user_language(callback.from_user)
        await callback.answer(translate(language, "catalog_account_not_found"), show_alert=True)
        return

    if not detail.is_favorite:
        page_data = await catalog_service.get_favorites_page(callback.from_user, page=callback_data.page)
        await render_screen_message(
            callback.message,
            text=render_favorites_text(page_data),
            reply_markup=build_favorites_markup(page_data),
            media=render_menu_view(Screen.FAVORITES, page_data.language).media,
            edit=True,
        )
        await callback.answer(render_catalog_favorite_alert(page_data.language, added=is_added))
        return

    current_detail = detail.model_copy(update={"detail_page": callback_data.detail_page})
    await render_screen_message(
        callback.message,
        text=render_catalog_detail_text(current_detail),
        reply_markup=build_favorites_account_detail_markup(current_detail, page=callback_data.page),
        media=render_menu_view(Screen.FAVORITES, detail.language).media,
        edit=True,
    )
    await callback.answer(render_catalog_favorite_alert(detail.language, added=is_added))
