# Report in GitHub Actions

Use this procedure to show each Hurl request as a test in the summary of a GitHub Actions job.

## Procedure

1. Add a workflow file, for example `.github/workflows/api-tests.yml`:

   <<< @/snippets/ci/tests.yml{yaml}

2. Keep `if: always()` on the report step. Without it, the step does not run after a failure.
3. Set `report-path` to the directory that you gave to hurl-orchestra and the file name. A relative `--report-ctrf` path goes into that directory.
4. Push the change and open the summary of the workflow run.

## Result

The [GitHub test reporter](https://github.com/ctrf-io/github-test-reporter) shows the passed, failed and skipped tests. A known failure shows as a flaky test with its name as a tag.

## Keep the Hurl reports

To keep the zip file, add a step after the tests:

```yaml
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: hurl-reports
    path: tests/report.zip
```
