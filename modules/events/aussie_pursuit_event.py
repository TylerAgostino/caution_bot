from modules.events import BaseEvent


class AussiePursuitEvent(BaseEvent):
    """Sends timed black-flag hold commands for an Aussie Pursuit format start.

    Iterates the pre-calculated penalty list and sends one !bl command per car,
    with a short delay between commands to avoid chat flooding. Intended to be
    triggered manually via the UI just before the race grid is released.
    """

    def __init__(self, penalty_commands: list[tuple], *args, **kwargs):
        """
        Args:
            penalty_commands: Ordered list of (car_number, hold) tuples where
                hold is either an int (seconds) or the string "D" (drive-through).
        """
        self.penalty_commands = penalty_commands
        super().__init__(*args, **kwargs)

    def event_sequence(self):
        self.logger.info(
            f"Aussie Pursuit: sending {len(self.penalty_commands)} penalty commands"
        )
        for car_number, hold in self.penalty_commands:
            self._chat(f"!bl {car_number} {hold}")
            self.sleep(0.5)
        self.logger.info("Aussie Pursuit: all penalties applied")
