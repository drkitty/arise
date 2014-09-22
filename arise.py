#!/usr/bin/env python2
# encoding=utf_8

from __future__ import unicode_literals

import argparse
import select
import socket
from sys import stderr

from common import PollWrapper, SocketWrapper


class ClientSocketWrapper(SocketWrapper):
    def interact_generator(self, command, dictionary):
        if command == 'show':
            self.prepare_send_message('show')
            while self.send_message() is None:
                yield

            self.prepare_receive_message()
            while True:
                ret = self.receive_message()
                if ret is not None:
                    items, dictionary = ret
                    break
                yield
            for device in items:
                dev_items, dev_dictionary = device
                print '{}:'.format(dev_dictionary['name'])
                for key, value in dev_dictionary.iteritems():
                    print '    {}="{}"'.format(key, value)
            yield True
        else:
            self.prepare_send_message(command, **dictionary)
            while self.send_message() is None:
                yield

            self.prepare_receive_message()
            while True:
                ret = self.receive_message()
                if ret is not None:
                    items, dictionary = ret
                    status = items[0]
                    break
                yield

            if status == 'success':
                print 'Success!'
            elif status == 'error':
                stderr.write('Error: ' + dictionary['desc'] + '\n')
            else:
                stderr.write('Server misbehaved')
            yield True

    def prepare_interact(self, command, dictionary):
        self.interact_g = self.interact_generator(command, dictionary)
        self.poller.extend(self.sock.fileno(), select.POLLOUT)

    def interact(self):
        if next(self.interact_g) is not None:
            del self.interact_g
            self.close()
            return True


def receive_list(s):
    pass


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-m', '--mount', metavar='MOUNTPOINT')
    group.add_argument('-u', '--unmount', action='store_true')
    group.add_argument('-a', '--automount', metavar='MOUNTPOINT')
    group.add_argument('-s', '--show', action='store_true')
    parser.add_argument('-i', '--uuid')
    parser.add_argument('-l', '--label')
    parser.add_argument('-n', '--name')
    parser.add_argument('-o', '--mountpoint')
    args = parser.parse_args()

    filters = {}

    for c in ('mount', 'unmount', 'automount', 'show'):
        if getattr(args, c):
            command = c
            if c in ('mount', 'automount'):
                filters['mountpoint'] = getattr(args, c)
            break

    for f in ('uuid', 'label', 'name', 'mountpoint'):
        if getattr(args, f) is not None:
            filters[f] = getattr(args, f)

    poller = PollWrapper()

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect('/tmp/arise.sock')

    sw = ClientSocketWrapper(sock=sock, poller=poller, verbose=False)
    sw.prepare_interact(command, filters)

    while True:
        poller.poll()
        ret = sw.interact()
        if ret is not None:
            return


if __name__ == '__main__':
    main()
