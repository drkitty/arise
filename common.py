from __future__ import unicode_literals

import select
import socket
from itertools import chain
from sys import stderr


OBJECT = 0x20
MAP = 0x40
END = 0x80


class PollWrapper(object):
    def __init__(self):
        self.fds = {}
        self.poll_object = select.poll()

    def register(self, fd, eventmask=0):
        self.poll_object.register(fd, eventmask)
        self.fds[fd] = eventmask

    def modify(self, fd, eventmask=0):
        self.poll_object.modify(fd, eventmask)
        self.fds[fd] = eventmask

    def extend(self, fd, eventmask):
        new = self.fds[fd] | eventmask
        self.poll_object.register(fd, new)
        self.fds[fd] = new

    def remove(self, fd, eventmask):
        if fd not in self.fds:
            return
        new = self.fds[fd] & ~eventmask
        self.poll_object.modify(fd, new)
        self.fds[fd] = new

    def unregister(self, fd):
        self.poll_object.unregister(fd)
        self.fds.pop(fd, None)

    def poll(self, timeout=None):
        return self.poll_object.poll(timeout)


class SocketWrapper(object):
    """
    (This class is not thread-safe, for what should be obvious reasons.)
    """

    receive_message_g = None

    def __init__(self, sock, poller):
        self.sock = sock
        self.poller = poller
        self.msg = b''

        self.poller.register(self.sock.fileno(), select.POLLHUP)

    def close(self):
        self.poller.unregister(self.sock.fileno())
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()

    def send_message_generator(self, message):
        while True:
            sent = self.sock.send(message)
            message = message[sent:]
            if not message:
                yield True

    def prepare_send_message(self, *items, **dictionary):
        message = format_message(*items, **dictionary)

        print 'About to send message {}'.format(repr(message))
        self.send_message_g = self.send_message_generator(message)
        self.poller.extend(self.sock.fileno(), select.POLLOUT)

    def send_message(self):
        ret = next(self.send_message_g)
        if ret is not None:
            self.poller.remove(self.sock.fileno(), select.POLLOUT)
            del self.send_message_g
            return True

    def receive_message_generator(self, old_g):
        def receive_thing():
            thing_length = bytearray()
            for _ in self.receive_bytes(length_length, into=thing_length):
                yield
            thing_length, flags = decode_length(thing_length, length_length)

            if flags & OBJECT:
                self.prepare_receive_message()
                while True:
                    message = self.receive_message()
                    if message is not None:
                        self.receive_message_g = old_g
                        yield message
                    yield
            else:
                thing = bytearray()
                for _ in self.receive_bytes(thing_length, into=thing):
                    yield
                thing = thing.decode('utf_8')
                yield thing

        message = ([], {})

        length_length = bytearray()
        for _ in self.receive_bytes(1, into=length_length):
            yield
        length_length = length_length[0]

        while True:
            first_byte = bytearray()
            for _ in self.peek_at_bytes(1, into=first_byte):
                yield
            if first_byte[0] & MAP:
                break
            elif first_byte[0] & END:
                next(self.receive_bytes(1, into=first_byte), None)
                self.receive_message_g = old_g
                yield message

            receive_thing_g = receive_thing()
            while True:
                ret = next(receive_thing_g)
                if ret is not None:
                    break
                yield
            message[0].append(ret)

        while True:
            first_byte = bytearray()
            for _ in self.peek_at_bytes(1, into=first_byte):
                yield
            if first_byte[0] & END:
                next(self.receive_bytes(1, into=first_byte), None)
                self.receive_message_g = old_g
                yield message

            pair = []
            for i in range(2):
                receive_thing_g = receive_thing()
                while True:
                    ret = next(receive_thing_g)
                    if ret is not None:
                        break
                    yield
                pair.append(ret)
            message[1][pair[0]] = pair[1]

    def prepare_receive_message(self):
        self.receive_message_g = self.receive_message_generator(
            self.receive_message_g)
        self.poller.extend(self.sock.fileno(), select.POLLIN)

    def receive_message(self):
        ret = next(self.receive_message_g)
        if ret is not None:
            if not self.receive_message_g:  # Outer level just finished.
                self.poller.remove(self.sock.fileno(), select.POLLIN)
            items, dictionary = ret
            return items, dictionary

    def receive_bytes(self, count, into):
        msg = b''
        while True:
            msg += self.sock.recv(count - len(msg))
            if len(msg) >= count:
                into += msg
                raise StopIteration
            yield

    def peek_at_bytes(self, count, into):
        while True:
            chunk = self.sock.recv(count, socket.MSG_PEEK)
            if len(chunk) >= count:
                into += chunk
                raise StopIteration
            yield


def format_message(*items, **dictionary):
    length_choices = (
        [len(item) for item in items] +
        [max(len(k), len(v)) for k, v in dictionary.iteritems()])
    max_length = max(length_choices) if length_choices else 0

    length_bits = 0
    while max_length > 0:
        max_length >>= 1
        length_bits += 1
    length_bytes = (length_bits + 7 + 3) / 8  # 3 reserved bits

    message = bytearray(chr(length_bytes))

    for item in items:
        if isinstance(item, tuple):
            message += encode_length(0, length_bytes, flags=OBJECT)
            message += format_message(*item[0], **item[1])
        else:
            item = item.encode('utf_8')
            message += encode_length(len(item), length_bytes) + item

    first = True
    for key, value in dictionary.iteritems():
        if isinstance(key, tuple):
            message += encode_length(0, length_bytes,
                                     OBJECT | (MAP if first else 0))
            message += format_message(*key[0], **key[1])
        else:
            key = key.encode('utf_8')
            message += encode_length(len(key), length_bytes,
                                     MAP if first else 0) + key

        if isinstance(value, tuple):
            message += encode_length(0, length_bytes, OBJECT)
            message += format_message(*value[0], **value[1])
        else:
            value = value.encode('utf_8')
            message += encode_length(len(value), length_bytes) + value

        first = False

    message += chr(END)

    return bytes(message)


def encode_length(length, length_bytes, flags=0):
    encoded = b''
    for i in range(length_bytes - 1):
        encoded += chr(length % 256)
        length >>= 8
    encoded += chr(length | flags)
    return encoded[::-1]


def decode_length(encoded, length_bytes):
    flags = encoded[0] & (OBJECT | MAP)
    length = encoded[0] & ~(OBJECT | MAP)
    for i in range(1, length_bytes):
        length <<= 8
        length += encoded[i]
    return length, flags
