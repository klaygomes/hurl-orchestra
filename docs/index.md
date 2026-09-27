---
layout: home
markdownStyles: false
title: hurl-orchestra
titleTemplate: Run Hurl files as a dependency graph
---

<HomeHero />

<HomeScore />

<div class="ho vp-doc">

<section class="ho-movement">
<div class="ho-movement__copy">

<p class="ho-movement__number">movement i</p>

## Declare the order. Do not script it.

Each file tells hurl-orchestra what it needs in `deps`. You do not write a shell script that calls Hurl in the correct sequence. You also do not copy a login request into each file.

</div>
<div class="ho-movement__code">

<<< @/snippets/getting-started/profile.hurl{hurl}

</div>
</section>

<section class="ho-movement">
<div class="ho-movement__copy">

<p class="ho-movement__number">movement ii</p>

## Captures go to the files that need them.

A file lists its captures in `outputs`. Each dependent file gets them with the node ID as a prefix, for example `auth_token`. Two files can capture a `token` without a collision.

</div>
<div class="ho-movement__code">

<<< @/snippets/getting-started/auth.hurl{hurl}

</div>
</section>

<section class="ho-movement">
<div class="ho-movement__copy">

<p class="ho-movement__number">movement iii</p>

## Name the flaky failures that you know.

A shared test database can reach its connection limit. Declare that signature in `known_failures`. The run stays green, the report shows the failure, and the tolerance stops on its `until` date.

</div>
<div class="ho-movement__code">

<<< @/snippets/known-failures/create_order.hurl{hurl}

</div>
</section>

<section class="ho-movement">
<div class="ho-movement__copy">

<p class="ho-movement__number">movement iv</p>

## Wait when the server asks you to wait.

A `retry` policy runs the node again after an exponential backoff with jitter. It obeys `Retry-After`, and it retries only the failures that you list in `when`.

</div>
<div class="ho-movement__code">

<<< @/snippets/retry/create_order.hurl{hurl}

</div>
</section>

<section class="ho-movement">
<div class="ho-movement__copy">

<p class="ho-movement__number">movement v</p>

## Let your agent write the next test.

AI first means that each part is easy for a coding agent to read and to check. The files are plain text. The plan is JSON. Each result is a CTRF test with the assertion and the actual value. There is no model inside hurl-orchestra, and there is nothing to configure.

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

## Ready for CI, and for review

Each run writes a zip file with the Hurl JSON reports. Add `--report-ctrf` to show each request as a test in the GitHub job summary, where you and your agent read the same result.

<a class="hh__button hh__button--brand" href="/hurl-orchestra/how-to/report-in-github-actions">Report in GitHub Actions</a>

</section>

</div>
