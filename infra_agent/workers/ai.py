import json
import logging
from typing import Any, List, Tuple

from openai import AsyncOpenAI, BadRequestError, RateLimitError
from ratelimit import limits, sleep_and_retry

from infra_agent.models.ai import OpenAIMessage, OpenAITool, OpenAIToolCall
from infra_agent.models.generic import PromptSummary, PromptToolError
from infra_agent.providers.router import router
from infra_agent.settings import settings

logger = logging.getLogger(__name__)


async def _load_config() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_API_URL)


@sleep_and_retry
@limits(calls=settings.OPENAI_API_RATE_LIMIT_REQUESTS, period=settings.OPENAI_API_RATE_LIMIT_TIMEWINDOW)
def __avoid_ratelimits():
    pass


async def __gpt_query(
    messages: List[OpenAIMessage],
    model: str = "gemini-2.5-flash",
    tools: List[OpenAITool] = [],
) -> OpenAIMessage | None:
    client = await _load_config()
    completions_create_kwargs = {
        "model": model,
        "messages": [message.model_dump(exclude_none=True) for message in messages],
    }
    completions_create_kwargs["tools"] = [tool.model_dump(exclude_none=True, exclude={"handler"}) for tool in tools]
    completions_create_kwargs["tool_choice"] = "auto"
    raw_ai_message = None
    try:
        __avoid_ratelimits()
        response = await client.chat.completions.create(**completions_create_kwargs)
        raw_ai_message = response.choices[0].message.to_dict()
    except RateLimitError as exc:
        logger.error(exc)
    except BadRequestError as exc:
        logger.error(exc)
    return OpenAIMessage(**raw_ai_message) if raw_ai_message else None


async def __call2log(fname: str, kwargs: dict[str, Any]):
    pretty_function_args = []
    for k, v in kwargs.items():
        _arg = k
        _arg += "="
        if isinstance(v, str):
            if "'" in v:
                _arg += f'"{v}"'
            else:
                _arg += f"'{v}'"
        else:
            _arg += str(v)
        pretty_function_args.append(_arg)
    return f"{fname}({','.join(pretty_function_args)})"


async def _run_tool(tool: OpenAITool, args: dict) -> Any:
    if tool.handler:
        logger.info(await __call2log(tool.function.name, args))
        tool_result = await tool.handler(**args)
        logger.debug(f"tool {tool.function.name} returned: {tool_result}")
        return tool_result
    else:
        logger.warning(f"tool {tool.function.name} didn't expose any handler, skipping!")
        return {}


async def _handle_tool_calls(
    tools: List[OpenAITool], tool_calls: List[OpenAIToolCall] | None = None
) -> Tuple[List[OpenAIMessage], List[OpenAITool]] | None:
    messages = []
    _tools = [router] + tools
    logger.info(f"Available tools: [{','.join([call.function.name for call in tool_calls or []])}]")
    for tool_call in tool_calls or []:
        parsed_args = json.loads(tool_call.function.arguments)

        tool_found = False
        for tool in _tools:
            if tool.function.name == tool_call.function.name:
                tool_found = True
                if tool.handler:
                    try:
                        tool_result = await _run_tool(tool, parsed_args)
                        if tool_call.function.name == router.function.name:
                            logger.info("router tool called, adding returned tools to available tools")
                            tools = tool_result
                            messages.append(
                                OpenAIMessage(
                                    role="tool",
                                    name=tool_call.function.name,
                                    content="New tools added to use, please continue.",
                                    tool_call_id=tool_call.id,
                                )
                            )
                        else:
                            messages.append(
                                OpenAIMessage(
                                    role="tool",
                                    name=tool_call.function.name,
                                    content=json.dumps(
                                        tool_result.model_dump(exclude_none=True) if tool_result else {}
                                    ),
                                    tool_call_id=tool_call.id,
                                )
                            )
                    except PromptToolError as exc:
                        logger.error(f"tool {tool_call.function.name} raised an exception: {exc}")
                        messages.append(
                            OpenAIMessage(
                                role="tool",
                                name=tool_call.function.name,
                                content=json.dumps(exc.model_dump(exclude_none=True)),
                                tool_call_id=tool_call.id,
                            )
                        )
                else:
                    logger.warning(f"tool {tool.function.name} didn't expose any handler, skipping!")
                    messages.append(
                        OpenAIMessage(
                            role="tool",
                            name=tool_call.function.name,
                            content=json.dumps(
                                PromptToolError(
                                    message="No handler defined for tool",
                                    tool_name=tool_call.function.name,
                                    inputs=parsed_args,
                                ).model_dump(exclude_none=True)
                            ),
                            tool_call_id=tool_call.id,
                        )
                    )
                break
        if not tool_found:
            logger.warning(f"tool {tool_call.function.name} not found in router tools, skipping!")
            messages.append(
                OpenAIMessage(
                    role="tool",
                    name=tool_call.function.name,
                    content=json.dumps(
                        PromptToolError(
                            message="Tool not found in router",
                            tool_name=tool_call.function.name,
                            inputs=parsed_args,
                        ).model_dump(exclude_none=True)
                    ),
                    tool_call_id=tool_call.id,
                )
            )
    return messages, tools


async def gpt_query(
    prompt: str,
    system_prompt: str | None = None,
    follow_up_prompt: str | None = None,
    messages: List[OpenAIMessage] = [],
    model: str = "gemini-2.5-flash",
    **kwargs: Any,
) -> PromptSummary:
    if not messages and system_prompt:
        messages.append(OpenAIMessage(role="developer", content=system_prompt.format(**kwargs)))
    messages.append(OpenAIMessage(role="user", content=prompt.format(**kwargs)))
    response_message = await __gpt_query(messages, model, [router])
    if response_message and response_message.content:
        logger.info(f"assistant: '{response_message.content}'")
    if not response_message:
        return PromptSummary(
            data=kwargs,
            messages=[
                message
                for message in messages
                if message.role not in ["function", "tool", "developer"] and message.content
            ][1:],
            resolved=False,
        )

    messages.append(response_message)

    tool_calls = response_message.tool_calls or []
    case_solved = False
    tools = []
    while tool_calls:
        _messages, tools = await _handle_tool_calls(tools, tool_calls) or ([], tools)
        messages.extend(_messages)
        response_message = await __gpt_query(messages, model, tools)
        if not response_message:
            break
        messages.append(response_message)
        tool_calls = response_message.tool_calls or []
        if follow_up_prompt and not case_solved:
            while not tool_calls:
                messages.append(OpenAIMessage(role="developer", content=follow_up_prompt.format(**kwargs)))
                response_message = await __gpt_query(messages, model, tools)
                if not response_message:
                    break
                tool_calls = response_message.tool_calls or []
                if response_message.content != "RESOLVED":
                    messages.append(response_message)
                else:
                    case_solved = True
                    break
        else:
            case_solved = True

    for message in messages:
        message.tool_calls = None
    return PromptSummary(
        data=kwargs,
        messages=[
            message for message in messages if message.role not in ["function", "tool", "developer"] and message.content
        ][1:],
        resolved=case_solved,
    )
