---
layout: home
markdownStyles: false
title: hurl-orchestra
titleTemplate: Test your API from login to checkout
---

<HomeHero />

<HomeScore />

<div class="ho vp-doc">

<section class="ho-movement">
<div class="ho-movement__copy">

<p class="ho-movement__number">movement i</p>

## Say what each step needs. The order follows.

Each file lists the steps that must pass first in `deps`. hurl-orchestra finds the correct order. You do not write a script for it, and you do not copy the login request into each file.

</div>
<div class="ho-movement__code">

<<< @/snippets/getting-started/profile.hurl{hurl}

</div>
</section>

<section class="ho-movement">
<div class="ho-movement__copy">

<p class="ho-movement__number">movement ii</p>

## Share a value, like a login token, between steps.

The login step saves the token from the response and lists it in `outputs`. Each later step reads it as `auth_token`: the name of the step, then the name of the value.

</div>
<div class="ho-movement__code">

<<< @/snippets/getting-started/auth.hurl{hurl}

</div>
</section>

<section class="ho-movement">
<div class="ho-movement__copy">

<p class="ho-movement__number">movement iii</p>

## Mark the failures that you already know about.

Sometimes a test fails for a known reason, for example a busy shared database. Describe that failure in `known_failures`. The run still passes, the report still shows the failure, and the exception ends on its `until` date.

</div>
<div class="ho-movement__code">

<<< @/snippets/known-failures/create_order.hurl{hurl}

</div>
</section>

<section class="ho-movement">
<div class="ho-movement__copy">

<p class="ho-movement__number">movement iv</p>

## Try again when the server is busy.

A `retry` block runs the step again after a short wait, and each wait is longer than the last one. It obeys the `Retry-After` header of the server, and it retries only the failures that you list in `when`.

</div>
<div class="ho-movement__code">

<<< @/snippets/retry/create_order.hurl{hurl}

</div>
</section>

<section class="ho-movement">
<div class="ho-movement__copy">

<p class="ho-movement__number">movement v</p>

## Let your AI assistant write the next test.

AI first means that an AI assistant, such as Claude Code, can read and check each part. The tests are plain text. The plan and the results are JSON, and each failure shows the expected value and the actual value. There is no AI inside hurl-orchestra, and there is nothing to configure.

[Work with AI agents →](/how-to/work-with-ai-agents)

</div>
<div class="ho-movement__code">

```bash
hurl-orchestra --dry-run --json tests
```

```json
{
  "ok": true,
  "waves": [["auth"], ["create_cart"]],
  "nodes": [
    {
      "id": "create_cart",
      "deps": ["auth"],
      "variables": ["auth_token"]
    }
  ]
}
```

</div>
</section>

<section class="ho-coda">

## Results that you can share

Each run saves a report of each request. On GitHub, each request shows as a test in the summary of the job, so your team and your AI assistant read the same result.

<a class="hh__button hh__button--brand" href="/hurl-orchestra/how-to/report-in-github-actions">Report in GitHub Actions</a>

</section>

</div>
