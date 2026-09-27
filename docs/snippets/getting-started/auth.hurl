---
id: auth
outputs: [token]
---
POST {{base_url}}/login
{
  "user": "ada",
  "password": "{{password}}"
}
HTTP 200
[Captures]
token: jsonpath "$.token"
