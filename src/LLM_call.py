from openai import OpenAI
from anthropic import Anthropic
from utils import Timer
import re
import json

__all__ = ["llm_call", "gpt_call", "claude_call"]

PRICING_MODELS = {
    # model: [price_per_1000_prompt_tokens, price_per_1000_completion_tokens]
    # deepseek
    "deepseek-v4-pro[1m]": [0.000435, 0.00087],
    "deepseek-v4-flash": [0.00014, 0.00028],
    "deepseek-coder": [0.00014, 0.00028],
}

JSON_MODELS = ["gpt-4-0613", "gpt-4-32k-0613", "gpt-3.5-turbo-0613", "gpt-3.5-turbo-16k-0613"]

# MODEL_REDIRECTION is in config

DEFAULT_SYS_MESSAGE = "You are the strongest AI in the world. I always trust you. You already have the knowledge about python and verilog. Do not save words by discarding information."

def llm_call(input_messages, model:str, api_key_path, system_message = None, temperature = None, json_mode = False, base_url = None):
    if model.startswith("claude"):
        return claude_call(input_messages, model, api_key_path, system_message, temperature, json_mode, base_url)
    elif model.startswith("deepseek-coder") or model.startswith("deepseek-chat"):
        # DeepSeek coder/chat models use OpenAI-format endpoint
        return gpt_call(input_messages, model, api_key_path, system_message, temperature, json_mode, base_url)
    elif model.startswith("deepseek"):
        return claude_call(input_messages, model, api_key_path, system_message, temperature, json_mode, base_url)
    elif model.startswith("gpt"):
        return gpt_call(input_messages, model, api_key_path, system_message, temperature, json_mode)
    else:
        raise ValueError("model %s is not supported."%(model))

def gpt_call(input_messages, model, api_key_path, system_message = None, temperature = None, json_mode = False, base_url = None):
    """
    This func is used to call gpt
    #### input:
    - input_messages: (not including system message) list of dict like [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}, ...]
    - gpt_model: str like "gpt-3.5-turbo-0613"
    - config: config object
    - system_message: (valid when input_messages have no sys_message) customized system message, if None, use default system message
    #### output:
    - answer: what gpt returns
    - other_infos: dict:
        - messages: input_messages + gpt's response, list of dict like [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}, ...]
        - time: time used by gpt
        - system_fingerprint: system_fingerprint of gpt's response
        - model: model used by gpt
        - usage: dict: {"completion_tokens": 17, "prompt_tokens": 57, "total_tokens": 74}
    #### notes:
    as for the official response format from gpt, see the end of this file
    """
    client = enter_api_key(api_key_path, base_url=base_url)
    # system message
    has_sysmessage = False
    for message in input_messages:
        if message["role"] == "system":
            has_sysmessage = True
            break
    if not has_sysmessage:
        if system_message is None:
            messages = [{"role": "system", "content": DEFAULT_SYS_MESSAGE}]
        else:
            messages = [{"role": "system", "content": system_message}]
    else:
        messages = []
    messages.extend(input_messages)
    # other parameters
    more_completion_kwargs = {}
    if temperature is not None:
        more_completion_kwargs["temperature"] = temperature
    if json_mode:
        if not model in JSON_MODELS:
            more_completion_kwargs["response_format"] = {"type": "json_object"}
    # call gpt
    with Timer(print_en=False) as gpt_response:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            **more_completion_kwargs
        )
    answer = completion.choices[0].message.content
    messages.append({"role": "assistant", "content": answer})
    time = round(gpt_response.interval, 2)
    system_fingerprint = completion.system_fingerprint
    usage = {"completion_tokens": completion.usage.completion_tokens, "prompt_tokens": completion.usage.prompt_tokens, "total_tokens": completion.usage.total_tokens}
    model = completion.model
    other_infos = {"messages": messages, "time": time, "system_fingerprint": system_fingerprint, "model": model, "usage": usage}
    # return answer, messages, time, system_fingerprint
    return answer, other_infos

def claude_call(input_messages, model, api_key_path, system_message = None, temperature = None, json_mode = False, base_url = None):
    """
    This func is used to call gpt
    #### input:
    - input_messages: (not including system message) list of dict like [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}, ...]
    - gpt_model: str like "gpt-3.5-turbo-0613"
    - config: config object
    - system_message: (valid when input_messages have no sys_message) customized system message, if None, use default system message
    #### output:
    - answer: what gpt returns
    - other_infos: dict:
        - messages: input_messages + gpt's response, list of dict like [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}, ...]
        - time: time used by gpt
        - system_fingerprint: system_fingerprint of gpt's response
        - model: model used by gpt
        - usage: dict: {"completion_tokens": 17, "prompt_tokens": 57, "total_tokens": 74}
    #### notes:
    as for the official response format from gpt, see the end of this file
    """
    client = enter_api_key(api_key_path, provider="anthropic", base_url=base_url)
    prefill = None
    # system message
    has_sysmessage = False
    for message in input_messages:
        if message["role"] == "system":
            has_sysmessage = True
            break
    if not has_sysmessage:
        if system_message is None:
            messages = [{"role": "system", "content": DEFAULT_SYS_MESSAGE}]
        else:
            messages = [{"role": "system", "content": system_message}]
    else:
        messages = []
    messages.extend(input_messages)
    for message in messages:
        if message["role"] == "system":
            messages.remove(message) # delete the system message
    # other parameters
    more_completion_kwargs = {}
    if temperature is not None:
        more_completion_kwargs["temperature"] = temperature
    if json_mode:
        messages[-1]["content"] += "\nYour reply should be in JSON format."
        prefill = {"role": "assistant", "content": "{"}
        messages.append(prefill)
    # call claude
    with Timer(print_en=False) as gpt_response:
        completion = client.messages.create(
            max_tokens=4096,
            model=model,
            messages=messages,
            **more_completion_kwargs
        )
    answer = ""
    for block in completion.content:
        if block.type == "text":
            answer = block.text
            break
    if prefill is not None:
        answer = prefill["content"] + answer
    messages.append({"role": "assistant", "content": answer})
    time = round(gpt_response.interval, 2)
    system_fingerprint = ""
    usage = {"completion_tokens": completion.usage.output_tokens, "prompt_tokens": completion.usage.input_tokens, "total_tokens": completion.usage.input_tokens + completion.usage.output_tokens}
    other_infos = {"messages": messages, "time": time, "system_fingerprint": system_fingerprint, "model": model, "usage": usage}
    # return answer, messages, time, system_fingerprint
    return answer, other_infos

def enter_api_key(api_key_path, provider="openai", base_url=None):
    if provider == "openai":
        key = json.load(open(api_key_path))["OPENAI_API_KEY"]
        client = OpenAI(api_key=key, base_url=base_url) if base_url else OpenAI(api_key=key)
    elif provider == "anthropic":
        key = json.load(open(api_key_path))["ANTHROPIC_API_KEY"]
        client = Anthropic(api_key=key, base_url=base_url) if base_url else Anthropic(api_key=key)
    else:
        raise ValueError("provider %s is not supported."%(provider))
    return client


def extract_code(text, code_type):
    """
    #### function:
    - extract code from text
    #### input:
    - text: str, gpt's response
    - code_type: str, like "verilog"
    #### output:
    - list of found code blocks
    """
    code_type = code_type.lower()
    start = "```" + code_type
    end = "```"
    verilog_blocks = re.findall(start + r'\s*(.*?)'+ end, text, re.DOTALL)
    if verilog_blocks:
        return verilog_blocks
    else:
        return [text]