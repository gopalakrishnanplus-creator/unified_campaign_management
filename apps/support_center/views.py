from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import DetailView, TemplateView

from .forms import SupportRequestForm
from .models import SupportItem, SupportRequest
from .services import (
    GENERAL_SUPPORT_FLOW,
    get_available_categories,
    get_available_flows,
    get_available_systems,
    get_faq_combination,
    get_faq_super_category,
    get_faq_super_category_overview,
    get_issue_sequences,
    submit_support_request,
)


ROLE_CONFIG = {
    "doctor": {"title": "Doctor Support", "page_title": "Doctor support landing page"},
    "clinic_staff": {"title": "Clinic Staff Support", "page_title": "Clinic staff support landing page"},
    "brand_manager": {"title": "Brand Manager Support", "page_title": "Brand manager support landing page"},
    "field_rep": {"title": "Field Rep Support", "page_title": "Field representative support landing page"},
    "patient": {"title": "Patient Support", "page_title": "Patient support landing page"},
}


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


def _build_combination_urls(request, user_type, super_slug, category_slug):
    page_url = reverse("support_center:faq_super_category", kwargs={"user_type": user_type, "super_slug": super_slug})
    widget_url = reverse(
        "support_center:faq_widget",
        kwargs={"user_type": user_type, "super_slug": super_slug, "category_slug": category_slug},
    )
    api_url = reverse(
        "support_center:faq_combination_api",
        kwargs={"user_type": user_type, "super_slug": super_slug, "category_slug": category_slug},
    )
    return {
        "page_url": request.build_absolute_uri(page_url),
        "widget_url": request.build_absolute_uri(widget_url),
        "embed_url": request.build_absolute_uri(f"{widget_url}?embed=1"),
        "api_url": request.build_absolute_uri(api_url),
    }


def _build_combination_payload(request, user_type, super_slug, category_slug):
    combination = get_faq_combination(user_type, super_slug, category_slug)
    if not combination:
        raise Http404("FAQ combination not found.")
    urls = _build_combination_urls(request, user_type, super_slug, category_slug)
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
        **urls,
        "faqs": [
            {
                "id": item.pk,
                "question": item.name,
                "answer": item.solution_body or item.summary or "No answer has been configured yet.",
                "summary": item.summary,
                "pdf_url": item.associated_pdf_url,
                "video_url": item.associated_video_url,
            }
            for item in combination["faq_items"]
        ],
    }


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
        if state.get("selected_ticket_case_id"):
            state.pop("selected_ticket_case_id", None)
        elif state.get("resolved_item_id"):
            state.pop("resolved_item_id", None)
            state["faq_index"] = max(0, state.get("faq_index", 0) - 1)
        elif state.get("category_id"):
            state.pop("category_id", None)
            state.pop("faq_index", None)
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
        faqs, ticket_cases = (
            get_issue_sequences(self.user_type, selected_system, selected_flow, selected_category.pk)
            if selected_system and selected_flow and selected_category
            else ([], [])
        )
        faq_index = state.get("faq_index", 0)
        selected_ticket_case = next((item for item in ticket_cases if item.pk == state.get("selected_ticket_case_id")), None)
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
            "ticket_cases": ticket_cases,
            "faq_index": faq_index,
            "current_faq": faqs[faq_index] if faq_index < len(faqs) else None,
            "selected_ticket_case": selected_ticket_case,
            "resolved_item": resolved_item,
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
        if context["selected_ticket_case"]:
            if context["selected_ticket_case"].ticket_required is False:
                return "ticket_case_info"
            return "ticket_form"
        if context["current_faq"]:
            return "faq"
        if context["ticket_cases"]:
            return "ticket_case"
        return "empty"

    def _build_transcript(self, context, stage):
        transcript = [
            {
                "speaker": "bot",
                "title": "Support Assistant",
                "body": "I’ll walk through the available FAQs first, then move into ticket cases only if the issue is still unresolved.",
            }
        ]
        if context["selected_system"]:
            transcript.append({"speaker": "user", "title": "System", "body": context["selected_system"]})
        if context["selected_flow"]:
            transcript.append({"speaker": "user", "title": "Flow", "body": context["selected_flow"]})
        if context["selected_category"]:
            transcript.append({"speaker": "user", "title": "Screen / Section", "body": context["selected_category"].name})

        if stage == "faq" and context["current_faq"]:
            current_faq = context["current_faq"]
            transcript.append(
                {
                    "speaker": "bot",
                    "title": f"FAQ {context['faq_index'] + 1} of {len(context['faqs'])}",
                    "heading": current_faq.name,
                    "body": current_faq.solution_body or current_faq.summary or "No standardized solution text is available yet.",
                    "item": current_faq,
                }
            )
        elif stage == "ticket_case" and context["ticket_cases"]:
            transcript.append(
                {
                    "speaker": "bot",
                    "title": "Escalation",
                    "body": "The available FAQs did not fully resolve the issue. Please choose the ticket case that best matches what happened.",
                }
            )
        elif stage == "ticket_form" and context["selected_ticket_case"]:
            transcript.append({"speaker": "user", "title": "Ticket case", "body": context["selected_ticket_case"].name})
            transcript.append(
                {
                    "speaker": "bot",
                    "title": "Ticket routing",
                    "body": (
                        context["selected_ticket_case"].solution_body
                        or f"This case will be routed to {context['selected_ticket_case'].ticket_department.name if context['selected_ticket_case'].ticket_department else 'the configured department'}."
                    ),
                    "item": context["selected_ticket_case"],
                }
            )
        elif stage == "ticket_case_info" and context["selected_ticket_case"]:
            transcript.append({"speaker": "user", "title": "Ticket case", "body": context["selected_ticket_case"].name})
            transcript.append(
                {
                    "speaker": "bot",
                    "title": "Imported guidance",
                    "body": context["selected_ticket_case"].solution_body or "This case is marked as a non-ticket case in the imported sheet.",
                }
            )
        elif stage == "resolved" and context["resolved_item"]:
            transcript.append(
                {
                    "speaker": "bot",
                    "title": "Resolved",
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
                "ticket_form": kwargs.get("ticket_form") or SupportRequestForm(initial={"subject": assistant_context["selected_ticket_case"].name if assistant_context["selected_ticket_case"] else ""}),
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
                        "faq_index": 0,
                    }
                )
            return redirect("support_center:assistant", user_type=self.user_type)

        if action == "faq_feedback" and context["selected_category"]:
            current_faq = context["current_faq"]
            if not current_faq:
                messages.warning(request, "There is no FAQ loaded for this step.")
                return redirect("support_center:assistant", user_type=self.user_type)
            updated_state = {
                "system": context["selected_system"],
                "flow": context["selected_flow"],
                "category_id": context["selected_category"].pk,
                "faq_index": context["faq_index"],
            }
            if request.POST.get("resolution") == "resolved":
                updated_state["resolved_item_id"] = current_faq.pk
            else:
                updated_state["faq_index"] = context["faq_index"] + 1
            self._save_state(updated_state)
            return redirect("support_center:assistant", user_type=self.user_type)

        if action == "select_ticket_case" and context["selected_category"]:
            selected_case = next((item for item in context["ticket_cases"] if str(item.pk) == request.POST.get("item_id")), None)
            if selected_case:
                self._save_state(
                    {
                        "system": context["selected_system"],
                        "flow": context["selected_flow"],
                        "category_id": context["selected_category"].pk,
                        "faq_index": max(len(context["faqs"]), context["faq_index"]),
                        "selected_ticket_case_id": selected_case.pk,
                    }
                )
            return redirect("support_center:assistant", user_type=self.user_type)

        if action == "create_ticket" and context["selected_ticket_case"]:
            form = SupportRequestForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Please complete the ticket details.")
                template_context = self.get_context_data(ticket_form=form)
                return self.render_to_response(template_context)

            support_request, ticket, error_message = submit_support_request(
                item=context["selected_ticket_case"],
                user_type=self.user_type,
                form=form,
                request_user=request.user,
            )
            self._clear_state()
            if ticket:
                messages.success(request, f"Ticket {ticket.ticket_number} created from the support assistant.")
            else:
                messages.info(request, error_message or "Support request recorded.")
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


def support_faq_links_api(request, user_type):
    if request.method == "OPTIONS":
        return _options_response()
    if user_type not in ROLE_CONFIG:
        raise Http404("Unsupported support audience.")
    results = []
    for block in get_faq_super_category_overview(user_type):
        for entry in block["categories"]:
            category = entry["category"]
            results.append(
                {
                    "super_category": {"name": block["super_category"].name, "slug": block["super_category"].slug},
                    "category": {"name": category.name, "slug": category.slug},
                    "faq_count": len(entry["faq_items"]),
                    **_build_combination_urls(request, user_type, block["super_category"].slug, category.slug),
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
