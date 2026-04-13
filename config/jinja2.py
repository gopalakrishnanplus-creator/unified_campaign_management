from django.templatetags.static import static
from django.urls import reverse
from jinja2 import Environment

from config.timezones import format_india_datetime


def build_url(name, *args, **kwargs):
    return reverse(name, args=args or None, kwargs=kwargs or None)


def environment(**options):
    env = Environment(**options)
    env.globals.update(static=static, url=build_url)
    env.filters["india_datetime"] = format_india_datetime
    return env
