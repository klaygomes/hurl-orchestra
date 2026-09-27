---
id: create_cart
deps: [auth]
outputs: [cart_id]
---
POST {{base_url}}/carts
Authorization: Bearer {{auth_token}}
HTTP 201
[Captures]
cart_id: jsonpath "$.id"
