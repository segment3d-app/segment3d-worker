
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
    def __init__(self, parameters: Parameters, exchange_name: str, exchange_type: ExchangeType, queue_name: str, routing_key: str):
        self.should_reconnect = False
        self.was_consuming = False

        self._parameters = parameters
        self._exchange_name = exchange_name
        self._exchange_type = exchange_type
        self._queue_name = queue_name
        self._routing_key = routing_key

        self._channel = None
        self._connection = None
        self._consumer_tag = None

        self._consuming = False
        self._closing = False

        self._prefetch_count = 1

    def connect(self) -> AsyncioConnection:
        LOG.info('Connecting to %s', self._parameters.host)
        return AsyncioConnection(
            parameters=self._parameters,
            on_open_error_callback=self.on_connection_open_error,
            on_open_callback=self.on_connection_open,
            on_close_callback=self.on_connection_closed)

    def on_connection_open_error(self, _: AsyncioConnection, error: BaseException):
        LOG.error('Connection open failed: %s', error)
        self.reconnect()

    def on_connection_open(self, _: AsyncioConnection):
        LOG.info('Connection opened')
        self.open_channel()

    def on_connection_closed(self, _: AsyncioConnection, reason: BaseException):
        self._channel = None

        # Close event is coming from internal
        if self._closing:
            self._connection.ioloop.stop()

        # Close event is coming from unknown external reason
        else:
            LOG.warning(
                'Connection closed, reconnect necessary: %s', reason)
            self.reconnect()

    def close_connection(self):
        self._consuming = False
        if self._connection.is_closing or self._connection.is_closed:
            LOG.info('Connection is closing or already closed')
        else:
            LOG.info('Closing connection')
            self._connection.close()

    def reconnect(self):
        self.should_reconnect = True
        self.stop()

    def open_channel(self):
        LOG.info('Creating a new channel')
        self._connection.channel(on_open_callback=self.on_channel_open)

    def on_channel_open(self, channel: Channel):
        LOG.info('Channel opened')
        self._channel = channel
        self._channel.add_on_close_callback(self.on_channel_closed)

        self.setup_exchange(self._exchange_name)

    def on_channel_closed(self, channel: Channel, reason: BaseException):
        LOG.warning('Channel %i was closed: %s', channel, reason)
        self.close_connection()

    def setup_exchange(self, exchange_name: str):
        LOG.info('Declaring exchange: %s', exchange_name)

        callback = functools.partial(
            self.on_exchange_declareok, exchange_name=exchange_name)
        self._channel.exchange_declare(
            exchange=exchange_name,
            exchange_type=self._exchange_type,
            callback=callback)

    def on_exchange_declareok(self, _: Method, exchange_name: str):
        LOG.info('Exchange declared: %s', exchange_name)
        self.setup_queue(self._queue_name)

    def setup_queue(self, queue_name: str):
        LOG.info('Declaring queue %s', queue_name)

        callback = functools.partial(
            self.on_queue_declareok, queue_name=queue_name)
        self._channel.queue_declare(queue=queue_name, callback=callback)

    def on_queue_declareok(self, _: Method, queue_name: str):
        LOG.info('Binding %s to %s with %s', self._exchange_name,
                 queue_name, self._routing_key)

        callback = functools.partial(self.on_bindok, queue_name=queue_name)
        self._channel.queue_bind(
            queue_name,
            self._exchange_name,
            routing_key=self._routing_key,
            callback=callback)

    def on_bindok(self, _: Method, queue_name: str):
        LOG.info('Queue bound: %s', queue_name)
        self.set_qos()

    def set_qos(self):
        self._channel.basic_qos(
            prefetch_count=self._prefetch_count, callback=self.on_basic_qos_ok)

    def on_basic_qos_ok(self, _: Method):
        LOG.info('QOS set to: %d', self._prefetch_count)
        self.start_consuming()

    def start_consuming(self):
        LOG.info('Issuing consumer related RPC commands')

        self._channel.add_on_cancel_callback(self.on_consumer_cancelled)
        self._consumer_tag = self._channel.basic_consume(
            self._queue_name, self.on_message)

        self.was_consuming = True
        self._consuming = True

    def on_consumer_cancelled(self, method_frame: Method):
        LOG.info('Consumer was cancelled remotely, shutting down: %r',
                 method_frame)

        if self._channel:
            self._channel.close()

    def on_message(self, _: Channel, basic_deliver: Basic.Deliver, properties: BasicProperties, body: bytes):
        LOG.info('Received message # %s from %s: %s',
                 basic_deliver.delivery_tag, properties.app_id, body)
        self.acknowledge_message(basic_deliver.delivery_tag)

    def acknowledge_message(self, delivery_tag: int):
        LOG.info('Acknowledging message %s', delivery_tag)
        self._channel.basic_ack(delivery_tag)

    def stop_consuming(self):
        if self._channel:
            LOG.info('Sending a Basic.Cancel RPC command to RabbitMQ')

            callback = functools.partial(
                self.on_cancelok, consumer_tag=self._consumer_tag)
            self._channel.basic_cancel(self._consumer_tag, callback)

    def on_cancelok(self, _: Method, consumer_tag: str):
        LOG.info(
            'RabbitMQ acknowledged the cancellation of the consumer: %s',
            consumer_tag)

        self._consuming = False
        self.close_channel()

    def close_channel(self):
        LOG.info('Closing the channel')
        self._channel.close()

    def run(self):
        self._connection = self.connect()
        self._connection.ioloop.run_forever()

    def stop(self):
        if self._closing:
            return

        LOG.info('Stopping')
        self._closing = True

        if self._consuming:
            self.stop_consuming()
            self._connection.ioloop.run_forever()

        else:
            self._connection.ioloop.stop()

        LOG.info('Stopped')


class ReconnectingConsumer:
    def __init__(self, parameters: Parameters, exchange_name: str, exchange_type: ExchangeType, queue_name: str, routing_key: str):
        self._reconnect_delay = 0

        self._parameters = parameters
        self._exchange_name = exchange_name
        self._exchange_type = exchange_type
        self._queue_name = queue_name
        self._routing_key = routing_key

        self._consumer = Consumer(self._parameters, self._exchange_name,
                                  self._exchange_type, self._queue_name, self._routing_key)

    def run(self):
        while True:
            try:
                self._consumer.run()
            except KeyboardInterrupt:
                self._consumer.stop()
                break
            self._maybe_reconnect()

    def _maybe_reconnect(self):
        if self._consumer.should_reconnect:
            self._consumer.stop()

            reconnect_delay = self._get_reconnect_delay()
            LOG.info('Reconnecting after %d seconds', reconnect_delay)

            time.sleep(reconnect_delay)
            self._consumer = Consumer(self._parameters, self._exchange_name,
                                      self._exchange_type, self._queue_name, self._routing_key)

    def _get_reconnect_delay(self):
        if self._consumer.was_consuming:
            self._reconnect_delay = 0
        else:
            self._reconnect_delay += 1

        if self._reconnect_delay > 30:
            self._reconnect_delay = 30

        return self._reconnect_delay
