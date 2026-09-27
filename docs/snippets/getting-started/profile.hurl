---
id: profile
deps: [auth]
---
GET {{base_url}}/profile
Authorization: Bearer {{auth_token}}
HTTP 200
[Asserts]
jsonpath "$.user" == "ada"
