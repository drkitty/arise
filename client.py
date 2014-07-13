# encoding=utf_8
from __future__ import unicode_literals

import socket
from time import sleep


def send_command(s, command, **kwargs):
    command = command.encode('utf_8')
    msg = b'{}:{}'.format(len(command), command)

    for key, value in kwargs.iteritems():
        key = key.encode('utf_8')
        value = value.encode('utf_8')
        msg += b'{}:{}={}'.format(len(key) + len(value) + 1, key, value)

    msg += b'$'

    print msg
    s.sendall(msg)


def main():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect('/tmp/arise.sock')
    send_command(s, 'mount', at='/mnt/place', label='UFDé')
    send_command(s, 'umount', label='UFDé')
    sleep(1)

if __name__ == '__main__':
    main()
