#!/usr/bin/env python2
# encoding=utf_8

from __future__ import unicode_literals

import os
import re
import select
import socket
import subprocess
from subprocess import Popen, PIPE, STDOUT
from sys import stderr, stdout
from time import sleep

from common import PollWrapper, SocketWrapper


block_add_pattern = re.compile(
    r'KERNEL\[[^]]*\]\s*add\s*(?P<path>\S*)\s*\(block\)')
block_remove_pattern = re.compile(
    r'KERNEL\[[^]]*\]\s*remove\s*(?P<path>\S*)\s*\(block\)')


class ServerSocketWrapper(SocketWrapper):
    def interact_generator(self, plugged):
        self.prepare_receive_message()
        while True:
            ret = self.receive_message()
            if ret is not None:
                items, args = ret
                command = items[0]
                break
            yield

        print 'Received message {}, {}'.format(items, args)

        if command == 'mount':
            mountpoint = args.pop('mountpoint', None)
            if mountpoint is None:
                self.prepare_send_message(
                    'error', desc='The "mountpoint" argument is required.')
                while self.send_message() is None:
                    yield
                yield True

            def f(dev):
                for field, value in args.iteritems():
                    if field in dev and dev[field] == value:
                        return True
                return False
            matches = filter(f, plugged.itervalues())

            if len(matches) > 1:
                self.prepare_send_message(
                    'error', desc='Multiple devices matched')
                while self.send_message() is None:
                    yield
                yield True
            if len(matches) == 0:
                self.prepare_send_message('error', desc='No devices matched')
                while self.send_message() is None:
                    yield
                yield True

            dev_path = '/dev/' + matches[0]['name']
            # FIXME: Fork or something.
            if subprocess.call(('mount', dev_path, mountpoint)) == 0:
                matches[0]['mountpoint'] = mountpoint
                self.prepare_send_message('success')
                while self.send_message() is None:
                    yield
                yield True
            else:
                self.prepare_send_message('error', desc='Mount failed')
                while self.send_message() is None:
                    yield
                yield True
        elif command == 'unmount':
            def f(dev):
                if 'mountpoint' not in dev:
                    return False
                for field, value in args.iteritems():
                    if field not in dev or dev[field] != value:
                        return False
                return True
            matches = filter(f, plugged.itervalues())

            if len(matches) > 1:
                self.prepare_send_message(
                    'error', desc='Multiple devices matched')
                while self.send_message() is None:
                    yield
                yield True
            if len(matches) == 0:
                self.prepare_send_message('error', desc='No devices matched')
                while self.send_message() is None:
                    yield
                yield True

            dev_path = '/dev/' + matches[0]['name']
            # FIXME: Fork or something.
            if subprocess.call(('umount', dev_path)) == 0:
                del matches[0]['mountpoint']
                self.prepare_send_message('success')
                while self.send_message() is None:
                    yield
                yield True
            else:
                self.prepare_send_message('error', desc='umount failed')
                while self.send_message() is None:
                    yield
                yield True
        else:
            self.prepare_send_message('error', desc='Invalid command')
            while self.send_message() is None:
                yield
            yield True

    def prepare_interact(self, plugged):
        self.interact_g = self.interact_generator(plugged)
        self.poller.extend(self.sock.fileno(), select.POLLIN)

    def interact(self):
        if next(self.interact_g) is not None:
            del self.interact_g
            fd = self.sock.fileno()
            self.close()
            print 'Socket with fd {} closed'.format(fd)
            return True


def get_dev_identifier(path):
    identifier = {}

    name_p = Popen(('udevadm', 'info', '-q', 'name', '-p', path), stdout=PIPE,
                   stderr=PIPE)
    name, _ = name_p.communicate()
    identifier['name'] = name.strip()

    symlinks_p = Popen(('udevadm', 'info', '-q', 'symlink', '-p', path),
                       stdout=PIPE, stderr=PIPE)
    symlinks, _ = symlinks_p.communicate()
    symlinks.strip()
    for symlink in symlinks.split():
        symlink = symlink[len('disk/'):]
        kind, value = symlink.split(b'/')
        kind = kind[len('by-'):].decode('utf_8')
        value = value.decode('string_escape').decode('utf_8')
        if kind in ('uuid', 'label'):
            identifier[kind] = value

    return identifier


def handle_monitor_event(monitor_line, plugged):
    m = block_add_pattern.match(monitor_line)
    if m:
        path = m.groupdict()['path']

        with open('/dev/null', 'w') as devnull:
            Popen(('udevadm', 'settle'), stdout=devnull,
                  stderr=STDOUT).wait()

        iden = get_dev_identifier(path)
        stdout.write('inserted {}\n'.format(iden))
        plugged[path] = iden
        return

    m = block_remove_pattern.match(monitor_line)
    if m:
        path = m.groupdict()['path']
        iden = plugged.pop(path, None)
        if iden is not None:
            stdout.write('removed {}\n'.format(iden))
        return


def main_event_loop():
    poller = PollWrapper()

    monitor = Popen(('stdbuf', '-oL', 'udevadm', 'monitor', '-k'),
                    stdout=PIPE, stderr=PIPE)
    poller.register(monitor.stdout, select.POLLIN)

    socket_master = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        os.remove('/tmp/arise.sock')
    except OSError as e:
        if e.errno != 2:  # "No such file or directory"
            raise
    socket_master.bind('/tmp/arise.sock')
    os.chmod('/tmp/arise.sock', 0666)
    socket_master.listen(1)
    poller.register(socket_master, select.POLLIN)

    plugged = {}
    clients = {}

    while True:
        events = poller.poll()
        for fd, kind in events:
            if fd == monitor.stdout.fileno():
                handle_monitor_event(monitor.stdout.readline(), plugged)
            elif fd == socket_master.fileno():
                assert kind & select.POLLIN

                sock, _ = socket_master.accept()
                print 'Socket with fd {} accepted'.format(sock.fileno())
                sw = ServerSocketWrapper(sock=sock, poller=poller)
                clients[sock.fileno()] = sw
                sw.prepare_interact(plugged)
            elif kind & select.POLLHUP:
                assert fd in clients

                clients[fd].close()
                print 'Socket with fd {} closed'.format(fd)
                del clients[fd]
            elif kind & (select.POLLIN | select.POLLOUT):
                assert fd in clients

                ret = clients[fd].interact()
                if ret is not None:
                    del clients[fd]
            else:
                raise Exception('An unacceptable state of affairs has '
                                'arisen')


if __name__ == '__main__':
    main_event_loop()
