---
id: isolation
deps:
  - sign_up: alice
  - sign_up: bob
---
GET {{base_url}}/users/{{alice_user_id}}
Authorization: Bearer {{bob_token}}
HTTP 403
