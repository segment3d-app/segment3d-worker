import logging
import os

from dotenv import load_dotenv

import pika
from pika.exchange_type import ExchangeType

from src.consumer import ReconnectingConsumer


def main():
    credentials = pika.PlainCredentials(os.getenv("RABBITMQ_USER"),
                                        os.getenv("RABBITMQ_PASSWORD"))

    parameters = pika.ConnectionParameters(host=os.getenv("RABBITMQ_HOST"),
                                           port=os.getenv("RABBITMQ_PORT"),
                                           credentials=credentials)

    consumer = ReconnectingConsumer(parameters=parameters,
                                    exchange_name="test",
                                    exchange_type=ExchangeType.direct,
                                    queue_name="test",
                                    routing_key="test")
    consumer.run()


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s]: (%(name)s) %(message)s")

    main()
