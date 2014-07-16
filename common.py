from __future__ import unicode_literals

import socket
from itertools import chain
from sys import stderr


MAP = 0x40
END = 0x80


class SocketWrapper(object):
    def __init__(self, sock, waiting_to_send, waiting_to_receive):
        self.sock = sock
        self.waiting_to_send = waiting_to_send
        self.waiting_to_receive = waiting_to_receive
        self.msg = b''

    def send_message(self, *items, **dictionary):
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
            if isinstance(item, unicode):
                item = item.encode('utf_8')
            self.msg += encode_length(len(item), length_bytes) + item

        first = True
        for key, value in dictionary.iteritems():
            if isinstance(key, unicode):
                key = key.encode('utf_8')
            if isinstance(value, unicode):
                value = value.encode('utf_8')
            self.msg += encode_length(len(key), length_bytes,
                                      MAP if first else 0) + key
            self.msg += encode_length(len(value), length_bytes) + value
            first = False

        return self.continue_send()


    def continue_send(self, block=False):
        print repr(self.msg)

        if not self.msg:
            return

        if block:
            self.sock.sendall(self.msg)
            return

        sent = self.sock.send(self.msg)
        self.msg = self.msg[sent:]

        if self.msg:
            self.waiting_to_send[sock.fileno()] = self
            return False
        else:
            self.waiting_to_send.pop(sock.fileno(), None)
            return True

    def receive_message_generator(self, items, arguments):
        length_bytes = bytearray()
        for _ in self.receive_bytes(1, into=length_bytes):
            yield
        length_bytes = length_bytes[0]

        while True:
            first_byte = bytearray()
            for _ in self.peek_at_bytes(1, into=first_byte):
                yield
            if first_byte[0] & MAP:
                break
            elif first_byte[0] & END:
                raise StopIteration

            item_bytes = bytearray()
            for _ in self.receive_bytes(length_bytes, into=item_bytes):
                yield
            item_bytes = decode_length(item_bytes, length_bytes)

            item = bytearray()
            for _ in self.receive_bytes(item_bytes, into=item):
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
            arguments[pair[0]] = pair[1]

        raise StopIteration

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
    length = 0
    flags = encoded[0] & (MAP | END)
    length = encoded[0] & ~(MAP | END)
    for i in range(1, length_bytes):
        length <<= 8
        length += encoded[i]

    return length, flags
