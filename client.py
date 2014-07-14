# encoding=utf_8
from __future__ import unicode_literals

import argparse
import socket
from sys import argv
from time import sleep


def send_command(s, command, **kwargs):
    def encode_length(length):
        return chr(length / 2**8) + chr(length % 2**8)

    command = command.encode('utf_8')
    msg = b'{}{}'.format(encode_length(len(command)), command)

    for key, value in kwargs.iteritems():
        key = key.encode('utf_8')
        value = value.encode('utf_8')
        msg += b'{}{}={}'.format(encode_length(len(key) + len(value) + 1),
                                 key, value)

    msg += b'\x00\x00'

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

    filters = {}
    for f in ('uuid', 'label', 'name'):
        if getattr(args, f) is not None:
            filters[f] = getattr(args, f)

    send_command(s, command, **filters)
    if command == 'show':
        receive_list(s)


if __name__ == '__main__':
    main()
