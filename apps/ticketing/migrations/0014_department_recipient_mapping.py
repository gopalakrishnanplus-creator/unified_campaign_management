from django.conf import settings
from django.db import migrations


DEPARTMENT_RECIPIENTS = [
    {
        "code": "PRODUCT",
        "name": "Product",
        "description": "Handles product review, approvals, and workflow decisions.",
        "support_email": "product@inditech.co.in",
        "recipient_email": "simran.galani@inditech.co.in",
    },
    {
        "code": "CONTENT",
        "name": "Content",
        "description": "Handles content, copy, creative, and asset updates.",
        "support_email": "content@inditech.co.in",
        "recipient_email": "rashmi.mohan@inditech.co.in",
    },
    {
        "code": "TECHNOLOGY",
        "name": "Technology",
        "description": "Handles product technology, integrations, and application issues.",
        "support_email": "technology@inditech.co.in",
        "recipient_email": "niomi.samani@inditech.co.in",
    },
    {
        "code": "IT",
        "name": "IT",
        "description": "Handles IT, access, devices, and internal infrastructure.",
        "support_email": "it@inditech.co.in",
        "recipient_email": "nikhil.verma@inditech.co.in",
    },
]


def unique_support_email(Department, desired_email, code, current_department=None):
    current_pk = getattr(current_department, "pk", None)
    if not Department.objects.exclude(pk=current_pk).filter(support_email__iexact=desired_email).exists():
        return desired_email
    fallback = f"{code.lower()}@inditech.local"
    if not Department.objects.exclude(pk=current_pk).filter(support_email__iexact=fallback).exists():
        return fallback
    return f"{code.lower()}-{current_pk or 'department'}@inditech.local"


def apply_department_recipient_mapping(apps, schema_editor):
    Department = apps.get_model("ticketing", "Department")
    User = apps.get_model("accounts", "User")

    for config in DEPARTMENT_RECIPIENTS:
        department = Department.objects.filter(code__iexact=config["code"]).first()
        recipient, _ = User.objects.update_or_create(
            email=config["recipient_email"],
            defaults={
                "full_name": config["recipient_email"].split("@", 1)[0].replace(".", " ").title(),
                "role": "department_owner",
                "is_staff": True,
                "is_active": True,
                "company": "Inditech",
            },
        )

        if not department:
            department = Department(
                code=config["code"],
                support_email=unique_support_email(Department, config["support_email"], config["code"]),
            )
        elif not department.support_email:
            department.support_email = unique_support_email(Department, config["support_email"], config["code"], department)

        department.name = config["name"]
        department.description = config["description"]
        department.is_active = True
        if recipient:
            department.default_recipient = recipient
        department.save()

        if recipient and recipient.department_id != department.id:
            recipient.department = department
            recipient.save(update_fields=["department"])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("ticketing", "0013_specialinstructionreview"),
    ]

    operations = [
        migrations.RunPython(apply_department_recipient_mapping, migrations.RunPython.noop),
    ]
