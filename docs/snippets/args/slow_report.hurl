---
id: slow_report
args:
  - verbose
  - connect-timeout: 30
  - variable: region=eu
---
GET {{base_url}}/reports/{{region}}
HTTP 200
