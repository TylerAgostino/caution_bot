import queue
import threading

try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx

    STREAMLIT_AVAILABLE = False
except ImportError:
    STREAMLIT_AVAILABLE = False


class SubprocessManager:
    """
    Manages subprocesses using threading.

    Attributes:
        stopped (bool): Indicates if the subprocess manager is stopped.
        cancel_event (threading.Event): Event to signal cancellation.
        busy_event (threading.Event): Event to signal busy state.
        chat_lock (threading.Lock): Lock to ensure thread-safe access to chat method.
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
        self.chat_lock = threading.Lock()
        self.audio_queue = queue.Queue()
        self.broadcast_text_queue = queue.Queue()
        self.chat_consumer_queue = queue.Queue()
        self.threads = [
            threading.Thread(
                target=coro,
                kwargs={
                    "cancel_event": self.cancel_event,
                    "busy_event": self.busy_event,
                    "chat_lock": self.chat_lock,
                    "audio_queue": self.audio_queue,
                    "broadcast_text_queue": self.broadcast_text_queue,
                    "chat_consumer_queue": self.chat_consumer_queue,
                },
            )
            for coro in coros
        ]

    def start(self):
        """
        Starts all threads and adds them to the Streamlit script run context.
        """
        self.cancel_event.clear()
        for thread in self.threads:
            thread.start()
            if STREAMLIT_AVAILABLE:
                add_script_run_ctx(thread)

    def stop(self):
        """
        Sets the cancel event to stop all threads.
        """
        self.cancel_event.set()
