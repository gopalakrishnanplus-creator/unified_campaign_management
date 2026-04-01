from typing import Any, Iterable, Optional, Set

import requests
from django.conf import settings

from apps.campaigns.models import Campaign

from .models import AdoptionSnapshot, ExternalGrowthSnapshot, InClinicSnapshot, PatientEducationSnapshot, RedFlagSnapshot


LIVE_SUBSYSTEMS = ("red_flag_alert", "in_clinic", "patient_education")
LIVE_ENDPOINT_SETTINGS = {
    "red_flag_alert": "REPORTING_API_RED_FLAG_ALERT_URL",
    "in_clinic": "REPORTING_API_IN_CLINIC_URL",
    "patient_education": "REPORTING_API_PATIENT_EDUCATION_URL",
}
LOCAL_MODEL_MAPPING = {
    "red_flag_alert": RedFlagSnapshot,
    "in_clinic": InClinicSnapshot,
    "patient_education": PatientEducationSnapshot,
    "adoption": AdoptionSnapshot,
    "external_growth": ExternalGrowthSnapshot,
}
EXTERNAL_CAMPAIGN_HINT_FIELDS = ("slug", "name", "brand_name")
WORDPRESS_ACTION_WEBINAR_REGISTRATIONS = "webinar_registrations"
WORDPRESS_ACTION_COURSE_BREAKDOWN = "course_breakdown"


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _campaign_aliases(campaign: Optional[Campaign]) -> Set[str]:
    if not campaign:
        return set()
    aliases = {_normalize_text(getattr(campaign, field)) for field in EXTERNAL_CAMPAIGN_HINT_FIELDS}
    aliases.add(_normalize_text(campaign.name).replace(" ", "-"))
    aliases.add(_normalize_text(campaign.brand_name).replace(" ", "-"))
    return {alias for alias in aliases if alias}


def _serialize_local_instance(obj):
    payload = {}
    for field in obj._meta.fields:
        value = getattr(obj, field.name)
        if value is None:
            payload[field.name] = None
        elif field.is_relation:
            if hasattr(value, "slug"):
                payload[field.name] = value.slug
            elif hasattr(value, "clinic_code"):
                payload[field.name] = value.clinic_code
            elif hasattr(value, "email"):
                payload[field.name] = value.email
            elif hasattr(value, "name"):
                payload[field.name] = value.name
            else:
                payload[field.name] = value.pk
        else:
            payload[field.name] = value.isoformat() if hasattr(value, "isoformat") else value
    return payload


def build_local_subsystem_payload(subsystem, campaign_slug=None):
    model = LOCAL_MODEL_MAPPING[subsystem]
    queryset = model.objects.all()
    if campaign_slug and hasattr(model, "campaign"):
        queryset = queryset.filter(campaign__slug=campaign_slug)
    records = [_serialize_local_instance(obj) for obj in queryset[:200]]
    return {
        "subsystem": subsystem,
        "count": len(records),
        "results": records,
        "source": "local",
        "endpoint": None,
        "notices": [],
        "filter_applied": bool(campaign_slug),
    }


def fetch_live_subsystem_payload(subsystem):
    endpoint = getattr(settings, LIVE_ENDPOINT_SETTINGS[subsystem])
    response = requests.get(endpoint, timeout=settings.REPORTING_API_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError(f"Unexpected payload from {endpoint}")
    payload["source"] = "live"
    payload["endpoint"] = endpoint
    payload.setdefault("notices", [])
    payload.setdefault("count", len(payload["results"]))
    return payload


def fetch_wordpress_payload(action, params=None):
    query = {"ld_api": action, "secret": settings.WORDPRESS_HELPER_SECRET}
    if params:
        query.update(params)
    response = requests.get(settings.WORDPRESS_HELPER_URL, params=query, timeout=settings.WORDPRESS_HELPER_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected WordPress payload for {action}")
    return payload


def _resolve_campaign_argument(campaign):
    if isinstance(campaign, Campaign):
        return campaign
    if isinstance(campaign, str) and campaign:
        return Campaign.objects.filter(slug=campaign).first()
    return None


def _filter_live_results(payload, campaign):
    campaign_obj = _resolve_campaign_argument(campaign)
    raw_identifier = campaign if isinstance(campaign, str) else campaign_obj.slug if campaign_obj else ""
    results = payload["results"]
    if not raw_identifier and not campaign_obj:
        payload["filter_applied"] = False
        return payload

    aliases = _campaign_aliases(campaign_obj)
    if raw_identifier:
        aliases.add(_normalize_text(raw_identifier))

    filtered = [row for row in results if _normalize_text(row.get("campaign")) in aliases]
    if filtered:
        payload["results"] = filtered
        payload["count"] = len(filtered)
        payload["filter_applied"] = True
        return payload

    payload["filter_applied"] = False
    payload["notices"].append(
        "Live reporting data uses external campaign identifiers that do not currently map to the selected local campaign. "
        "Showing the available live feed instead."
    )
    return payload


def get_subsystem_payload(subsystem, campaign=None):
    campaign_slug = campaign.slug if isinstance(campaign, Campaign) else campaign
    if subsystem not in LIVE_SUBSYSTEMS or not settings.REPORTING_API_USE_LIVE:
        return build_local_subsystem_payload(subsystem, campaign_slug=campaign_slug)

    try:
        payload = fetch_live_subsystem_payload(subsystem)
        return _filter_live_results(payload, campaign)
    except (requests.RequestException, ValueError) as exc:
        fallback = build_local_subsystem_payload(subsystem, campaign_slug=campaign_slug)
        fallback["source"] = "local_fallback"
        fallback["notices"].append(f"Live endpoint unavailable, using local snapshot data instead: {exc}")
        return fallback


def _sum_rows(records, field_names):
    totals = {field_name: 0 for field_name in field_names}
    for row in records:
        for field_name in field_names:
            totals[field_name] += int(row.get(field_name) or 0)
    return totals


def _group_rows(records, group_fields, sum_fields, label_mapping):
    grouped = {}
    for row in records:
        key = tuple(row.get(field) or "Unknown" for field in group_fields)
        if key not in grouped:
            grouped[key] = {label_mapping[field]: value for field, value in zip(group_fields, key)}
            for sum_field in sum_fields:
                grouped[key][label_mapping[sum_field]] = 0
        for sum_field in sum_fields:
            grouped[key][label_mapping[sum_field]] += int(row.get(sum_field) or 0)
    return list(grouped.values())


def _count_unique(records, field_name, predicate=None):
    values = set()
    for row in records:
        if predicate and not predicate(row):
            continue
        normalized = _normalize_text(row.get(field_name))
        if normalized and normalized not in {"unknown", "na"}:
            values.add(normalized)
    return len(values)


def _get_wordpress_course_ids():
    return [int(value) for value in _split_csv(settings.WORDPRESS_CERTIFICATE_COURSE_IDS)]


def _get_matching_webinar_registrations():
    payload = fetch_wordpress_payload(WORDPRESS_ACTION_WEBINAR_REGISTRATIONS)
    registrations = payload.get("data", [])
    filters = [item.lower() for item in _split_csv(settings.WORDPRESS_GROWTH_WEBINAR_FILTERS)] or ["sapa growth clinics"]
    return [
        row
        for row in registrations
        if any(filter_text in (row.get("event_title") or "").lower() for filter_text in filters)
    ]


def _get_completed_course_users():
    completed_by_email = {}
    sources = []
    for course_id in _get_wordpress_course_ids():
        payload = fetch_wordpress_payload(WORDPRESS_ACTION_COURSE_BREAKDOWN, {"course_id": course_id})
        users = payload.get("data", [])
        completed_count = 0
        for user in users:
            if user.get("progress_status") != "Completed":
                continue
            email = _normalize_text(user.get("user_email"))
            if not email:
                continue
            completed_count += 1
            completed_by_email[email] = user
        sources.append({"course_id": course_id, "completed": completed_count, "users": len(users)})
    return completed_by_email, sources


def _candidate_identity_tokens(record, fields):
    tokens = set()
    for field_name in fields:
        value = record.get(field_name)
        normalized = _normalize_text(value)
        if normalized and normalized not in {"unknown", "na"}:
            tokens.add(normalized)
    combined_name = " ".join(part for part in [record.get("first_name"), record.get("last_name")] if part)
    combined_normalized = _normalize_text(combined_name)
    if combined_normalized:
        tokens.add(combined_normalized)
    return tokens


def build_adoption_rows(red_flag_records, in_clinic_records, patient_education_records):
    return [
        {
            "system_type": "red_flag_alert",
            "doctors_added_total": _count_unique(red_flag_records, "clinic"),
            "clinics_added_total": _count_unique(red_flag_records, "clinic"),
            "clinics_with_shares_total": _count_unique(red_flag_records, "clinic", predicate=lambda row: int(row.get("form_shares") or 0) > 0),
            "adoption_basis": "Doctor-level IDs are not present in the live RFA feed, so adoption is represented using unique clinic activity.",
        },
        {
            "system_type": "patient_education",
            "doctors_added_total": _count_unique(patient_education_records, "clinic"),
            "clinics_added_total": _count_unique(patient_education_records, "clinic"),
            "clinics_with_shares_total": _count_unique(
                patient_education_records,
                "clinic",
                predicate=lambda row: int(row.get("cluster_shares") or 0) > 0,
            ),
            "adoption_basis": "Doctor-level IDs are not present in the live patient education feed, so adoption is represented using unique clinic activity.",
        },
        {
            "system_type": "in_clinic",
            "doctors_added_total": _count_unique(in_clinic_records, "doctor"),
            "clinics_added_total": _count_unique(in_clinic_records, "clinic"),
            "clinics_with_shares_total": _count_unique(in_clinic_records, "clinic", predicate=lambda row: int(row.get("shares") or 0) > 0),
            "adoption_basis": "Uses doctor and clinic identifiers directly from the live in-clinic feed.",
        },
    ]


def build_external_growth_totals(red_flag_records):
    notices = []
    sources = []
    webinar_attendees = 0
    certificate_completed = 0
    onboarded_certificate_completed = 0
    non_onboarded_certificate_completed = 0

    try:
        registrations = _get_matching_webinar_registrations()
        webinar_attendees = len({_normalize_text(row.get("email")) for row in registrations if _normalize_text(row.get("email"))})
        sources.append(
            {
                "subsystem": "external_growth",
                "source": "wordpress_webinars",
                "count": webinar_attendees,
                "details": f"{len(registrations)} matching registration rows",
                "filter_applied": True,
            }
        )
    except (requests.RequestException, ValueError) as exc:
        notices.append(f"WordPress webinar registrations could not be loaded: {exc}")

    try:
        completed_users, course_sources = _get_completed_course_users()
        certificate_completed = len(completed_users)
        sources.extend(
            {
                "subsystem": "external_growth",
                "source": "wordpress_course",
                "count": course_source["completed"],
                "details": f"course_id={course_source['course_id']} across {course_source['users']} enrolled users",
                "filter_applied": True,
            }
            for course_source in course_sources
        )

        onboarded_tokens = set()
        for row in red_flag_records:
            onboarded_tokens.update(
                _candidate_identity_tokens(
                    row,
                    fields=("clinic", "clinic_group", "campaign"),
                )
            )

        for user in completed_users.values():
            user_tokens = _candidate_identity_tokens(
                user,
                fields=("user_email", "display_name", "phone"),
            )
            if onboarded_tokens.intersection(user_tokens):
                onboarded_certificate_completed += 1
            else:
                non_onboarded_certificate_completed += 1

        if certificate_completed and onboarded_certificate_completed == 0:
            notices.append(
                "The current live RFA feed does not expose doctor-level identifiers, so the onboarded vs non-onboarded certificate split is a best-effort match and may undercount onboarded doctors."
            )
    except (requests.RequestException, ValueError) as exc:
        notices.append(f"WordPress certificate-course data could not be loaded: {exc}")

    return (
        {
            "webinar_attendees": webinar_attendees,
            "certificate_completed": certificate_completed,
            "onboarded_certificate_completed": onboarded_certificate_completed,
            "non_onboarded_certificate_completed": non_onboarded_certificate_completed,
        },
        notices,
        sources,
    )


def get_live_performance_payloads(campaign=None):
    payloads = {subsystem: get_subsystem_payload(subsystem, campaign) for subsystem in LIVE_SUBSYSTEMS}
    notices = []
    sources = []
    for subsystem, payload in payloads.items():
        notices.extend(payload.get("notices", []))
        sources.append(
            {
                "subsystem": subsystem,
                "source": payload.get("source", "local"),
                "endpoint": payload.get("endpoint"),
                "count": payload.get("count", 0),
                "filter_applied": payload.get("filter_applied", False),
            }
        )
    return payloads, notices, sources


def build_live_performance_sections(campaign=None):
    payloads, notices, sources = get_live_performance_payloads(campaign)
    red_flag_records = payloads["red_flag_alert"]["results"]
    in_clinic_records = payloads["in_clinic"]["results"]
    patient_education_records = payloads["patient_education"]["results"]
    adoption_rows = build_adoption_rows(red_flag_records, in_clinic_records, patient_education_records)
    external_growth_totals, external_notices, external_sources = build_external_growth_totals(red_flag_records)
    notices.extend(external_notices)
    sources.extend(external_sources)

    red_flag_by_clinic = _group_rows(
        red_flag_records,
        group_fields=("clinic", "clinic_group"),
        sum_fields=("form_fills", "red_flags_total", "reminders_sent"),
        label_mapping={
            "clinic": "clinic__name",
            "clinic_group": "clinic_group__name",
            "form_fills": "form_fills_total",
            "red_flags_total": "red_flags_total_value",
            "reminders_sent": "reminders_sent_total",
        },
    )
    red_flag_by_clinic.sort(key=lambda row: (-row["form_fills_total"], row["clinic__name"]))

    patient_education_by_clinic = _group_rows(
        patient_education_records,
        group_fields=("clinic", "clinic_group"),
        sum_fields=("video_views", "cluster_shares"),
        label_mapping={
            "clinic": "clinic__name",
            "clinic_group": "clinic_group__name",
            "video_views": "video_views_total",
            "cluster_shares": "cluster_shares_total",
        },
    )
    patient_education_by_clinic.sort(key=lambda row: (-row["video_views_total"], row["clinic__name"]))

    in_clinic_by_field_rep = _group_rows(
        in_clinic_records,
        group_fields=("field_rep", "campaign"),
        sum_fields=("shares", "link_opens", "pdf_downloads"),
        label_mapping={
            "field_rep": "field_rep__full_name",
            "campaign": "campaign__name",
            "shares": "shares_total",
            "link_opens": "link_opens_total",
            "pdf_downloads": "pdf_downloads_total",
        },
    )
    for row in in_clinic_by_field_rep:
        row["field_rep__full_name"] = row["field_rep__full_name"] or "Unassigned"
    in_clinic_by_field_rep.sort(key=lambda row: (-row["shares_total"], row["field_rep__full_name"]))

    return {
        "red_flag_totals": _sum_rows(
            red_flag_records,
            (
                "form_fills",
                "red_flags_total",
                "patient_video_views",
                "reports_emailed_to_doctors",
                "form_shares",
                "patient_scans",
                "follow_ups_scheduled",
                "reminders_sent",
            ),
        ),
        "red_flag_by_clinic": red_flag_by_clinic,
        "patient_education_totals": _sum_rows(
            patient_education_records,
            ("video_views", "video_completions", "cluster_shares", "patient_scans", "banner_clicks"),
        ),
        "patient_education_by_clinic": patient_education_by_clinic,
        "adoption_rows": adoption_rows,
        "in_clinic_totals": _sum_rows(
            in_clinic_records,
            ("shares", "link_opens", "pdf_reads_completed", "video_views", "video_completions", "pdf_downloads"),
        ),
        "in_clinic_by_field_rep": in_clinic_by_field_rep,
        "external_growth_totals": external_growth_totals,
        "reporting_notices": notices,
        "reporting_sources": sources,
    }
