from abc import ABC, abstractmethod
import base64
import json
from typing import Callable, Optional, Any, Awaitable
import asyncio
from websockets.client import connect as ws_connect
from websockets.exceptions import ConnectionClosedOK
from elevenlabs import AsyncElevenLabs
import traceback
import logging

class AsyncAudioInterface(ABC):
    """AudioInterface provides an abstraction for handling audio input and output."""
    
    @abstractmethod
    async def start(self, input_callback: Callable[[bytes], Awaitable[None]]):
        """Starts the audio interface.
        
        Called one time before the conversation starts.
        The `input_callback` should be called regularly with input audio chunks from
        the user. The audio should be in 16-bit PCM mono format at 16kHz. Recommended
        chunk size is 4000 samples (250 milliseconds).
        """
        pass

    @abstractmethod
    async def stop(self):
        """Stops the audio interface.
        
        Called one time after the conversation ends. Should clean up any resources
        used by the audio interface and stop any audio streams.
        """
        pass

    @abstractmethod
    async def output(self, audio: bytes):
        """Output audio to the user.
        
        The `audio` input is in 16-bit PCM mono format at 16kHz.
        """
        pass

    @abstractmethod
    async def interrupt(self):
        """Interruption signal to stop any audio output.
        
        User has interrupted the agent and all previously buffered audio output should
        be stopped.
        """
        pass


class AsyncClientTools:
    """Handles registration and execution of client-side tools that can be called by the agent."""

    def __init__(self):
        self.tools: dict[str, tuple[Callable[[dict], Awaitable[Any]], bool]] = {}
        self._running = False

    async def start(self):
        """Start the client tools."""
        self._running = True

    async def stop(self):
        """Stop the client tools."""
        self._running = False

    def register(
        self,
        tool_name: str,
        handler: Callable[[dict], Awaitable[Any]],
    ) -> None:
        """Register a new tool that can be called by the AI agent.

        Args:
            tool_name: Unique identifier for the tool
            handler: Async function that implements the tool's logic
        """
        if not asyncio.iscoroutinefunction(handler):
            raise ValueError("Handler must be an async function")
        if tool_name in self.tools:
            raise ValueError(f"Tool '{tool_name}' is already registered")
        self.tools[tool_name] = handler

    async def handle(self, tool_name: str, parameters: dict) -> Any:
        """Execute a registered tool with the given parameters.

        Returns the result of the tool execution.
        """
        if not self._running:
            raise RuntimeError("ClientTools is not running")
            
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' is not registered")
            
        handler = self.tools[tool_name]
        return await handler(parameters)


class AsyncConversationInitiationData:
    """Configuration options for the Conversation."""

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
        """Conversational AI session.

        Args:
            client: The ElevenLabs client to use for the conversation.
            agent_id: The ID of the agent to converse with.
            requires_auth: Whether the agent requires authentication.
            audio_interface: The audio interface to use for input and output.
            client_tools: The client tools to use for the conversation.
            callback_agent_response: Async callback for agent responses.
            callback_agent_response_correction: Async callback for agent response corrections.
            callback_user_transcript: Async callback for user transcripts.
            callback_latency_measurement: Async callback for latency measurements.
        """
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

    async def start_session(self):
        """Starts the conversation session."""
        if self._running:
            return

        self._running = True
        ws_url = await self._get_signed_url() if self.requires_auth else self._get_wss_url()
        
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
                    print(f"Error sending user audio chunk: {e}")
                    await self.end_session()

            await self.audio_interface.start(input_callback)
            
            try:
                async for message in ws:
                    if not self._running:
                        break
                    await self._handle_message(json.loads(message))
            except ConnectionClosedOK:
                await self.end_session()
            except Exception as e:
                traceback.print_exc()
                print(f"Error in websocket loop: {e}")
                await self.end_session()

    async def end_session(self):
        """Ends the conversation session and cleans up resources."""
        if not self._running:
            return
            
        self._running = False
        await self.audio_interface.stop()
        await self.client_tools.stop()
        
        if self._ws and not self._ws.closed:
            await self._ws.close()

    async def _handle_message(self, message: dict):
        msg_type = message["type"]

        if msg_type == "conversation_initiation_metadata":
            event = message["conversation_initiation_metadata_event"]
            self._conversation_id = event["conversation_id"]

        elif msg_type == "audio":
            event = message["audio_event"]
            if int(event["event_id"]) <= self._last_interrupt_id:
                return
            audio = base64.b64decode(event["audio_base_64"])
            await self.audio_interface.output(audio)

        elif msg_type == "agent_response" and self.callback_agent_response:
            event = message["agent_response_event"]
            asyncio.create_task(self.callback_agent_response(event["agent_response"].strip()))

        elif msg_type == "agent_response_correction" and self.callback_agent_response_correction:
            event = message["agent_response_correction_event"]
            asyncio.create_task(self.callback_agent_response_correction(
                event["original_agent_response"].strip(),
                event["corrected_agent_response"].strip()
            ))

        elif msg_type == "user_transcript" and self.callback_user_transcript:
            event = message["user_transcription_event"]
            asyncio.create_task(self.callback_user_transcript(event["user_transcript"].strip()))

        elif msg_type == "interruption":
            event = message["interruption_event"]
            self._last_interrupt_id = int(event["event_id"])
            asyncio.create_task(self.audio_interface.interrupt())

        elif msg_type == "ping":
            event = message["ping_event"]
            await self._ws.send(json.dumps({
                "type": "pong",
                "event_id": event["event_id"],
            }))
            if self.callback_latency_measurement and event["ping_ms"]:
                asyncio.create_task(self.callback_latency_measurement(int(event["ping_ms"])))

        elif msg_type == "client_tool_call":
            tool_call = message.get("client_tool_call", {})
            tool_name = tool_call.get("tool_name")
            logging.debug(f"Calling tool: {tool_name}")

            parameters = {
                "tool_call_id": tool_call["tool_call_id"],
                **tool_call.get("parameters", {})
            }
            logging.debug(f"Parameters: {parameters}")
            print(f"Parameters: {parameters}")
            try:
                result = await self.client_tools.handle(tool_name, parameters)
                logging.debug(f"Result: {result}")
                print(f"Result: {result}")
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

            if self._running:
                await self._ws.send(json.dumps(response))

    def _get_wss_url(self) -> str:
        base_url = self.client._client_wrapper._base_url
        base_ws_url = base_url.replace("http", "ws", 1)
        return f"{base_ws_url}/v1/convai/conversation?agent_id={self.agent_id}"

    async def _get_signed_url(self) -> str:
        response = await self.client.conversational_ai.get_signed_url(agent_id=self.agent_id)
        return response.signed_url