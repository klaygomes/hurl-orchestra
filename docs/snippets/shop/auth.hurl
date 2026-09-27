---
id: auth
outputs: [token]
---
POST {{base_url}}/login
HTTP 200
[Captures]
token: jsonpath "$.token"
