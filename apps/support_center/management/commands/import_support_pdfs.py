from dataclasses import dataclass
import re
from pathlib import Path

import pdfplumber
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.accounts.models import User
from apps.support_center.models import SupportCategory, SupportItem, SupportPage, SupportSuperCategory
from apps.ticketing.models import Department


SYSTEM_LABELS = {
    "Inclinic-FAQs": "In-clinic",
    "PE-FAQs": "Patient Education",
    "RFA-FAQs": "Red Flag Alert",
}

ROLE_LABELS = {
    "Doctor": "doctor",
    "FieldRep": "field_rep",
    "Patient": "patient",
    "Publisher": "publisher",
    "BrandManager": "brand_manager",
    "Student": "student",
    "Expert": "expert",
}

SAPLAICME_TITLE_METADATA = {
    "expertwebinarflowfaqs": {
        "flow_name": "Expert Webinar Flow",
        "audience": "expert",
        "knowledge_type": SupportItem.KnowledgeType.FAQ,
    },
    "studentaicmeflowfaqs": {
        "flow_name": "Student AI-CME Flow",
        "audience": "student",
        "knowledge_type": SupportItem.KnowledgeType.FAQ,
    },
    "studentlectureflowfaqs": {
        "flow_name": "Student Lecture Flow",
        "audience": "student",
        "knowledge_type": SupportItem.KnowledgeType.FAQ,
    },
    "studentwebinarflowfaqs": {
        "flow_name": "Student Webinar Flow",
        "audience": "student",
        "knowledge_type": SupportItem.KnowledgeType.FAQ,
    },
}

DEPARTMENT_SPECS = {
    "Product": {
        "code": "PRODUCT",
        "name": "Product",
        "email": "product-support@inditech.co.in",
        "user_email": "product.owner@inditech.co.in",
        "user_name": "Product Owner",
    },
    "Engineering": {
        "code": "ENGINEERING",
        "name": "Engineering",
        "email": "engineering-support@inditech.co.in",
        "user_email": "engineering.owner@inditech.co.in",
        "user_name": "Engineering Owner",
    },
    "IT": {
        "code": "IT",
        "name": "IT Support",
        "email": "it-support@inditech.co.in",
        "user_email": "it.owner@inditech.co.in",
        "user_name": "IT Owner",
    },
}


@dataclass
class ParsedSheet:
    system_name: str
    flow_name: str
    audience: str
    knowledge_type: str
    source_document: str
    associated_pdf_url: str
    source_page: int
    rows: list


class Command(BaseCommand):
    help = "Imports support FAQs and ticket cases from PDF sheet exports."

    def add_arguments(self, parser):
        parser.add_argument("pdf_paths", nargs="+", help="PDF files to import.")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Replace previously imported items for the systems found in the supplied PDFs.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        pdf_paths = [Path(path).expanduser() for path in options["pdf_paths"]]
        for pdf_path in pdf_paths:
            if not pdf_path.exists():
                raise CommandError(f"PDF not found: {pdf_path}")

        sheets = []
        systems_in_batch = set()
        for pdf_path in pdf_paths:
            parsed = self.parse_pdf(pdf_path)
            sheets.extend(parsed)
            systems_in_batch.update(sheet.system_name for sheet in parsed)

        departments = self.ensure_departments()
        default_faq_department = departments["Product"]

        if options["replace"] and systems_in_batch:
            deleted, _ = SupportItem.objects.filter(source_system__in=systems_in_batch).delete()
            self.stdout.write(f"Deleted {deleted} existing support items for systems: {', '.join(sorted(systems_in_batch))}")

        counters = {"super": 0, "category": 0, "item": 0}
        for sheet in sheets:
            for row in sheet.rows:
                super_category = self.get_or_create_super_category(sheet.system_name, row["super_category"], counters)
                page = self.get_or_create_page(sheet, row["page"], counters)
                category = self.get_or_create_category(super_category, row["category"], counters)
                department = self.resolve_department(row.get("ticket_department"), departments)
                ticket_required = self.resolve_ticket_required(row.get("ticket_required"), row.get("ticket_department"))
                response_mode = (
                    SupportItem.ResponseMode.STANDARDIZED
                    if sheet.knowledge_type == SupportItem.KnowledgeType.FAQ or not ticket_required
                    else SupportItem.ResponseMode.DIRECT_TICKET
                )

                item = SupportItem.objects.filter(
                    category=category,
                    source_flow=sheet.flow_name,
                    knowledge_type=sheet.knowledge_type,
                    name=row["name"],
                ).first()
                defaults = {
                    "page": page,
                    "slug": self.build_item_slug(sheet, row["name"]),
                    "summary": row["summary"],
                    "response_mode": response_mode,
                    "solution_title": row["solution_title"],
                    "solution_body": row["solution_body"],
                    "ticket_department": department or (default_faq_department if response_mode == SupportItem.ResponseMode.STANDARDIZED else None),
                    "default_ticket_type": f"{sheet.system_name} {sheet.audience.replace('_', ' ')} {'FAQ escalation' if sheet.knowledge_type == SupportItem.KnowledgeType.FAQ else 'ticket case'}",
                    "source_system": sheet.system_name,
                    "source_flow": sheet.flow_name,
                    "source_document": sheet.source_document,
                    "source_page": sheet.source_page,
                    "associated_pdf_url": sheet.associated_pdf_url,
                    "knowledge_type": sheet.knowledge_type,
                    "ticket_required": ticket_required,
                    "display_order": counters["item"],
                    "is_active": True,
                    "is_visible_to_doctors": sheet.audience == "doctor",
                    "is_visible_to_clinic_staff": False,
                    "is_visible_to_brand_managers": sheet.audience == "brand_manager",
                    "is_visible_to_publishers": sheet.audience == "publisher",
                    "is_visible_to_field_reps": sheet.audience == "field_rep",
                    "is_visible_to_patients": sheet.audience == "patient",
                    "is_visible_to_students": sheet.audience == "student",
                    "is_visible_to_experts": sheet.audience == "expert",
                }
                counters["item"] += 1
                if item:
                    for key, value in defaults.items():
                        setattr(item, key, value)
                    item.save()
                else:
                    SupportItem.objects.create(category=category, name=row["name"], **defaults)

        self.stdout.write(self.style.SUCCESS(f"Imported {counters['item']} support entries from {len(pdf_paths)} PDFs."))

    def ensure_departments(self):
        departments = {}
        for label, spec in DEPARTMENT_SPECS.items():
            user, _ = User.objects.get_or_create(
                email=spec["user_email"],
                defaults={
                    "full_name": spec["user_name"],
                    "role": User.Role.DEPARTMENT_OWNER,
                    "is_staff": True,
                },
            )
            department, _ = Department.objects.get_or_create(
                code=spec["code"],
                defaults={
                    "name": spec["name"],
                    "support_email": spec["email"],
                    "default_recipient": user,
                },
            )
            if user.department_id != department.id:
                user.department = department
                user.save(update_fields=["department"])
            departments[label] = department
        return departments

    def parse_pdf(self, pdf_path):
        parsed_sheets = []
        associated_pdf_url = self.build_associated_pdf_url(pdf_path)
        with pdfplumber.open(pdf_path) as pdf:
            for page_number, page in enumerate(pdf.pages, 1):
                text_lines = [line.strip() for line in (page.extract_text() or "").splitlines() if line.strip()]
                if not text_lines:
                    continue
                title_line = text_lines[0]
                metadata = self.parse_title(title_line)
                if not metadata:
                    continue
                table = page.extract_table()
                if not table or len(table) < 2:
                    continue

                header = [self.normalize_spaces(cell) for cell in table[0]]
                knowledge_type = metadata["knowledge_type"]
                rows = []
                for raw_row in table[1:]:
                    clean_row = [self.normalize_spaces(cell) for cell in raw_row]
                    if not any(clean_row):
                        continue
                    if knowledge_type == SupportItem.KnowledgeType.FAQ:
                        if len(clean_row) < 5:
                            continue
                        super_category, page_name, category, question, answer = clean_row[:5]
                        if not (super_category and page_name and category and question):
                            continue
                        rows.append(
                            {
                                "super_category": super_category,
                                "page": page_name,
                                "category": category,
                                "name": question,
                                "summary": answer[:255],
                                "solution_title": question,
                                "solution_body": answer,
                                "ticket_required": None,
                                "ticket_department": "Product",
                            }
                        )
                    else:
                        if len(clean_row) < 7:
                            continue
                        super_category, page_name, category, edge_case, ticket_required, ticket_department, notes = clean_row[:7]
                        if not (super_category and page_name and category and edge_case):
                            continue
                        rows.append(
                            {
                                "super_category": super_category,
                                "page": page_name,
                                "category": category,
                                "name": edge_case,
                                "summary": notes[:255] if notes else "Imported ticket case",
                                "solution_title": "",
                                "solution_body": notes,
                                "ticket_required": ticket_required,
                                "ticket_department": ticket_department,
                            }
                        )

                parsed_sheets.append(
                    ParsedSheet(
                        system_name=metadata["system_name"],
                        flow_name=metadata["flow_name"],
                        audience=metadata["audience"],
                        knowledge_type=knowledge_type,
                        source_document=pdf_path.name,
                        associated_pdf_url=associated_pdf_url,
                        source_page=page_number,
                        rows=rows,
                    )
                )
        return parsed_sheets

    def parse_title(self, title_line):
        compact_title = re.sub(r"[\s_-]+", "", title_line).lower()
        saplaicme_metadata = SAPLAICME_TITLE_METADATA.get(compact_title) or SAPLAICME_TITLE_METADATA.get(
            compact_title.removeprefix("saplaicme")
        )
        if saplaicme_metadata:
            return {
                "system_name": "SAPLAICME",
                **saplaicme_metadata,
            }

        match = re.match(r"^(?P<system>[A-Za-z-]+)\s+(?P<flow>Flow\d+_[A-Za-z]+)_(?P<kind>FAQS|TicketCases)$", title_line)
        if not match:
            return None
        system_name = SYSTEM_LABELS.get(match.group("system"), match.group("system"))
        flow_name = match.group("flow").replace("_", " / ")
        audience_key = match.group("flow").split("_", 1)[1]
        audience = ROLE_LABELS.get(audience_key)
        if not audience:
            raise CommandError(f"Unsupported audience in sheet title: {title_line}")
        knowledge_type = (
            SupportItem.KnowledgeType.FAQ
            if match.group("kind") == "FAQS"
            else SupportItem.KnowledgeType.TICKET_CASE
        )
        return {
            "system_name": system_name,
            "flow_name": flow_name,
            "audience": audience,
            "knowledge_type": knowledge_type,
        }

    def get_or_create_super_category(self, system_name, raw_super_category, counters):
        name = f"{system_name} / {raw_super_category}"
        super_category, created = SupportSuperCategory.objects.get_or_create(
            slug=slugify(name),
            defaults={"name": name, "display_order": counters["super"], "is_active": True},
        )
        if created:
            counters["super"] += 1
        return super_category

    def get_or_create_page(self, sheet, raw_page, counters):
        page_name = self.normalize_spaces(raw_page)
        page_slug = slugify(f"{sheet.system_name}-{sheet.flow_name}-{page_name}")[:220]
        page, created = SupportPage.objects.get_or_create(
            slug=page_slug,
            defaults={
                "name": page_name,
                "source_system": sheet.system_name,
                "source_flow": sheet.flow_name,
                "display_order": counters["category"],
                "is_active": True,
            },
        )
        if created:
            counters["category"] += 1
        return page

    def get_or_create_category(self, super_category, raw_category, counters):
        slug = slugify(raw_category)
        category, created = SupportCategory.objects.get_or_create(
            super_category=super_category,
            slug=slug,
            defaults={"name": raw_category, "display_order": counters["category"], "is_active": True},
        )
        if created:
            counters["category"] += 1
        return category

    def build_item_slug(self, sheet, name):
        base = slugify(name)
        flow = slugify(sheet.flow_name)
        kind = slugify(sheet.knowledge_type)
        return f"{flow}-{kind}-{base}"[:255]

    def build_associated_pdf_url(self, pdf_path):
        bundled_pdf_path = Path(settings.BASE_DIR) / "static" / "support-pdfs" / pdf_path.name
        if not bundled_pdf_path.exists():
            return ""
        static_url = settings.STATIC_URL.rstrip("/") or "/static"
        return f"{static_url}/support-pdfs/{pdf_path.name}"

    def resolve_department(self, label, departments):
        if not label or label.upper() == "NA":
            return None
        return departments.get(label)

    def resolve_ticket_required(self, raw_value, department_label):
        value = (raw_value or "").strip().lower()
        if value in {"yes", "true"}:
            return True
        if value in {"no", "false"}:
            return False
        if (department_label or "").strip().upper() == "NA":
            return False
        return True

    def normalize_spaces(self, value):
        if value is None:
            return ""
        return re.sub(r"\s+", " ", value.replace("\n", " ")).strip()
