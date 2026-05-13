"""Unit tests for the Anthropic provider's OpenAI -> Anthropic message translation.

These cover the regression where tool-result messages with ``role=tool`` hit
the Anthropic API and 400'd with ``Unexpected role 'tool'``. The translator
must rewrite those into a user message containing a ``tool_result`` content
block.
"""
from __future__ import annotations

from app.providers.anthropic import AnthropicProvider


def test_system_messages_are_collapsed_onto_system_field():
    system, msgs = AnthropicProvider._to_anthropic_messages(
        [
            {"role": "system", "content": "you are helpful"},
            {"role": "user", "content": "hi"},
        ]
    )
    assert system == "you are helpful"
    assert msgs == [{"role": "user", "content": "hi"}]


def test_multiple_system_messages_join_with_blank_line():
    system, _msgs = AnthropicProvider._to_anthropic_messages(
        [
            {"role": "system", "content": "rule one"},
            {"role": "system", "content": "rule two"},
            {"role": "user", "content": "hi"},
        ]
    )
    assert system == "rule one\n\nrule two"


def test_tool_role_message_becomes_user_tool_result_block():
    """The exact regression: specialists send role=tool, gateway must rewrite."""
    _system, msgs = AnthropicProvider._to_anthropic_messages(
        [
            {"role": "user", "content": "do you have mice?"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "toolu_abc123",
                        "name": "search_products",
                        "input": {"q": "mice"},
                    }
                ],
            },
            {
                "role": "tool",
                "content": "[]",
                "tool_call_id": "toolu_abc123",
            },
        ]
    )
    # The third message must be rewritten into a user message with a
    # tool_result content block, NOT left as role=tool.
    assert msgs[-1]["role"] == "user"
    blocks = msgs[-1]["content"]
    assert isinstance(blocks, list)
    assert blocks[0]["type"] == "tool_result"
    assert blocks[0]["tool_use_id"] == "toolu_abc123"
    assert blocks[0]["content"] == "[]"
    # And no message in the output has role=tool.
    assert all(m["role"] != "tool" for m in msgs)


def test_assistant_with_tool_calls_expands_to_content_blocks():
    _system, msgs = AnthropicProvider._to_anthropic_messages(
        [
            {"role": "user", "content": "do you have mice?"},
            {
                "role": "assistant",
                "content": "let me check",
                "tool_calls": [
                    {
                        "id": "toolu_abc123",
                        "name": "search_products",
                        "input": {"q": "mice"},
                    }
                ],
            },
        ]
    )
    assistant = msgs[-1]
    assert assistant["role"] == "assistant"
    blocks = assistant["content"]
    assert isinstance(blocks, list)
    # Text block first, then tool_use block.
    assert blocks[0] == {"type": "text", "text": "let me check"}
    assert blocks[1]["type"] == "tool_use"
    assert blocks[1]["id"] == "toolu_abc123"
    assert blocks[1]["name"] == "search_products"
    assert blocks[1]["input"] == {"q": "mice"}


def test_assistant_with_tool_calls_handles_args_alias():
    """Specialists may emit 'args' instead of 'input' — translator should accept either."""
    _system, msgs = AnthropicProvider._to_anthropic_messages(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "toolu_x", "name": "kb_search", "args": {"q": "vpn"}},
                ],
            },
        ]
    )
    assert msgs[-1]["content"][0]["input"] == {"q": "vpn"}


def test_plain_user_and_assistant_pass_through():
    _system, msgs = AnthropicProvider._to_anthropic_messages(
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "bye"},
        ]
    )
    assert msgs == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "bye"},
    ]


def test_full_tool_use_round_trip_shape():
    """End-to-end shape of a 4-message conversation including a tool round-trip."""
    system, msgs = AnthropicProvider._to_anthropic_messages(
        [
            {"role": "system", "content": "you are a shop assistant"},
            {"role": "user", "content": "do you have mice?"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "toolu_1", "name": "search_products", "input": {"q": "mice"}}
                ],
            },
            {
                "role": "tool",
                "content": "{'items': []}",
                "tool_call_id": "toolu_1",
            },
        ]
    )
    assert system == "you are a shop assistant"
    assert len(msgs) == 3
    # 1) user prompt unchanged
    assert msgs[0] == {"role": "user", "content": "do you have mice?"}
    # 2) assistant tool_use block
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"][0]["type"] == "tool_use"
    assert msgs[1]["content"][0]["id"] == "toolu_1"
    # 3) tool result rewritten as user/tool_result
    assert msgs[2]["role"] == "user"
    assert msgs[2]["content"][0]["type"] == "tool_result"
    assert msgs[2]["content"][0]["tool_use_id"] == "toolu_1"


def test_tool_result_missing_id_falls_back_to_unknown():
    _system, msgs = AnthropicProvider._to_anthropic_messages(
        [{"role": "tool", "content": "x"}]
    )
    assert msgs[0]["content"][0]["tool_use_id"] == "toolu_unknown"
