import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import threading
from display import Display
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation, ClientTools
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface
from spotify import play_spotify_track
from wakeword import WakeWordDetector
from util.is_raspberry import is_raspberry_pi
from dotenv import load_dotenv
from elevenlabs import AsyncElevenLabs

load_dotenv()
print(os.getenv("PORCUPINE_API_KEY"))

# Set up the display based on the platform.
display: Display = None
if is_raspberry_pi():
    print("Raspberry Pi detected")
    from display_led import LedDisplay
    display = LedDisplay()
else:
    from display_cli import CliDisplay
    display = CliDisplay()

# Create both synchronous and asynchronous clients.
async_elevenlabs_client = AsyncElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
elevenlabs_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
logging.basicConfig(level=logging.INFO)

client_tools = ClientTools()

async def play_existing_music(parameters: dict):
    print(parameters)
    try:
        songQuery = parameters.get("songQuery")
        logging.info(f"Requested music: {songQuery}")
        return json.dumps(await play_spotify_track(songQuery))
    except Exception as e:
        logging.error(f"Error playing existing music: {e}")
        return json.dumps({"error": f"Error playing existing music: {e}"})

client_tools.register("playExistingSong", play_existing_music, is_async=True)
wakeword = WakeWordDetector()

# --- Create a dedicated event loop for callbacks ---

callback_loop = asyncio.new_event_loop()

def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

# Run the callback loop in a separate daemon thread.
threading.Thread(target=start_loop, args=(callback_loop,), daemon=True).start()

# --- Define async helper functions for your callbacks ---

async def _on_agent_response(response):
    print(f"Agent: {response}")
    display.show_spinner()

async def _on_agent_response_correction(original, corrected):
    print(f"Agent: {original} -> {corrected}")
    display.show_spinner()

async def _on_user_transcript(transcript):
    print(f"User: {transcript}")
    display.turn_off()

async def main():
    display.turn_off()
    while True:
        await wakeword.wait_for_wake_word()
        display.show_spinner()

        # Synchronous callback wrappers that schedule async tasks on our dedicated callback loop.
        def on_agent_response(response):
            asyncio.run_coroutine_threadsafe(_on_agent_response(response), callback_loop)

        def on_agent_response_correction(original, corrected):
            asyncio.run_coroutine_threadsafe(_on_agent_response_correction(original, corrected), callback_loop)

        def on_user_transcript(transcript):
            asyncio.run_coroutine_threadsafe(_on_user_transcript(transcript), callback_loop)

       
        async def start_session_async():
            conversation = Conversation(
                requires_auth=True,
                client=elevenlabs_client,
                agent_id=os.getenv("ELEVENLABS_AGENT_ID"),
                client_tools=client_tools,
                audio_interface=DefaultAudioInterface(),
                callback_agent_response=on_agent_response,
                callback_agent_response_correction=on_agent_response_correction,
                callback_user_transcript=on_user_transcript,
            )
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor() as pool:
                # Run the blocking call in a thread pool
                await loop.run_in_executor(pool, conversation.start_session)
        try:
            await start_session_async()
        except Exception as e:
            logging.error(f"Error during session: {e}")
        display.turn_off()

if __name__ == "__main__":
    asyncio.run(main())
