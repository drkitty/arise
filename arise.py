# encoding=utf_8
from __future__ import unicode_literals

import argparse
import socket
from sys import argv
from time import sleep


def send_command(s, command, **kwargs):
    def encode_length(length, flags):
        return chr((length / 2**8) | flags) + chr(length % 2**8)

    command = command.encode('utf_8')
    msg = b'\x02{}{}'.format(encode_length(len(command), 0), command)

    first = True
    for key, value in kwargs.iteritems():
        key = key.encode('utf_8')
        value = value.encode('utf_8')
        msg += b'{}{}'.format(
            encode_length(len(key), 0x40 if first else 0x00), key)
        msg += b'{}{}'.format(encode_length(len(value), 0), value)

        first = False

    msg += b'\x80'

    print repr(msg)
    s.sendall(msg)


def receive_list(s):
    pass


def main():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect('/tmp/arise.sock')

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-m', '--mount', action='store_true')
    group.add_argument('-u', '--unmount', action='store_true')
    group.add_argument('-a', '--automount', action='store_true')
    group.add_argument('-s', '--show', action='store_true')
    parser.add_argument('-i', '--uuid')
    parser.add_argument('-l', '--label')
    parser.add_argument('-n', '--name')
    args = parser.parse_args()

    for c in ('mount', 'unmount', 'automount', 'show'):
        if getattr(args, c):
            command = c
            break

    filters = {}
    for f in ('uuid', 'label', 'name'):
        if getattr(args, f) is not None:
            filters[f] = getattr(args, f)

    send_command(s, command, **filters)
    if command == 'show':
        receive_list(s)
    try:
        while True:
            pass
    finally:
        s.shutdown(socket.SHUT_RDWR)
        s.close()


if __name__ == '__main__':
    main()
