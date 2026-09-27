---
id: add_item
deps: [auth, create_cart]
---
POST {{base_url}}/carts/{{create_cart_cart_id}}/items
Authorization: Bearer {{auth_token}}
{ "sku": "cauliflower", "quantity": 2 }
HTTP 201
