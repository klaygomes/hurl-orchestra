---
id: search
---
GET {{base_url}}/notes?q=score
HTTP 200
[Asserts]
jsonpath "$.items" count > 0
