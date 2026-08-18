from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class NavigationCallback(CallbackData, prefix="nav"):
    screen: str


class ProfileAction(StrEnum):
    TOP_UP = "top_up"
    OPEN_LANGUAGE = "open_language"
    HISTORY = "history"


class ProfileActionCallback(CallbackData, prefix="profile"):
    action: ProfileAction


class ProfileLanguageCallback(CallbackData, prefix="profile_lang"):
    language: str


class ProfileHistoryPageCallback(CallbackData, prefix="profile_history_page"):
    page: int


class CatalogGameTypeCallback(CallbackData, prefix="catalog_game_type"):
    game_type: str


class CatalogFilterPageCallback(CallbackData, prefix="catalog_filter_page"):
    game_type: str
    page: int


class CatalogFilterFieldCallback(CallbackData, prefix="catalog_filter_field"):
    game_type: str
    page: int
    field: str


class CatalogFilterAction(StrEnum):
    SEARCH = "search"
    ASK_RESET = "ask_reset"
    CONFIRM_RESET = "confirm_reset"
    CANCEL_RESET = "cancel_reset"


class CatalogFilterActionCallback(CallbackData, prefix="catalog_filter_action"):
    action: CatalogFilterAction
    game_type: str
    page: int


class CatalogBooleanFilterCallback(CallbackData, prefix="catalog_filter_bool"):
    game_type: str
    page: int
    field: str
    choice: str


class CatalogResultsPageCallback(CallbackData, prefix="catalog_results_page"):
    game_type: str
    page: int


class CatalogClearFieldCallback(CallbackData, prefix="catalog_clear_field"):
    game_type: str
    page: int
    field: str


class CatalogSortCallback(CallbackData, prefix="catalog_sort"):
    game_type: str
    field: str


class CatalogAccountDetailCallback(CallbackData, prefix="catalog_account_detail"):
    account_id: int
    game_type: str
    page: int
    detail_page: int


class CatalogAccountAction(StrEnum):
    BUY = "b"
    TOGGLE_FAVORITE = "f"
    REFRESH = "r"
    PREVIOUS_DETAIL_PAGE = "pp"
    NEXT_DETAIL_PAGE = "np"
    BACK_TO_RESULTS = "br"


class CatalogAccountActionCallback(CallbackData, prefix="catalog_account_action"):
    action: CatalogAccountAction
    account_id: int
    game_type: str
    page: int
    detail_page: int


class FavoritesPageCallback(CallbackData, prefix="favorites_page"):
    page: int


class FavoritesAccountDetailCallback(CallbackData, prefix="favorites_account_detail"):
    account_id: int
    page: int
    detail_page: int


class FavoritesAccountAction(StrEnum):
    BUY = "b"
    TOGGLE_FAVORITE = "f"
    REFRESH = "r"
    PREVIOUS_DETAIL_PAGE = "pp"
    NEXT_DETAIL_PAGE = "np"
    BACK_TO_LIST = "bl"


class FavoritesAccountActionCallback(CallbackData, prefix="favorites_account_action"):
    action: FavoritesAccountAction
    account_id: int
    page: int
    detail_page: int


class AccountRefreshSource(StrEnum):
    CATALOG = "c"
    FAVORITES = "f"


class AccountRefreshAction(StrEnum):
    STOP = "s"
    BACK_TO_DETAIL = "d"
    BACK_TO_LIST = "l"
    MAIN_MENU = "m"


class AccountRefreshCallback(CallbackData, prefix="account_refresh"):
    source: str
    action: str
    account_id: int
    game_type: str
    page: int
    detail_page: int


class ReviewsPageCallback(CallbackData, prefix="reviews_page"):
    page: int


class ReviewRulesCallback(CallbackData, prefix="review_rules"):
    page: int


class FaqPageCallback(CallbackData, prefix="faq_page"):
    page: int


class FaqDetailCallback(CallbackData, prefix="faq_detail"):
    faq_id: int
    page: int
    content_page: int = 1


class ReviewFlowAction(StrEnum):
    START = "start"
    CANCEL = "cancel"


class ReviewFlowCallback(CallbackData, prefix="review_flow"):
    action: ReviewFlowAction
    page: int


class ReviewRatingCallback(CallbackData, prefix="review_rating"):
    rating: str
    page: int


class AdminPanelAction(StrEnum):
    REGISTRY = "registry"
    USERS = "users"
    STATISTICS = "statistics"
    FAQ = "faq"
    PRODUCTS = "products"
    TRANSACTIONS = "transactions"
    TOGGLE_SALES = "toggle_sales"
    SALES = "sales"
    FORCE_REFRESH = "force_refresh"
    DATABASE_BACKUP = "database_backup"
    BACK_TO_MAIN = "back_to_main"


class AdminPanelCallback(CallbackData, prefix="admin_panel"):
    action: AdminPanelAction


class AdminSalesAction(StrEnum):
    TOGGLE_ALL = "all"
    TOGGLE_MIR_TANKOV = "mt"
    TOGGLE_TANKS_BLITZ = "tb"
    TOGGLE_WORLD_OF_TANKS = "wot"
    TOGGLE_WOT_BLITZ = "wb"
    BACK = "back"


class AdminSalesCallback(CallbackData, prefix="admin_sales"):
    action: AdminSalesAction


class AdminUsersAction(StrEnum):
    OPEN_MENU = "open_menu"
    BROADCAST = "broadcast"
    EXPORT = "export"
    EDIT = "edit"
    BACK_TO_MAIN = "back_to_main"


class AdminUsersCallback(CallbackData, prefix="admin_users"):
    action: AdminUsersAction


class AdminStatisticsAction(StrEnum):
    OPEN_MENU = "open_menu"
    ALL_TIME = "all_time"
    CURRENT_MONTH = "current_month"
    PREVIOUS_MONTH = "previous_month"
    WEEK = "week"
    DAY = "day"
    CUSTOM = "custom"
    BACK_TO_MAIN = "back_to_main"


class AdminStatisticsCallback(CallbackData, prefix="admin_statistics"):
    action: AdminStatisticsAction


class AdminBroadcastAction(StrEnum):
    SEND = "send"
    CANCEL = "cancel"
    BACK = "back"


class AdminBroadcastCallback(CallbackData, prefix="admin_broadcast"):
    action: AdminBroadcastAction


class AdminUserLookupTypeCallback(CallbackData, prefix="admin_user_lookup_type"):
    identifier_type: str


class AdminUserEditField(StrEnum):
    BALANCE = "balance"


class AdminUserViewCallback(CallbackData, prefix="admin_user_view"):
    user_id: int


class AdminUserEditFieldCallback(CallbackData, prefix="admin_user_edit_field"):
    field: AdminUserEditField
    user_id: int


class AdminReviewRegistryCallback(CallbackData, prefix="admin_review_registry"):
    status: str
    page: int


class AdminReviewDetailCallback(CallbackData, prefix="admin_review_detail"):
    review_id: int
    status: str
    page: int


class AdminReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    ASK_DELETE = "ask_delete"
    DELETE = "delete"
    CANCEL_DELETE = "cancel_delete"


class AdminReviewActionCallback(CallbackData, prefix="admin_review_action"):
    action: AdminReviewAction
    review_id: int
    status: str
    page: int


class AdminFaqAction(StrEnum):
    OPEN_MENU = "open_menu"
    ADD = "add"
    BACK_TO_MAIN = "back_to_main"


class AdminFaqActionCallback(CallbackData, prefix="admin_faq_action"):
    action: AdminFaqAction


class AdminFaqAddCallback(CallbackData, prefix="admin_faq_add"):
    page: int


class AdminFaqPageCallback(CallbackData, prefix="admin_faq_page"):
    page: int


class AdminFaqDetailCallback(CallbackData, prefix="admin_faq_detail"):
    faq_id: int
    page: int


class AdminFaqEditField(StrEnum):
    QUESTION_RU = "question_ru"
    QUESTION_EN = "question_en"
    ANSWER_RU = "answer_ru"
    ANSWER_EN = "answer_en"


class AdminFaqEditFieldCallback(CallbackData, prefix="admin_faq_edit_field"):
    faq_id: int
    page: int
    field: AdminFaqEditField


class AdminFaqDeleteAction(StrEnum):
    ASK = "ask"
    CONFIRM = "confirm"
    CANCEL = "cancel"


class AdminFaqDeleteCallback(CallbackData, prefix="admin_faq_delete"):
    faq_id: int
    page: int
    action: AdminFaqDeleteAction


class AdminProductsAction(StrEnum):
    OPEN_MENU = "open_menu"
    LOOKUP = "lookup"
    EXPORT = "export"
    MARKUPS = "markups"
    BACK_TO_MAIN = "back_to_main"


class AdminProductsCallback(CallbackData, prefix="admin_products"):
    action: AdminProductsAction


class AdminProductDetailCallback(CallbackData, prefix="admin_product_detail"):
    product_id: int
    detail_page: int


class AdminProductDeleteAction(StrEnum):
    ASK = "ask"
    CONFIRM = "confirm"
    CANCEL = "cancel"


class AdminProductDeleteCallback(CallbackData, prefix="admin_product_delete"):
    product_id: int
    detail_page: int
    action: AdminProductDeleteAction


class AdminTransactionsAction(StrEnum):
    OPEN_MENU = "open_menu"
    OPEN_COMPLETED = "open_completed"
    OPEN_PENDING = "open_pending"
    LOOKUP = "lookup"
    EXPORT = "export"
    BACK_TO_MAIN = "back_to_main"


class AdminTransactionsCallback(CallbackData, prefix="admin_transactions"):
    action: AdminTransactionsAction


class AdminTransactionPageCallback(CallbackData, prefix="admin_transaction_page"):
    status: str
    page: int


class AdminTransactionDetailCallback(CallbackData, prefix="admin_transaction_detail"):
    transaction_id: int
    status: str
    page: int


class AdminTransactionAction(StrEnum):
    CANCEL = "cancel"


class AdminTransactionActionCallback(CallbackData, prefix="admin_transaction_action"):
    action: AdminTransactionAction
    transaction_id: int
    status: str
    page: int
