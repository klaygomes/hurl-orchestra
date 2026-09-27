---
id: sign_up
outputs: [token, user_id]
---
POST {{base_url}}/users
{ "email": "{{newUuid}}@example.com" }
HTTP 201
[Captures]
token: jsonpath "$.token"
user_id: jsonpath "$.id"
