import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx


class SubprocessManager:
    def __init__(self, coros):
        self.stopped = False
        for coro in coros:
            print(coro)
        self.threads = [threading.Thread(target=coro) for coro in coros]

    def start(self):
        for thread in self.threads:
            t = thread.start()
            add_script_run_ctx(thread)
            add_script_run_ctx(t)