from abc import ABC, abstractmethod
import base64
import json
from typing import Callable, Optional, Any, Awaitable
import asyncio
from websockets.client import connect as ws_connect, WebSocketClientProtocol
from websockets.exceptions import ConnectionClosedOK
from elevenlabs import AsyncElevenLabs
import traceback
import logging

class AsyncAudioInterface(ABC):
    @abstractmethod
    async def start(self, input_callback: Callable[[bytes], Awaitable[None]]):
        pass

    @abstractmethod
    async def stop(self):
        pass

    @abstractmethod
    async def output(self, audio: bytes):
        pass

    @abstractmethod
    async def interrupt(self):
        pass

class AsyncClientTools:
    def __init__(self):
        self.tools: dict[str, Callable[[dict], Awaitable[Any]]] = {}
        self._running = False

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    def register(
        self,
        tool_name: str,
        handler: Callable[[dict], Awaitable[Any]],
    ) -> None:
        if not asyncio.iscoroutinefunction(handler):
            raise ValueError("Handler must be an async function")
        if tool_name in self.tools:
            raise ValueError(f"Tool '{tool_name}' is already registered")
        self.tools[tool_name] = handler

    async def handle(self, tool_name: str, parameters: dict) -> Any:
        if not self._running:
            raise RuntimeError("ClientTools is not running")
            
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' is not registered")
            
        handler = self.tools[tool_name]
        return await handler(parameters)

class AsyncConversationInitiationData:
    def __init__(
        self,
        extra_body: Optional[dict] = None,
        conversation_config_override: Optional[dict] = None,
        dynamic_variables: Optional[dict] = None,
    ):
        self.extra_body = extra_body or {}
        self.conversation_config_override = conversation_config_override or {}
        self.dynamic_variables = dynamic_variables or {}

class AsyncConversation:
    def __init__(
        self,
        client: AsyncElevenLabs,
        agent_id: str,
        *,
        requires_auth: bool,
        audio_interface: AsyncAudioInterface,
        config: Optional[AsyncConversationInitiationData] = None,
        client_tools: Optional[AsyncClientTools] = None,
        callback_agent_response: Optional[Callable[[str], Awaitable[None]]] = None,
        callback_agent_response_correction: Optional[Callable[[str, str], Awaitable[None]]] = None,
        callback_user_transcript: Optional[Callable[[str], Awaitable[None]]] = None,
        callback_latency_measurement: Optional[Callable[[int], Awaitable[None]]] = None,
    ):
        self.client = client
        self.agent_id = agent_id
        self.requires_auth = requires_auth
        self.audio_interface = audio_interface
        self.config = config or AsyncConversationInitiationData()
        self.client_tools = client_tools or AsyncClientTools()
        self.callback_agent_response = callback_agent_response
        self.callback_agent_response_correction = callback_agent_response_correction
        self.callback_user_transcript = callback_user_transcript
        self.callback_latency_measurement = callback_latency_measurement

        self._conversation_id = None
        self._last_interrupt_id = 0
        self._ws = None
        self._running = False
        self._main_task = None

    async def start_session(self):
        """Starts the conversation session."""
        if self._running:
            return

        self._running = True
        ws_url = await self._get_signed_url() if self.requires_auth else self._get_wss_url()
        
        self._main_task = asyncio.create_task(self._run(ws_url))

    async def _run(self, ws_url: str):
        async with ws_connect(ws_url, max_size=16 * 1024 * 1024) as ws:
            self._ws = ws
            await self.client_tools.start()
            
            # Send initial configuration
            await ws.send(json.dumps({
                "type": "conversation_initiation_client_data",
                "custom_llm_extra_body": self.config.extra_body,
                "conversation_config_override": self.config.conversation_config_override,
                "dynamic_variables": self.config.dynamic_variables,
            }))

            async def input_callback(audio: bytes):
                if not self._running:
                    return
                try:
                    await ws.send(json.dumps({
                        "user_audio_chunk": base64.b64encode(audio).decode(),
                    }))
                except ConnectionClosedOK:
                    await self.end_session()
                except Exception as e:
                    logging.error(f"Error sending user audio chunk: {e}")
                    await self.end_session()

            await self.audio_interface.start(input_callback)
            
            while self._running:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    if not self._running:
                        break
                    
                    data = json.loads(message)
                    await self._handle_message(data)
                    
                except asyncio.TimeoutError:
                    continue
                except ConnectionClosedOK:
                    await self.end_session()
                except Exception as e:
                    logging.error(f"Error in websocket loop: {e}")
                    await self.end_session()

    async def end_session(self):
        """Ends the conversation session and cleans up resources."""
        if not self._running:
            return
            
        self._running = False
        
        if self._main_task:
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
            
        await self.audio_interface.stop()
        await self.client_tools.stop()
        
        if self._ws and not self._ws.closed:
            await self._ws.close()

    async def _handle_message(self, message: dict):
        """Handle websocket messages."""
        msg_type = message["type"]

        if msg_type == "conversation_initiation_metadata":
            event = message["conversation_initiation_metadata_event"]
            assert self._conversation_id is None
            self._conversation_id = event["conversation_id"]

        elif msg_type == "audio":
            event = message["audio_event"]
            if int(event["event_id"]) <= self._last_interrupt_id:
                return
            audio = base64.b64decode(event["audio_base_64"])
            await self.audio_interface.output(audio)

        elif msg_type == "agent_response" and self.callback_agent_response:
            event = message["agent_response_event"]
            await self.callback_agent_response(event["agent_response"].strip())

        elif msg_type == "agent_response_correction" and self.callback_agent_response_correction:
            event = message["agent_response_correction_event"]
            await self.callback_agent_response_correction(
                event["original_agent_response"].strip(),
                event["corrected_agent_response"].strip()
            )

        elif msg_type == "user_transcript" and self.callback_user_transcript:
            event = message["user_transcription_event"]
            await self.callback_user_transcript(event["user_transcript"].strip())

        elif msg_type == "interruption":
            event = message["interruption_event"]
            self._last_interrupt_id = int(event["event_id"])
            await self.audio_interface.interrupt()

        elif msg_type == "ping":
            event = message["ping_event"]
            await self._ws.send(json.dumps({
                "type": "pong",
                "event_id": event["event_id"],
            }))
            if self.callback_latency_measurement and event["ping_ms"]:
                await self.callback_latency_measurement(int(event["ping_ms"]))

        elif msg_type == "client_tool_call":
            tool_call = message.get("client_tool_call", {})
            tool_name = tool_call.get("tool_name")
            parameters = {
                "tool_call_id": tool_call["tool_call_id"],
                **tool_call.get("parameters", {})
            }
            
            try:
                result = await self.client_tools.handle(tool_name, parameters)
                response = {
                    "type": "client_tool_result",
                    "tool_call_id": parameters["tool_call_id"],
                    "result": result or f"Client tool: {tool_name} called successfully.",
                    "is_error": False,
                }
            except Exception as e:
                response = {
                    "type": "client_tool_result",
                    "tool_call_id": parameters["tool_call_id"],
                    "result": str(e),
                    "is_error": True,
                }

            if self._running and self._ws:
                await self._ws.send(json.dumps(response))

    def _get_wss_url(self) -> str:
        base_url = self.client._client_wrapper._base_url
        base_ws_url = base_url.replace("http", "ws", 1)
        return f"{base_ws_url}/v1/convai/conversation?agent_id={self.agent_id}"

    async def _get_signed_url(self) -> str:
        response = await self.client.conversational_ai.get_signed_url(agent_id=self.agent_id)
        return response.signed_url