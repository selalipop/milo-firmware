from abc import ABC, abstractmethod

class Display(ABC):
    @abstractmethod
    async def show_spinner(self) -> None:
        pass

    async def turn_off(self) -> None:
        pass
