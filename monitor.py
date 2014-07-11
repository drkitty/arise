from __future__ import unicode_literals

import re
from subprocess import Popen, PIPE, STDOUT
from sys import stdout
from time import sleep


bit_bucket = open('/dev/null', 'w')


monitor_p = Popen(('stdbuf', '-oL', 'udevadm', 'monitor', '-k'), stdout=PIPE,
          stderr=PIPE, bufsize=1)


block_add_pattern = re.compile(
    r'KERNEL\[[^]]*\]\s*add\s*(?P<path>\S*)\s*\(block\)')
block_remove_pattern = re.compile(
    r'KERNEL\[[^]]*\]\s*remove\s*(?P<path>\S*)\s*\(block\)')


info_uuid_pattern = re.compile(
    r'S:\s*disk/by-uuid/(?P<uuid>\S*)')
info_label_pattern = re.compile(
    r'S:\s*disk/by-label/(?P<label>\S*)')
info_name_pattern = re.compile(
    r'N:\s*(?P<name>\S*)')


def get_dev_identifier(path):
    info_p = Popen(('udevadm', 'info', '-p', path), stdout=PIPE,
              stderr=PIPE)
    info, _ = info_p.communicate()
    info = info.decode('string_escape').decode('utf_8')

    identifier = {}

    for info_line in info.splitlines():
        for pattern in (info_uuid_pattern, info_label_pattern,
                info_name_pattern):
            m = pattern.match(info_line)
            if m is not None:
                identifier.update(m.groupdict())
                break

    return identifier


def monitor_loop():
    plugged = {}

    for monitor_line in iter(monitor_p.stdout.readline, b''):
        m = block_add_pattern.match(monitor_line)
        if m:
            path = m.groupdict()['path']

            Popen(('udevadm', 'settle'), stdout=bit_bucket,
                  stderr=bit_bucket).wait()

            iden = get_dev_identifier(path)
            #stdout.write('{} inserted\n'.format(iden))
            print plugged
            plugged[path] = iden

        m = block_remove_pattern.match(monitor_line)
        if m:
            path = m.groupdict()['path']
            iden = plugged.pop(path, None)
            if iden:
                #stdout.write('{} removed\n'.format(iden))
                print plugged


if __name__ == '__main__':
    monitor_loop()
