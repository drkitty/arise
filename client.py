# encoding=utf_8
from __future__ import unicode_literals

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


def main():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect('/tmp/arise.sock')

    command = argv[1]
    args = dict(arg.split('=', 1) for arg in argv[2:])
    send_command(s, command, **args)

if __name__ == '__main__':
    main()
