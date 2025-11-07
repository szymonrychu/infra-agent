import json
import logging
from typing import Any, List

from openai import AsyncOpenAI, BadRequestError, RateLimitError
from ratelimit import limits, sleep_and_retry

from infra_agent.models.ai import (
    OpenAICaseSummary,
    OpenAIMessage,
    OpenAIPromptSummary,
    OpenAITool,
    OpenAIToolCall,
)
from infra_agent.models.generic import PromptToolError
from infra_agent.providers.router import closer, tools
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
    completions_create_kwargs["tools"] = [tool.model_dump(exclude_none=True) for tool in tools]
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
    messages: List[OpenAIMessage], tool_calls: List[OpenAIToolCall] | None = None
) -> List[OpenAIMessage] | None:
    for tool_call in tool_calls or []:
        parsed_args = json.loads(tool_call.function.arguments)

        tool_found = False
        for tool in tools:
            if tool.function.name == tool_call.function.name:
                tool_found = True
                if tool.handler:
                    try:
                        tool_result = await _run_tool(tool, parsed_args)
                        tool_call.result = tool_result
                        if tool_call.function.name == closer.function.name:
                            logger.info("closer tool called, finishing reasoning")
                            messages.append(
                                OpenAIMessage(
                                    role="tool",
                                    name=tool_call.function.name,
                                    tool_call_id=tool_call.id,
                                    tool_call_arguments=tool_call.function.arguments,
                                )
                            )
                            return messages
                        else:
                            messages.append(
                                OpenAIMessage(
                                    role="tool",
                                    name=tool_call.function.name,
                                    content="""
Tool named {tool_name} was called with parameters:
{tool_parameters}
it's result was:
```
{tool_result}
```
""".format(
                                        tool_name=tool_call.function.name,
                                        tool_parameters="\n".join(
                                            [f"  - '{k}' = '{v}'" for k, v in parsed_args.items()]
                                        ),
                                        tool_result=json.dumps(
                                            tool_result.model_dump(exclude_none=True) if tool_result else {}
                                        ),
                                    ),
                                    tool_call_id=tool_call.id,
                                    tool_call_arguments=tool_call.function.arguments,
                                )
                            )
                    except PromptToolError as exc:
                        logger.error(f"tool {tool_call.function.name} raised an exception: {exc}")
                        messages.append(
                            OpenAIMessage(
                                role="tool",
                                name=tool_call.function.name,
                                content=exc.model().error,
                                tool_call_id=tool_call.id,
                            )
                        )
                    except Exception as exc:
                        logger.error(
                            f"Error running a tool {await __call2log(tool_call.function.name, parsed_args)} - {exc}"
                        )
                        messages.append(
                            OpenAIMessage(
                                role="tool",
                                name=tool_call.function.name,
                                content=f"There was a problem calling the tool! {exc}",
                                tool_call_id=tool_call.id,
                            )
                        )
                else:
                    logger.warning(f"tool {tool.function.name} didn't expose any handler, skipping!")
                    messages.append(
                        OpenAIMessage(
                            role="tool",
                            name=tool_call.function.name,
                            content="No handler defined for tool",
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
                    content="Tool not found in router",
                    tool_call_id=tool_call.id,
                )
            )
    return messages


async def gpt_query(
    prompt: str,
    system_prompt: str | None = None,
    messages: List[OpenAIMessage] = [],
    model: str = "gemini-2.5-flash",
    **kwargs: Any,
) -> OpenAIPromptSummary:
    if not messages and system_prompt:
        system_prompt_kwargs = kwargs
        system_prompt_kwargs["finish_function_name"] = closer.function.name
        _system_prompt = system_prompt.format(**system_prompt_kwargs)
        messages.append(OpenAIMessage(role="developer", content=_system_prompt))
        logger.debug(f"System prompt: {_system_prompt}")
    _prompt = prompt.format(**kwargs)
    logger.debug(f"Prompt: {_prompt}")
    messages.append(OpenAIMessage(role="user", content=_prompt))
    response_message = await __gpt_query(messages, model, tools)
    if response_message and response_message.content:
        logger.info(f"assistant: '{response_message.content}'")
    if not response_message:
        return OpenAIPromptSummary(
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
    summary = None
    while not case_solved:
        messages = await _handle_tool_calls(messages, tool_calls) or []
        for call in [c for m in messages for c in m.tool_calls or []]:
            if call.function.name == closer.function.name:
                case_summary = (
                    OpenAICaseSummary.model_validate(call.result.model_dump(exclude_none=True)) if call.result else None
                )
                logger.info("closer tool called PROPERLY, finishing reasoning")
                logger.info(
                    f"Details: case_solved={case_summary.solved if case_summary else False},\nmissing_tools=[{','.join(case_summary.missing_tools or [] if case_summary else [])}]explanation={case_summary.explanation if case_summary else ''}"
                )
                return OpenAIPromptSummary(
                    data=case_summary,
                    messages=[m for m in messages[2:] if m.role not in ["tool"] and m.content],
                    resolved=case_summary.solved if case_summary else False,
                )
        # if messages[-1]
        response_message = await __gpt_query(messages, model, tools)
        if response_message and response_message.content:
            logger.info(f"assistant: '{response_message.content}'")
        if not response_message:
            break
        messages.append(response_message)
        tool_calls = response_message.tool_calls or []
        if not tool_calls:
            logger.warning("AI didn't respond with any tool_requests!")
            try:
                summary = OpenAICaseSummary.model_validate(json.loads(response_message.content or "")["arguments"])
                case_solved = summary.solved
                logger.info("closer tool called, finishing reasoning")
                messages.append(OpenAIMessage(role="assistant", content=response_message.content))
                break
            except json.JSONDecodeError:
                pass
            messages.append(
                OpenAIMessage(
                    role="user",
                    content=f"Use provided tools to solve the task, do not ask for permissions, just do things! If all other options are exhausted, run `{closer.function.name}` and provide appropriate parameters!",
                )
            )
            response_message = await __gpt_query(messages, model, tools)
            if response_message and response_message.content:
                logger.info(f"assistant: '{response_message.content}'")
            if not response_message:
                break
            messages.append(response_message)
            tool_calls = response_message.tool_calls or []

    # for message in messages:
    #     message.tool_calls = None
    return OpenAIPromptSummary(
        data=summary,
        messages=[],  # [m for m in messages[2:] if m.role not in ["tool"] and m.content],
        resolved=case_solved,
    )
