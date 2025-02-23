
import asyncio
import logging
import os
from pvrecorder import PvRecorder
import pvporcupine
import pvcobra
from pvrecorder import PvRecorder

valid_microphone_names = ["USB PnP Sound Device", "PCM2902"]

def find_microphone_index():
    for i, device in enumerate(PvRecorder.get_available_devices()):
        if any(name in device for name in valid_microphone_names):
            return i
    logging.error("No microphone found")
    return 0

class WakeWordDetector:
    def __init__(self, access_key=None, keyword=None, keyword_path=None):
        if access_key is None:
            access_key = os.getenv("PORCUPINE_API_KEY")
        if keyword is None:
            keyword = "milo"
        if keyword_path is None:
            keyword_path = "models/wakeword/hey_milo.ppn"
        self._access_key = access_key
        self._keyword = keyword
        self._device_index = find_microphone_index()
        self._keyword_path = keyword_path
        self._stop_event = asyncio.Event()

        self._porcupine = pvporcupine.create(
            access_key=access_key,
            keywords=[self._keyword],
            keyword_paths=[self._keyword_path]
        )
        self._recorder = PvRecorder(frame_length=self._porcupine.frame_length, device_index=self._device_index)

    async def wait_for_wake_word(self):
        self._recorder.start()
        wait_for_wakeword = False
        try:
            is_recording = not wait_for_wakeword
            silence_counter = 0
            speech_counter = 0
            logging.info("Waiting for wake word...")
            while not self._stop_event.is_set():
                pcm = await asyncio.to_thread(self._recorder.read)
                wake_word_index = self._porcupine.process(pcm)

                if wake_word_index >= 0:
                    logging.info(f'Wake word ({self._keyword}) detected!')
                    break
               
                await asyncio.sleep(0)

        except Exception as e:
            logging.error(f'Error: {e}')
        finally:
            self._recorder.stop()

    def stop(self):
        self._stop_event.set()
        self._recorder.stop()
