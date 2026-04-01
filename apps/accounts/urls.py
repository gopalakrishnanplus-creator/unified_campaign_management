from django.urls import path

from .views import AccountHealthView, DevelopmentLoginView


app_name = "accounts"

urlpatterns = [
    path("dev-login/", DevelopmentLoginView.as_view(), name="dev_login"),
    path("health/", AccountHealthView.as_view(), name="health"),
]
