# Run specific files

Use this procedure to run one file and the files that it needs. The other files in the directory do not run.

## Procedure

1. Give the path of the file to hurl-orchestra:

   ```bash
   hurl-orchestra tests/checkout.hurl
   ```

2. Read the first line of the output. It shows the dependencies that hurl-orchestra added:

   ```text
   Resolved dependencies: add_item, auth, create_cart
   ```

3. To run more than one file, give all paths:

   ```bash
   hurl-orchestra tests/checkout.hurl tests/catalog.hurl
   ```

## Result

hurl-orchestra loads all `.hurl` files in the directory of each file that you gave. It runs the files that you gave and all of their dependencies. It does not run the other files.

## Run only the listed files

Add `--no-deps` to stop the resolution. Then give each dependency on the command line:

```bash
hurl-orchestra --no-deps tests/auth.hurl tests/profile.hurl
```

If a dependency is not on the command line, the run stops before it calls Hurl.

## Read the .env file next to the files

When you give files, hurl-orchestra reads `.env` from the current directory, not from the directory of the files. To read a different file, add `--env-file`:

```bash
hurl-orchestra --env-file tests/.env tests/checkout.hurl
```

If you forget it, the run shows a `NOTE` line with this command. hurl-orchestra also writes `report.zip` to the current directory.
