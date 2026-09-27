---
id: create_order
retry:
  attempts: 4
  backoff_ms: 500
  max_backoff_ms: 20000
  multiplier: 2
  jitter: full
  when:
    - status: 429
    - status: 503
    - stderr: 'Connection refused'
---
POST {{base_url}}/orders
HTTP 201
