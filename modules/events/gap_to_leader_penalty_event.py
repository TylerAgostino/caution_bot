from modules.events import BaseEvent


class GapToLeaderPenaltyEvent(BaseEvent):
    """
    An event which penalizes drivers who fall more than a specified gap behind the leader.

    This class monitors cars that are falling too far behind the leader. When a car's gap
    exceeds the specified threshold, a penalty is issued via text chat.

    Attributes:
        gap_to_leader (float): Maximum allowed gap in seconds to the leader before a penalty is issued.
        penalty (str): The penalty to issue when a car exceeds the gap threshold.
        sound (bool): If True, plays a sound when a penalty is issued.

    The gap is calculated based on total race time, not lap times.
    Cars that receive a penalty are considered out of the race and won't receive additional penalties.
    Cars that reach 75% of the penalty gap will receive a warning message.
    """

    def __init__(
        self,
        gap_to_leader: float = 60.0,
        penalty: str = "4120",
        sound: bool = True,
    ):
        """
        Initializes the GapToLeaderPenaltyEvent class.

        Args:
            gap_to_leader (float): Maximum allowed gap in seconds to the leader before a penalty is issued.
            penalty (str): The penalty to issue when a car exceeds the gap threshold.
            sound (bool): If True, plays a sound when a penalty is issued.
        """
        self.gap_to_leader = float(gap_to_leader)
        self.penalty = penalty
        self.penalized = []
        self.sound = sound
        super().__init__()

    @staticmethod
    def ui(ident=""):
        """
        UI for the GapToLeaderPenaltyEvent.
        """
        import streamlit as st

        col1, col2, col3 = st.columns(3)
        return {
            "gap_to_leader": col1.number_input(
                "Gap to Leader (sec)", value=60.0, key=f"{ident}gap_to_leader"
            ),
            "sound": col2.checkbox("Sound", value=True, key=f"{ident}sound"),
        }

    def event_sequence(self):
        """
        Monitors cars' gaps to the leader and applies penalties to any car that exceeds the threshold.
        """
        next_tone = None
        laps_complete = 0
        while True:
            for car in self.get_current_running_order():
                if car['f2time'] == 0 and car['LapCompleted'] > laps_complete:
                    laps_complete = car['LapCompleted']
                    self.audio_queue.put("pacer1") if self.sound else None
                    next_tone = self.sdk['SessionTime'] + self.gap_to_leader

                if car['f2time'] > self.gap_to_leader and car['CarIdx'] not in self.penalized:
                    self.penalized.append(car['CarIdx'])
                    self._chat(f'!bl {car["CarNumber"]} {self.penalty}')
                    self.audio_queue.put('penalty')  if self.sound else None

            if next_tone and next_tone <= self.sdk['SessionTime']:
                self.audio_queue.put("pacer2") if self.sound else None
                next_tone = None

            self.sleep(0.1)
