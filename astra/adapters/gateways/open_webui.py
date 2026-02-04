import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from astra.config import Config, get_config
from astra.interfaces.gateway import Command, Gateway

logger = logging.getLogger(__name__)

class OpenWebUIGateway(Gateway):
    """
    Gateway implementation for Open Web UI integration.
    Exposes an OpenAI-compatible API that maps ASTra commands to Tool calls.
    """

    def __init__(self, config: Config | None = None):
        self._config = config or get_config()
        self._handlers: dict[str, Callable[[Command], Awaitable[None]]] = {}
        self._handlers_meta: dict[str, dict[str, bool]] = {}

        # O(1) Optimizations
        self._cached_tool_schemas: list[dict[str, Any]] = []
        self._auth_tokens: set[str] = set()

        # FastAPI App
        self.app = FastAPI(title="ASTra Agent API", version="1.0.0")
        self._setup_middleware()
        self._setup_routes()

        self._server_task: asyncio.Task | None = None
        self._server: uvicorn.Server | None = None

        # Load auth tokens if configured
        # For simple setup, we might assume no auth or config-based token
        # self._auth_tokens.add(self._config.webui_api_key)

    def _setup_middleware(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _setup_routes(self):
        @self.app.get("/v1/models")
        async def list_models():
            """Auto-discovery endpoint."""
            return {
                "object": "list",
                "data": [
                    {
                        "id": "astra-agent",
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "astra",
                    }
                ]
            }

        @self.app.post("/v1/chat/completions")
        async def chat_completions(request: Request):
            """Handle chat completion requests."""
            data = await request.json()
            messages = data.get("messages", [])
            stream = data.get("stream", False)

            # Smart Context Filtering: O(1) check of last message
            if not messages:
                raise HTTPException(status_code=400, detail="No messages provided")

            last_message = messages[-1]

            # Check if this is a tool response or a user prompt
            # For Open Web UI, we get the whole history.
            # If the last message is from user, check if we need to stream logs or call a tool.

            if stream:
                return EventSourceResponse(self._stream_response(last_message))
            else:
                 # Non-streaming not implemented for 'thinking' logs effectively
                 # Just return a simple response
                 return await self._handle_sync_request(data)

    def register_command(
        self,
        name: str,
        handler: Callable[[Command], Awaitable[None]],
        description: str = "",
        params: list[Any] | None = None,
        group: str | None = None,
        requires_auth: bool = False,
        requires_admin: bool = False,
        requires_mfa: bool = False,
    ) -> None:
        """Register a command and cache its JSON schema."""
        register_key = f"{group}.{name}" if group else name
        self._handlers[register_key] = handler
        self._handlers_meta[register_key] = {
            "auth": requires_auth,
            "admin": requires_admin,
            "mfa": requires_mfa
        }

        # Build JSON Schema Tool Definition
        tool_params = {
            "type": "object",
            "properties": {},
            "required": []
        }

        if params:
            for param in params:
                param_type = "string"
                if param.type is int:
                    param_type = "integer"
                elif param.type is bool:
                    param_type = "boolean"
                elif param.type is float:
                    param_type = "number"

                tool_params["properties"][param.name] = {
                    "type": param_type,
                    "description": param.description
                }

                if param.required:
                    tool_params["required"].append(param.name)

        tool_schema = {
            "type": "function",
            "function": {
                "name": register_key.replace(".", "_"), # OpenAI tools don't like dots usually
                "description": description,
                "parameters": tool_params
            }
        }

        self._cached_tool_schemas.append(tool_schema)

    def register_command_group(self, name: str, description: str = "") -> None:
        pass # Groups are flattened in this implementation schema-wise

    async def start(self) -> None:
        """Start the Uvicorn server."""
        config = uvicorn.Config(
            app=self.app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
            loop="asyncio"
        )
        self._server = uvicorn.Server(config)

        # Run in a separate task because uvicorn blocks
        logger.info("Starting Open WebUI Gateway on port 8000")
        self._server_task = asyncio.create_task(self._server.serve())

    async def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._server_task:
            await self._server_task

    async def send_message(self, message: Any):
        # In a request-response model, we can't easily push unsolicited messages
        # unless stored in a buffer or sent via SSE "thinking" events if a request is open.
        # For now, we log it.
        logger.info(f"OpenWebUI Message: {message}")

    async def get_response(self, prompt: str) -> str | None:
        return None

    def is_user_authorized(self, user_id: str) -> bool:
        return True # For local open web ui, assume trusted or validate token

    def is_admin(self, user_id: str) -> bool:
        return True

    async def broadcast(self, message: str) -> None:
        """Broadcast a message (Placeholder for WebSockets)."""
        logger.info(f"BROADCAST: {message}")

    # --- Internal Helpers ---

    async def _stream_response(self, last_message: dict):
        """Stream 'thinking' logs and then the tool call."""

        # 1. Simulate finding tools (O(1) lookup)
        # In reality, we'd pass the prompt to an LLM here to decide which tool to call.
        # BUT, ASTra is the agent. Open Web UI thinks ASTra IS the model.
        # If Open Web UI prompts: "Fix the bug", ASTra (as the 'model') should reply with a tool call?
        # NO. Open Web UI uses Ollama/OpenAI as the *inference engine*.
        # Wait. If ASTra pretends to be the Model, then ASTra must do the inference or proxy it.
        # IF Open Web UI connects to ASTra as an OpenAI URL, then ASTra MUST proxy the request to an actual LLM
        # (e.g. LiteLLM) to get the tool call, OR ASTra simply executes internal logic.

        # Let's assume ASTra proxies the chat request to its internal LLM (LiteLLM)
        # WITH the valid ASTra tools injected.

        # This implementation requires ASTra to act as an inference proxy.
        # For now, to keep it simple and QOL-focused:
        # We will yield a "Thinking..." generic log.

        yield {
            "choices": [{
                "delta": {"content": "ASTra: Analyzing request..."}
            }]
        }

        # TODO: Real inference integration would go here.
        # For the purpose of the gateway interface, we expose the tools.
        # The user's request implies we need to be the "backend".
        pass

    async def _handle_sync_request(self, data: dict):
         return {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": int(time.time()),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "ASTra Web UI Gateway Ready."
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
