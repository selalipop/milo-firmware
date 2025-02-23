from abc import ABC, abstractmethod

class Display(ABC):
    @abstractmethod
    def show_spinner(self) -> None:
        pass

    def turn_off(self) -> None:
        pass
