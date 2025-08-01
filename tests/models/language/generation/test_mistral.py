# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
import copy
import json

import pytest

from vllm.entrypoints.openai.tool_parsers.mistral_tool_parser import (
    MistralToolCall, MistralToolParser)
from vllm.sampling_params import SamplingParams
from vllm.transformers_utils.tokenizer import MistralTokenizer

from ...utils import check_logprobs_close

MODELS = [
    "mistralai/Mistral-7B-Instruct-v0.3",
]

MISTRAL_FORMAT_MODELS = [
    "mistralai/Mistral-7B-Instruct-v0.3",
    # uses the v3-Tekken tokenizer
    "mistralai/Ministral-8B-Instruct-2410",
    # Mistral-Nemo is to big for CI, but passes locally
    # "mistralai/Mistral-Nemo-Instruct-2407"
]

SAMPLING_PARAMS = SamplingParams(max_tokens=512, temperature=0.0, logprobs=5)
SYMBOLIC_LANG_PROMPTS = [
    "勇敢な船乗りについての詩を書く",  # japanese
    "寫一首關於勇敢的水手的詩",  # chinese
    "ပုံပြင်လေးပြောပြပါ်:\n",  # burmese
    "Repeat the phrase 'URGENCY🌶️':\nURGENCY🌶️\nURGENCY🌶️\n",  # see https://github.com/vllm-project/vllm/pull/9625
]

# for function calling
TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_current_weather",
        "description": "Get the current weather in a given location",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type":
                    "string",
                    "description":
                    "The city to find the weather for, e.g. 'San Francisco'"
                },
                "state": {
                    "type":
                    "string",
                    "description":
                    "the two-letter abbreviation for the state that the city is"
                    " in, e.g. 'CA' which would mean 'California'"
                },
                "unit": {
                    "type": "string",
                    "description": "The unit to fetch the temperature in",
                    "enum": ["celsius", "fahrenheit"]
                }
            },
            "required": ["city", "state", "unit"]
        }
    },
}, {
    "type": "function",
    "function": {
        "name": "rewrite",
        "description": "Rewrites text",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The input text to rewrite."
                }
            }
        }
    }
}]
MSGS = [
    {
        "role": "system",
        "content": "You are an assistant."
    },
    {
        "role":
        "user",
        "content":
        "Could you please rewrite the below article? \n\n My English needs improvving, maybe I make errors."  # noqa
    },
    {
        "role":
        "assistant",
        "content":
        "",
        "tool_calls": [{
            "id": "bbc5b7ede",
            "type": "function",
            "function": {
                "name":
                "rewrite",
                "arguments":
                '{\"text\":\"My English needs improvving, maybe I make errors.\"}'  # noqa
            }
        }]
    },
    {
        "role": "tool",
        "content":
        "{\"action\":\"rewrite\",\"outcome\":\"My English needs improving, maybe I make errors.\"}",  # noqa
        "tool_call_id": "bbc5b7ede",
        "name": "rewrite"
    },
    {
        "role": "assistant",
        "content": "---\n\nMy English needs improving, maybe I make errors"
    },
    {
        "role":
        "user",
        "content": ("Can you tell me what the temperate"
                    " will be in Dallas, in fahrenheit?")
    }
]

SAMPLE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string"
        },
        "age": {
            "type": "integer"
        },
        "skills": {
            "type": "array",
            "items": {
                "type": "string",
                "maxLength": 10
            },
            "minItems": 3
        },
        "work_history": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string"
                    },
                    "duration": {
                        "type": "number"
                    },
                    "position": {
                        "type": "string"
                    }
                },
                "required": ["company", "position"]
            }
        }
    },
    "required": ["name", "age", "skills", "work_history"]
}


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("dtype", ["bfloat16"])
@pytest.mark.parametrize("max_tokens", [64])
@pytest.mark.parametrize("num_logprobs", [5])
def test_models(hf_runner, vllm_runner, example_prompts, model: str,
                dtype: str, max_tokens: int, num_logprobs: int) -> None:
    # TODO(sang): Sliding window should be tested separately.
    with hf_runner(model, dtype=dtype) as hf_model:
        hf_outputs = hf_model.generate_greedy_logprobs_limit(
            example_prompts, max_tokens, num_logprobs)

    with vllm_runner(model, dtype=dtype,
                     tokenizer_mode="mistral") as vllm_model:
        vllm_outputs = vllm_model.generate_greedy_logprobs(
            example_prompts, max_tokens, num_logprobs)

    check_logprobs_close(
        outputs_0_lst=hf_outputs,
        outputs_1_lst=vllm_outputs,
        name_0="hf",
        name_1="vllm",
    )


@pytest.mark.parametrize("model", MISTRAL_FORMAT_MODELS)
@pytest.mark.parametrize("dtype", ["bfloat16"])
@pytest.mark.parametrize("max_tokens", [64])
@pytest.mark.parametrize("num_logprobs", [5])
def test_mistral_format(vllm_runner, example_prompts, model: str, dtype: str,
                        max_tokens: int, num_logprobs: int) -> None:
    with vllm_runner(
            model,
            dtype=dtype,
            tokenizer_mode="mistral",
            load_format="mistral",
            config_format="mistral",
    ) as mistral_format_model:
        mistral_format_outputs = mistral_format_model.generate_greedy_logprobs(
            example_prompts, max_tokens, num_logprobs)

    with vllm_runner(
            model,
            dtype=dtype,
            tokenizer_mode="auto",
            load_format="safetensors",
            config_format="hf",
    ) as hf_format_model:
        hf_format_outputs = hf_format_model.generate_greedy_logprobs(
            example_prompts, max_tokens, num_logprobs)

    check_logprobs_close(
        outputs_0_lst=hf_format_outputs,
        outputs_1_lst=mistral_format_outputs,
        name_0="hf",
        name_1="mistral",
    )


@pytest.mark.parametrize("model", MISTRAL_FORMAT_MODELS)
@pytest.mark.parametrize("dtype", ["bfloat16"])
def test_mistral_symbolic_languages(vllm_runner, model: str,
                                    dtype: str) -> None:
    with vllm_runner(model,
                     dtype=dtype,
                     max_model_len=8192,
                     tokenizer_mode="mistral",
                     config_format="mistral",
                     load_format="mistral") as vllm_model:
        for prompt in SYMBOLIC_LANG_PROMPTS:
            msg = {"role": "user", "content": prompt}
            outputs = vllm_model.llm.chat([msg],
                                          sampling_params=SAMPLING_PARAMS)
            assert "�" not in outputs[0].outputs[0].text.strip()


@pytest.mark.parametrize("model", MISTRAL_FORMAT_MODELS)
@pytest.mark.parametrize("dtype", ["bfloat16"])
def test_mistral_function_calling(vllm_runner, model: str, dtype: str) -> None:
    with vllm_runner(model,
                     dtype=dtype,
                     tokenizer_mode="mistral",
                     config_format="mistral",
                     load_format="mistral") as vllm_model:

        msgs = copy.deepcopy(MSGS)
        outputs = vllm_model.llm.chat(msgs,
                                      tools=TOOLS,
                                      sampling_params=SAMPLING_PARAMS)

        tokenizer = vllm_model.llm.get_tokenizer()
        tool_parser = MistralToolParser(tokenizer)

        model_output = outputs[0].outputs[0].text.strip()
        assert model_output.startswith(tool_parser.bot_token), model_output
        parsed_message = tool_parser.extract_tool_calls(model_output, None)

        assert parsed_message.tools_called

        assert MistralToolCall.is_valid_id(parsed_message.tool_calls[0].id)
        assert parsed_message.tool_calls[
            0].function.name == "get_current_weather"
        assert parsed_message.tool_calls[
            0].function.arguments == '{"city": "Dallas", "state": "TX", "unit": "fahrenheit"}'  # noqa
        assert parsed_message.content is None


def test_mistral_function_call_nested_json():
    """Ensure that the function-name regex captures the entire outer-most
    JSON block, including nested braces."""

    # Create a minimal stub tokenizer that provides the few attributes the
    # parser accesses (`version` and `get_vocab`).
    class _StubMistralTokenizer(MistralTokenizer):
        version = 11  # Satisfy the version check

        def __init__(self):
            pass

        @staticmethod
        def get_vocab():
            # Provide the special TOOL_CALLS token expected by the parser.
            return {"[TOOL_CALLS]": 0}

    tokenizer = _StubMistralTokenizer()
    parser = MistralToolParser(tokenizer)

    # Craft a model output featuring nested JSON inside the arguments.
    args_dict = {
        "city": "Dallas",
        "state": "TX",
        "unit": "fahrenheit",
        "sub_dict": {
            "foo": "bar",
            "inner": {
                "x": 1,
                "y": 2
            }
        },
    }

    model_output = (
        f"{parser.bot_token}get_current_weather{json.dumps(args_dict)}")

    parsed = parser.extract_tool_calls(model_output, None)

    # Assertions: the tool call is detected and the full nested JSON is parsed
    # without truncation.
    assert parsed.tools_called

    assert MistralToolCall.is_valid_id(parsed.tool_calls[0].id)
    assert parsed.tool_calls[0].function.name == "get_current_weather"
    assert json.loads(parsed.tool_calls[0].function.arguments) == args_dict
    # No additional content outside the tool call should be returned.
    assert parsed.content is None
