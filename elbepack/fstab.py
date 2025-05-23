# ELBE - Debian Based Embedded Rootfilesystem Builder
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2013-2014, 2017 Linutronix GmbH
# SPDX-FileCopyrightText: 2015 Matthias Buehler <matthias.buehler@de.trumpf.com>

import os
import subprocess
import time

from elbepack.imgutils import losetup
from elbepack.shellhelper import do


def get_mtdnum(xml, label):
    tgt = xml.node('target')
    if not tgt.has('images'):
        raise Exception('No images tag in target')

    for i in tgt.node('images'):
        if i.tag != 'mtd':
            continue

        if not i.has('ubivg'):
            continue

        for v in i.node('ubivg'):
            if v.tag != 'ubi':
                continue

            if v.text('label') == label:
                return i.text('nr')

    raise Exception('No ubi volume with label ' + label + ' found')


def get_devicelabel(xml, node):
    if node.text('fs/type') == 'ubifs':
        return f"ubi{get_mtdnum(xml, node.text('label'))}:{node.text('label')}"

    return 'LABEL=' + node.text('label')


class mountpoint_dict (dict):
    def __init__(self):
        super().__init__()
        self.id_count = 0

    def register(self, fstab_entry):
        mp = fstab_entry.mountpoint

        if mp in self:
            fstab_entry.id = self[mp].id
        else:
            fstab_entry.id = str(self.id_count)
            self[mp] = fstab_entry
            self.id_count += 1

    @staticmethod
    def mountdepth(mp):
        depth = 0

        while True:
            mp, t = os.path.split(mp)
            if t == '':
                return depth
            depth += 1

    def depthlist(self):
        mplist = sorted(self.keys(), key=mountpoint_dict.mountdepth)

        return [self[x] for x in mplist]


class hdpart:
    def __init__(self):
        # These attributes are filled later
        # using set_geometry()
        self.size = 0
        self.offset = 0
        self.filename = ''
        self.partnum = 0
        self.number = ''

    def set_geometry(self, ppart, disk):
        sector_size = 512
        self.offset = ppart.geometry.start * sector_size
        self.size = ppart.getLength() * sector_size
        self.filename = disk.device.path
        self.partnum = ppart.number
        self.number = f'{disk.type}{ppart.number}'

    def losetup(self):
        while True:
            try:
                return losetup(self.filename, [
                    '--offset', str(self.offset),
                    '--sizelimit', str(self.size),
                ])
            except subprocess.CalledProcessError as e:
                if e.returncode != 1:
                    raise
                do('sync')
                time.sleep(1)


class fstabentry(hdpart):

    def __init__(self, xml, entry, fsid=0):
        super().__init__()

        if entry.has('source'):
            self.source = entry.text('source')
        else:
            self.source = get_devicelabel(xml, entry)

        if entry.has('label'):
            self.label = entry.text('label')

        self.mountpoint = entry.text('mountpoint')
        self.options = entry.text('options', default='defaults')
        if entry.has('fs'):
            self.fstype = entry.text('fs/type')
            self.mkfsopt = entry.text('fs/mkfs', default='')
            self.passno = entry.text('fs/passno', default='0')

            self.fs_device_commands = []
            self.fs_path_commands = []
            for command in entry.node('fs/fs-finetuning') or []:
                if command.tag == 'device-command':
                    self.fs_device_commands.append(command.text('.'))
                elif command.tag == 'path-command':
                    self.fs_path_commands.append(command.text('.'))

        self.id = str(fsid)
        # Attributes for storing root directory properties (for bug fix)
        self.root_mode = None
        self.root_uid = None
        self.root_gid = None

    def get_str(self):
        return (f'{self.source} {self.mountpoint} {self.fstype} {self.options} '
                f'0 {self.passno}\n')

    def mountdepth(self):
        h = self.mountpoint
        depth = 0

        while True:
            h, t = os.path.split(h)
            if t == '':
                return depth
            depth += 1

    def get_label_opt(self):
        if self.fstype in ('ext4', 'ext3', 'ext2', 'btrfs'):
            return '-L ' + self.label
        if self.fstype == 'vfat':
            return '-n ' + self.label
        if self.fstype == 'f2fs':
            return '-l ' + self.label
        return ''
