from django.utils import timezone
from zoneinfo import ZoneInfo


INDIA_TIME_ZONE_NAME = "Asia/Kolkata"
INDIA_TIME_ZONE = ZoneInfo(INDIA_TIME_ZONE_NAME)


def localize_to_india(value):
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, INDIA_TIME_ZONE)
    return timezone.localtime(value, INDIA_TIME_ZONE)


def format_india_datetime(value, fmt="%d %b %Y %H:%M"):
    localized_value = localize_to_india(value)
    if localized_value is None:
        return ""
    return localized_value.strftime(fmt)
