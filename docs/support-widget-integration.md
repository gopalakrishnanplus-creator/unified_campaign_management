# FAQ Support Widget Integration

Use these endpoints when another system needs to open page-wise FAQ support in a bottom-right chat widget.

## 1. Get all available links for a role

Call:

- `/support/api/doctor/faq-links/`
- `/support/api/clinic_staff/faq-links/`
- `/support/api/brand_manager/faq-links/`
- `/support/api/field_rep/faq-links/`
- `/support/api/patient/faq-links/`

Each response returns one record per `page`. Every record includes:

- `page`: the page metadata
- `sections`: the list of super categories available on that page
- `page_url`: the FAQ page for the page-level support view
- `widget_url`: the standalone widget page
- `embed_url`: the iframe-safe widget URL for bottom-right embedding
- `api_url`: the JSON payload for that exact page

## 2. Embed a specific page

For a single page, use:

- `/support/<role>/faq/page/<page_slug>/widget/?embed=1`

Example pattern:

- `/support/doctor/faq/page/in-clinic-flow1-doctor-doctor-verification-page/widget/?embed=1`

This URL is safe to place inside an iframe and is intended for the support launcher in another system.

## 3. Fetch the JSON payload directly

For a single page, use:

- `/support/api/<role>/pages/<page_slug>/`

Example pattern:

- `/support/api/doctor/pages/in-clinic-flow1-doctor-doctor-verification-page/`

The JSON contains the full page structure and includes:

- `page`
- `sections`
- `faq_count`
- `section_count`
- `page_url`
- `widget_url`
- `embed_url`
- `api_url`

## 4. Expected embedding behavior

The external system should:

1. identify the current `role` and `page_slug`
2. use the corresponding `embed_url`
3. open that URL in a fixed bottom-right iframe or chat drawer

The widget is FAQ-only right now. It shows a radio-button list of sections for the page, then the FAQ questions for the selected section, displays answers inline, and lets the user continue until the issue is resolved or they raise a query.
