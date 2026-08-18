from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.db.models.catalog_account import CatalogSortField, GameAccountType, SortDirection
from src.db.models.review import ReviewRating, ReviewStatus
from src.db.models.transaction import TransactionStatus
from src.i18n import Language, translate
from src.keyboards.callbacks import (
    AccountRefreshAction,
    AccountRefreshCallback,
    AccountRefreshSource,
    AdminFaqAction,
    AdminFaqActionCallback,
    AdminFaqAddCallback,
    AdminFaqDeleteAction,
    AdminFaqDeleteCallback,
    AdminFaqDetailCallback,
    AdminFaqEditField,
    AdminFaqEditFieldCallback,
    AdminFaqPageCallback,
    AdminProductDeleteAction,
    AdminProductDeleteCallback,
    AdminProductDetailCallback,
    AdminTransactionAction,
    AdminTransactionActionCallback,
    AdminTransactionDetailCallback,
    AdminTransactionPageCallback,
    AdminTransactionsAction,
    AdminTransactionsCallback,
    AdminProductsAction,
    AdminProductsCallback,
    AdminBroadcastAction,
    AdminBroadcastCallback,
    AdminPanelAction,
    AdminPanelCallback,
    AdminSalesAction,
    AdminSalesCallback,
    AdminReviewAction,
    AdminReviewActionCallback,
    AdminReviewDetailCallback,
    AdminReviewRegistryCallback,
    AdminStatisticsAction,
    AdminStatisticsCallback,
    AdminUserEditField,
    AdminUserEditFieldCallback,
    AdminUserLookupTypeCallback,
    AdminUserViewCallback,
    AdminUsersAction,
    AdminUsersCallback,
    CatalogAccountAction,
    CatalogAccountActionCallback,
    CatalogAccountDetailCallback,
    CatalogBooleanFilterCallback,
    CatalogClearFieldCallback,
    CatalogFilterAction,
    CatalogFilterActionCallback,
    CatalogFilterFieldCallback,
    CatalogFilterPageCallback,
    CatalogGameTypeCallback,
    CatalogResultsPageCallback,
    CatalogSortCallback,
    FavoritesAccountAction,
    FavoritesAccountActionCallback,
    FavoritesAccountDetailCallback,
    FavoritesPageCallback,
    FaqDetailCallback,
    FaqPageCallback,
    NavigationCallback,
    ProfileAction,
    ProfileActionCallback,
    ProfileHistoryPageCallback,
    ProfileLanguageCallback,
    ReviewFlowAction,
    ReviewFlowCallback,
    ReviewRatingCallback,
    ReviewRulesCallback,
    ReviewsPageCallback,
)
from src.schemas.admin import (
    AdminProductDetailSchema,
    AdminTransactionDetailSchema,
    AdminTransactionPageSchema,
    AdminUserSummarySchema,
)
from src.schemas.catalog import (
    CatalogAccountDetailSchema,
    CatalogBooleanChoice,
    CatalogFilterField,
    CatalogFilterViewSchema,
    CatalogResultsPageSchema,
)
from src.schemas.faq import FaqDetailSchema, FaqListViewSchema
from src.schemas.favorites import FavoritesPageSchema
from src.schemas.common.menu import Screen, render_menu_view
from src.schemas.reviews import ReviewRegistryPageSchema
from src.services.catalog import build_catalog_account_button_text
from src.services.reviews import build_admin_review_button_text
from src.services.transactions import build_admin_transaction_button_text


def build_menu_markup(screen: Screen, language: Language) -> InlineKeyboardMarkup:
    view = render_menu_view(screen, language)
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text=button.text,
                url=button.url,
                callback_data=(
                    NavigationCallback(screen=button.target.value).pack() # type: ignore
                    if button.target is not None
                    else None
                ),
            )
            for button in row
        ]
        for row in view.buttons
    ]

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_profile_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "profile_button_top_up"),
                    callback_data=ProfileActionCallback(action=ProfileAction.TOP_UP).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "profile_button_language"),
                    callback_data=ProfileActionCallback(action=ProfileAction.OPEN_LANGUAGE).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "profile_button_history"),
                    callback_data=ProfileActionCallback(action=ProfileAction.HISTORY).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
                ),
            ],
        ]
    )


def build_top_up_prompt_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=NavigationCallback(screen=Screen.PROFILE.value).pack(),  # type: ignore
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(),  # type: ignore
                ),
            ],
        ]
    )


def build_payment_link_markup(language: Language, payment_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=translate(language, "payment_button_pay"), url=payment_url)],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=NavigationCallback(screen=Screen.PROFILE.value).pack(),  # type: ignore
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(),  # type: ignore
                ),
            ],
        ]
    )


def build_purchase_payment_link_markup(
    detail: CatalogAccountDetailSchema,
    *,
    page: int,
    payment_url: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=translate(detail.language, "payment_button_pay"), url=payment_url)],
            [
                InlineKeyboardButton(
                    text=translate(detail.language, "back"),
                    callback_data=CatalogAccountActionCallback(
                        action=CatalogAccountAction.BACK_TO_RESULTS,
                        account_id=detail.id,
                        game_type=detail.game_type.value,  # type: ignore
                        page=page,
                        detail_page=detail.detail_page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(detail.language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(),  # type: ignore
                ),
            ],
        ]
    )


def build_favorite_purchase_payment_link_markup(
    detail: CatalogAccountDetailSchema,
    *,
    page: int,
    payment_url: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=translate(detail.language, "payment_button_pay"), url=payment_url)],
            [
                InlineKeyboardButton(
                    text=translate(detail.language, "back"),
                    callback_data=FavoritesAccountActionCallback(
                        action=FavoritesAccountAction.BACK_TO_LIST,
                        account_id=detail.id,
                        page=page,
                        detail_page=detail.detail_page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(detail.language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(),  # type: ignore
                ),
            ],
        ]
    )


def build_profile_language_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_language_button_label(language, Language.RU),
                    callback_data=ProfileLanguageCallback(language=Language.RU.value).pack(), # type: ignore
                ),
                InlineKeyboardButton(
                    text=_language_button_label(language, Language.EN),
                    callback_data=ProfileLanguageCallback(language=Language.EN.value).pack(), # type: ignore
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=NavigationCallback(screen=Screen.PROFILE.value).pack(), # type: ignore
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
                ),
            ],
        ]
    )


def build_profile_history_markup(
    language: Language,
    *,
    page: int,
    has_previous: bool,
    has_next: bool,
) -> InlineKeyboardMarkup:
    inline_keyboard: list[list[InlineKeyboardButton]] = []

    pagination_row: list[InlineKeyboardButton] = []
    if has_previous:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(language, "pagination_previous"),
                callback_data=ProfileHistoryPageCallback(page=page - 1).pack(),
            )
        )
    if has_next:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(language, "pagination_next"),
                callback_data=ProfileHistoryPageCallback(page=page + 1).pack(),
            )
        )
    if pagination_row:
        inline_keyboard.append(pagination_row)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(language, "back"),
                callback_data=NavigationCallback(screen=Screen.PROFILE.value).pack(), # type: ignore
            ),
        ]
    )
    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(language, "back_to_main_menu"),
                callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_catalog_game_type_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "catalog_game_type_mir_tankov"),
                    callback_data=CatalogGameTypeCallback(game_type=GameAccountType.MIR_TANKOV.value).pack(), # type: ignore
                ),
                InlineKeyboardButton(
                    text=translate(language, "catalog_game_type_tanks_blitz"),
                    callback_data=CatalogGameTypeCallback(game_type=GameAccountType.TANKS_BLITZ.value).pack(), # type: ignore
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "catalog_game_type_world_of_tanks"),
                    callback_data=CatalogGameTypeCallback(game_type=GameAccountType.WORLD_OF_TANKS.value).pack(), # type: ignore
                ),
                InlineKeyboardButton(
                    text=translate(language, "catalog_game_type_wot_blitz"),
                    callback_data=CatalogGameTypeCallback(game_type=GameAccountType.WOT_BLITZ.value).pack(), # type: ignore
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
                ),
            ],
        ]
    )


def build_catalog_filter_markup(view: CatalogFilterViewSchema) -> InlineKeyboardMarkup:
    fields = _catalog_fields_for_page(view.game_type, view.page)
    inline_keyboard: list[list[InlineKeyboardButton]] = []

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(view.language, "catalog_button_search"),
                callback_data=CatalogFilterActionCallback(
                    action=CatalogFilterAction.SEARCH,
                    game_type=view.game_type.value, # type: ignore
                    page=view.page,
                ).pack(),
                style="primary",
            )
        ]
    )

    for index in range(0, len(fields), 2):
        row = fields[index:index + 2]
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=_catalog_filter_button_label(view.language, field),
                    callback_data=CatalogFilterFieldCallback(
                        game_type=view.game_type.value, # type: ignore
                        page=view.page,
                        field=field.value, # type: ignore
                    ).pack(),
                )
                for field in row
            ]
        )

    pagination_row: list[InlineKeyboardButton] = []
    if view.page > 1:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(view.language, "pagination_previous"),
                callback_data=CatalogFilterPageCallback(game_type=view.game_type.value, page=view.page - 1).pack(), # type: ignore
            )
        )
    if view.page < view.total_pages:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(view.language, "pagination_next"),
                callback_data=CatalogFilterPageCallback(game_type=view.game_type.value, page=view.page + 1).pack(), # type: ignore
            )
        )
    if pagination_row:
        inline_keyboard.append(pagination_row)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(view.language, "catalog_button_reset_filter"),
                callback_data=CatalogFilterActionCallback(
                    action=CatalogFilterAction.ASK_RESET,
                    game_type=view.game_type.value, # type: ignore
                    page=view.page,
                ).pack(),
            ),
        ]
    )

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(view.language, "back"),
                callback_data=NavigationCallback(screen=Screen.BUY.value).pack(), # type: ignore
            ),
        ]
    )
    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(view.language, "back_to_main_menu"),
                callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_catalog_filter_input_back_markup(
    language: Language,
    game_type: GameAccountType,
    page: int,
    field: CatalogFilterField,
    *,
    include_clear_field: bool = True,
) -> InlineKeyboardMarkup:
    inline_keyboard: list[list[InlineKeyboardButton]] = []
    if include_clear_field:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=translate(language, "catalog_button_clear_field"),
                    callback_data=CatalogClearFieldCallback(
                        game_type=game_type.value, # type: ignore
                        page=page,
                        field=field.value, # type: ignore
                    ).pack(),
                    style="danger",
                ),
            ]
        )
    inline_keyboard.extend(
        [
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=CatalogFilterPageCallback(game_type=game_type.value, page=page).pack(), # type: ignore
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_catalog_boolean_markup(
    language: Language,
    game_type: GameAccountType,
    page: int,
    field: CatalogFilterField,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "yes"),
                    callback_data=CatalogBooleanFilterCallback(
                        game_type=game_type.value, # type: ignore
                        page=page,
                        field=field.value, # type: ignore
                        choice=CatalogBooleanChoice.YES.value, # type: ignore
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "no"),
                    callback_data=CatalogBooleanFilterCallback(
                        game_type=game_type.value, # type: ignore
                        page=page,
                        field=field.value, # type: ignore
                        choice=CatalogBooleanChoice.NO.value, # type: ignore
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "catalog_filter_any_value"),
                    callback_data=CatalogBooleanFilterCallback(
                        game_type=game_type.value, # type: ignore
                        page=page,
                        field=field.value, # type: ignore
                        choice=CatalogBooleanChoice.ANY.value, # type: ignore
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "catalog_button_clear_field"),
                    callback_data=CatalogClearFieldCallback(
                        game_type=game_type.value, # type: ignore
                        page=page,
                        field=field.value, # type: ignore
                    ).pack(),
                    style="danger",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=CatalogFilterPageCallback(game_type=game_type.value, page=page).pack(), # type: ignore
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
                ),
            ],
        ]
    )


def build_catalog_results_markup(results: CatalogResultsPageSchema) -> InlineKeyboardMarkup:
    inline_keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=_catalog_sort_button_text(
                    results.language,
                    CatalogSortField.LAST_ACTIVITY,
                    results.last_activity_sort_direction,
                ),
                callback_data=CatalogSortCallback(game_type=results.game_type.value, field=CatalogSortField.LAST_ACTIVITY.value).pack(), # type: ignore
            ),
        ],
        [
            InlineKeyboardButton(
                text=_catalog_sort_button_text(
                    results.language,
                    CatalogSortField.PRICE,
                    results.price_sort_direction,
                ),
                callback_data=CatalogSortCallback(game_type=results.game_type.value, field=CatalogSortField.PRICE.value).pack(), # type: ignore
            ),
            InlineKeyboardButton(
                text=_catalog_sort_button_text(
                    results.language,
                    CatalogSortField.NEWEST,
                    results.newest_sort_direction,
                ),
                callback_data=CatalogSortCallback(game_type=results.game_type.value, field=CatalogSortField.NEWEST.value).pack(), # type: ignore
            ),
        ],
    ]

    for item in results.items:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=build_catalog_account_button_text(item),
                    callback_data=CatalogAccountDetailCallback(
                        account_id=item.id,
                        game_type=results.game_type.value, # type: ignore
                        page=results.page,
                        detail_page=1,
                    ).pack(),
                ),
            ]
        )

    pagination_row: list[InlineKeyboardButton] = []
    if results.page > 1:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(results.language, "pagination_previous"),
                callback_data=CatalogResultsPageCallback(game_type=results.game_type.value, page=results.page - 1).pack(), # type: ignore
            )
        )
    if results.page < results.total_pages:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(results.language, "pagination_next"),
                callback_data=CatalogResultsPageCallback(game_type=results.game_type.value, page=results.page + 1).pack(), # type: ignore
            )
        )
    if pagination_row:
        inline_keyboard.append(pagination_row)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(results.language, "back"),
                callback_data=CatalogFilterPageCallback(game_type=results.game_type.value, page=1).pack(), # type: ignore
            ),
        ]
    )
    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(results.language, "back_to_main_menu"),
                callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_catalog_account_detail_markup(detail: CatalogAccountDetailSchema, *, page: int) -> InlineKeyboardMarkup:
    favorite_key = "catalog_button_remove_favorite" if detail.is_favorite else "catalog_button_add_favorite"
    inline_keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=translate(detail.language, "catalog_button_buy_account"),
                callback_data=CatalogAccountActionCallback(
                    action=CatalogAccountAction.BUY,
                    account_id=detail.id,
                    game_type=detail.game_type.value, # type: ignore
                    page=page,
                    detail_page=detail.detail_page,
                ).pack(),
                style="success",
            ),
        ],
        [
            InlineKeyboardButton(
                text=translate(detail.language, favorite_key),
                callback_data=CatalogAccountActionCallback(
                    action=CatalogAccountAction.TOGGLE_FAVORITE,
                    account_id=detail.id,
                    game_type=detail.game_type.value, # type: ignore
                    page=page,
                    detail_page=detail.detail_page,
                ).pack(),
                style="danger" if detail.is_favorite else None,
            ),
        ],
        [
            InlineKeyboardButton(
                text=translate(detail.language, "catalog_button_refresh_account"),
                callback_data=CatalogAccountActionCallback(
                    action=CatalogAccountAction.REFRESH,
                    account_id=detail.id,
                    game_type=detail.game_type.value, # type: ignore
                    page=page,
                    detail_page=detail.detail_page,
                ).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=translate(detail.language, "back"),
                callback_data=CatalogAccountActionCallback(
                    action=CatalogAccountAction.BACK_TO_RESULTS,
                    account_id=detail.id,
                    game_type=detail.game_type.value, # type: ignore
                    page=page,
                    detail_page=detail.detail_page,
                ).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=translate(detail.language, "back_to_main_menu"),
                callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
            ),
        ],
    ]
    if detail.total_detail_pages > 1:
        pagination_row: list[InlineKeyboardButton] = []
        if detail.detail_page > 1:
            pagination_row.append(
                InlineKeyboardButton(
                    text=translate(detail.language, "pagination_previous"),
                    callback_data=CatalogAccountActionCallback(
                        action=CatalogAccountAction.PREVIOUS_DETAIL_PAGE,
                        account_id=detail.id,
                        game_type=detail.game_type.value, # type: ignore
                        page=page,
                        detail_page=detail.detail_page,
                    ).pack(),
                )
            )
        if detail.detail_page < detail.total_detail_pages:
            pagination_row.append(
                InlineKeyboardButton(
                    text=translate(detail.language, "pagination_next"),
                    callback_data=CatalogAccountActionCallback(
                        action=CatalogAccountAction.NEXT_DETAIL_PAGE,
                        account_id=detail.id,
                        game_type=detail.game_type.value, # type: ignore
                        page=page,
                        detail_page=detail.detail_page,
                    ).pack(),
                )
            )
        if pagination_row:
            inline_keyboard.insert(3, pagination_row)
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_catalog_purchase_failed_markup(
    language: Language,
    *,
    account_id: int,
    game_type: GameAccountType,
    page: int,
    detail_page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=CatalogAccountActionCallback(
                        action=CatalogAccountAction.BACK_TO_RESULTS,
                        account_id=account_id,
                        game_type=game_type.value,
                        page=page,
                        detail_page=detail_page,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(),  # type: ignore
                )
            ],
        ]
    )


def build_catalog_reset_confirmation_markup(language: Language, game_type: GameAccountType, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "yes"),
                    callback_data=CatalogFilterActionCallback(
                        action=CatalogFilterAction.CONFIRM_RESET,
                        game_type=game_type.value, # type: ignore
                        page=page,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "no"),
                    callback_data=CatalogFilterActionCallback(
                        action=CatalogFilterAction.CANCEL_RESET,
                        game_type=game_type.value, # type: ignore
                        page=page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=CatalogFilterPageCallback(game_type=game_type.value, page=page).pack(), # type: ignore
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
                ),
            ],
        ]
    )


def build_favorites_markup(page_data: FavoritesPageSchema) -> InlineKeyboardMarkup:
    inline_keyboard: list[list[InlineKeyboardButton]] = []

    for item in page_data.items:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=build_catalog_account_button_text(item),
                    callback_data=FavoritesAccountDetailCallback(account_id=item.id, page=page_data.page, detail_page=1).pack(),
                ),
            ]
        )

    pagination_row: list[InlineKeyboardButton] = []
    if page_data.page > 1:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(page_data.language, "pagination_previous"),
                callback_data=FavoritesPageCallback(page=page_data.page - 1).pack(),
            )
        )
    if page_data.page < page_data.total_pages:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(page_data.language, "pagination_next"),
                callback_data=FavoritesPageCallback(page=page_data.page + 1).pack(),
            )
        )
    if pagination_row:
        inline_keyboard.append(pagination_row)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(page_data.language, "back"),
                callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_favorites_account_detail_markup(detail: CatalogAccountDetailSchema, *, page: int) -> InlineKeyboardMarkup:
    favorite_key = "catalog_button_remove_favorite" if detail.is_favorite else "catalog_button_add_favorite"
    inline_keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=translate(detail.language, "catalog_button_buy_account"),
                callback_data=FavoritesAccountActionCallback(
                    action=FavoritesAccountAction.BUY,
                    account_id=detail.id,
                    page=page,
                    detail_page=detail.detail_page,
                ).pack(),
                style="success",
            ),
        ],
        [
            InlineKeyboardButton(
                text=translate(detail.language, favorite_key),
                callback_data=FavoritesAccountActionCallback(
                    action=FavoritesAccountAction.TOGGLE_FAVORITE,
                    account_id=detail.id,
                    page=page,
                    detail_page=detail.detail_page,
                ).pack(),
                style="danger" if detail.is_favorite else None,
            ),
        ],
        [
            InlineKeyboardButton(
                text=translate(detail.language, "catalog_button_refresh_account"),
                callback_data=FavoritesAccountActionCallback(
                    action=FavoritesAccountAction.REFRESH,
                    account_id=detail.id,
                    page=page,
                    detail_page=detail.detail_page,
                ).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=translate(detail.language, "back"),
                callback_data=FavoritesAccountActionCallback(
                    action=FavoritesAccountAction.BACK_TO_LIST,
                    account_id=detail.id,
                    page=page,
                    detail_page=detail.detail_page,
                ).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=translate(detail.language, "back_to_main_menu"),
                callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
            ),
        ],
    ]
    if detail.total_detail_pages > 1:
        pagination_row: list[InlineKeyboardButton] = []
        if detail.detail_page > 1:
            pagination_row.append(
                InlineKeyboardButton(
                    text=translate(detail.language, "pagination_previous"),
                    callback_data=FavoritesAccountActionCallback(
                        action=FavoritesAccountAction.PREVIOUS_DETAIL_PAGE,
                        account_id=detail.id,
                        page=page,
                        detail_page=detail.detail_page,
                    ).pack(),
                )
            )
        if detail.detail_page < detail.total_detail_pages:
            pagination_row.append(
                InlineKeyboardButton(
                    text=translate(detail.language, "pagination_next"),
                    callback_data=FavoritesAccountActionCallback(
                        action=FavoritesAccountAction.NEXT_DETAIL_PAGE,
                        account_id=detail.id,
                        page=page,
                        detail_page=detail.detail_page,
                    ).pack(),
                )
            )
        if pagination_row:
            inline_keyboard.insert(3, pagination_row)
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_favorite_purchase_failed_markup(
    language: Language,
    *,
    account_id: int,
    page: int,
    detail_page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=FavoritesAccountActionCallback(
                        action=FavoritesAccountAction.BACK_TO_LIST,
                        account_id=account_id,
                        page=page,
                        detail_page=detail_page,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(),  # type: ignore
                )
            ],
        ]
    )


def build_purchase_completed_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=NavigationCallback(screen=Screen.BUY.value).pack(),  # type: ignore
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(),  # type: ignore
                )
            ],
        ]
    )


def build_catalog_refresh_markup(
    language: Language,
    *,
    source: AccountRefreshSource,
    account_id: int,
    game_type: GameAccountType,
    page: int,
    detail_page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "catalog_button_stop_refresh"),
                    callback_data=AccountRefreshCallback(
                        source=source.value,
                        action=AccountRefreshAction.STOP.value,
                        account_id=account_id,
                        game_type=game_type.value, # type: ignore
                        page=page,
                        detail_page=detail_page,
                    ).pack(),
                    style="danger",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AccountRefreshCallback(
                        source=source.value,
                        action=AccountRefreshAction.BACK_TO_DETAIL.value,
                        account_id=account_id,
                        game_type=game_type.value, # type: ignore
                        page=page,
                        detail_page=detail_page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=AccountRefreshCallback(
                        source=source.value,
                        action=AccountRefreshAction.MAIN_MENU.value,
                        account_id=account_id,
                        game_type=game_type.value, # type: ignore
                        page=page,
                        detail_page=detail_page,
                    ).pack(),
                ),
            ],
        ]
    )


def build_catalog_refresh_result_markup(
    language: Language,
    *,
    source: AccountRefreshSource,
    account_id: int,
    game_type: GameAccountType,
    page: int,
    detail_page: int,
    deleted: bool,
) -> InlineKeyboardMarkup:
    back_action = AccountRefreshAction.BACK_TO_LIST if deleted else AccountRefreshAction.BACK_TO_DETAIL
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AccountRefreshCallback(
                        source=source.value,
                        action=back_action.value,
                        account_id=account_id,
                        game_type=game_type.value, # type: ignore
                        page=page,
                        detail_page=detail_page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=AccountRefreshCallback(
                        source=source.value,
                        action=AccountRefreshAction.MAIN_MENU.value,
                        account_id=account_id,
                        game_type=game_type.value, # type: ignore
                        page=page,
                        detail_page=detail_page,
                    ).pack(),
                ),
            ],
        ]
    )


def build_reviews_markup(page: int, has_previous: bool, has_next: bool, language: Language) -> InlineKeyboardMarkup:
    inline_keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=translate(language, "review_button_leave"),
                callback_data=ReviewFlowCallback(action=ReviewFlowAction.START, page=page).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=translate(language, "review_button_rules"),
                callback_data=ReviewRulesCallback(page=page).pack(),
            ),
        ],
    ]

    pagination_row: list[InlineKeyboardButton] = []
    if has_previous:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(language, "pagination_previous"),
                callback_data=ReviewsPageCallback(page=page - 1).pack(),
            )
        )
    if has_next:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(language, "pagination_next"),
                callback_data=ReviewsPageCallback(page=page + 1).pack(),
            )
        )
    if pagination_row:
        inline_keyboard.append(pagination_row)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(language, "back"),
                callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_review_rating_markup_for_page(language: Language, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "review_rating_positive"),
                    callback_data=ReviewRatingCallback(rating=ReviewRating.POSITIVE.value, page=page).pack(), # type: ignore
                ),
                InlineKeyboardButton(
                    text=translate(language, "review_rating_negative"),
                    callback_data=ReviewRatingCallback(rating=ReviewRating.NEGATIVE.value, page=page).pack(), # type: ignore
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=ReviewFlowCallback(action=ReviewFlowAction.CANCEL, page=page).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
                ),
            ],
        ]
    )


def build_review_rules_markup(language: Language, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=ReviewsPageCallback(page=page).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
                ),
            ],
        ]
    )


def build_review_waiting_markup(language: Language, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=ReviewFlowCallback(action=ReviewFlowAction.CANCEL, page=page).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
                ),
            ],
        ]
    )


def build_public_faq_list_markup(view: FaqListViewSchema) -> InlineKeyboardMarkup:
    inline_keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=_truncate_button_text(item.display_question),
                callback_data=FaqDetailCallback(faq_id=item.id, page=view.page).pack(),
            )
        ]
        for item in view.items
    ]
    pagination_row: list[InlineKeyboardButton] = []
    if view.has_previous:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(view.language, "pagination_previous"),
                callback_data=FaqPageCallback(page=view.page - 1).pack(),
            )
        )
    if view.has_next:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(view.language, "pagination_next"),
                callback_data=FaqPageCallback(page=view.page + 1).pack(),
            )
        )
    if pagination_row:
        inline_keyboard.append(pagination_row)
    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(view.language, "back"),
                callback_data=NavigationCallback(screen=Screen.INFO.value).pack(), # type: ignore
            ),
        ]
    )
    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(view.language, "back_to_main_menu"),
                callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_public_faq_detail_markup(language: Language, *, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=FaqPageCallback(page=page).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=NavigationCallback(screen=Screen.MAIN.value).pack(), # type: ignore
                ),
            ],
        ]
    )


def build_admin_back_markup(language: Language, callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=callback_data,
                ),
            ],
        ]
    )


def build_admin_main_markup(language: Language, sales_enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_registry"),
                    callback_data=AdminPanelCallback(action=AdminPanelAction.REGISTRY).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_button_users"),
                    callback_data=AdminPanelCallback(action=AdminPanelAction.USERS).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_statistics"),
                    callback_data=AdminPanelCallback(action=AdminPanelAction.STATISTICS).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_button_products"),
                    callback_data=AdminPanelCallback(action=AdminPanelAction.PRODUCTS).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_transactions"),
                    callback_data=AdminPanelCallback(action=AdminPanelAction.TRANSACTIONS).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_button_manage_faq"),
                    callback_data=AdminPanelCallback(action=AdminPanelAction.FAQ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_force_refresh"),
                    callback_data=AdminPanelCallback(action=AdminPanelAction.FORCE_REFRESH).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_sales"),
                    callback_data=AdminPanelCallback(action=AdminPanelAction.SALES).pack(),
                ),
            ],
        ]
    )


def build_admin_sales_markup(language: Language, game_enabled: dict[GameAccountType, bool]) -> InlineKeyboardMarkup:
    def game_button(game_type: GameAccountType, action: AdminSalesAction) -> InlineKeyboardButton:
        status = "🟢" if game_enabled[game_type] else "🔴"
        label_key = {
            GameAccountType.MIR_TANKOV: "catalog_game_type_mir_tankov",
            GameAccountType.TANKS_BLITZ: "catalog_game_type_tanks_blitz",
            GameAccountType.WORLD_OF_TANKS: "catalog_game_type_world_of_tanks",
            GameAccountType.WOT_BLITZ: "catalog_game_type_wot_blitz",
        }[game_type]
        return InlineKeyboardButton(
            text=f"{status} {translate(language, label_key)}",
            callback_data=AdminSalesCallback(action=action).pack(),
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_toggle_all_sales"),
                    callback_data=AdminSalesCallback(action=AdminSalesAction.TOGGLE_ALL).pack(),
                ),
            ],
            [game_button(GameAccountType.MIR_TANKOV, AdminSalesAction.TOGGLE_MIR_TANKOV)],
            [game_button(GameAccountType.TANKS_BLITZ, AdminSalesAction.TOGGLE_TANKS_BLITZ)],
            [game_button(GameAccountType.WORLD_OF_TANKS, AdminSalesAction.TOGGLE_WORLD_OF_TANKS)],
            [game_button(GameAccountType.WOT_BLITZ, AdminSalesAction.TOGGLE_WOT_BLITZ)],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminSalesCallback(action=AdminSalesAction.BACK).pack(),
                ),
            ],
        ]
    )


def build_admin_products_menu_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_find_product"),
                    callback_data=AdminProductsCallback(action=AdminProductsAction.LOOKUP).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_button_export_products"),
                    callback_data=AdminProductsCallback(action=AdminProductsAction.EXPORT).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_product_markups"),
                    callback_data=AdminProductsCallback(action=AdminProductsAction.MARKUPS).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminProductsCallback(action=AdminProductsAction.BACK_TO_MAIN).pack(),
                ),
            ],
        ]
    )


def build_admin_transactions_menu_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_completed_transactions"),
                    callback_data=AdminTransactionsCallback(action=AdminTransactionsAction.OPEN_COMPLETED).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_button_pending_transactions"),
                    callback_data=AdminTransactionsCallback(action=AdminTransactionsAction.OPEN_PENDING).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_find_transaction"),
                    callback_data=AdminTransactionsCallback(action=AdminTransactionsAction.LOOKUP).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_button_export_transactions"),
                    callback_data=AdminTransactionsCallback(action=AdminTransactionsAction.EXPORT).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminTransactionsCallback(action=AdminTransactionsAction.BACK_TO_MAIN).pack(),
                ),
            ],
        ]
    )


def build_admin_transaction_lookup_prompt_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminTransactionsCallback(action=AdminTransactionsAction.OPEN_MENU).pack(),
                ),
            ],
        ]
    )


def build_admin_transactions_page_markup(page_data: AdminTransactionPageSchema) -> InlineKeyboardMarkup:
    inline_keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=build_admin_transaction_button_text(item, page_data.language),
                callback_data=AdminTransactionDetailCallback(
                    transaction_id=item.id,
                    status=page_data.status.value,
                    page=page_data.page,
                ).pack(),
            ),
        ]
        for item in page_data.items
    ]

    pagination_row: list[InlineKeyboardButton] = []
    if page_data.has_previous:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(page_data.language, "pagination_previous"),
                callback_data=AdminTransactionPageCallback(
                    status=page_data.status.value,
                    page=page_data.page - 1,
                ).pack(),
            )
        )
    if page_data.has_next:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(page_data.language, "pagination_next"),
                callback_data=AdminTransactionPageCallback(
                    status=page_data.status.value,
                    page=page_data.page + 1,
                ).pack(),
            )
        )
    if pagination_row:
        inline_keyboard.append(pagination_row)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(page_data.language, "back"),
                callback_data=AdminTransactionsCallback(action=AdminTransactionsAction.OPEN_MENU).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_admin_transaction_detail_markup(
    detail: AdminTransactionDetailSchema,
    *,
    status: TransactionStatus,
    page: int,
) -> InlineKeyboardMarkup:
    inline_keyboard: list[list[InlineKeyboardButton]] = []

    if status == TransactionStatus.PENDING:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=translate(detail.language, "admin_button_cancel_transaction"),
                    callback_data=AdminTransactionActionCallback(
                        action=AdminTransactionAction.CANCEL,
                        transaction_id=detail.id,
                        status=status.value,
                        page=page,
                    ).pack(),
                    style="danger",
                ),
            ]
        )

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(detail.language, "back"),
                callback_data=AdminTransactionPageCallback(status=status.value, page=page).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_admin_product_lookup_prompt_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminProductsCallback(action=AdminProductsAction.OPEN_MENU).pack(),
                ),
            ],
        ]
    )


def build_admin_product_detail_markup(product: AdminProductDetailSchema) -> InlineKeyboardMarkup:
    inline_keyboard: list[list[InlineKeyboardButton]] = [
        [
                InlineKeyboardButton(
                    text=translate(product.language, "admin_button_delete_product"),
                    callback_data=AdminProductDeleteCallback(
                        product_id=product.id,
                        detail_page=product.detail_page,
                        action=AdminProductDeleteAction.ASK,
                    ).pack(),
                    style="danger",
                ),
        ],
        [
            InlineKeyboardButton(
                text=translate(product.language, "back"),
                callback_data=AdminProductsCallback(action=AdminProductsAction.OPEN_MENU).pack(),
            ),
        ],
    ]
    if product.total_detail_pages > 1:
        pagination_row: list[InlineKeyboardButton] = []
        if product.detail_page > 1:
            pagination_row.append(
                InlineKeyboardButton(
                    text=translate(product.language, "pagination_previous"),
                    callback_data=AdminProductDetailCallback(
                        product_id=product.id,
                        detail_page=product.detail_page - 1,
                    ).pack(),
                )
            )
        if product.detail_page < product.total_detail_pages:
            pagination_row.append(
                InlineKeyboardButton(
                    text=translate(product.language, "pagination_next"),
                    callback_data=AdminProductDetailCallback(
                        product_id=product.id,
                        detail_page=product.detail_page + 1,
                    ).pack(),
                )
            )
        if pagination_row:
            inline_keyboard.insert(1, pagination_row)
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_admin_product_delete_confirmation_markup(
    language: Language,
    product_id: int,
    *,
    detail_page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "yes"),
                    callback_data=AdminProductDeleteCallback(
                        product_id=product_id,
                        detail_page=detail_page,
                        action=AdminProductDeleteAction.CONFIRM,
                    ).pack(),
                    style="danger",
                ),
                InlineKeyboardButton(
                    text=translate(language, "no"),
                    callback_data=AdminProductDeleteCallback(
                        product_id=product_id,
                        detail_page=detail_page,
                        action=AdminProductDeleteAction.CANCEL,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminProductDetailCallback(product_id=product_id, detail_page=detail_page).pack(),
                ),
            ],
        ]
    )


def build_admin_registry_menu_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_pending_reviews"),
                    callback_data=AdminReviewRegistryCallback(
                        status=ReviewStatus.PENDING.value, # type: ignore
                        page=1,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_button_approved_reviews"),
                    callback_data=AdminReviewRegistryCallback(
                        status=ReviewStatus.APPROVED.value,  # type: ignore
                        page=1,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminPanelCallback(action=AdminPanelAction.BACK_TO_MAIN).pack(),
                ),
            ],
        ]
    )


def build_admin_users_menu_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_broadcast"),
                    callback_data=AdminUsersCallback(action=AdminUsersAction.BROADCAST).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_button_export_users"),
                    callback_data=AdminUsersCallback(action=AdminUsersAction.EXPORT).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_edit_user"),
                    callback_data=AdminUsersCallback(action=AdminUsersAction.EDIT).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminUsersCallback(action=AdminUsersAction.BACK_TO_MAIN).pack(),
                ),
            ],
        ]
    )


def build_admin_faq_list_markup(view: FaqListViewSchema) -> InlineKeyboardMarkup:
    inline_keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=_truncate_button_text(item.display_question),
                callback_data=AdminFaqDetailCallback(faq_id=item.id, page=view.page).pack(),
            ),
        ]
        for item in view.items
    ]
    pagination_row: list[InlineKeyboardButton] = []
    if view.has_previous:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(view.language, "pagination_previous"),
                callback_data=AdminFaqPageCallback(page=view.page - 1).pack(),
            )
        )
    if view.has_next:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(view.language, "pagination_next"),
                callback_data=AdminFaqPageCallback(page=view.page + 1).pack(),
            )
        )
    if pagination_row:
        inline_keyboard.append(pagination_row)
    inline_keyboard.append(
        [
                InlineKeyboardButton(
                    text=translate(view.language, "admin_button_add_faq"),
                    callback_data=AdminFaqAddCallback(page=view.page).pack(),
                ),
            ]
    )
    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(view.language, "back"),
                callback_data=AdminFaqActionCallback(action=AdminFaqAction.BACK_TO_MAIN).pack(),
            ),
        ]
    )
    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(view.language, "back_to_main_menu"),
                callback_data=AdminFaqActionCallback(action=AdminFaqAction.BACK_TO_MAIN).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_admin_faq_detail_markup(detail: FaqDetailSchema) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(detail.language, "admin_button_edit_faq_question_ru"),
                    callback_data=AdminFaqEditFieldCallback(
                        faq_id=detail.id,
                        page=detail.page,
                        field=AdminFaqEditField.QUESTION_RU,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(detail.language, "admin_button_edit_faq_question_en"),
                    callback_data=AdminFaqEditFieldCallback(
                        faq_id=detail.id,
                        page=detail.page,
                        field=AdminFaqEditField.QUESTION_EN,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(detail.language, "admin_button_edit_faq_answer_ru"),
                    callback_data=AdminFaqEditFieldCallback(
                        faq_id=detail.id,
                        page=detail.page,
                        field=AdminFaqEditField.ANSWER_RU,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(detail.language, "admin_button_edit_faq_answer_en"),
                    callback_data=AdminFaqEditFieldCallback(
                        faq_id=detail.id,
                        page=detail.page,
                        field=AdminFaqEditField.ANSWER_EN,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(detail.language, "admin_button_delete_faq"),
                    callback_data=AdminFaqDeleteCallback(
                        faq_id=detail.id,
                        page=detail.page,
                        action=AdminFaqDeleteAction.ASK,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(detail.language, "back"),
                    callback_data=AdminFaqPageCallback(page=detail.page).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(detail.language, "back_to_main_menu"),
                    callback_data=AdminFaqActionCallback(action=AdminFaqAction.BACK_TO_MAIN).pack(),
                ),
            ],
        ]
    )


def build_admin_faq_prompt_markup(language: Language, *, faq_id: int | None = None, page: int = 1) -> InlineKeyboardMarkup:
    back_callback = (
        AdminFaqDetailCallback(faq_id=faq_id, page=page).pack()
        if faq_id is not None
        else AdminFaqPageCallback(page=page).pack()
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=back_callback,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=AdminFaqActionCallback(action=AdminFaqAction.BACK_TO_MAIN).pack(),
                ),
            ],
        ]
    )


def build_admin_faq_delete_confirmation_markup(language: Language, faq_id: int, *, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "yes"),
                    callback_data=AdminFaqDeleteCallback(
                        faq_id=faq_id,
                        page=page,
                        action=AdminFaqDeleteAction.CONFIRM,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "no"),
                    callback_data=AdminFaqDeleteCallback(
                        faq_id=faq_id,
                        page=page,
                        action=AdminFaqDeleteAction.CANCEL,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminFaqDetailCallback(faq_id=faq_id, page=page).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_main_menu"),
                    callback_data=AdminFaqActionCallback(action=AdminFaqAction.BACK_TO_MAIN).pack(),
                ),
            ],
        ]
    )


def build_admin_statistics_menu_markup(language: Language, *, custom_prompt: bool = False) -> InlineKeyboardMarkup:
    back_action = AdminStatisticsAction.OPEN_MENU if custom_prompt else AdminStatisticsAction.BACK_TO_MAIN
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_statistics_button_all_time"),
                    callback_data=AdminStatisticsCallback(action=AdminStatisticsAction.ALL_TIME).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_statistics_button_current_month"),
                    callback_data=AdminStatisticsCallback(action=AdminStatisticsAction.CURRENT_MONTH).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_statistics_button_previous_month"),
                    callback_data=AdminStatisticsCallback(action=AdminStatisticsAction.PREVIOUS_MONTH).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_statistics_button_week"),
                    callback_data=AdminStatisticsCallback(action=AdminStatisticsAction.WEEK).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_statistics_button_day"),
                    callback_data=AdminStatisticsCallback(action=AdminStatisticsAction.DAY).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_statistics_button_custom"),
                    callback_data=AdminStatisticsCallback(action=AdminStatisticsAction.CUSTOM).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminStatisticsCallback(action=back_action).pack(),
                ),
            ],
        ]
    )


def build_admin_statistics_back_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminStatisticsCallback(action=AdminStatisticsAction.OPEN_MENU).pack(),
                ),
            ],
        ]
    )


def build_admin_broadcast_prompt_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminUsersCallback(action=AdminUsersAction.OPEN_MENU).pack(),
                ),
            ],
        ]
    )


def build_admin_broadcast_confirmation_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "yes"),
                    callback_data=AdminBroadcastCallback(action=AdminBroadcastAction.SEND).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "no"),
                    callback_data=AdminBroadcastCallback(action=AdminBroadcastAction.CANCEL).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminBroadcastCallback(action=AdminBroadcastAction.BACK).pack(),
                ),
            ],
        ]
    )


def build_admin_user_lookup_type_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_user_identifier_bot_id"),
                    callback_data=AdminUserLookupTypeCallback(identifier_type="bot_id").pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_user_identifier_tg_id"),
                    callback_data=AdminUserLookupTypeCallback(identifier_type="telegram_id").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminUsersCallback(action=AdminUsersAction.OPEN_MENU).pack(),
                ),
            ],
        ]
    )


def build_admin_user_lookup_prompt_markup(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminUsersCallback(action=AdminUsersAction.EDIT).pack(),
                ),
            ],
        ]
    )


def build_admin_user_detail_markup(user: AdminUserSummarySchema) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(user.language, "admin_button_edit_balance"),
                    callback_data=AdminUserEditFieldCallback(
                        field=AdminUserEditField.BALANCE,
                        user_id=user.bot_user_id,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(user.language, "back"),
                    callback_data=AdminUsersCallback(action=AdminUsersAction.OPEN_MENU).pack(),
                ),
            ],
        ]
    )


def build_admin_user_balance_prompt_markup(language: Language, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminUserViewCallback(
                        user_id=user_id,
                    ).pack(),
                ),
            ],
        ]
    )


def build_admin_registry_page_markup(page_data: ReviewRegistryPageSchema) -> InlineKeyboardMarkup:
    language = page_data.language
    inline_keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=build_admin_review_button_text(review),
                callback_data=AdminReviewDetailCallback(
                    review_id=review.id,
                    status=page_data.status.value, # type: ignore
                    page=page_data.page,
                ).pack(),
            )
        ]
        for review in page_data.items
    ]

    pagination_row: list[InlineKeyboardButton] = []
    if page_data.has_previous:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(language, "pagination_previous"),
                callback_data=AdminReviewRegistryCallback(
                    status=page_data.status.value, # type: ignore
                    page=page_data.page - 1,
                ).pack(),
            )
        )
    if page_data.has_next:
        pagination_row.append(
            InlineKeyboardButton(
                text=translate(language, "pagination_next"),
                callback_data=AdminReviewRegistryCallback(
                    status=page_data.status.value, # type: ignore
                    page=page_data.page + 1,
                ).pack(),
            )
        )
    if pagination_row:
        inline_keyboard.append(pagination_row)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate(language, "back"),
                callback_data=AdminPanelCallback(action=AdminPanelAction.REGISTRY).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_admin_pending_detail_markup(review_id: int, status: ReviewStatus, page: int, language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_approve"),
                    callback_data=AdminReviewActionCallback(
                        action=AdminReviewAction.APPROVE,
                        review_id=review_id,
                        status=status.value, # type: ignore
                        page=page,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "admin_button_reject"),
                    callback_data=AdminReviewActionCallback(
                        action=AdminReviewAction.REJECT,
                        review_id=review_id,
                        status=status.value, # type: ignore
                        page=page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminReviewRegistryCallback(status=status.value, page=page).pack(), # type: ignore
                ),
            ],
        ]
    )


def build_admin_rejection_prompt_markup(review_id: int, status: ReviewStatus, page: int, language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminReviewDetailCallback(
                        review_id=review_id,
                        status=status.value, # type: ignore
                        page=page,
                    ).pack(),
                ),
            ],
        ]
    )


def build_admin_approved_detail_markup(review_id: int, status: ReviewStatus, page: int, language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "admin_button_delete"),
                    callback_data=AdminReviewActionCallback(
                        action=AdminReviewAction.ASK_DELETE,
                        review_id=review_id,
                        status=status.value, # type: ignore
                        page=page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminReviewRegistryCallback(status=status.value, page=page).pack(), # type: ignore
                ),
            ],
        ]
    )


def build_admin_delete_confirmation_markup(review_id: int, status: ReviewStatus, page: int, language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "yes"),
                    callback_data=AdminReviewActionCallback(
                        action=AdminReviewAction.DELETE,
                        review_id=review_id,
                        status=status.value, # type: ignore
                        page=page,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=translate(language, "no"),
                    callback_data=AdminReviewActionCallback(
                        action=AdminReviewAction.CANCEL_DELETE,
                        review_id=review_id,
                        status=status.value, # type: ignore
                        page=page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=AdminReviewDetailCallback(
                        review_id=review_id,
                        status=status.value, # type: ignore
                        page=page,
                    ).pack(),
                ),
            ],
        ]
    )


def _language_button_label(current_language: Language, target_language: Language) -> str:
    if target_language == Language.RU:
        label = translate(current_language, "language_russian")
    else:
        label = translate(current_language, "language_english")

    if current_language == target_language:
        return f"• {label}"

    return label


def _catalog_fields_for_page(game_type: GameAccountType, page: int) -> tuple[CatalogFilterField, ...]:
    field_map = {
        1: (
            CatalogFilterField.TOP_TANK_COUNT,
            CatalogFilterField.PREMIUM_TANK_COUNT,
            CatalogFilterField.TOTAL_TANK_COUNT,
            CatalogFilterField.SILVER_AMOUNT,
            CatalogFilterField.GOLD_AMOUNT,
            CatalogFilterField.BATTLES_COUNT,
            CatalogFilterField.WINS_COUNT,
            CatalogFilterField.WIN_RATE_PERCENT,
        ),
        2: (
            CatalogFilterField.LAST_ACTIVE,
            CatalogFilterField.HAS_TIER_11,
            CatalogFilterField.REGISTERED_AT,
            CatalogFilterField.IS_PHONE_BOUND,
            CatalogFilterField.IS_IN_CLAN,
            CatalogFilterField.TANK_QUERY,
            CatalogFilterField.REGION,
            CatalogFilterField.SUPPLIER_LOADED_AT,
        ),
    }
    fields = field_map[page]
    if game_type in {GameAccountType.MIR_TANKOV, GameAccountType.TANKS_BLITZ}:
        return tuple(field for field in fields if field != CatalogFilterField.REGION)
    return fields


def _catalog_filter_button_label(language: Language, field: CatalogFilterField) -> str:
    key_map = {
        CatalogFilterField.TOP_TANK_COUNT: "catalog_filter_field_top_tanks",
        CatalogFilterField.PREMIUM_TANK_COUNT: "catalog_filter_field_premium_tanks",
        CatalogFilterField.TOTAL_TANK_COUNT: "catalog_filter_field_total_tanks",
        CatalogFilterField.SILVER_AMOUNT: "catalog_filter_field_silver",
        CatalogFilterField.GOLD_AMOUNT: "catalog_filter_field_gold",
        CatalogFilterField.BATTLES_COUNT: "catalog_filter_field_battles",
        CatalogFilterField.WINS_COUNT: "catalog_filter_field_wins",
        CatalogFilterField.WIN_RATE_PERCENT: "catalog_filter_field_win_rate",
        CatalogFilterField.LAST_ACTIVE: "catalog_filter_field_last_active",
        CatalogFilterField.HAS_TIER_11: "catalog_filter_field_has_tier_11",
        CatalogFilterField.REGISTERED_AT: "catalog_filter_field_registered_at",
        CatalogFilterField.IS_PHONE_BOUND: "catalog_filter_field_phone_bound",
        CatalogFilterField.IS_IN_CLAN: "catalog_filter_field_in_clan",
        CatalogFilterField.TANK_QUERY: "catalog_filter_field_tank_query",
        CatalogFilterField.REGION: "catalog_filter_field_region",
        CatalogFilterField.SUPPLIER_LOADED_AT: "catalog_filter_field_supplier_loaded_at",
    }
    return translate(language, key_map[field])


def _catalog_sort_button_text(
    language: Language,
    button_field: CatalogSortField,
    current_direction: SortDirection,
) -> str:
    key_map = {
        CatalogSortField.PRICE: "catalog_sort_price",
        CatalogSortField.LAST_ACTIVITY: "catalog_sort_last_activity",
        CatalogSortField.NEWEST: "catalog_sort_newest",
    }
    arrow = "⬆️" if current_direction == SortDirection.ASC else "⬇️"
    return f"{translate(language, key_map[button_field])} {arrow}"


def _truncate_button_text(value: str, limit: int = 60) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit - 3].rstrip()}..."
