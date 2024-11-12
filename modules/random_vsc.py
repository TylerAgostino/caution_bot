from modules.random_caution import RandomCaution


class RandomVSC(RandomCaution):
    def __init__(self, *args, **kwargs):
        self.active_vsc = False
        super().__init__(*args, **kwargs)

    def event_sequence(self):
        if self.is_caution_active() or self.active_vsc:
            if self.notify_on_skipped_caution:
                self._chat('Additional caution skipped due to active caution.')
            return

        self.active_vsc = True

        # wait for the leader to reach a certain point on the track

        # announce the VSC

        # capture the current positions

        # if cars pit, move them in the captured order to where they came out
        # make sure they didn't gain any positions before entering the pits

        # wait for all cars to be within a certain distance of the leader, or the manual override

        # announce the end of the VSC

        self.active_vsc = False
