# Reporting API Contract

The campaign performance system needs the following API values from the three reporting subsystems.

## Red Flag Alert Reporting

| Variable | Type | Required | Description |
| --- | --- | --- | --- |
| `campaign_slug` | `string` | Yes | Campaign identifier |
| `period_start` | `date` | Yes | Inclusive reporting start date |
| `period_end` | `date` | Yes | Inclusive reporting end date |
| `clinic_group` | `string` | Yes | Clinic group or geography bucket |
| `clinic_code` | `string` | Yes | Clinic identifier |
| `form_fills` | `integer` | Yes | Screening or monitoring form submissions |
| `red_flags_total` | `integer` | Yes | Total red flags triggered |
| `patient_video_views` | `integer` | Yes | Patient education video views |
| `reports_emailed_to_doctors` | `integer` | Yes | Doctor reports emailed |
| `form_shares` | `integer` | Yes | Forms shared by clinics or doctors |
| `patient_scans` | `integer` | Yes | Patient scans or opens |
| `follow_ups_scheduled` | `integer` | Yes | Follow-ups scheduled |
| `reminders_sent` | `integer` | Yes | Reminders sent |

## In-Clinic Reporting

| Variable | Type | Required | Description |
| --- | --- | --- | --- |
| `campaign_slug` | `string` | Yes | Campaign identifier |
| `period_start` | `date` | Yes | Inclusive reporting start date |
| `period_end` | `date` | Yes | Inclusive reporting end date |
| `clinic_group` | `string` | Yes | Clinic group or geography bucket |
| `clinic_code` | `string` | Yes | Clinic identifier |
| `doctor_name` | `string` | No | Doctor who received the content |
| `field_rep_email` | `string` | No | Field rep who shared the content |
| `shares` | `integer` | Yes | Collateral shares completed |
| `link_opens` | `integer` | Yes | Doctor opens |
| `pdf_reads_completed` | `integer` | Yes | PDF reads to the last page |
| `video_views` | `integer` | Yes | Video views |
| `video_completions` | `integer` | Yes | Video completions |
| `pdf_downloads` | `integer` | Yes | PDF downloads |

## Patient Education Reporting

| Variable | Type | Required | Description |
| --- | --- | --- | --- |
| `campaign_slug` | `string` | Yes | Campaign identifier |
| `period_start` | `date` | Yes | Inclusive reporting start date |
| `period_end` | `date` | Yes | Inclusive reporting end date |
| `clinic_group` | `string` | Yes | Clinic group or geography bucket |
| `clinic_code` | `string` | Yes | Clinic identifier |
| `video_views` | `integer` | Yes | Patient video views |
| `video_completions` | `integer` | Yes | Patient video completions |
| `cluster_shares` | `integer` | Yes | Video cluster shares |
| `patient_scans` | `integer` | Yes | Patient scans or opens |
| `banner_clicks` | `integer` | Yes | Sponsor acknowledgement banner clicks |
