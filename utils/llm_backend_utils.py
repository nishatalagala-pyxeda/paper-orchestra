# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import mimetypes
from pathlib import Path

from google.genai import types
from utils.model_config import is_openai_model
from utils.gemini_utils import call_gemini_with_contents, parse_gemini_json_results
from utils.openai_utils import call_openai_responses, parse_openai_json_results


def identity_parse(response):
    return response


def get_llm_parser(model_name, return_json=True):
    if not return_json:
        return identity_parse
    return parse_openai_json_results if is_openai_model(model_name) else parse_gemini_json_results


def _openai_parts(contents):
    """Convert the pipeline's text and inline attachments to Responses input."""
    parts = []
    for item in contents if isinstance(contents, list) else [contents]:
        if isinstance(item, str):
            parts.append({"type": "input_text", "text": item})
        elif isinstance(item, types.Content):
            parts.extend(_openai_parts(item.parts or []))
        elif isinstance(item, types.Part):
            if item.text is not None:
                parts.append({"type": "input_text", "text": item.text})
            elif item.inline_data:
                mime = item.inline_data.mime_type
                encoded = base64.b64encode(item.inline_data.data).decode("ascii")
                data_url = f"data:{mime};base64,{encoded}"
                if mime == "application/pdf":
                    parts.append({"type": "input_file", "filename": "paper.pdf", "file_data": data_url})
                elif mime.startswith("image/"):
                    parts.append({"type": "input_image", "image_url": data_url})
                else:
                    raise ValueError(f"Unsupported inline attachment: {mime}")
            else:
                raise ValueError("Unsupported content part; expected text, image or PDF")
        else:
            raise TypeError(f"Unsupported content: {type(item).__name__}")
    return parts


def call_llm_with_contents(contents, model_name, generation_configs=None,
                           check_parsed_response_not_none=True, return_json=True,
                           result_parsing_func=None):
    parser = result_parsing_func or get_llm_parser(model_name, return_json)
    configs = dict(generation_configs or {})
    if not is_openai_model(model_name):
        return call_gemini_with_contents(
            contents=contents, model_name=model_name, generation_configs=configs,
            result_parsing_func=parser,
            check_parsed_response_not_none=check_parsed_response_not_none)

    instructions = configs.pop("system_instruction", None)
    # Sampling controls from the Gemini prompts are unsupported by reasoning models.
    configs.pop("temperature", None)
    tools = []
    for tool in configs.pop("tools", []):
        if isinstance(tool, types.Tool) and tool.google_search is not None:
            tools.append({"type": "web_search"})
        elif isinstance(tool, dict) and tool.get("type") == "web_search":
            tools.append(dict(tool))
        else:
            raise ValueError("Only web search is supported by this adapter")
    return call_openai_responses(
        content=_openai_parts(contents), model_name=model_name,
        instructions=instructions, tools=tools, generation_configs=configs,
        result_parsing_func=parser,
        check_parsed_response_not_none=check_parsed_response_not_none)


def call_llm_with_text_prompt(prompt, model_name, generation_configs=None,
                              check_parsed_response_not_none=True, return_json=True,
                              result_parsing_func=None):
    return call_llm_with_contents(
        [prompt], model_name, generation_configs, check_parsed_response_not_none,
        return_json, result_parsing_func)


def call_llm_with_images(prompt, images, model_name, generation_configs=None,
                         check_parsed_response_not_none=True, return_json=True,
                         result_parsing_func=None):
    contents = [prompt]
    for image_path in images:
        mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
        contents.append(types.Part.from_bytes(data=Path(image_path).read_bytes(), mime_type=mime))
    return call_llm_with_contents(
        contents, model_name, generation_configs, check_parsed_response_not_none,
        return_json, result_parsing_func)


def call_llm_with_pdf(pdf_path, prompt, model_name, system_instruction=None,
                      temperature=0.7, check_parsed_response_not_none=True,
                      return_json=True, result_parsing_func=None):
    return call_llm_with_contents(
        [types.Part.from_bytes(data=Path(pdf_path).read_bytes(), mime_type="application/pdf"), prompt],
        model_name, {"system_instruction": system_instruction, "temperature": temperature},
        check_parsed_response_not_none, return_json, result_parsing_func)
