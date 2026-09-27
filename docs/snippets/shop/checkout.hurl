---
id: checkout
deps: [auth, create_cart, add_item]
---
POST {{base_url}}/carts/{{create_cart_cart_id}}/checkout
Authorization: Bearer {{auth_token}}
HTTP 200
