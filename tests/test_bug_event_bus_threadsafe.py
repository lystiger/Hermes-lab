import asyncio
import threading
import pytest

from events.event_bus import RuntimeEventBus


class RecordingQueue(asyncio.Queue):
    """Queue wrapper recording the thread that calls put_nowait."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.put_threads = []

    def put_nowait(self, item):
        self.put_threads.append(threading.current_thread())
        return super().put_nowait(item)


@pytest.mark.anyio
async def test_publish_from_worker_thread_hands_off_to_subscriber_loop():
    bus = RuntimeEventBus()
    subscriber_loop = asyncio.get_running_loop()
    subscriber_thread = threading.current_thread()

    queue = RecordingQueue()
    bus.subscribe(queue)

    worker_error = None

    def worker():
        nonlocal worker_error
        try:
            bus.publish(
                source_id="worker",
                kind="test_event",
                detail="test_detail",
            )
        except Exception as e:
            worker_error = e

    worker_thread = threading.Thread(target=worker, name="worker-thread")
    worker_thread.start()
    worker_thread.join()

    if worker_error:
        raise worker_error

    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event.detail == "test_detail"

    assert len(queue.put_threads) == 1
    assert queue.put_threads[0] == subscriber_thread
