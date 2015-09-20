#!/usr/bin/env python
"""
Usage: ./distribute_lab.py lab_directory recipients
    - lab_directory is the name of the directory containing the lab files.
      This MUST contain an __init__.py file - details below.
    - recipients can be
        - "staff" to distribute to all staff, or
        - "students" to distribute to all students, or
        - "honors" to distribute to all honors students
          (assumes roster at _class/Honors/honors.txt), or
        - a comma-separated list of NetIDs, to distribute to only those NetIDs.
This DOES NOT actually commit to SVN, but it does everything else

Examples:
    ./distribute_lab.py Lab1 staff
    Distributes Lab 1 files to all staff

    ./distribute_lab.py Lab2 students
    Distributes Lab 2 files to all students

    ./distribute_lab.py Lab4 foo1,bar2,baz3
    Distributes Lab 4 files to students foo1, bar2 and baz3

__init.py__ details
This script (ab)uses the __init__.py file to hold distribution information.
The __init__.py can have the following (all elements are optional):
    - a list called "readonly" containing the names of all files to be
      distributed as read-only.
    - a list called "writable" containing the names of all files to be
      distributed as read-write.
    - a list called "shared" containing the names of all files to be
      distributed to _shared/lab_name.
    - a list called "ignore" containing additional file patterns to ignore.
      These will be added to the svn:ignore of the Lab folder, so format them
      accordingly. Some patterns are automatically ignored - see the list
      called "ignore_patterns" below.
    - a function called "generate" which takes a NetID as an argument and
      generates files specific to that NetID. The names of these files should
      be included in either the readonly or writable list as appropriate.
    - a boolean called "individual" which prevents generation of partners.txt
      files if true. Assumed to be false if not present.
    - a list called "readonly_updated". If this list is present and not empty,
      only the files in this list are distributed as read-only, and
      partners.txt files are not regenerated.
    - a list called "writable_updated". The same as "readonly_updated", except
      the files are distributed as read-write. Both *_updated lists can be
      present, and can be used to correct files distributed with incorrect
      write permissions as well as add new files.
    - a list called "shared_updated", to update any _shared files.
"""

from __future__ import print_function

import os
import shutil
import stat
import subprocess
import sys
import traceback

# trailing commas are okay in Python thankfully
ignore_patterns = [
    '*.bak',  # Vim backup files
    '*.exe',  # Windows executable files
    '*.o',  # object files
    '*.swp',  # Vim swap files
    '*.vcd',  # wavedumps
    '*~',  # Emacs backup files and gedit temp files
    '*.pyc',  # Python bytecode
    '*.dSYM',  # debug symbols file
    # what am I missing?
]


def distribute_lab(lab_name, recipients):
    """
    Distributes the specified lab to the specified recipients.
        lab_name: the name of the lab, which should also be
                  the name of a directory under _class
        recipients: see file documentation above
    """
    # this should be using importlib.import_module, but that's Python 2.7+,
    # whereas EWS runs Python 2.6
    lab = __import__(lab_name)
    process_lab_module(lab)

    script_dir = os.path.dirname(os.path.realpath(__file__))
    lab_dir = os.path.join(script_dir, lab_name)
    # assumes this script is directly under _class
    svn_dir = os.path.dirname(script_dir)

    if recipients in ('honors', 'staff', 'students'):
        if recipients == 'honors':
            roster_dir = os.path.join('_class', 'Honors')
        else:
            roster_dir = '_rosters'
        roster_path = os.path.join(svn_dir, roster_dir, recipients + '.txt')
        with open(roster_path) as roster_file:
            netids = list(roster_file)
    else:
        netids = recipients.split(',')

    update_mode = lab.readonly_updated or lab.writable_updated or \
        lab.shared_updated
    readonly = lab.readonly_updated if update_mode else lab.readonly
    writable = lab.writable_updated if update_mode else lab.writable
    shared = lab.shared_updated if update_mode else lab.shared
    add_shared_files(lab_dir, svn_dir, lab_name, shared)

    for netid in netids:
        try:
            netid = netid.strip()
            print('Distributing to', netid)
            lab.generate(netid)
            dest_dir = os.path.join(svn_dir, netid, lab_name)
            add_directory(dest_dir)
            add_files(readonly + writable, lab_dir, dest_dir)
            mark_readonly(readonly, dest_dir)
            mark_writable(writable, dest_dir)
            mark_ignored(lab.ignore, dest_dir)
            if not (update_mode or lab.individual):
                add_partner_file(netid, dest_dir)
        except:
            traceback.print_exc()


def process_lab_module(lab):
    """
    Processes a lab module to fill in default values for optional members
    and process all file lists.
    """
    lab.readonly = getattr(lab, 'readonly', [])
    lab.writable = getattr(lab, 'writable', [])
    lab.shared = getattr(lab, 'shared', [])
    lab.ignore = getattr(lab, 'ignore', [])
    lab.generate = getattr(lab, 'generate', lambda _: None)
    lab.individual = getattr(lab, 'individual', False)
    lab.readonly_updated = getattr(lab, 'readonly_updated', [])
    lab.writable_updated = getattr(lab, 'writable_updated', [])
    lab.shared_updated = getattr(lab, 'shared_updated', [])

    lab.readonly = process_file_list(lab.readonly)
    lab.writable = process_file_list(lab.writable)
    lab.shared = process_file_list(lab.shared)
    lab.ignore = process_file_list(lab.ignore)
    lab.readonly_updated = process_file_list(lab.readonly_updated)
    lab.writable_updated = process_file_list(lab.writable_updated)
    lab.shared_updated = process_file_list(lab.shared_updated)


def process_file_list(file_list):
    """
    Splits the file names in a file list by directory,
    to allow subdirectory files to be handled properly.
    """
    return [path.split('/') for path in file_list]


def add_shared_files(lab_dir, svn_dir, lab_name, shared):
    """
    Adds shared files to _shared/lab_name
    """
    if not shared:
        return

    print('Distributing shared files')
    shared_dir = os.path.join(svn_dir, '_shared', lab_name)
    add_directory(shared_dir)
    add_files(shared, lab_dir, shared_dir)


def add_to_svn(path):
    """
    Adds the path to SVN, if it's not already present.
    """
    not_in_svn = call_silently(['svn', 'info', path], True)
    if not_in_svn:
        call_silently(['svn', 'add', path])


def add_directory(dest_dir):
    """
    Creates a directory and adds it to SVN.
    """
    if not os.path.isdir(dest_dir):
        os.mkdir(dest_dir)
    add_to_svn(dest_dir)


def add_subdirectories(file_path, dest_dir):
    """
    Creates and adds all the subdirectories in a path to SVN.
    """
    current_dir = dest_dir
    for child_dir in file_path[:-1]:
        current_dir = os.path.join(current_dir, child_dir)
        add_directory(current_dir)


def add_files(file_names, lab_dir, dest_dir):
    """
    Copies over all files in file_names from lab_dir to dest_dir
    and adds the copied files to SVN.
    """
    for file_name in file_names:
        add_subdirectories(file_name, dest_dir)
        file_path = os.path.join(lab_dir, *file_name)
        dest_path = os.path.join(dest_dir, *file_name)
        if os.path.exists(dest_path):
            # overwrite file even if it's presently read-only
            os.chmod(dest_path, stat.S_IWUSR)
        shutil.copy2(file_path, dest_path)
        add_to_svn(dest_path)


def add_partner_file(netid, dest_dir):
    """
    Adds a partners.txt file containing netid to dest_dir.
    """
    partner_file_path = os.path.join(dest_dir, 'partners.txt')
    # opening as binary so that newline is written as '\n' even on Windows
    with open(partner_file_path, 'wb') as partner_file:
        partner_file.write((netid + '\n').encode('utf_8'))
        add_to_svn(partner_file_path)


def mark_readonly(file_names, dest_dir):
    """
    Marks the files in file_names as read-only, both in SVN and the filesystem.
    """
    if not file_names:
        # don't call svn propset on empty path list
        return

    file_paths = [os.path.join(dest_dir, *name) for name in file_names]
    # the value of the property doesn't matter, just that it's set
    call_silently(['svn', 'propset', 'svn:needs-lock', 'yes'] + file_paths)
    for file_path in file_paths:
        file_stat = os.stat(file_path)
        write_mask = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
        os.chmod(file_path, file_stat.st_mode & ~write_mask)


def mark_writable(file_names, dest_dir):
    """
    Marks the files in file_names as writable, both in SVN and the filesystem.
    """
    if not file_names:
        # don't call svn propset on empty path list
        return

    file_paths = [os.path.join(dest_dir, *name) for name in file_names]
    call_silently(['svn', 'propdel', 'svn:needs-lock'] + file_paths, True)
    for file_path in file_paths:
        file_stat = os.stat(file_path)
        os.chmod(file_path, file_stat.st_mode | stat.S_IWUSR)


def mark_ignored(patterns, dest_dir):
    """
    Adds the specified patterns to the svn:ignore of dest_dir.
    """
    patterns = [os.path.join(*pattern) for pattern in patterns]
    ignore_list = '\n'.join(ignore_patterns + patterns)
    call_silently(['svn', 'propset', 'svn:ignore', ignore_list, dest_dir])


def call_silently(args, suppress_stderr=False):
    """
    Calls a command silently, suppressing stdout and optionally stderr.
    """
    with open(os.devnull, 'w') as fnull:
        stderr = fnull if suppress_stderr else None
        return subprocess.call(args, stdout=fnull, stderr=stderr)

if __name__ == '__main__':
    if len(sys.argv) == 3:
        distribute_lab(sys.argv[1], sys.argv[2])
    else:
        print(__doc__.strip())
