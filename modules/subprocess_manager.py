import queue
import threading


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
        Starts all threads.
        """
        self.cancel_event.clear()
        for thread in self.threads:
            thread.start()

    def stop(self):
        """
        Sets the cancel event to stop all threads.
        """
        self.cancel_event.set()

        # send sigterm to any threads that remain
        # Wait for threads to finish gracefully
        for thread in self.threads:
            thread.join(timeout=10)
        # Forcibly kill any threads that are still alive
        for thread in self.threads:
            if thread.is_alive():
                try:
                    import ctypes

                    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                        ctypes.c_long(thread.ident), ctypes.py_object(SystemExit)
                    )
                    if res == 0:
                        raise ValueError("Thread id not found")
                    elif res > 1:
                        # If it returns a number greater than one, we're in trouble, so reset
                        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, 0)
                        raise SystemError("PyThreadState_SetAsyncExc failed")
                except Exception as e:
                    print(f"Failed to forcibly kill thread {thread.name}: {e}")
