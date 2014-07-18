from __future__ import unicode_literals

import select
import socket
from itertools import chain
from sys import stderr


MAP = 0x40
END = 0x80


class PollWrapper(object):
    def __init__(self):
        self.fds = {}
        self.poll = select.poll()

    def register(self, fd, eventmask=0):
        self.poll.register(fd, eventmask)
        self.fds[fd] = eventmask

    def modify(self, fd, eventmask=0):
        self.poll.modify(fd, eventmask)
        self.fds[fd] = eventmask

    def extend(self, fd, eventmask):
        new = self.fds[fd] | eventmask
        self.poll.register(fd, new)
        self.fds[fd] = new

    def remove(self, fd, eventmask):
        if fd not in self.fds:
            return
        new = self.fds[fd] & ~eventmask
        self.poll.modify(fd, new)
        self.fds[fd] = new

    def unregister(self, fd):
        self.poll.unregister(fd)
        self.fds.pop(fd, None)

    def poll(self, timeout=None):
        return self.poll.poll(timeout)


class SocketWrapper(object):
    """
    (This class is not thread-safe, for what should be obvious reasons.)

    To send, call setup_send_message, then call send_message until it
    returns True.

    To receive, call receive_message until it doesn't return None.
    """

    receiver = None

    def __init__(self, sock, poller):
        self.sock = sock
        self.poller = poller
        self.msg = b''

        self.poller.register(self.sock.fileno(),
                             select.POLLIN | select.POLLHUP)

    def close(self):
        self.poller.unregister(fd)
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()

    def prepare_send(self, *items, **dictionary):
        max_length = max(chain(
            (len(item) for item in items),
            (len(k) + len(v) for k, v in dictionary.iteritems())
        ))

        length_bits = 0
        while max_length > 0:
            max_length >>= 1
            length_bits += 1
        length_bytes = (length_bits + 7 + 3) / 8  # 3 reserved bits

        self.msg += chr(length_bytes)

        for item in items:
            item = item.encode('utf_8')
            self.msg += encode_length(len(item), length_bytes) + item

        first = True
        for key, value in dictionary.iteritems():
            key = key.encode('utf_8')
            value = value.encode('utf_8')
            self.msg += encode_length(len(key), length_bytes,
                                      MAP if first else 0) + key
            self.msg += encode_length(len(value), length_bytes) + value
            first = False

        self.poller.extend(self.sock.fd, select.POLLOUT)

    def send_message(self, block=False):
        if not self.msg:
            return True

        if block:
            self.sock.sendall(self.msg)
            return True

        sent = self.sock.send(self.msg)
        self.msg = self.msg[sent:]

        if self.msg:
            self.poller.extend(self.sock.fd, select.POLLOUT)
            return
        else:
            self.poller.remove(self.sock.fd, select.POLLOUT)
            return True

    def receive_message_generator(self, items, dictionary):
        length_length = bytearray()
        for _ in self.receive_bytes(1, into=length_length):
            yield
        length_length = length_length[0]

        while True:
            item_length = bytearray()
            for _ in self.receive_bytes(1, into=item_length):
                yield
            if item_length[0] & MAP:
                break
            elif item_length[0] & END:
                raise StopIteration

            for _ in self.receive_bytes(length_length - 1, into=item_length):
                yield
            item_length = decode_length(item_length, length_length)

            item = bytearray()
            for _ in self.receive_bytes(item_length, into=item):
                yield
            items += item.decode('utf_8')

        while True:
            first_byte = bytearray()
            for _ in self.peek_at_bytes(1, into=first_byte):
                yield
            if first_byte[0] & END:
                raise StopIteration

            pair = (bytearray(), bytearray())
            for i in range(2):
                thing_bytes = bytearray()
                for _ in self.receive_bytes(length_bytes, into=thing_bytes):
                    yield
                thing_bytes = decode_length(thing_bytes, length_bytes)

                for _ in self.receive_bytes(key_bytes, into=pair[i]):
                    yield
                pair[i] = pair[i].decode('utf_8')
            dictionary[pair[0]] = pair[1]

        raise StopIteration

    def receive_message(self):
        if not self.receiver:
            self.received_items = []
            self.received_dictionary = {}
            self.receiver = self.receive_message_generator(
                self.received_items, self.received_dictionary)

        if next(self.receiver, True):
            self.receiver = None
            items = self.received_items
            dictionary = self.received_dictionary
            del self.received_items
            del self.received_dictionary

            return items, dictionary

    def receive_bytes(self, count, into):
        while True:
            into += self.sock.recv(count - len(msg))
            if len(into) >= count:
                raise StopIteration
            yield

    def peek_at_bytes(self, count, into):
        while True:
            chunk = self.sock.recv(count, socket.MSG_PEEK)
            if len(chunk) >= count:
                into += chunk
                raise StopIteration
            yield


def encode_length(length, length_bytes, flags=0):
    encoded = b''
    for i in range(length_bytes - 1):
        encoded += chr(length % 256)
        length >>= 8
    encoded += chr(length | flags)
    return encoded[::-1]


def decode_length(encoded, length_bytes):
    length = encoded[0] & ~(MAP | END)
    for i in range(1, length_bytes):
        length <<= 8
        length += encoded[i]
    return length
