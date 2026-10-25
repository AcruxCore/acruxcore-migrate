"""Copy prompts from a Langfuse project into an AcruxCore team.

For each prompt: create it in AcruxCore, commit every Langfuse version in the same
order, then point an AcruxCore alias at the version each Langfuse label was on.

What changes on the way, and why:

- A variable name AcruxCore's template engine cannot read as one name
  (`{{order-id}}`, `{{user.name}}`, `{{first name}}`) becomes snake_case
  (`{{ order_id }}`). Left as it was, `{{order-id}}` would mean "order minus id".
- `{%`, `{#` and an unmatched `{{` in plain text are escaped, because AcruxCore
  templates read them as template syntax. They still render as the same characters.
- A text prompt becomes one message, with the role chosen by the caller.
- A chat `placeholder` message is dropped; the caller's code inserts those messages
  after rendering, at the index this module reports.
- Prompt references (`@@@langfusePrompt:...@@@`) arrive resolved, so the
  referenced text is copied in.
- `config.model` is bound as the version's default model when the AcruxCore gateway
  has that model. Other config keys are not copied.

A prompt whose name already exists in AcruxCore is skipped, never merged.
"""
import re

import httpx
from acruxcore import AcruxCore, AcruxCoreError

# A name the template engine reads as one variable: a letter or _ first, then letters, digits, _.
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class LangfuseSource:
    """Reads prompts over the Langfuse public REST API (v2 prompts endpoints)."""

    def __init__(self, host, public_key, secret_key):
        self._client = httpx.Client(base_url=host.rstrip("/"), auth=(public_key, secret_key), timeout=30)
        self.host = host.rstrip("/")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()

    def prompt_names(self):
        """Every prompt name in the project, across all pages."""
        names, page = [], 1
        while True:
            body = self._get("/api/public/v2/prompts", page=page, limit=50)
            names += [p["name"] for p in body["data"]]
            if page >= body["meta"]["totalPages"]:
                return names
            page += 1

    def versions(self, name):
        """Every version of one prompt, oldest first, with references resolved."""
        listing = self._get("/api/public/v2/prompts", name=name, limit=50)
        numbers = sorted(next(p["versions"] for p in listing["data"] if p["name"] == name))
        return [self._get(f"/api/public/v2/prompts/{name}", version=n) for n in numbers]

    def _get(self, path, **params):
        res = self._client.get(path, params=params)
        res.raise_for_status()
        return res.json()


# --- Conversion: pure functions, no I/O --------------------------------------


def snake_case(name):
    """Turn a Langfuse variable name into one AcruxCore reads as a single variable."""
    name = re.sub(r"\W+", "_", name).strip("_") or "var"
    return f"var_{name}" if name[0].isdigit() else name


def escape_text(text):
    """Make plain text render as itself: `{{`, `{%` and `{#` are template syntax."""
    return re.sub(r"\{([{%#])", lambda m: '{{ "{' + m.group(1) + '" }}', text)


def convert_template(content, renamed):
    """Rewrite one Langfuse template for AcruxCore.

    Follows Langfuse's own parsing: everything between `{{` and the next `}}` is one
    variable name, and everything else is plain text. `renamed` collects old -> new
    variable names.
    """
    out, i = [], 0
    while True:
        start = content.find("{{", i)
        end = content.find("}}", start) if start != -1 else -1
        if start == -1 or end == -1:
            out.append(escape_text(content[i:]))
            return "".join(out)
        out.append(escape_text(content[i:start]))
        name = content[start + 2 : end].strip()
        if not IDENTIFIER.match(name):
            renamed[name] = snake_case(name)
            name = renamed[name]
        out.append("{{ " + name + " }}")
        i = end + 2


def convert_version(version, text_role="user"):
    """Turn one Langfuse version into AcruxCore messages, plus notes on what changed."""
    renamed, notes = {}, []
    if version["type"] == "text":
        messages = [{"role": text_role, "content": convert_template(version["prompt"], renamed)}]
    else:
        messages = []
        for item in version["prompt"]:
            if item.get("type") == "placeholder":
                notes.append(f"placeholder '{item['name']}' dropped: insert those messages at index {len(messages)}")
                continue
            messages.append({"role": item["role"], "content": convert_template(item["content"], renamed)})
    for old, new in renamed.items():
        notes.append(f"variable '{old}' renamed to '{new}'")
    for deps in ((version.get("resolutionGraph") or {}).get("dependencies") or {}).values():
        for dep in deps:
            notes.append(f"text of prompt '{dep['name']}' v{dep['version']} copied in; it will not follow later changes")
    dropped = sorted(k for k in version.get("config") or {} if k != "model")
    if dropped:
        notes.append(f"config not copied: {', '.join(dropped)}")
    return messages, notes


# --- AcruxCore side ----------------------------------------------------------


async def _prompt_exists(hub, name):
    found = await hub.prompts.list(search=name, limit=100)
    return any(p.name == name for p in found.data)


async def _commit(hub, prompt_id, messages, model, notes):
    """Commit one version, binding `model` only if the gateway knows it."""
    if model:
        try:
            return await hub.prompts.commit_version(prompt_id, messages, model=model)
        except AcruxCoreError as err:
            if "not registered" not in str(err):
                raise
            notes.append(f"model '{model}' is not registered in your gateway, so the version has no default model")
    return await hub.prompts.commit_version(prompt_id, messages)


async def migrate_prompt(hub, source, name, text_role, dry_run):
    """Migrate one prompt and print what happened."""
    versions = source.versions(name)
    print(f"\n{name}: {len(versions)} version(s) in Langfuse")

    if not dry_run and await _prompt_exists(hub, name):
        print("  skipped: a prompt with this name already exists in AcruxCore")
        return

    prompt_id = None if dry_run else (await hub.prompts.create(name)).id
    labels = {}  # label -> AcruxCore version number
    for number, version in enumerate(versions, start=1):
        messages, notes = convert_version(version, text_role)
        model = (version.get("config") or {}).get("model")
        if not dry_run:
            committed = await _commit(hub, prompt_id, messages, model, notes)
            number = committed.version_number
        print(f"  Langfuse v{version['version']} -> AcruxCore v{number}")
        for note in notes:
            print(f"    - {note}")
        for label in version["labels"]:
            labels[label] = number

    for label, number in sorted(labels.items()):
        if not dry_run:
            await hub.prompts.promote_alias(prompt_id, label, number)
        print(f"  alias '{label}' -> v{number}")
    # AcruxCore creates production and staging on the first commit. Name any
    # that Langfuse had no label for, so the reader knows they point at v1.
    for alias in ("production", "staging"):
        if alias not in labels:
            print(f"  alias '{alias}' -> v1 (created by AcruxCore; Langfuse had no '{alias}' label)")


async def migrate_all(source, names, text_role="user", dry_run=False):
    """Migrate `names`, or every prompt in the project when `names` is empty."""
    names = names or source.prompt_names()
    print(f"{len(names)} prompt(s) in Langfuse at {source.host}" + (" (dry run)" if dry_run else ""))
    async with AcruxCore() as hub:
        for name in names:
            await migrate_prompt(hub, source, name, text_role, dry_run)
