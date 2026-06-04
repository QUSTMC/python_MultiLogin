import asyncio
import threading
from concurrent.futures import Future

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None


def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def start_loop() -> None:
    global _loop, _thread
    if _loop is not None:
        return
    _loop = asyncio.new_event_loop()
    _thread = threading.Thread(target=_run_loop, args=(_loop,), daemon=True)
    _thread.start()


def stop_loop() -> None:
    global _loop, _thread
    if _loop is None:
        return
    _loop.call_soon_threadsafe(_loop.stop)
    if _thread:
        _thread.join(timeout=5)
    _loop.close()
    _loop = None
    _thread = None


def run_async(coro) -> any:
    if _loop is None or _loop.is_closed():
        start_loop()
    future: Future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=60)
