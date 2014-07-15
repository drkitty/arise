from __future__ import unicode_literals

import socket
from itertools import chain


FIRST_ITEM = 0x80
FIRST_ARG = 0x40
END = 0xC0


def SocketWrapper(object):
    def __init__(self, sock, waiting_to_send, waiting_to_receive):
        self.sock = sock
        self.waiting_to_send = waiting_to_send
        self.waiting_to_receive = waiting_to_receive
        self.msg = b''

    def send(self, msg=None):
        if msg is not None:
            self.msg += msg
        sent = self.sock.send(self.msg)
        self.msg = self.msg[sent:]

        if sent < len(self.msg):
            if fd not in self.waiting_to_send:
                self.waiting_to_send[sock.fileno()] = self
            return False
        else:
            self.waiting_to_send.pop(sock.fileno(), None)
            return True

    # FIXME: Implement me!
    def receive(self, count):
        pass


def encode_length(length, length_bytes, flags=0):
    encoded = b''
    for i in range(length_bytes - 1):
        encoded += chr(length % 256)
        length >>= 8
    encoded += chr(length | flags)
    return encoded[::-1]


def send_message(sender, *items, **arguments):
    max_length = max(chain(
        (len(item) for item in items),
        (len(k) + len(v) for k, v in arguments.iteritems())
    ))

    length_bits = 0
    while max_length > 0:
        max_length >>= 1
        length_bits += 1
    length_bytes = (length_bits + 7 + 3) / 8  # 3 reserved bits

    sender.send(chr(length_bytes))

    first = True
    for item in items:
        if isinstance(item, unicode):
            item = item.encode('utf_8')
        sender.send(encode_length(len(item), length_bytes,
                                  FIRST_ITEM if first else 0) + item)
        first = False

    first = True
    for key, value in arguments.iteritems():
        if isinstance(key, unicode):
            key = key.encode('utf_8')
        if isinstance(value, unicode):
            value = value.encode('utf_8')
        sender.send(encode_length(len(key), length_bytes,
                                  FIRST_ARG if first else 0) + key)
        sender.send(encode_length(len(value), length_bytes) + value)

        first = False


def receive_message(receiver):
    pass
