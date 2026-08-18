import asyncio
import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from src.db.models.catalog_account import GameAccountType
from src.i18n import translate
from src.keyboards.callbacks import (
    AccountRefreshAction,
    AccountRefreshCallback,
    AccountRefreshSource,
)
from src.keyboards.inline import (
    build_catalog_account_detail_markup,
    build_catalog_purchase_failed_markup,
    build_purchase_completed_markup,
    build_purchase_payment_link_markup,
    build_catalog_refresh_markup,
    build_catalog_refresh_result_markup,
    build_catalog_results_markup,
    build_favorites_account_detail_markup,
    build_favorite_purchase_failed_markup,
    build_favorite_purchase_payment_link_markup,
)
from src.routers.common.navigation import (
    render_screen_message,
    render_screen_message_by_id,
    show_favorites_screen,
    show_screen,
)
from src.schemas.common.menu import (
    CATALOG_ACCOUNT_SCREEN_MEDIA,
    CATALOG_RESULTS_SCREEN_MEDIA,
    Screen,
    render_menu_view,
)
from src.services.catalog import (
    CatalogAccountNotFoundError,
    CatalogService,
    render_catalog_detail_text,
    render_catalog_results_text,
)
from src.services.sync import (
    account_refresh_task_registry,
    catalog_sync_service,
    render_catalog_refresh_failed_text,
    render_catalog_refresh_not_configured_text,
    render_catalog_refresh_progress_text,
    render_catalog_refresh_result_text,
    render_catalog_refresh_stopped_text,
)
from src.services.payments import (
    AccountUnavailableError,
    AccountValidationError,
    PaymentError,
    PaymentUnavailableError,
    payment_service,
)
from src.services.transactions import TransactionService

logger = logging.getLogger(__name__)

router = Router(name="user-account-refresh")
catalog_service = CatalogService()
transaction_service = TransactionService()


async def start_account_refresh(
    callback: CallbackQuery,
    *,
    source: AccountRefreshSource,
    account_id: int,
    page: int,
    detail_page: int,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = await catalog_service.get_user_language(callback.from_user)
    if not catalog_sync_service.is_configured():
        await callback.answer(render_catalog_refresh_not_configured_text(language), show_alert=True)
        return

    try:
        detail = await catalog_service.get_account_detail(
            callback.from_user,
            account_id=account_id,
            detail_page=detail_page,
        )
    except CatalogAccountNotFoundError:
        await callback.answer(translate(language, "catalog_account_not_found"), show_alert=True)
        return

    await render_screen_message(
        callback.message,
        text=render_catalog_refresh_progress_text(detail.language, detail.id),
        reply_markup=build_catalog_refresh_markup(
            detail.language,
            source=source,
            account_id=detail.id,
            game_type=detail.game_type,
            page=page,
            detail_page=detail.detail_page,
        ),
        media=CATALOG_ACCOUNT_SCREEN_MEDIA,
        edit=True,
    )

    task = asyncio.create_task(
        _run_account_refresh_task(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            language=detail.language,
            source=source,
            account_id=detail.id,
            game_type=detail.game_type,
            page=page,
            detail_page=detail.detail_page,
            telegram_user=callback.from_user,
        )
    )
    account_refresh_task_registry.register(callback.from_user.id, task)
    await callback.answer()


async def start_account_purchase(
    callback: CallbackQuery,
    *,
    source: AccountRefreshSource,
    account_id: int,
    page: int,
    detail_page: int,
) -> None:
    """Show a cancellable supplier validation screen, then start checkout."""
    if callback.message is None:
        await callback.answer()
        return

    language = await catalog_service.get_user_language(callback.from_user)
    try:
        detail = await catalog_service.get_account_detail(
            callback.from_user,
            account_id=account_id,
            detail_page=detail_page,
        )
    except CatalogAccountNotFoundError:
        await callback.answer(translate(language, "catalog_account_not_found"), show_alert=True)
        return

    await render_screen_message(
        callback.message,
        text=render_catalog_refresh_progress_text(detail.language, detail.id),
        reply_markup=build_catalog_refresh_markup(
            detail.language,
            source=source,
            account_id=detail.id,
            game_type=detail.game_type,
            page=page,
            detail_page=detail.detail_page,
        ),
        media=CATALOG_ACCOUNT_SCREEN_MEDIA,
        edit=True,
    )
    task = asyncio.create_task(
        _run_account_purchase_task(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            telegram_user=callback.from_user,
            language=detail.language,
            source=source,
            account_id=detail.id,
            game_type=detail.game_type,
            page=page,
            detail_page=detail.detail_page,
        )
    )
    account_refresh_task_registry.register(callback.from_user.id, task)
    await callback.answer()


async def _run_account_purchase_task(
    *,
    bot,
    chat_id: int,
    message_id: int,
    telegram_user,
    language,
    source: AccountRefreshSource,
    account_id: int,
    game_type: GameAccountType,
    page: int,
    detail_page: int,
) -> None:
    try:
        result = await payment_service.purchase_account(
            bot,
            telegram_user,
            account_id=account_id,
            checkout_chat_id=chat_id,
            checkout_message_id=message_id,
        )
    except asyncio.CancelledError:
        logger.debug("Account purchase validation cancelled account_id=%s", account_id)
        raise
    except PaymentUnavailableError as error:
        text = translate(language, "payment_unavailable")
        await _notify_admins_about_account_error(bot, telegram_user, account_id, "purchase", error)
    except AccountValidationError as error:
        text = render_catalog_refresh_failed_text(language, account_id)
        await _notify_admins_about_account_error(bot, telegram_user, account_id, "purchase", error)
    except (AccountUnavailableError, PaymentError) as error:
        text = translate(language, "payment_purchase_failed")
        await _notify_admins_about_account_error(bot, telegram_user, account_id, "purchase", error)
    except Exception as error:
        logger.exception("Account purchase failed account_id=%s", account_id)
        text = translate(language, "payment_purchase_failed")
        await _notify_admins_about_account_error(bot, telegram_user, account_id, "purchase", error)
    else:
        if result.completed:
            text = translate(result.language, "payment_purchase_completed", transaction_id=result.transaction_id)
            if result.delivery_text:
                text = f"{text}\n\n{result.delivery_text}"
            await render_screen_message_by_id(
                bot,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=build_purchase_completed_markup(result.language),
                media=CATALOG_ACCOUNT_SCREEN_MEDIA,
            )
            return
        try:
            detail = await catalog_service.get_account_detail(
                telegram_user,
                account_id=account_id,
                detail_page=detail_page,
            )
        except CatalogAccountNotFoundError:
            text = translate(result.language, "payment_purchase_failed")
        else:
            markup = (
                build_favorite_purchase_payment_link_markup(
                    detail,
                    page=page,
                    payment_url=result.payment_url or "",
                )
                if source == AccountRefreshSource.FAVORITES
                else build_purchase_payment_link_markup(
                    detail,
                    page=page,
                    payment_url=result.payment_url or "",
                )
            )
            await render_screen_message_by_id(
                bot,
                chat_id=chat_id,
                message_id=message_id,
                text=translate(
                    result.language,
                    (
                        "payment_purchase_pending_with_balance"
                        if result.balance_amount > 0
                        else "payment_purchase_pending"
                    ),
                    account_id=detail.id,
                    amount=_format_payment_amount(result.payment_amount),
                    total_amount=_format_payment_amount(detail.sale_price),
                    balance_amount=_format_payment_amount(result.balance_amount),
                ),
                reply_markup=markup,
                media=CATALOG_ACCOUNT_SCREEN_MEDIA,
            )
            return

    await render_screen_message_by_id(
        bot,
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=_build_purchase_failed_markup(
            source=source,
            language=language,
            account_id=account_id,
            game_type=game_type,
            page=page,
            detail_page=detail_page,
        ),
        media=CATALOG_ACCOUNT_SCREEN_MEDIA,
    )


def _build_purchase_failed_markup(
    *,
    source: AccountRefreshSource,
    language,
    account_id: int,
    game_type: GameAccountType,
    page: int,
    detail_page: int,
):
    if source == AccountRefreshSource.FAVORITES:
        return build_favorite_purchase_failed_markup(
            language,
            account_id=account_id,
            page=page,
            detail_page=detail_page,
        )
    return build_catalog_purchase_failed_markup(
        language,
        account_id=account_id,
        game_type=game_type,
        page=page,
        detail_page=detail_page,
    )


def _format_payment_amount(amount) -> str:
    return str(int(amount)) if amount == amount.to_integral() else f"{amount:.2f}"


@router.callback_query(AccountRefreshCallback.filter())
async def handle_account_refresh_callback(
    callback: CallbackQuery,
    callback_data: AccountRefreshCallback,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    source = AccountRefreshSource(callback_data.source)
    action = AccountRefreshAction(callback_data.action)
    language = await catalog_service.get_user_language(callback.from_user)

    if action == AccountRefreshAction.STOP:
        stopped = await account_refresh_task_registry.cancel(callback.from_user.id)
        if stopped:
            await render_screen_message(
                callback.message,
                text=render_catalog_refresh_stopped_text(language, callback_data.account_id),
                reply_markup=build_catalog_refresh_result_markup(
                    language,
                    source=source,
                    account_id=callback_data.account_id,
                    game_type=GameAccountType(callback_data.game_type),
                    page=callback_data.page,
                    detail_page=callback_data.detail_page,
                    deleted=False,
                ),
                media=CATALOG_ACCOUNT_SCREEN_MEDIA,
                edit=True,
            )
            await callback.answer()
            return
        await callback.answer()
        return

    stopped = await account_refresh_task_registry.cancel(callback.from_user.id)
    answer_text = None
    show_alert = False

    try:
        if action == AccountRefreshAction.MAIN_MENU:
            await show_screen(callback.message, Screen.MAIN, callback.from_user, edit=True)
        elif source == AccountRefreshSource.FAVORITES:
            if action == AccountRefreshAction.BACK_TO_LIST:
                await show_favorites_screen(
                    callback.message,
                    callback.from_user,
                    edit=True,
                    page=callback_data.page,
                )
            else:
                await _render_favorites_detail(
                    callback,
                    account_id=callback_data.account_id,
                    page=callback_data.page,
                    detail_page=callback_data.detail_page,
                )
        else:
            game_type = GameAccountType(callback_data.game_type)
            if action == AccountRefreshAction.BACK_TO_LIST:
                await _render_catalog_results(
                    callback,
                    game_type=game_type,
                    page=callback_data.page,
                )
            else:
                await _render_catalog_detail(
                    callback,
                    account_id=callback_data.account_id,
                    page=callback_data.page,
                    detail_page=callback_data.detail_page,
                )
    except CatalogAccountNotFoundError:
        answer_text = translate(language, "catalog_account_not_found")
        show_alert = True
        if source == AccountRefreshSource.FAVORITES:
            await show_favorites_screen(
                callback.message,
                callback.from_user,
                edit=True,
                page=callback_data.page,
            )
        else:
            await _render_catalog_results(
                callback,
                game_type=GameAccountType(callback_data.game_type),
                page=callback_data.page,
            )

    if answer_text is not None:
        await callback.answer(answer_text, show_alert=show_alert)
        return
    await callback.answer()


async def _run_account_refresh_task(
    *,
    bot,
    chat_id: int,
    message_id: int,
    language,
    source: AccountRefreshSource,
    account_id: int,
    game_type: GameAccountType,
    page: int,
    detail_page: int,
    telegram_user,
) -> None:
    try:
        result = await catalog_sync_service.refresh_account(local_account_id=account_id)
    except asyncio.CancelledError:
        logger.debug("Account refresh task cancelled account_id=%s", account_id)
        raise
    except Exception as error:
        logger.exception("Account refresh failed account_id=%s", account_id)
        await _notify_admins_about_account_error(bot, telegram_user, account_id, "refresh", error)
        await render_screen_message_by_id(
            bot,
            chat_id=chat_id,
            message_id=message_id,
            text=render_catalog_refresh_failed_text(language, account_id),
            reply_markup=build_catalog_refresh_result_markup(
                language,
                source=source,
                account_id=account_id,
                game_type=game_type,
                page=page,
                detail_page=detail_page,
                deleted=False,
            ),
            media=CATALOG_ACCOUNT_SCREEN_MEDIA,
        )
        return

    await render_screen_message_by_id(
        bot,
        chat_id=chat_id,
        message_id=message_id,
        text=render_catalog_refresh_result_text(language, result),
        reply_markup=build_catalog_refresh_result_markup(
            language,
            source=source,
            account_id=account_id,
            game_type=game_type,
            page=page,
            detail_page=detail_page,
            deleted=result.deleted,
        ),
        media=CATALOG_ACCOUNT_SCREEN_MEDIA,
    )


async def _notify_admins_about_account_error(
    bot,
    telegram_user,
    account_id: int,
    operation: str,
    error: Exception,
) -> None:
    try:
        await transaction_service.notify_admins_about_account_operation_error(
            bot,
            telegram_user=telegram_user,
            account_id=account_id,
            operation=operation,
            error=error,
        )
    except Exception:
        logger.exception("Unable to notify admins about account operation error account_id=%s", account_id)


async def _render_catalog_detail(
    callback: CallbackQuery,
    *,
    account_id: int,
    page: int,
    detail_page: int,
) -> None:
    detail = await catalog_service.get_account_detail(
        callback.from_user,
        account_id=account_id,
        detail_page=detail_page,
    )
    await render_screen_message(
        callback.message,
        text=render_catalog_detail_text(detail),
        reply_markup=build_catalog_account_detail_markup(detail, page=page),
        media=CATALOG_ACCOUNT_SCREEN_MEDIA,
        edit=True,
    )


async def _render_catalog_results(
    callback: CallbackQuery,
    *,
    game_type: GameAccountType,
    page: int,
) -> None:
    results = await catalog_service.get_search_results(
        callback.from_user,
        game_type=game_type,
        page=page,
    )
    await render_screen_message(
        callback.message,
        text=render_catalog_results_text(results),
        reply_markup=build_catalog_results_markup(results),
        media=CATALOG_RESULTS_SCREEN_MEDIA,
        edit=True,
    )


async def _render_favorites_detail(
    callback: CallbackQuery,
    *,
    account_id: int,
    page: int,
    detail_page: int,
) -> None:
    detail = await catalog_service.get_account_detail(
        callback.from_user,
        account_id=account_id,
        detail_page=detail_page,
    )
    await render_screen_message(
        callback.message,
        text=render_catalog_detail_text(detail),
        reply_markup=build_favorites_account_detail_markup(detail, page=page),
        media=render_menu_view(Screen.FAVORITES, detail.language).media,
        edit=True,
    )
