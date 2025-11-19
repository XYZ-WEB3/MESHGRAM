from src.queue.delivery import DeliveryManager, MessageQueue, QueuedMessage


def test_queue_roundtrip() -> None:
    queue = MessageQueue()
    manager = DeliveryManager(queue, floodwait_threshold=2)
    message = QueuedMessage(payload="hello", direction="telegram", user_id="1")
    queue.enqueue_outbound(message)
    fetched = queue.next_outbound()
    assert fetched is not None
    manager.record_failure(fetched)
    assert len(queue.outbound) == 1
    assert manager.should_pause() is False
