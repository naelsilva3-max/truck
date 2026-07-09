from datetime import date

from django.http import JsonResponse
from django.template.loader import render_to_string


def is_ajax_request(request) -> bool:
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def infinite_scroll_json(request, template_name: str, context: dict, page_obj) -> JsonResponse:
    """Render a list page's row-partial for the base.html infinite-scroll script,
    which expects a JSON payload of {html, has_next}."""
    html = render_to_string(template_name, context, request=request)
    return JsonResponse({'html': html, 'has_next': page_obj.has_next()})


def parse_date_param(value):
    """Parse a 'YYYY-MM-DD' query-string value, returning None if blank/invalid."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
