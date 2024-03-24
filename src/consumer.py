import functools
import logging
import time

from pika.adapters.asyncio_connection import AsyncioConnection
from pika.spec import Basic, BasicProperties
from pika.exchange_type import ExchangeType
from pika.connection import Parameters
from pika.channel import Channel
from pika.frame import Method


LOG = logging.getLogger(__name__)


class Consumer:
    """
    RabbitMQ consumer that will handle unexpected interactions such as channel
    and connection closures.

    If RabbitMQ closes the connection, the class will stop and indicate that
    reconnection is necessary. There are limited reasons why the connection
    may be closed, which usually are tied to permission related issues or
    socket timeouts, which will be logged in the output.
    """

    def __init__(
        self,
        parameters: Parameters,
        exchange_name: str,
        exchange_type: ExchangeType,
        queue_name: str,
        routing_key: str,
    ):
        self.should_reconnect = False
        self.was_consuming = False

        self.__parameters = parameters
        self.__exchange_name = exchange_name
        self.__exchange_type = exchange_type
        self.__queue_name = queue_name
        self.__routing_key = routing_key

        self.__channel = None
        self.__connection = None
        self.__consumer_tag = None

        self.__consuming = False
        self.__closing = False

        self.__prefetch_count = 1

    def __connect(self) -> AsyncioConnection:
        """Establishes the connection to the RabbitMQ server."""

        LOG.info("Connecting to %s", self.__parameters.host)
        return AsyncioConnection(
            parameters=self.__parameters,
            on_open_error_callback=self.__on_connection_open_error,
            on_open_callback=self.__on_connection_open,
            on_close_callback=self.__on_connection_closed,
        )

    def __on_connection_open_error(self, _: AsyncioConnection, error: BaseException):
        """Called when the connection failed to open, triggering reconnection."""

        LOG.error("Connection open failed: %s", error)
        self.__reconnect()

    def __on_connection_open(self, _: AsyncioConnection):
        """Called when the connection is successfully opened."""

        LOG.info("Connection opened")
        self.__open_channel()

    def __on_connection_closed(self, _: AsyncioConnection, reason: BaseException):
        """
        Called when the connection is closed, either intentionally or
        unintentionally from connections issues.
        """

        self.__channel = None

        # Close event is coming from internal
        if self.__closing:
            self.__connection.ioloop.stop()

        # Close event is coming from unknown external reason
        else:
            LOG.warning("Connection closed, reconnect necessary: %s", reason)
            self.__reconnect()

    def __close_connection(self):
        """Closes the connection."""

        self.__consuming = False

        if self.__connection.is_closing or self.__connection.is_closed:
            LOG.info("Connection is closing or already closed")

        else:
            LOG.info("Closing connection")
            self.__connection.close()

    def __reconnect(self):
        """Requests for reconnection in case of connection closure."""

        self.should_reconnect = True
        self.stop()

    def __open_channel(self):
        """Opens a new channel on the established connection."""

        LOG.info("Creating a new channel")
        self.__connection.channel(on_open_callback=self.__on_channel_open)

    def __on_channel_open(self, channel: Channel):
        """Called when the channel is successfully opened."""

        LOG.info("Channel opened")
        self.__channel = channel
        self.__channel.add_on_close_callback(self.__on_channel_closed)

        self.__setup_exchange()

    def __on_channel_closed(self, channel: Channel, reason: BaseException):
        """Called when the channel is closed, triggering connection closure."""

        LOG.warning("Channel %i was closed: %s", channel, reason)
        self.__close_connection()

    def __setup_exchange(self):
        """Declares the exchange on the channel."""

        LOG.info("Declaring exchange: %s", self.__exchange_name)
        self.__channel.exchange_declare(
            exchange=self.__exchange_name,
            exchange_type=self.__exchange_type,
            callback=self.__on_exchange_declareok,
        )

    def __on_exchange_declareok(self, _: Method):
        """Called when the exchange is successfully declared."""

        LOG.info("Exchange declared: %s", self.__exchange_name)
        self.__setup_queue()

    def __setup_queue(self):
        """Declares the queue on the channel."""

        LOG.info("Declaring queue %s", self.__queue_name)
        self.__channel.queue_declare(
            queue=self.__queue_name, callback=self.__on_queue_declareok
        )

    def __on_queue_declareok(self, _: Method):
        """Called when the queue is successfully declared, binding the queue."""

        LOG.info(
            "Binding %s to %s with %s",
            self.__exchange_name,
            self.__queue_name,
            self.__routing_key,
        )

        self.__channel.queue_bind(
            self.__queue_name,
            self.__exchange_name,
            routing_key=self.__routing_key,
            callback=self.__on_bindok,
        )

    def __on_bindok(self, _: Method):
        """Called when the queue is successfully bound, spcifying  the qos."""

        LOG.info("Queue bound: %s", self.__queue_name)
        self.__set_qos()

    def __set_qos(self):
        """Specifies quality of service for the queue."""

        self.__channel.basic_qos(
            prefetch_count=self.__prefetch_count, callback=self.__on_basic_qos_ok
        )

    def __on_basic_qos_ok(self, _: Method):
        """Called when the QOS is accepted."""

        LOG.info("QOS set to: %d", self.__prefetch_count)
        self.__start_consuming()

    def __start_consuming(self):
        """Starts the consumption of messages from the queue."""

        LOG.info("Issuing consumer related RPC commands")

        self.__channel.add_on_cancel_callback(self.__on_consumer_cancelled)
        self.__consumer_tag = self.__channel.basic_consume(
            self.__queue_name, self.__on_message
        )

        self.was_consuming = True
        self.__consuming = True

    def __on_consumer_cancelled(self, method_frame: Method):
        """Called when the channel is closed remotely."""

        LOG.info("Consumer was cancelled remotely, shutting down: %r", method_frame)

        if self.__channel:
            self.__channel.close()

    def __on_message(
        self,
        _: Channel,
        basic_deliver: Basic.Deliver,
        properties: BasicProperties,
        body: bytes,
    ):
        """Called when a message is received from the queue."""

        LOG.info(
            "Received message # %s from %s: %s",
            basic_deliver.delivery_tag,
            properties.app_id,
            body,
        )
        self.__acknowledge_message(basic_deliver.delivery_tag)

    def __acknowledge_message(self, delivery_tag: int):
        """Acknowledges that a message has been received and processed."""

        LOG.info("Acknowledging message %s", delivery_tag)
        self.__channel.basic_ack(delivery_tag)

    def stop_consuming(self):
        """Stops the consumption of messages."""

        if self.__channel:
            LOG.info("Sending a Basic.Cancel RPC command to RabbitMQ")
            self.__channel.basic_cancel(self.__consumer_tag, self.__on_cancelok)

    def __on_cancelok(self, _: Method):
        """Called when the cancellation is accepted."""

        LOG.info(
            "RabbitMQ acknowledged the cancellation of the consumer: %s",
            self.__consumer_tag,
        )

        self.__consuming = False
        self.__close_channel()

    def __close_channel(self):
        """Closes the channel."""

        LOG.info("Closing the channel")
        self.__channel.close()

    def run(self):
        """Starts the consumer by connecting and entering the I/O loop."""

        self.__connection = self.__connect()
        self.__connection.ioloop.run_forever()

    def stop(self):
        """Stops the consumer and exits the I/O loop."""

        if self.__closing:
            return

        LOG.info("Stopping")
        self.__closing = True

        if self.__consuming:
            self.stop_consuming()
            self.__connection.ioloop.run_forever()

        else:
            self.__connection.ioloop.stop()

        LOG.info("Stopped")


class ReconnectingConsumer:
    """
    RabbitMQ consumer that automatically tries to reconnect on connection failures.

    This class wraps around the Consumer class, adding automatic reconnection logic.
    It handles the lifecycle of a RabbitMQ consumer, including starting, stopping,
    and managing reconnection attempts after unexpected issues.
    """

    def __init__(
        self,
        parameters: Parameters,
        exchange_name: str,
        exchange_type: ExchangeType,
        queue_name: str,
        routing_key: str,
    ):
        """
        Initializes the ReconnectingConsumer instance

        Args:
            parameters (Parameters): Configuration for the connection.
            exchange_name (str): The name of the exchange to use.
            exchange_type (ExchangeType): The type of exchange (direct, topic, etc.).
            queue_name (str): The name of the queue to bind to.
            routing_key (str): The routing key for message delivery.
        """
        self.__reconnect_delay = 0

        self.__parameters = parameters
        self.__exchange_name = exchange_name
        self.__exchange_type = exchange_type
        self.__queue_name = queue_name
        self.__routing_key = routing_key

        self.__consumer = Consumer(
            self.__parameters,
            self.__exchange_name,
            self.__exchange_type,
            self.__queue_name,
            self.__routing_key,
        )

    def run(self):
        """Starts the consumer process in a loop."""

        while True:
            try:
                self.__consumer.run()

            # Catches KeyboardInterrupt to allow for graceful shutdown.
            except KeyboardInterrupt:
                self.__consumer.stop()
                break

            # Check and handle reconnection logic if necessary.
            self.__maybe_reconnect()

    def __maybe_reconnect(self):
        """Reconnects with original parameters if necessary."""

        if self.__consumer.should_reconnect:
            # Stops the current consumer.
            self.__consumer.stop()

            # Waits for a calculated delay before reconnecting.
            reconnect_delay = self._get_reconnect_delay()
            LOG.info("Reconnecting after %d seconds", reconnect_delay)

            time.sleep(reconnect_delay)
            self.__consumer = Consumer(
                self.__parameters,
                self.__exchange_name,
                self.__exchange_type,
                self.__queue_name,
                self.__routing_key,
            )

    def _get_reconnect_delay(self):
        """
        Calculates the delay before attempting to reconnect. The delay is
        increased based on each failed attempt, up to a maximum limit.
        """

        if self.__consumer.was_consuming:
            self.__reconnect_delay = 0
        else:
            self.__reconnect_delay += 1

        if self.__reconnect_delay > 30:
            self.__reconnect_delay = 30

        return self.__reconnect_delay
