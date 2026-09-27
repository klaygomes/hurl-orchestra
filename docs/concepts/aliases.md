# Aliases

An alias runs one Hurl file again as a different node. Each alias has its own ID, so each alias has its own outputs.

## Syntax

In `deps`, write the template ID, a colon and the new ID:

<<< @/snippets/aliases/isolation.hurl{hurl}

The template is the file with the ID `sign_up`:

<<< @/snippets/aliases/sign_up.hurl{hurl}

hurl-orchestra runs `sign_up.hurl` two times, as `alice` and as `bob`. The `isolation` node gets `alice_token`, `alice_user_id`, `bob_token` and `bob_user_id`.

## Inputs

Each alias runs the same file with the same variables. To get two different results, use a value that changes on each call, for example the Hurl function <code v-pre>{{newUuid}}</code>. In the example, each alias makes a new user.

## The template node

The template file is also a node with its own ID. When you run a directory, the template runs one time as itself. The aliases also run.

```bash
hurl-orchestra --dry-run ./tests
```

```text
Plan: 4 node(s)
  wave 1: alice, bob, sign_up
  wave 2: isolation
```

When you run specific files, hurl-orchestra adds only the aliases that the files need.

## Dependencies of a template

If the template has `deps`, each alias gets the same `deps`. If the template `deps` contain aliases, hurl-orchestra makes those aliases too.
