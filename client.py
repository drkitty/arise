# encoding=utf-8
from __future__ import unicode_literals

import socket
from time import sleep


def mount(s, at, uuid=None, label=None, name=None):
    for name, value in ((b'uuid', uuid), (b'label', label), (b'name', name)):
        if value is not None:
            value = value.encode('utf_8')
            at = at.encode('utf_8')
            msg = b'5:mount {0}:{1}={2} {3}:at={4} $'.format(
                len(name + value) + 1, name, value,
                len(b'at' + at) + 1, at)
            print repr(msg)
            s.sendall(msg[0:9])
            sleep(1)
            s.sendall(msg[9:])
            return


def main():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect('/tmp/arise.sock')
    mount(s, '/mnt/place', label='UFDé')
    sleep(1)


if __name__ == '__main__':
    main()
