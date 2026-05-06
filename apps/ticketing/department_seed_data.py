from .department_routing import DEPARTMENT_ROUTING_CONFIG


RECIPIENTS_BY_DEPARTMENT_CODE = {
    "PRODUCT": {
        "recipient_email": "simran.galani@inditech.co.in",
        "recipient_name": "Simran Galani",
    },
    "CONTENT": {
        "recipient_email": "rashmi.mohan@inditech.co.in",
        "recipient_name": "Rashmi Mohan",
    },
    "TECHNOLOGY": {
        "recipient_email": "niomi.samani@inditech.co.in",
        "recipient_name": "Niomi Samani",
    },
    "IT": {
        "recipient_email": "nikhil.verma@inditech.co.in",
        "recipient_name": "Nikhil Verma",
    },
}


DEPARTMENT_RECIPIENT_CONFIG = [
    {
        **config,
        **RECIPIENTS_BY_DEPARTMENT_CODE[config["code"]],
    }
    for config in DEPARTMENT_ROUTING_CONFIG
]
