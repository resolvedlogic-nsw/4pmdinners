# store/templatetags/store_tags.py
from django import template

register = template.Library()


@register.filter
def getitem(d, key):
    """Allow dict[key] access in templates: {{ dict|getitem:key }}"""
    if isinstance(d, dict):
        return d.get(key, '')
    return ''


@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ''
