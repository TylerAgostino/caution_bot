import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx


class SubprocessManager:
    def __init__(self, coros):
        self.stopped = False
        self.cancel_event = threading.Event()
        self.busy_event = threading.Event()
        kwargs = {'cancel_event': self.cancel_event, 'busy_event': self.busy_event}
        self.threads = [threading.Thread(target=coro, kwargs=kwargs) for coro in coros]

    def start(self):
        self.cancel_event.clear()
        for thread in self.threads:
            t = thread.start()
            add_script_run_ctx(thread)
            add_script_run_ctx(t)

    def stop(self):
        self.cancel_event.set()
