from display import Display


class CliDisplay(Display):
    def __init__(self):
        pass

    async def show_spinner(self) -> None:
        print("Showing spinner")

    async def turn_off(self) -> None:
        print("Turning off")
