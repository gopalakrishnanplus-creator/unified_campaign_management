from django.utils import timezone

from .models import SupportWidgetMetricReset


GLOBAL_WIDGET_METRIC_RESET_SCOPE = "__all__"


def normalized_support_token(value):
    return "".join(character for character in (value or "").lower() if character.isalnum())


def canonical_support_system(system_name, flow_name=""):
    system_name = (system_name or "").strip()
    flow_name = (flow_name or "").strip()
    system_token = normalized_support_token(system_name)
    flow_token = normalized_support_token(flow_name)
    combined_token = f"{system_token}{flow_token}"

    if system_token == "saplaicme":
        if "aicme" in flow_token:
            return "AICME"
        return "SAPL"
    if system_token == "aicme" or "aicme" in combined_token:
        return "AICME"
    if system_token == "sapl" or "sapl" in combined_token:
        return "SAPL"
    if system_token in {"inclinic", "inclinicsystem"} or "inclinic" in combined_token:
        return "In-clinic"
    if system_token in {"patienteducation", "pe"} or "patienteducation" in combined_token:
        return "Patient Education"
    if system_token in {"redflagalert", "rfa"} or "redflagalert" in combined_token:
        return "Red Flag Alert"
    if not system_name:
        return "Unknown"
    return system_name


def is_generic_support_system(system_name):
    return normalized_support_token(system_name) in {"", "unknown", "customersupport", "generalsupport", "support"}


def resolve_support_system(source_system, source_flow="", *fallback_records):
    resolved_system = canonical_support_system(source_system, source_flow)
    fallback_systems = []
    for record in fallback_records:
        if not record:
            continue
        fallback_systems.append(
            canonical_support_system(
                getattr(record, "source_system", ""),
                getattr(record, "source_flow", ""),
            )
        )

    if is_generic_support_system(resolved_system):
        for fallback_system in fallback_systems:
            if not is_generic_support_system(fallback_system):
                return fallback_system
    return resolved_system


def support_page_system(page):
    return resolve_support_system(page.source_system, page.source_flow)


def support_item_system(item):
    return resolve_support_system(item.source_system, item.source_flow, item.page)


def support_request_system(support_request):
    return resolve_support_system(support_request.source_system, support_request.source_flow, support_request.support_page)


def widget_event_system(event):
    request_page = event.support_request.support_page if event.support_request_id else None
    return resolve_support_system(event.source_system, event.source_flow, event.support_page, event.support_request, request_page)


def get_widget_metric_reset_cutoffs():
    return dict(SupportWidgetMetricReset.objects.values_list("system", "reset_at"))


def widget_metric_cutoff_for_system(system_name, reset_cutoffs=None):
    reset_cutoffs = reset_cutoffs if reset_cutoffs is not None else get_widget_metric_reset_cutoffs()
    system_reset_at = reset_cutoffs.get(canonical_support_system(system_name))
    global_reset_at = reset_cutoffs.get(GLOBAL_WIDGET_METRIC_RESET_SCOPE)
    reset_dates = [reset_at for reset_at in (system_reset_at, global_reset_at) if reset_at]
    return max(reset_dates) if reset_dates else None


def is_after_widget_metric_reset(system_name, occurred_at, reset_cutoffs=None):
    if not occurred_at:
        return False
    reset_at = widget_metric_cutoff_for_system(system_name, reset_cutoffs=reset_cutoffs)
    return not reset_at or occurred_at > reset_at


def reset_widget_metric_counters(system_name=None):
    scope = canonical_support_system(system_name) if system_name else GLOBAL_WIDGET_METRIC_RESET_SCOPE
    reset, _ = SupportWidgetMetricReset.objects.update_or_create(
        system=scope,
        defaults={"reset_at": timezone.now()},
    )
    return reset
