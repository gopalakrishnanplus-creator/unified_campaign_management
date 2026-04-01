from django.templatetags.static import static
from django.urls import reverse
from jinja2 import Environment


def build_url(name, *args, **kwargs):
    return reverse(name, args=args or None, kwargs=kwargs or None)


def environment(**options):
    env = Environment(**options)
    env.globals.update(static=static, url=build_url)
    return env
