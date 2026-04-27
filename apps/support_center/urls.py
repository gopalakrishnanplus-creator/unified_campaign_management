from django.urls import path

from .views import (
    SupportAssistantView,
    SupportFaqPageView,
    SupportFaqPageWidgetView,
    SupportFaqSuperCategoryView,
    SupportFaqWidgetView,
    SupportItemDetailView,
    SupportLandingView,
    SupportRequestEscalateView,
    SupportRequestRaiseTicketView,
    SupportSuccessView,
    support_faq_other_issue,
    support_faq_combination_api,
    support_faq_page_api,
    support_faq_page_other_issue,
    support_faq_page_widget_event,
    support_faq_links_api,
    support_faq_widget_event,
)


app_name = "support_center"

urlpatterns = [
    path("api/<str:user_type>/pages/<slug:page_slug>/", support_faq_page_api, name="faq_page_api"),
    path("api/<str:user_type>/faq-links/", support_faq_links_api, name="faq_links_api"),
    path("api/<str:user_type>/<slug:super_slug>/<slug:category_slug>/", support_faq_combination_api, name="faq_combination_api"),
    path("<str:user_type>/", SupportLandingView.as_view(), name="landing"),
    path("<str:user_type>/faq/page/<slug:page_slug>/", SupportFaqPageView.as_view(), name="faq_page"),
    path("<str:user_type>/faq/<slug:super_slug>/", SupportFaqSuperCategoryView.as_view(), name="faq_super_category"),
    path(
        "<str:user_type>/faq/page/<slug:page_slug>/other/",
        support_faq_page_other_issue,
        name="faq_page_other_issue",
    ),
    path(
        "<str:user_type>/faq/page/<slug:page_slug>/widget-event/",
        support_faq_page_widget_event,
        name="faq_page_widget_event",
    ),
    path(
        "<str:user_type>/faq/<slug:super_slug>/<slug:category_slug>/other/",
        support_faq_other_issue,
        name="faq_other_issue",
    ),
    path(
        "<str:user_type>/faq/<slug:super_slug>/<slug:category_slug>/widget-event/",
        support_faq_widget_event,
        name="faq_widget_event",
    ),
    path(
        "<str:user_type>/faq/page/<slug:page_slug>/widget/",
        SupportFaqPageWidgetView.as_view(),
        name="faq_page_widget",
    ),
    path(
        "<str:user_type>/faq/<slug:super_slug>/<slug:category_slug>/widget/",
        SupportFaqWidgetView.as_view(),
        name="faq_widget",
    ),
    path("<str:user_type>/assistant/", SupportAssistantView.as_view(), name="assistant"),
    path("<str:user_type>/request/<int:request_id>/success/", SupportSuccessView.as_view(), name="success"),
    path("requests/<int:request_id>/escalate/", SupportRequestEscalateView.as_view(), name="escalate_request"),
    path("requests/<int:request_id>/raise-ticket/", SupportRequestRaiseTicketView.as_view(), name="raise_ticket"),
    path(
        "<str:user_type>/<slug:super_slug>/<slug:category_slug>/<slug:item_slug>/",
        SupportItemDetailView.as_view(),
        name="item_detail",
    ),
]
