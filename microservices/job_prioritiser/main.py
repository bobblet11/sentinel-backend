import datetime

from common.models.api.redis_models import Message, MessageHeader, MessageURLPayload
from .config import INPUT_STREAMS, OUTPUT_STREAM, GROUP_NAME, PRIORITY_MAP, LOWEST_PRIORITY
from common.redis_client.consumer_combiner import RedisConsumerCombiner
from common.redis_client.publisher import RedisPublisher

# message_dict = {
#     'stream': stream_name.decode('utf-8'),
#     'redis_message_id': redis_message_id.decode('utf-8'),
#     'data': message_data
# }

BATCH_SIZE = 10

def prioritize_messages(messages: list) -> list:
    """
    Sorts a list of message dictionaries based on the PRIORITY_MAP.
    """
    def get_priority(message):
        message_type = message.get('data', {}).get('type')
        return PRIORITY_MAP.get(message_type, LOWEST_PRIORITY)
    return sorted(messages, key=get_priority)


def exec():
    """
    Main execution loop. Fetches a batch of messages, prioritizes them,
    and then processes them one by one.
    """
    print(INPUT_STREAMS)
    combiner = RedisConsumerCombiner(streams=INPUT_STREAMS, group_name=GROUP_NAME)
    publisher = RedisPublisher(stream_name=OUTPUT_STREAM)

    while True:
        print(f"[{datetime.datetime.now()}] Waiting for up to {BATCH_SIZE} messages...")
        messages = combiner.consume_many(num_to_consume=BATCH_SIZE, block=0)
        
        if not messages:
            continue
        print(f"--> Fetched {len(messages)} messages. Prioritizing...")
        
        
        prioritized_messages = prioritize_messages(messages)
        print(f"--> Messages are in priority order. Publishing")

   
        for message in prioritized_messages:
            stream = message['stream']
            redis_msg_id = message['redis_message_id']
            message_data = message['data']
            if not publisher.publish_one(message_data):
                print(f"Failed to publish {redis_msg_id}. Skipping...")
                continue
            combiner.acknowledge(stream, redis_msg_id)
            print(f"  - Acknowledged Msg ID {redis_msg_id}")


if __name__ == "__main__":
    print(f"\n\nmain.py is being run. It is currently {datetime.datetime.now()}")
    try:
        exec()
    except KeyboardInterrupt:
        print("\n\nShutdown signal received.")
    finally:
        print(f"\n\nmain.py is finished. It is currently {datetime.datetime.now()}")
