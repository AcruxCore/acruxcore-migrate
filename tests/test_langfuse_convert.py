"""Conversion tests. Fixtures are real responses from a Langfuse v4.5.0 public API."""
import json
from pathlib import Path

from acruxcore_migrate.langfuse import convert_template, convert_version

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def test_chat_prompt_keeps_messages_and_reports_dropped_config():
    messages, notes = convert_version(load("support-reply-v2.json"))
    assert messages == [
        {"role": "system", "content": "You answer support questions for Acme. Use the customer name."},
        {"role": "user", "content": "{{ customer_name }} asks: {{ question }}"},
    ]
    assert notes == ["config not copied: temperature"]


def test_placeholder_is_dropped_at_its_index_and_reference_is_reported():
    messages, notes = convert_version(load("support-reply-v3.json"))
    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[0]["content"].endswith("Be friendly and brief. Never promise a refund.")
    assert "placeholder 'history' dropped: insert those messages at index 1" in notes
    assert "text of prompt 'tone' v1 copied in; it will not follow later changes" in notes


def test_text_prompt_becomes_one_message_and_hyphen_variable_is_renamed():
    messages, notes = convert_version(load("ticket-summary-v2.json"), text_role="system")
    assert messages == [{
        "role": "system",
        "content": "Summarise this ticket in at most {{ max_words }} words: {{ ticket_text }}",
    }]
    assert notes == ["variable 'max-words' renamed to 'max_words'"]


def test_names_the_template_engine_would_misread_are_renamed():
    renamed = {}
    out = convert_template("Hi {{user.name}} and {{ first name }}, order {{order-id}} {{2fa}}", renamed)
    assert out == "Hi {{ user_name }} and {{ first_name }}, order {{ order_id }} {{ var_2fa }}"
    assert renamed == {"user.name": "user_name", "first name": "first_name", "order-id": "order_id", "2fa": "var_2fa"}


def test_template_syntax_in_plain_text_is_escaped():
    out = convert_template("Show 100{%} done, tag {#vip, keep {{ open", {})
    assert out == 'Show 100{{ "{%" }}} done, tag {{ "{#" }}vip, keep {{ "{{" }} open'


def test_plain_json_braces_are_left_alone():
    assert convert_template('Return {"a": {"b": 1}} for {{name}}', {}) == 'Return {"a": {"b": 1}} for {{ name }}'
