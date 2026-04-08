import os
from collections import OrderedDict
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.files import File
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, TemplateView

from apps.ticketing.forms import TicketCreateForm
from apps.ticketing.external_ticketing import ExternalTicketingSyncError, external_ticketing_enabled, sync_external_directory
from apps.ticketing.models import Department, TicketAttachment, TicketNote, TicketTypeDefinition
from apps.ticketing.services import create_ticket

from .forms import SupportOtherIssueForm, SupportRequestForm
from .models import SupportItem, SupportRequest
from .services import (
    GENERAL_SUPPORT_FLOW,
    build_support_request_ticket_initial,
    create_other_support_request,
    get_available_categories,
    get_available_flows,
    get_available_systems,
    get_faq_combination,
    get_faq_super_category,
    get_faq_super_category_overview,
    resolve_support_request_context,
    submit_support_request,
)


ROLE_CONFIG = {
    "doctor": {"title": "Doctor Support", "page_title": "Doctor support landing page"},
    "clinic_staff": {"title": "Clinic Staff Support", "page_title": "Clinic staff support landing page"},
    "brand_manager": {"title": "Brand Manager Support", "page_title": "Brand manager support landing page"},
    "field_rep": {"title": "Field Rep Support", "page_title": "Field representative support landing page"},
    "patient": {"title": "Patient Support", "page_title": "Patient support landing page"},
}
CONTEXT_QUERY_KEYS = ("system", "source_system", "context_system", "flow", "source_flow", "context_flow")


def _current_context_params(request):
    return {key: value for key in CONTEXT_QUERY_KEYS if (value := (request.GET.get(key) or "").strip())}


def _cors_json(payload, status=200):
    response = JsonResponse(payload, status=status)
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def _options_response():
    response = HttpResponse(status=204)
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def _build_combination_urls(request, user_type, super_slug, category_slug, *, context_params=None):
    if context_params is None:
        context_params = _current_context_params(request)

    def with_query(path, extra_params=None):
        params = dict(context_params)
        if extra_params:
            params.update(extra_params)
        if not params:
            return path
        return f"{path}?{urlencode(params)}"

    page_url = reverse("support_center:faq_super_category", kwargs={"user_type": user_type, "super_slug": super_slug})
    widget_path = reverse(
        "support_center:faq_widget",
        kwargs={"user_type": user_type, "super_slug": super_slug, "category_slug": category_slug},
    )
    api_path = reverse(
        "support_center:faq_combination_api",
        kwargs={"user_type": user_type, "super_slug": super_slug, "category_slug": category_slug},
    )
    return {
        "page_url": request.build_absolute_uri(with_query(page_url)),
        "widget_url": request.build_absolute_uri(with_query(widget_path)),
        "embed_url": request.build_absolute_uri(with_query(widget_path, {"embed": "1"})),
        "api_url": request.build_absolute_uri(with_query(api_path)),
    }


def _faq_context_groups(faq_items):
    grouped = OrderedDict()
    for item in faq_items:
        key = (item.source_system or "", item.source_flow or "")
        if key not in grouped:
            grouped[key] = {
                "source_system": item.source_system or "",
                "source_flow": item.source_flow or "",
                "faq_count": 0,
            }
        grouped[key]["faq_count"] += 1
    return list(grouped.values())


def _requested_support_context(request):
    return {
        "system_name": (
            request.GET.get("context_system")
            or request.GET.get("source_system")
            or request.GET.get("system")
            or ""
        ).strip(),
        "flow_name": (
            request.GET.get("context_flow")
            or request.GET.get("source_flow")
            or request.GET.get("flow")
            or ""
        ).strip(),
    }


def _infer_support_context_from_referrer(referrer):
    referrer_value = (referrer or "").lower()
    if not referrer_value:
        return {"system_name": "", "flow_name": ""}
    if any(token in referrer_value for token in ("in-clinic", "inclinic")):
        return {"system_name": "In-clinic", "flow_name": ""}
    if any(token in referrer_value for token in ("patient-education", "patienteducation", "patient_education")):
        return {"system_name": "Patient Education", "flow_name": ""}
    if any(token in referrer_value for token in ("red-flag", "red_flag", "redflag", "/rfa", "sapa")):
        return {"system_name": "Red Flag Alert", "flow_name": ""}
    return {"system_name": "", "flow_name": ""}


def _build_combination_payload(request, user_type, super_slug, category_slug):
    combination = get_faq_combination(user_type, super_slug, category_slug)
    if not combination:
        raise Http404("FAQ combination not found.")
    urls = _build_combination_urls(request, user_type, super_slug, category_slug)
    context_params = _current_context_params(request)
    requested_context = _requested_support_context(request)
    resolved_system = requested_context["system_name"] or combination["source_system"]
    if requested_context["flow_name"]:
        resolved_flow = requested_context["flow_name"]
    elif requested_context["system_name"] and requested_context["system_name"] != combination["source_system"]:
        resolved_flow = combination["super_category"].name
    else:
        resolved_flow = combination["source_flow"] or GENERAL_SUPPORT_FLOW
    return {
        "user_type": user_type,
        "role_title": ROLE_CONFIG[user_type]["title"],
        "super_category": {
            "name": combination["super_category"].name,
            "slug": combination["super_category"].slug,
        },
        "category": {
            "name": combination["category"].name,
            "slug": combination["category"].slug,
        },
        "faq_count": combination["faq_count"],
        "completion_label": "Issue Resolved",
        "source_system": resolved_system,
        "source_flow": resolved_flow,
        "default_context_available": bool(resolved_system),
        "other_issue_url": request.build_absolute_uri(
            "{}{}".format(
                reverse(
                    "support_center:faq_other_issue",
                    kwargs={"user_type": user_type, "super_slug": super_slug, "category_slug": category_slug},
                ),
                f"?{urlencode(context_params)}" if context_params else "",
            )
        ),
        **urls,
        "faqs": [
            {
                "id": item.pk,
                "question": item.name,
                "answer": item.solution_body or item.summary or "No answer has been configured yet.",
                "summary": item.summary,
                "pdf_url": item.associated_pdf_url,
                "video_url": item.associated_video_url,
                "source_system": item.source_system,
                "source_flow": item.source_flow or GENERAL_SUPPORT_FLOW,
            }
            for item in combination["faq_items"]
        ],
    }


class ProjectManagerAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser or self.request.user.is_project_manager


class SupportAudienceMixin:
    user_type = None
    config = None

    def dispatch(self, request, *args, **kwargs):
        self.user_type = kwargs["user_type"]
        self.config = ROLE_CONFIG.get(self.user_type)
        if not self.config:
            raise Http404("Unsupported support audience.")
        return super().dispatch(request, *args, **kwargs)


class SupportLandingView(SupportAudienceMixin, TemplateView):
    template_name = "support_center/landing.jinja"
    template_engine = "jinja2"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        faq_super_categories = []
        for block in get_faq_super_category_overview(self.user_type):
            faq_super_categories.append(
                {
                    "super_category": block["super_category"],
                    "faq_count": block["faq_count"],
                    "category_count": block["category_count"],
                    "category_names": [entry["category"].name for entry in block["categories"]],
                }
            )
        context.update(
            {
                "faq_super_categories": faq_super_categories,
                "user_type": self.user_type,
                "role_title": self.config["title"],
                "page_title": self.config["page_title"],
                "assistant_systems": get_available_systems(self.user_type),
                "free_text_form": kwargs.get("free_text_form") or SupportRequestForm(initial={"subject": f"{self.config['title']} request"}),
                "faq_links_api_url": self.request.build_absolute_uri(
                    reverse("support_center:faq_links_api", kwargs={"user_type": self.user_type})
                ),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        form = SupportRequestForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please complete the support request fields.")
            context = self.get_context_data(free_text_form=form)
            return self.render_to_response(context)

        support_request, ticket, error_message = submit_support_request(
            item=None,
            user_type=self.user_type,
            form=form,
            request_user=request.user,
        )
        if ticket:
            messages.success(request, f"Support request escalated to ticket {ticket.ticket_number}.")
        else:
            messages.info(request, error_message or "Support request recorded.")
        return redirect("support_center:success", user_type=self.user_type, request_id=support_request.pk)


class SupportFaqSuperCategoryView(SupportAudienceMixin, TemplateView):
    template_name = "support_center/faq_super_category.jinja"
    template_engine = "jinja2"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        block = get_faq_super_category(self.user_type, kwargs["super_slug"])
        if not block:
            raise Http404("FAQ page not found.")
        category_entries = []
        for entry in block["categories"]:
            category = entry["category"]
            urls = _build_combination_urls(self.request, self.user_type, block["super_category"].slug, category.slug)
            category_entries.append(
                {
                    "category": category,
                    "faq_count": len(entry["faq_items"]),
                    "sample_questions": [item.name for item in entry["faq_items"][:3]],
                    **urls,
                }
            )
        context.update(
            {
                "user_type": self.user_type,
                "role_title": self.config["title"],
                "page_title": block["super_category"].name,
                "super_category": block["super_category"],
                "category_entries": category_entries,
                "faq_links_api_url": self.request.build_absolute_uri(
                    reverse("support_center:faq_links_api", kwargs={"user_type": self.user_type})
                ),
            }
        )
        return context


@method_decorator(xframe_options_exempt, name="dispatch")
class SupportFaqWidgetView(SupportAudienceMixin, TemplateView):
    template_name = "support_center/widget.jinja"
    template_engine = "jinja2"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payload = _build_combination_payload(
            self.request,
            self.user_type,
            kwargs["super_slug"],
            kwargs["category_slug"],
        )
        context.update(
            {
                "user_type": self.user_type,
                "role_title": self.config["title"],
                "page_title": f"{payload['super_category']['name']} / {payload['category']['name']}",
                "embedded": self.request.GET.get("embed") == "1",
                "faq_payload": payload,
            }
        )
        return context


class SupportAssistantView(SupportAudienceMixin, TemplateView):
    template_name = "support_center/assistant.jinja"
    template_engine = "jinja2"

    def _session_key(self):
        return f"support-assistant:{self.user_type}"

    def _get_state(self):
        return dict(self.request.session.get(self._session_key(), {}))

    def _save_state(self, state):
        self.request.session[self._session_key()] = state
        self.request.session.modified = True

    def _clear_state(self):
        self.request.session.pop(self._session_key(), None)
        self.request.session.modified = True

    def _rewind_state(self):
        state = self._get_state()
        if state.get("resolved_item_id"):
            state.pop("resolved_item_id", None)
        elif state.get("other_selected"):
            state.pop("other_selected", None)
        elif state.get("selected_faq_id"):
            state.pop("selected_faq_id", None)
        elif state.get("category_id"):
            state.pop("category_id", None)
            state.pop("last_selected_faq_id", None)
        elif state.get("flow"):
            state.pop("flow", None)
        elif state.get("system"):
            state.pop("system", None)
        self._save_state(state)

    def _selected_context(self):
        state = self._get_state()
        systems = get_available_systems(self.user_type)
        selected_system = state.get("system") if state.get("system") in systems else None
        flows = get_available_flows(self.user_type, selected_system) if selected_system else []
        selected_flow = state.get("flow") if state.get("flow") in flows else None
        categories = get_available_categories(self.user_type, selected_system, selected_flow) if selected_system and selected_flow else []
        category_lookup = {category.pk: category for category in categories}
        selected_category = category_lookup.get(state.get("category_id"))
        faqs = (
            get_faq_combination(self.user_type, selected_category.super_category.slug, selected_category.slug)["faq_items"]
            if selected_system and selected_flow and selected_category and get_faq_combination(self.user_type, selected_category.super_category.slug, selected_category.slug)
            else []
        )
        selected_faq = next((item for item in faqs if item.pk == state.get("selected_faq_id")), None)
        last_selected_faq = next((item for item in faqs if item.pk == state.get("last_selected_faq_id")), None)
        resolved_item = next((item for item in faqs if item.pk == state.get("resolved_item_id")), None)
        return {
            "state": state,
            "systems": systems,
            "selected_system": selected_system,
            "flows": flows,
            "selected_flow": selected_flow,
            "categories": categories,
            "selected_category": selected_category,
            "faqs": faqs,
            "selected_faq": selected_faq,
            "last_selected_faq": last_selected_faq,
            "resolved_item": resolved_item,
            "other_selected": bool(state.get("other_selected")),
        }

    def _assistant_stage(self, context):
        if not context["selected_system"]:
            return "system"
        if not context["selected_flow"]:
            return "flow"
        if not context["selected_category"]:
            return "category"
        if context["resolved_item"]:
            return "resolved"
        if context["other_selected"]:
            return "other_issue"
        if context["selected_faq"]:
            return "faq_answer"
        return "faq_menu"

    def _build_transcript(self, context, stage):
        transcript = [
            {
                "speaker": "bot",
                "title": "Support Bot",
                "body": "Select the FAQ question that best matches your issue. I’ll show the answer immediately, and you can continue until the issue is resolved.",
            }
        ]

        if stage == "faq_answer" and context["selected_faq"]:
            selected_faq = context["selected_faq"]
            transcript.append({"speaker": "user", "title": "You", "body": selected_faq.name})
            transcript.append(
                {
                    "speaker": "bot",
                    "title": "Support Bot",
                    "body": (
                        selected_faq.solution_body
                        or selected_faq.summary
                        or "No standardized solution text is available yet."
                    ),
                    "item": selected_faq,
                }
            )
        elif stage == "other_issue":
            transcript.append(
                {
                    "speaker": "user",
                    "title": "You",
                    "body": "Other",
                }
            )
            transcript.append(
                {
                    "speaker": "bot",
                    "title": "Support Bot",
                    "body": "Describe the unlisted issue and attach a screenshot or image if available. This will be sent for PM review.",
                }
            )
        elif stage == "resolved" and context["resolved_item"]:
            transcript.append(
                {
                    "speaker": "bot",
                    "title": "Support Bot",
                    "body": f"Great. I’ll treat “{context['resolved_item'].name}” as the working solution for now.",
                }
            )
        elif stage == "empty":
            transcript.append(
                {
                    "speaker": "bot",
                    "title": "No matching entries",
                    "body": "There are no matching FAQs or ticket cases for this combination.",
                }
            )
        return transcript

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        assistant_context = self._selected_context()
        stage = self._assistant_stage(assistant_context)
        context.update(
            {
                **assistant_context,
                "stage": stage,
                "user_type": self.user_type,
                "role_title": self.config["title"],
                "page_title": f"{self.config['title']} assistant",
                "general_support_flow": GENERAL_SUPPORT_FLOW,
                "transcript": self._build_transcript(assistant_context, stage),
                "other_issue_form": kwargs.get("other_issue_form") or SupportOtherIssueForm(),
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("restart") == "1":
            self._clear_state()
            return redirect("support_center:assistant", user_type=self.user_type)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        if action == "restart":
            self._clear_state()
            return redirect("support_center:assistant", user_type=self.user_type)
        if action == "back":
            self._rewind_state()
            return redirect("support_center:assistant", user_type=self.user_type)

        context = self._selected_context()

        if action == "choose_system":
            system_name = request.POST.get("system")
            if system_name in context["systems"]:
                self._save_state({"system": system_name})
            return redirect("support_center:assistant", user_type=self.user_type)

        if action == "choose_flow" and context["selected_system"]:
            flow_name = request.POST.get("flow")
            if flow_name in context["flows"]:
                self._save_state({"system": context["selected_system"], "flow": flow_name})
            return redirect("support_center:assistant", user_type=self.user_type)

        if action == "choose_category" and context["selected_system"] and context["selected_flow"]:
            category_id = request.POST.get("category_id")
            category = next((category for category in context["categories"] if str(category.pk) == category_id), None)
            if category:
                self._save_state(
                    {
                        "system": context["selected_system"],
                        "flow": context["selected_flow"],
                        "category_id": category.pk,
                    }
                )
            return redirect("support_center:assistant", user_type=self.user_type)

        if action == "select_faq" and context["selected_category"]:
            selection = request.POST.get("selection")
            if selection == "other":
                self._save_state(
                    {
                        "system": context["selected_system"],
                        "flow": context["selected_flow"],
                        "category_id": context["selected_category"].pk,
                        "last_selected_faq_id": context["selected_faq"].pk if context["selected_faq"] else context["state"].get("last_selected_faq_id"),
                        "other_selected": True,
                    }
                )
                return redirect("support_center:assistant", user_type=self.user_type)

            selected_faq = next((item for item in context["faqs"] if str(item.pk) == selection), None)
            if not selected_faq:
                messages.warning(request, "Please choose a question or select Other.")
                return redirect("support_center:assistant", user_type=self.user_type)
            self._save_state(
                {
                    "system": context["selected_system"],
                    "flow": context["selected_flow"],
                    "category_id": context["selected_category"].pk,
                    "selected_faq_id": selected_faq.pk,
                    "last_selected_faq_id": selected_faq.pk,
                }
            )
            return redirect("support_center:assistant", user_type=self.user_type)

        if action == "faq_resolution" and context["selected_category"]:
            if not context["selected_faq"]:
                messages.warning(request, "Please choose a question first.")
                return redirect("support_center:assistant", user_type=self.user_type)

            if request.POST.get("resolution") == "resolved":
                self._save_state(
                    {
                        "system": context["selected_system"],
                        "flow": context["selected_flow"],
                        "category_id": context["selected_category"].pk,
                        "resolved_item_id": context["selected_faq"].pk,
                        "last_selected_faq_id": context["selected_faq"].pk,
                    }
                )
            else:
                self._save_state(
                    {
                        "system": context["selected_system"],
                        "flow": context["selected_flow"],
                        "category_id": context["selected_category"].pk,
                        "last_selected_faq_id": context["selected_faq"].pk,
                    }
                )
            return redirect("support_center:assistant", user_type=self.user_type)

        if action == "submit_other_issue" and context["selected_category"]:
            form = SupportOtherIssueForm(request.POST, request.FILES)
            if not form.is_valid():
                messages.error(request, "Please describe the issue and correct any upload errors.")
                template_context = self.get_context_data(other_issue_form=form)
                return self.render_to_response(template_context)

            request_context = resolve_support_request_context(
                selected_faq=context["last_selected_faq"],
                selected_system=context["selected_system"],
                selected_flow=context["selected_flow"],
            )
            support_request = create_other_support_request(
                user_type=self.user_type,
                category=context["selected_category"],
                system_name=request_context["system_name"],
                flow_name=request_context["flow_name"],
                form=form,
                request_user=request.user,
            )
            self._clear_state()
            messages.success(request, "Issue recorded. It is now available in the PM dashboard for review and ticket creation.")
            return redirect("support_center:success", user_type=self.user_type, request_id=support_request.pk)

        return redirect("support_center:assistant", user_type=self.user_type)


class SupportItemDetailView(SupportAudienceMixin, DetailView):
    template_name = "support_center/item_detail.jinja"
    template_engine = "jinja2"
    model = SupportItem
    context_object_name = "item"

    def get_object(self, queryset=None):
        return get_object_or_404(
            SupportItem.objects.select_related("category__super_category", "ticket_department"),
            category__super_category__slug=self.kwargs["super_slug"],
            category__slug=self.kwargs["category_slug"],
            slug=self.kwargs["item_slug"],
            is_active=True,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_type"] = self.kwargs["user_type"]
        context["request_form"] = SupportRequestForm(initial={"subject": self.object.name})
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = SupportRequestForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please complete the support request fields.")
            context = self.get_context_data()
            context["request_form"] = form
            return self.render_to_response(context)

        support_request, ticket, error_message = submit_support_request(
            item=self.object,
            user_type=self.kwargs["user_type"],
            form=form,
            request_user=request.user,
        )
        if ticket:
            messages.success(request, f"Ticket {ticket.ticket_number} created from support.")
        else:
            messages.info(request, error_message or "Support request recorded.")
        return redirect("support_center:success", user_type=self.kwargs["user_type"], request_id=support_request.pk)


class SupportSuccessView(TemplateView):
    template_name = "support_center/success.jinja"
    template_engine = "jinja2"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["support_request"] = get_object_or_404(SupportRequest, pk=kwargs["request_id"])
        return context


class SupportRequestRaiseTicketView(ProjectManagerAccessMixin, TemplateView):
    template_name = "support_center/raise_ticket.jinja"
    template_engine = "jinja2"

    def dispatch(self, request, *args, **kwargs):
        self.support_request = get_object_or_404(
            SupportRequest.objects.select_related("campaign", "support_category__super_category"),
            pk=kwargs["request_id"],
        )
        try:
            self.existing_ticket = self.support_request.ticket_link
        except SupportRequest.ticket_link.RelatedObjectDoesNotExist:
            self.existing_ticket = None
        if self.existing_ticket:
            messages.info(request, "This issue has already been converted into a ticket.")
            return redirect("ticketing:detail", pk=self.existing_ticket.pk)

        self.synced_departments = None
        if external_ticketing_enabled():
            try:
                self.synced_departments = sync_external_directory()
                if not self.synced_departments:
                    messages.warning(
                        request,
                        "No departments were returned from the internal ticketing directory. Choose a department after the directory is available.",
                    )
            except ExternalTicketingSyncError as exc:
                messages.warning(request, f"Internal ticketing directory sync could not be refreshed right now: {exc}")
        return super().dispatch(request, *args, **kwargs)

    def _build_initial(self):
        initial = build_support_request_ticket_initial(self.support_request)
        initial.setdefault("status", "not_started")
        if not initial.get("requester_number") and self.request.user.phone_number:
            initial["requester_number"] = self.request.user.phone_number
        return initial

    def _get_form(self, data=None):
        kwargs = {"data": data, "user": self.request.user, "initial": self._build_initial()}
        if self.synced_departments is not None:
            synced_ids = [department.pk for department in self.synced_departments]
            kwargs["departments"] = Department.objects.filter(pk__in=synced_ids, is_active=True).select_related("default_recipient").order_by("name")
        return TicketCreateForm(**kwargs)

    def _attach_uploaded_file(self, ticket):
        if not self.support_request.uploaded_file:
            return
        note = TicketNote.objects.create(
            ticket=ticket,
            author=self.request.user,
            body="Imported attachment from a support widget 'Other' submission.",
        )
        self.support_request.uploaded_file.open("rb")
        attachment = TicketAttachment(note=note)
        attachment.file.save(
            os.path.basename(self.support_request.uploaded_file.name),
            File(self.support_request.uploaded_file.file),
            save=True,
        )
        self.support_request.uploaded_file.close()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = kwargs.get("form") or self._get_form()
        ticket_types = TicketTypeDefinition.objects.filter(is_active=True).select_related("category").order_by("category__name", "name")
        uploaded_file_name = self.support_request.uploaded_file.name.split("/")[-1] if self.support_request.uploaded_file else ""
        uploaded_file_is_image = uploaded_file_name.lower().endswith((".jpg", ".jpeg", ".png", ".heic", ".svg", ".webp"))
        context.update(
            {
                "support_request": self.support_request,
                "uploaded_file_name": uploaded_file_name,
                "uploaded_file_is_image": uploaded_file_is_image,
                "form": form,
                "ticket_types_payload": [
                    {"id": ticket_type.id, "category_id": ticket_type.category_id, "name": ticket_type.name}
                    for ticket_type in ticket_types
                ],
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        form = self._get_form(data=request.POST)
        if not form.is_valid():
            messages.error(request, "Please complete the ticket details before raising it.")
            return self.render_to_response(self.get_context_data(form=form))

        department = form.cleaned_data["department"]
        if not department.default_recipient:
            messages.error(request, "This department does not have a default recipient configured yet.")
            return self.render_to_response(self.get_context_data(form=form))

        payload = {
            key: value
            for key, value in form.cleaned_data.items()
            if key not in {"ticket_category", "ticket_type_definition", "new_ticket_type_name"}
        }
        ticket = create_ticket(
            created_by=request.user,
            submitted_by=request.user,
            ticket_category=form.cleaned_data["ticket_category"],
            ticket_type_definition=form.cleaned_data.get("ticket_type_definition"),
            new_ticket_type_name=form.cleaned_data.get("new_ticket_type_name"),
            support_request=self.support_request,
            **payload,
        )
        self._attach_uploaded_file(ticket)
        self.support_request.status = SupportRequest.Status.TICKET_CREATED
        self.support_request.save(update_fields=["status"])
        ticket.refresh_from_db()

        if ticket.external_ticket_number:
            messages.success(
                request,
                f"Ticket {ticket.ticket_number} created and mirrored to internal ticket {ticket.external_ticket_number}.",
            )
        elif ticket.external_ticket_error:
            messages.warning(
                request,
                f"Ticket {ticket.ticket_number} created, but internal sync failed: {ticket.external_ticket_error}",
            )
        else:
            messages.success(request, f"Ticket {ticket.ticket_number} created.")
        return redirect("ticketing:detail", pk=ticket.pk)


@csrf_exempt
@require_http_methods(["POST"])
def support_faq_other_issue(request, user_type, super_slug, category_slug):
    if user_type not in ROLE_CONFIG:
        raise Http404("Unsupported support audience.")
    combination = get_faq_combination(user_type, super_slug, category_slug)
    if not combination:
        raise Http404("FAQ combination not found.")

    form = SupportOtherIssueForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

    selected_faq = None
    selected_faq_id = request.POST.get("selected_faq_id")
    if selected_faq_id:
        selected_faq = next((item for item in combination["faq_items"] if str(item.pk) == str(selected_faq_id)), None)
    referrer_context = _infer_support_context_from_referrer(request.POST.get("context_referrer"))
    requested_context = _requested_support_context(request)
    request_context = resolve_support_request_context(
        selected_faq=selected_faq,
        selected_system=(
            request.POST.get("source_system")
            or requested_context["system_name"]
            or referrer_context["system_name"]
            or combination["source_system"]
        ),
        selected_flow=(
            request.POST.get("source_flow")
            or requested_context["flow_name"]
            or referrer_context["flow_name"]
            or combination["source_flow"]
        ),
    )
    support_request = create_other_support_request(
        user_type=user_type,
        category=combination["category"],
        system_name=request_context["system_name"],
        flow_name=request_context["flow_name"],
        form=form,
        request_user=request.user,
    )
    return JsonResponse(
        {
            "success": True,
            "request_id": support_request.pk,
            "message": "Issue recorded. It is now available in the PM dashboard for review.",
        }
    )


def support_faq_links_api(request, user_type):
    if request.method == "OPTIONS":
        return _options_response()
    if user_type not in ROLE_CONFIG:
        raise Http404("Unsupported support audience.")
    results = []
    for block in get_faq_super_category_overview(user_type):
        for entry in block["categories"]:
            category = entry["category"]
            for context_group in _faq_context_groups(entry["faq_items"]):
                context_params = {}
                if context_group["source_system"]:
                    context_params["system"] = context_group["source_system"]
                if context_group["source_flow"]:
                    context_params["flow"] = context_group["source_flow"]
                results.append(
                    {
                        "source_system": context_group["source_system"],
                        "source_flow": context_group["source_flow"] or GENERAL_SUPPORT_FLOW,
                        "super_category": {"name": block["super_category"].name, "slug": block["super_category"].slug},
                        "category": {"name": category.name, "slug": category.slug},
                        "faq_count": context_group["faq_count"],
                        **_build_combination_urls(
                            request,
                            user_type,
                            block["super_category"].slug,
                            category.slug,
                            context_params=context_params,
                        ),
                    }
                )
    return _cors_json(
        {
            "user_type": user_type,
            "role_title": ROLE_CONFIG[user_type]["title"],
            "count": len(results),
            "results": results,
        }
    )


def support_faq_combination_api(request, user_type, super_slug, category_slug):
    if request.method == "OPTIONS":
        return _options_response()
    if user_type not in ROLE_CONFIG:
        raise Http404("Unsupported support audience.")
    return _cors_json(_build_combination_payload(request, user_type, super_slug, category_slug))
