# acruxcore-migrate

`acruxcore-migrate` copies your prompts from Langfuse into
[AcruxCore](https://acruxcore.com), the open-source LLM tracing, gateway and prompt
management platform. Every prompt keeps its versions in the same order, and every
Langfuse label becomes an AcruxCore alias on the same version.

The step-by-step guide, including the change to your app code, is
[Migrate your prompts from Langfuse](https://docs.acruxcore.com/docs/guides/migrate-prompts-from-langfuse).

## Install

```bash
pip install git+https://github.com/AcruxCore/acruxcore-migrate
```

It needs Python 3.9 or newer, and it installs the `acruxcore` SDK with it.

## Run

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://cloud.langfuse.com   # or your self-hosted URL
export ACRUXCORE_API_KEY=acx_sk_...
export ACRUXCORE_BASE_URL=https://api.acruxcore.com/api/v1

acruxcore-migrate langfuse --dry-run    # print the plan, write nothing
acruxcore-migrate langfuse              # migrate every prompt
acruxcore-migrate langfuse support-reply ticket-summary   # migrate only these
```

A run prints each version and alias, and every change you may need to act on:

```text
3 prompt(s) in Langfuse at http://localhost:3050

support-reply: 3 version(s) in Langfuse
  Langfuse v1 -> AcruxCore v1
  Langfuse v2 -> AcruxCore v2
    - config not copied: temperature
    - model 'gpt-4o-mini' is not registered in your gateway, so the version has no default model
  Langfuse v3 -> AcruxCore v3
    - placeholder 'history' dropped: insert those messages at index 1
    - text of prompt 'tone' v1 copied in; it will not follow later changes
    - config not copied: temperature
    - model 'gpt-4o-mini' is not registered in your gateway, so the version has no default model
  alias 'latest' -> v3
  alias 'production' -> v2
  alias 'staging' -> v3

ticket-summary: 2 version(s) in Langfuse
  Langfuse v1 -> AcruxCore v1
  Langfuse v2 -> AcruxCore v2
    - variable 'max-words' renamed to 'max_words'
  alias 'canary' -> v2
  alias 'latest' -> v2
  alias 'production' -> v2
  alias 'staging' -> v1 (created by AcruxCore; Langfuse had no 'staging' label)

tone: 1 version(s) in Langfuse
  Langfuse v1 -> AcruxCore v1
  alias 'latest' -> v1
  alias 'production' -> v1
  alias 'staging' -> v1 (created by AcruxCore; Langfuse had no 'staging' label)
```

## What changes on the way

| In Langfuse | In AcruxCore |
|---|---|
| Version 1, 2, 3 … | Version 1, 2, 3 …, committed in the same order |
| Label | Alias with the same name. `latest` stays where the tool put it and does not follow new commits. |
| Text prompt | One message with the `user` role. Pass `--text-role system` to change it. |
| `{{order-id}}`, `{{user.name}}`, `{{first name}}` | `{{ order_id }}`, `{{ user_name }}`, `{{ first_name }}`. The AcruxCore template engine reads `order-id` as `order` minus `id`. |
| `{%` or `{#` in plain text | Escaped, so the text renders unchanged |
| `placeholder` message | Not stored. Your code inserts those messages after rendering, at the printed index. |
| Prompt reference `@@@langfusePrompt:…@@@` | The referenced text, copied in |
| `config.model` | The version's default model, if your AcruxCore gateway has that model |
| Other `config` keys, tags, commit messages | Not copied |

A prompt whose name already exists in AcruxCore is skipped, not merged, so a second
run copies only the prompts that are missing. If a run stops in the middle of a
prompt, delete the half-copied prompt in AcruxCore before you run the tool again.

The tool moves prompts only. Traces, datasets and scores stay in Langfuse.

## How it was tested

Against a self-hosted Langfuse v4.5.0 and AcruxCore, with Langfuse SDK 5.0.4 and
`acruxcore` 0.19.0. After the migration, Langfuse's `compile()` and AcruxCore's
`render()` returned the same messages for the `production` and `staging` labels of
every prompt above. The unit tests in `tests/` run the conversion on real Langfuse API
responses:

```bash
pip install -e ".[test]"
pytest
```

## License

Apache 2.0, the same as [AcruxCore](https://github.com/AcruxCore/AcruxCore).
