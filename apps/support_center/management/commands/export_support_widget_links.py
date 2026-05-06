import csv
from pathlib import Path
from urllib.parse import urlencode

from django.core.management.base import BaseCommand

from apps.support_center.services import GENERAL_SUPPORT_FLOW, get_faq_page_overview


ROLE_CONFIG = {
    "doctor": "Doctor Support",
    "clinic_staff": "Clinic Staff Support",
    "brand_manager": "Brand Manager Support",
    "publisher": "Publisher Support",
    "field_rep": "Field Rep Support",
    "patient": "Patient Support",
    "student": "Student Support",
    "expert": "Expert Support",
}


class Command(BaseCommand):
    help = "Exports page-wise support widget links to CSV and Markdown."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default="https://help.cpdinclinic.co.in", help="Public base URL for widget links.")
        parser.add_argument("--csv-output", default="docs/support-widget-page-links.csv", help="CSV output path.")
        parser.add_argument("--md-output", default="docs/support-widget-page-links.md", help="Markdown output path.")

    def handle(self, *args, **options):
        base_url = options["base_url"].rstrip("/")
        csv_output = Path(options["csv_output"])
        md_output = Path(options["md_output"])
        csv_output.parent.mkdir(parents=True, exist_ok=True)
        md_output.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for user_type, role_title in ROLE_CONFIG.items():
            for block in get_faq_page_overview(user_type):
                page = block["page"]
                params = {}
                if page.source_system:
                    params["system"] = page.source_system
                if page.source_flow:
                    params["flow"] = page.source_flow
                query = f"?{urlencode(params)}" if params else ""
                page_path = f"/support/{user_type}/faq/page/{page.slug}/"
                widget_path = f"{page_path}widget/"
                api_path = f"/support/api/{user_type}/pages/{page.slug}/"
                rows.append(
                    {
                        "source_system": page.source_system,
                        "source_flow": page.source_flow or GENERAL_SUPPORT_FLOW,
                        "role": user_type,
                        "role_title": role_title,
                        "page": page.name,
                        "page_slug": page.slug,
                        "section_count": block["section_count"],
                        "faq_count": block["faq_count"],
                        "sections": " | ".join(section["super_category"].name for section in block["sections"]),
                        "page_url": f"{base_url}{page_path}{query}",
                        "widget_url": f"{base_url}{widget_path}{query}",
                        "embed_url": f"{base_url}{widget_path}?{urlencode({**params, 'embed': '1'})}" if params else f"{base_url}{widget_path}?embed=1",
                        "api_url": f"{base_url}{api_path}{query}",
                    }
                )

        with csv_output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "source_system",
                    "source_flow",
                    "role",
                    "role_title",
                    "page",
                    "page_slug",
                    "section_count",
                    "faq_count",
                    "sections",
                    "page_url",
                    "widget_url",
                    "embed_url",
                    "api_url",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

        lines = [
            "# Support Widget Links",
            "",
            "Generated from the current support catalog. Each row is a valid page-wise FAQ widget/API combination for the specified role.",
            "",
            "| System | Flow | Role | Page | Sections | FAQs | Widget URL | API URL |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            lines.append(
                f"| {row['source_system']} | {row['source_flow']} | {row['role']} | {row['page']} | {row['section_count']} | {row['faq_count']} | {row['widget_url']} | {row['api_url']} |"
            )
        md_output.write_text("\n".join(lines) + "\n", encoding="utf-8")

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {len(rows)} page-wise support widget links to {csv_output} and {md_output}."
            )
        )
