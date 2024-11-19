import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx

class SubprocessManager:
    """
    Manages subprocesses using threading.

    Attributes:
        stopped (bool): Indicates if the subprocess manager is stopped.
        cancel_event (threading.Event): Event to signal cancellation.
        busy_event (threading.Event): Event to signal busy state.
        threads (list): List of threads for the subprocesses.
    """

    def __init__(self, coros):
        """
        Initializes the SubprocessManager class.

        Args:
            coros (list): List of coroutine functions to be run in threads.
        """
        self.stopped = False
        self.cancel_event = threading.Event()
        self.busy_event = threading.Event()
        self.threads = [threading.Thread(target=coro, kwargs={'cancel_event': self.cancel_event, 'busy_event': self.busy_event}) for coro in coros]

    def start(self):
        """
        Starts all threads and adds them to the Streamlit script run context.
        """
        self.cancel_event.clear()
        for thread in self.threads:
            thread.start()
            add_script_run_ctx(thread)

    def stop(self):
        """
        Sets the cancel event to stop all threads.
        """
        self.cancel_event.set()