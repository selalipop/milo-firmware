import asyncio
import os
from time import sleep
from display import Display
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation, ClientTools
from util.is_raspberry import is_raspberry_pi
from dotenv import load_dotenv
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface


load_dotenv()
display : Display = None
if is_raspberry_pi():
    print("Raspberry Pi detected")
    from display_led import LedDisplay
    display = LedDisplay()
else:
    from display_cli import CliDisplay
    display = CliDisplay()


async def main():
    await display.show_spinner()
    await asyncio.sleep(100000)
    await display.turn_off()


if __name__ == "__main__":
    asyncio.run(main())

def log_message(parameters):
    message = parameters.get("message")
    print(message)

client_tools = ClientTools()
client_tools.register("logMessage", log_message)
elevenlabs_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

conversation = Conversation(
    client=elevenlabs_client,
    agent_id=os.getenv("ELEVENLABS_AGENT_ID"),
    client_tools=client_tools,
    audio_interface=DefaultAudioInterface(),
    callback_agent_response=lambda response: print(f"Agent: {response}"),
    callback_agent_response_correction=lambda original, corrected: print(f"Agent: {original} -> {corrected}"),
    callback_user_transcript=lambda transcript: print(f"User: {transcript}"),

)

conversation.start_session()
