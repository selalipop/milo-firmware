from typing import Callable, Awaitable
import queue
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor

from asyncelevenlabs.conversation import AsyncAudioInterface



class AsyncDefaultAudioInterface(AsyncAudioInterface):
    INPUT_FRAMES_PER_BUFFER = 4000  # 250ms @ 16kHz
    OUTPUT_FRAMES_PER_BUFFER = 1000  # 62.5ms @ 16kHz

    def __init__(self):
        try:
            import pyaudio
        except ImportError:
            raise ImportError("To use DefaultAudioInterface you must install pyaudio.")
        self.pyaudio = pyaudio
        
        # Initialize queues and events
        self.output_queue: queue.Queue[bytes] = queue.Queue()
        self.should_stop = threading.Event()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread_pool = ThreadPoolExecutor(max_workers=1)
        
        # Will be initialized in start()
        self.p = None
        self.in_stream = None
        self.out_stream = None
        self.output_thread = None
        self.input_callback = None

    async def start(self, input_callback: Callable[[bytes], Awaitable[None]]):
        """Start the audio interface with an async input callback."""
        self.loop = asyncio.get_running_loop()
        self.input_callback = input_callback

        # Initialize PyAudio in the main thread
        self.p = self.pyaudio.PyAudio()
        
        # Create a sync wrapper for the async input callback
        def sync_input_wrapper(in_data, frame_count, time_info, status):
            if self.input_callback and not self.should_stop.is_set():
                # Schedule the async callback in the event loop
                asyncio.run_coroutine_threadsafe(
                    self.input_callback(in_data), 
                    self.loop
                )
            return (None, self.pyaudio.paContinue)

        # Open streams
        self.in_stream = self.p.open(
            format=self.pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            stream_callback=sync_input_wrapper,
            frames_per_buffer=self.INPUT_FRAMES_PER_BUFFER,
            start=True,
        )
        
        self.out_stream = self.p.open(
            format=self.pyaudio.paInt16,
            channels=1,
            rate=16000,
            output=True,
            frames_per_buffer=self.OUTPUT_FRAMES_PER_BUFFER,
            start=True,
        )

        # Start output thread
        self.output_thread = threading.Thread(
            target=self._output_thread,
            daemon=True
        )
        self.output_thread.start()

    async def stop(self):
        """Stop the audio interface."""
        self.should_stop.set()
        
        if self.output_thread:
            # Use thread pool to avoid blocking
            await self.loop.run_in_executor(
                self.thread_pool,
                self.output_thread.join
            )

        # Clean up PyAudio resources
        if self.in_stream:
            self.in_stream.stop_stream()
            self.in_stream.close()
        if self.out_stream:
            self.out_stream.close()
        if self.p:
            self.p.terminate()

        # Clean up thread pool
        self.thread_pool.shutdown(wait=False)

    async def output(self, audio: bytes):
        """Queue audio for output."""
        if not self.should_stop.is_set():
            self.output_queue.put_nowait(audio)

    async def interrupt(self):
        """Clear the output queue to stop current audio."""
        try:
            while True:
                self.output_queue.get_nowait()
        except queue.Empty:
            pass

    def _output_thread(self):
        """Thread for handling audio output."""
        while not self.should_stop.is_set():
            try:
                audio = self.output_queue.get(timeout=0.25)
                if not self.should_stop.is_set():
                    self.out_stream.write(audio)
            except queue.Empty:
                continue
            except Exception as e:
                if not self.should_stop.is_set():
                    print(f"Error in audio output thread: {e}")