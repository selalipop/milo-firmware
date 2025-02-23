from display import Display


class CliDisplay(Display):
    def __init__(self):
        pass

    def show_spinner(self) -> None:
        print("Showing spinner")

    def turn_off(self) -> None:
        print("Turning off")
