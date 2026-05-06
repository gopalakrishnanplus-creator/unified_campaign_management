DEPARTMENT_ROUTING_CONFIG = [
    {
        "code": "PRODUCT",
        "name": "Product",
        "description": "Handles product review, approvals, and workflow decisions.",
        "support_email": "product@inditech.co.in",
    },
    {
        "code": "CONTENT",
        "name": "Content",
        "description": "Handles content, copy, creative, and asset updates.",
        "support_email": "content@inditech.co.in",
    },
    {
        "code": "TECHNOLOGY",
        "name": "Technology",
        "description": "Handles product technology, integrations, and application issues.",
        "support_email": "technology@inditech.co.in",
        "aliases": ("TECH", "Technical Support"),
    },
    {
        "code": "IT",
        "name": "IT",
        "description": "Handles IT, access, devices, and internal infrastructure.",
        "support_email": "it@inditech.co.in",
        "aliases": ("IT Support",),
    },
]


def normalize_department_key(value):
    return str(value or "").strip().lower().replace("-", " ").replace("_", " ")


def department_config_for_values(*values):
    normalized_values = {normalize_department_key(value) for value in values if value}
    for config in DEPARTMENT_ROUTING_CONFIG:
        keys = {
            normalize_department_key(config["code"]),
            normalize_department_key(config["name"]),
            *(normalize_department_key(alias) for alias in config.get("aliases", ())),
        }
        if normalized_values & keys:
            return config
    return None


def department_config_for_department(department):
    if not department:
        return None
    return department_config_for_values(
        department.code,
        department.name,
        department.external_directory_code,
        department.external_directory_name,
    )
