import datetime
import time
from .config import INPUT_STREAMS, GROUP_NAME, PRIORITY_MAP, LOWEST_PRIORITY
from common.redis_client.consumer_combiner import RedisConsumerCombiner

# How many messages to pull from Redis at once.
# A larger batch size allows for more effective prioritization.
BATCH_SIZE = 10

def prioritize_messages(messages: list) -> list:
    """
    Sorts a list of message dictionaries based on the PRIORITY_MAP.
    """
    # The 'key' for sorting is a function that returns the priority value.
    # We look inside the message's 'data' for a 'type' field.
    # If the type isn't in our map or doesn't exist, it gets the lowest priority.
    def get_priority(message):
        message_type = message.get('data', {}).get('type')
        return PRIORITY_MAP.get(message_type, LOWEST_PRIORITY)

    return sorted(messages, key=get_priority)


def exec():
    """
    Main execution loop. Fetches a batch of messages, prioritizes them,
    and then processes them one by one.
    """
    combiner = RedisConsumerCombiner(streams=INPUT_STREAMS, group_name=GROUP_NAME)
    print("\nStarting continuous listening loop...")

    while True:
        print(f"[{datetime.datetime.now()}] Waiting for up to {BATCH_SIZE} messages...")
        # Step 1: Fetch a batch of messages. Use consume_many.
        # We use a small block timeout (e.g., 2000ms) so the loop can
        # feel responsive, or block=0 to wait forever for the first message.
        messages = combiner.consume_many(num_to_consume=BATCH_SIZE, block=0)

        if not messages:
            # If we timed out, the loop just continues and tries again.
            continue

        print(f"--> Fetched {len(messages)} messages. Prioritizing...")
        print(messages)
        return
        # Step 2: Prioritize the fetched messages using our sorting logic.
        prioritized_messages = prioritize_messages(messages)

        print(f"--> Processing {len(prioritized_messages)} messages in priority order...")

        # Step 3: Process the messages in their new, sorted order.
        for message in prioritized_messages:
            stream = message['stream']
            msg_id = message['message_id']
            data = message['data']
            msg_type = data.get('type', 'N/A')

            print(f"  - Processing Msg ID {msg_id} (Type: {msg_type}) from stream '{stream}'")
            
            # --- YOUR BUSINESS LOGIC GOES HERE ---
            # For example, call a function based on message type.
            time.sleep(0.5) # Simulate work

            # Step 4: Acknowledge the message only after it's been successfully processed.
            combiner.acknowledge(stream, msg_id)
            print(f"  - Acknowledged Msg ID {msg_id}")


if __name__ == "__main__":
    print(f"\n\nmain.py is being run. It is currently {datetime.datetime.now()}")
    try:
        exec()
    except KeyboardInterrupt:
        print("\n\nShutdown signal received.")
    finally:
        print(f"\n\nmain.py is finished. It is currently {datetime.datetime.now()}")
