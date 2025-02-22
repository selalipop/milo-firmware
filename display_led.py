import asyncio
from enum import Enum
from display import Display
import neopixel
import math
import board

pixel_pin = board.D12
num_pixels = 8
ORDER = neopixel.GRB

class AnimationType(Enum):
    CHASE = 1

class LedDisplay(Display):
    def __init__(self):
        self.pixels = neopixel.NeoPixel(
            pixel_pin, num_pixels, brightness=0.1, auto_write=False, pixel_order=ORDER
        )
        self.current_animation = AnimationType.CHASE

    async def show_spinner(self) -> None:
        asyncio.create_task(self.chase_animation(duration=-1, color=(255, 255, 255)))

    async def chase_animation(self, duration=-1, color=(255, 255, 255)):
        self.current_animation = AnimationType.CHASE
        start_time = asyncio.get_event_loop().time()
        position = 0
        while asyncio.get_event_loop().time() - start_time < duration or duration == -1:
            if self.current_animation != AnimationType.CHASE:
                return
            for i in range(num_pixels):
                distance = min((i - position) % num_pixels, (position - i) % num_pixels)
                brightness = math.cos(distance * math.pi / num_pixels) * 0.5 + 0.1
                pixel_color = tuple(int(c * brightness) for c in color)
                self.pixels[i] = pixel_color
            self.pixels.show()
            await asyncio.sleep(0.05)
            position = (position + 1) % num_pixels

    async def turn_off(self) -> None:
        self.current_animation = AnimationType.OFF
        self.pixels.fill((0, 0, 0))
        self.pixels.show()
