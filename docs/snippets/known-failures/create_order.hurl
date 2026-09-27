---
id: create_order
outputs: [order_id]
known_failures:
  - name: db_pool_exhausted
    reason: The shared test database is at its connection limit
    until: 2026-12-31
    link: https://example.com/runbooks/test-db-pool
    status: 500
    header:
      name: X-Error-Code
      pattern: '^ERR-DB-\d+$'
---
POST {{base_url}}/orders
HTTP 200
[Captures]
order_id: jsonpath "$.id"
