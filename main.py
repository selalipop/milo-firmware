import asyncio
import logging
import os
from time import sleep
from display import Display
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation, ClientTools
from spotify import play_spotify_track
from wakeword import WakeWordDetector
from util.is_raspberry import is_raspberry_pi
from dotenv import load_dotenv
from asyncelevenlabs.conversation import AsyncConversation, AsyncClientTools
from asyncelevenlabs.audio import AsyncDefaultAudioInterface
from elevenlabs import AsyncElevenLabs
load_dotenv()

print(os.getenv("PORCUPINE_API_KEY"))
display : Display = None
if is_raspberry_pi():
    print("Raspberry Pi detected")
    from display_led import LedDisplay
    display = LedDisplay()
else:
    from display_cli import CliDisplay
    display = CliDisplay()



# def log_message(parameters):
#     message = parameters.get("message")
#     print(message)

# client_tools = ClientTools()
# client_tools.register("logMessage", log_message)
elevenlabs_client = AsyncElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

logging.basicConfig(level=logging.DEBUG)


client_tools = AsyncClientTools()
async def play_existing_music(parameters: dict):
    songName = parameters.get("songName")
    logging.info(f"Requested music: {songName}")
    return await play_spotify_track(songName)

client_tools.register("playExistingSong", play_existing_music)


wakeword = WakeWordDetector()
async def main():
    display.turn_off()
    while True:
        await wakeword.wait_for_wake_word()
        display.show_spinner()
        async def on_agent_response(response):
            print(f"Agent: {response}")
            display.show_spinner()
        async def on_agent_response_correction(original, corrected):
            print(f"Agent: {original} -> {corrected}")
            display.show_spinner()
        async def on_user_transcript(transcript):
            print(f"User: {transcript}")
            display.turn_off()
        conversation = AsyncConversation(
            requires_auth=True,
            client=elevenlabs_client,
            agent_id=os.getenv("ELEVENLABS_AGENT_ID"),
            client_tools=client_tools,
            audio_interface=AsyncDefaultAudioInterface(),
            callback_agent_response=on_agent_response,
            callback_agent_response_correction=on_agent_response_correction,
            callback_user_transcript=on_user_transcript,
        )
        await conversation.start_session()
        display.turn_off()


if __name__ == "__main__":
    asyncio.run(main())



