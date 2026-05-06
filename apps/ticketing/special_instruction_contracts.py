"""
Analysis-only contract definitions for the RFA Special Instruction workflow.

These contracts are intentionally separate from apps.reporting.contracts because
Special Instruction approval is an operational ticketing workflow, not a
campaign-performance reporting feed.
"""

SPECIAL_INSTRUCTION_CONTRACT_BASE_URL = "https://red-flag-alerts.co.in"
SPECIAL_INSTRUCTION_PM_WEBHOOK_PATH = "/app/special-instructions/webhook/"

SPECIAL_INSTRUCTION_API_CONTRACTS = {
    "pm_webhook_intake": {
        "label": "PM Special Instruction webhook intake",
        "direction": "RFA -> PM",
        "method": "POST",
        "endpoint": SPECIAL_INSTRUCTION_PM_WEBHOOK_PATH,
        "auth": {
            "primary": "Authorization: Bearer <SPECIAL_INSTRUCTION_PM_API_TOKEN>",
            "fallback": "X-Special-Instruction-Token: <SPECIAL_INSTRUCTION_PM_API_TOKEN>",
        },
        "purpose": "Create or update a PM Special Instruction review ticket when RFA receives a doctor upload.",
        "side_effects": [
            "Creates or updates one PM ticket keyed by doctor_id and campaign_id.",
            "Auto-assigns the review to the PRODUCT department default recipient.",
            "Sends the assigned reviewer an email with Download and Approve actions.",
        ],
        "accepted_payloads": [
            "Full RFA ticket payload under the top-level ticket key.",
            "Full RFA ticket payload wrapped under data, payload, request, ticket_payload, ticketPayload, or body.",
            "Minimal doctor_id and optional campaign_id payload for webhook retry recovery.",
            "Form-encoded doctor_id and optional campaign_id payload for delivery retries.",
        ],
        "request_variables": [
            {"name": "ticket.doctor.id", "type": "string", "required": True, "description": "RFA doctor identifier used as the primary review key."},
            {"name": "ticket.doctor.name", "type": "string", "required": False, "description": "Doctor display name shown in PM and email."},
            {"name": "ticket.doctor.email", "type": "email", "required": False, "description": "Doctor email copied into review metadata."},
            {"name": "ticket.clinic.name", "type": "string", "required": False, "description": "Clinic display name shown in PM and email."},
            {"name": "ticket.clinic.phone", "type": "string", "required": False, "description": "Clinic phone copied into ticket requester details."},
            {"name": "ticket.associated_campaign.campaign_id", "type": "string", "required": False, "description": "RFA campaign UUID; combines with doctor id for idempotency."},
            {"name": "ticket.associated_campaign.campaign_name", "type": "string", "required": False, "description": "Campaign name shown in PM and email."},
            {"name": "ticket.associated_campaign.brand_name", "type": "string", "required": False, "description": "Brand name shown in PM and email."},
            {"name": "ticket.associated_campaign.field_rep.id", "type": "string", "required": False, "description": "Campaign field representative external id."},
            {"name": "ticket.associated_campaign.field_rep.internal_id", "type": "integer", "required": False, "description": "Campaign field representative internal RFA id."},
            {"name": "ticket.associated_campaign.field_rep.name", "type": "string", "required": False, "description": "Campaign field representative display name."},
            {"name": "ticket.assigned_field_rep.id", "type": "string", "required": False, "description": "Assigned field representative external id."},
            {"name": "ticket.assigned_field_rep.internal_id", "type": "integer", "required": False, "description": "Assigned field representative internal RFA id."},
            {"name": "ticket.assigned_field_rep.name", "type": "string", "required": False, "description": "Assigned field representative display name."},
            {"name": "ticket.special_instruction.current_status", "type": "string", "required": False, "description": "Human-readable RFA status, for example Document in process."},
            {"name": "ticket.special_instruction.status_code", "type": "string", "required": False, "description": "Machine status code, for example in_process or uploaded."},
            {"name": "ticket.special_instruction.uploaded_at", "type": "datetime", "required": False, "description": "Upload timestamp from RFA, preferably ISO 8601 with timezone."},
            {"name": "ticket.special_instruction.download_url", "type": "url", "required": False, "description": "RFA download endpoint; must match the configured RFA host."},
            {"name": "ticket.special_instruction.approve_url", "type": "url", "required": False, "description": "RFA approval endpoint; must match the configured RFA host."},
        ],
        "response_variables": [
            {"name": "success", "type": "boolean", "required": True, "description": "Whether the PM webhook accepted and stored the request."},
            {"name": "review_id", "type": "integer", "required": True, "description": "PM SpecialInstructionReview primary key."},
            {"name": "ticket_number", "type": "string", "required": True, "description": "PM ticket number created or updated for this review."},
            {"name": "ticket_url", "type": "url", "required": True, "description": "Absolute PM ticket detail URL."},
            {"name": "doctor_id", "type": "string", "required": True, "description": "Doctor id accepted by PM."},
            {"name": "status", "type": "string", "required": False, "description": "Current RFA status code stored by PM."},
            {"name": "assignee_email", "type": "email", "required": True, "description": "Email of the PM reviewer assigned from the Product department default recipient."},
        ],
    },
    "rfa_ticket_payload": {
        "label": "RFA Special Instruction ticket payload",
        "direction": "PM -> RFA",
        "method": "GET",
        "endpoint": "/internal/special-instructions/<doctor_id>/ticket/",
        "query_params": [
            {"name": "campaign_id", "type": "string", "required": False, "description": "RFA campaign UUID when the doctor has multiple campaign contexts."},
        ],
        "auth": {
            "primary": "Authorization: Bearer <SPECIAL_INSTRUCTION_PM_API_TOKEN>",
            "fallback": "X-Special-Instruction-Token: <SPECIAL_INSTRUCTION_PM_API_TOKEN>",
        },
        "purpose": "Fetch all data needed by PM to create a Special Instruction review ticket.",
        "side_effects": [
            "Triggers RFA Product Team email notification according to the RFA API behavior.",
        ],
        "response_root": "ok + ticket",
        "response_variables": [
            {"name": "ok", "type": "boolean", "required": True, "description": "True when RFA returned a usable ticket payload."},
            {"name": "ticket", "type": "object", "required": True, "description": "Full Special Instruction ticket payload consumed by PM webhook/manual reload."},
        ],
    },
    "rfa_document_download": {
        "label": "RFA Special Instruction document download",
        "direction": "PM reviewer -> PM -> RFA",
        "method": "GET",
        "endpoint": "/internal/special-instructions/<doctor_id>/download/",
        "auth": {
            "primary": "Authorization: Bearer <SPECIAL_INSTRUCTION_PM_API_TOKEN>",
            "fallback": "X-Special-Instruction-Token: <SPECIAL_INSTRUCTION_PM_API_TOKEN>",
        },
        "purpose": "Download the uploaded Special Instruction document as an attachment through PM proxy action.",
        "response": "Binary file attachment. The S3 URL must not be exposed to PM users.",
    },
    "rfa_document_approve": {
        "label": "RFA Special Instruction approval",
        "direction": "PM reviewer -> PM -> RFA",
        "method": "POST",
        "endpoint": "/internal/special-instructions/<doctor_id>/approve/",
        "auth": {
            "primary": "Authorization: Bearer <SPECIAL_INSTRUCTION_PM_API_TOKEN>",
            "fallback": "X-Special-Instruction-Token: <SPECIAL_INSTRUCTION_PM_API_TOKEN>",
        },
        "purpose": "Approve the Special Instruction document after reviewer validation.",
        "side_effects": [
            "RFA changes special_instructions_present from N to Y.",
            "RFA changes current status from Document in process to Document uploaded.",
            "PM marks the local Special Instruction ticket completed and records approved_at in IST-capable display.",
        ],
        "response_variables": [
            {"name": "ok", "type": "boolean", "required": False, "description": "RFA success flag when returned."},
            {"name": "ticket.special_instruction.current_status", "type": "string", "required": False, "description": "Updated human-readable RFA status."},
            {"name": "ticket.special_instruction.status_code", "type": "string", "required": False, "description": "Updated machine status code."},
        ],
    },
}

SPECIAL_INSTRUCTION_WORKFLOW_STATES = [
    {
        "state": "Document in process",
        "status_code": "in_process",
        "owner": "RFA",
        "meaning": "Doctor uploaded a Special Instruction document and PM review is pending.",
    },
    {
        "state": "Assigned",
        "status_code": "pm_assigned",
        "owner": "PM",
        "meaning": "PM created or updated the review ticket and assigned it to the Product department default recipient.",
    },
    {
        "state": "Document uploaded",
        "status_code": "uploaded",
        "owner": "RFA",
        "meaning": "PM reviewer approved the document and RFA persisted the approved flag.",
    },
]
