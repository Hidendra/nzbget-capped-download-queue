#!/usr/bin/env python

#
# CappedDownloadQueue for NZBGet
#
# Copyright (C) 2021 Tyler Blair <tyler@viru.ca>
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

##############################################################################
### TASK TIME: *                                                           ###
### NZBGET QUEUE/SCHEDULER SCRIPT                                          ###
### QUEUE EVENTS: NZB_ADDED                                                ###

# Caps the maximum total size of NZBs that are currently being downloaded/processed.
#
# Queued downloads will be PAUSED until the total size of NZBs being actively worked on (download, PP, script, etc)
# reaches the configured limit. Then, downloads will be resumed in priority order.
#
# NZBs can use any priority; the download queue itself is not paused so any post-processing downloading
# and so on will continue to work as normal. NZBs will be picked in priority order when deciding which
# NZB to resume next.
#
# Queue-Script: Pauses newly-added NZBs.
#
# Scheduler-Script: Resumes NZBs until the sum of the resumed NZBs reaches the configured storage size limit.
#
# Script version: 1.0.0
#
# NOTE: This script requires Python 2 or 3 installed on your system.

##############################################################################
### OPTIONS                                                                ###

# Amount of storage (in GB) that is allocated to active downloads (GB).
# NZBs will be un-paused as free space in the queue allows.
#StorageSizeGB=100

# The number of seconds between checking if any downloads can be resumed (seconds).
#SchedulerRefreshInterval=15

### NZBGET QUEUE/SCHEDULER SCRIPT                                          ###
##############################################################################

import io
import os
import sys
import time

try:
    # Python 3.x
    from xmlrpc.client import ServerProxy
except ImportError:
    # Python 2.x
    from xmlrpclib import ServerProxy


PP_SUCCESS=93
PP_ERROR=94


def nzbget_connect_xml_rpc():
    host = os.environ['NZBOP_CONTROLIP']
    port = os.environ['NZBOP_CONTROLPORT']
    username = os.environ['NZBOP_CONTROLUSERNAME']
    password = os.environ['NZBOP_CONTROLPASSWORD']
    
    if host == '0.0.0.0':
        host = '127.0.0.1'

    rpc_url = 'http://%s:%s@%s:%s/xmlrpc' % (username, password, host, port);

    return ServerProxy(rpc_url)


def nzbget_group_is_active(group):
    """ Returns True if the group is considered 'active' i.e. downloading, post-processing, running a script, etc, but NOT 'PAUSED'. """
    return group['Status'] != 'PAUSED'

def nzbget_groups_total_active_size_mb(groups, ignore_group_id=None):
    """ Returns the total size (in MB) of the groups that are considered active. """
    total_size_mb = 0

    for group in groups:
        group_id = group['NZBID']

        if group_id != ignore_group_id and nzbget_group_is_active(group):
            total_size_mb += group['FileSizeMB']

    return total_size_mb

def nzbget_groups_iter_nzbs_by_priority(groups):
    """ Generator func that yields nzbs (groups) from the list of groups in the order of priority. """
    yielded_groups = 0

    # the current priority being yielded
    # On each iteration, this will be set to the next lowest priority until all
    # groups are exhausted
    current_priority = 999999

    while len(groups) != yielded_groups:
        # discover current priority
        next_priority = -999999
        for group in groups:
            group_priority = group['MaxPriority']
            
            if group_priority > next_priority and group_priority < current_priority:
                next_priority = group_priority

        # print('[nzbget_group_iter_nzbs_by_priority] Moving from priority %d to %d' % (current_priority, next_priority))
        current_priority = next_priority

        # now yield all groups that match the priority
        # priority is matched exactly so no need for fuzzy matching
        for group in groups:
            if group['MaxPriority'] == current_priority:
                yielded_groups += 1
                yield group


def main_schedulerscript():
    # Disable print output buffering - https://stackoverflow.com/a/181654
    try:
        # Python 3, open as binary, then wrap in a TextIOWrapper with write-through.
        sys.stdout = io.TextIOWrapper(open(sys.stdout.fileno(), 'wb', 0), write_through=True)
    except TypeError:
        # Python 2
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    print('[INFO] Starting scheduler script - will continue to run')

    storage_size_mb = int(os.environ.get('NZBPO_STORAGESIZEGB', 0)) * 1024
    sleep_period_secs = int(os.environ.get('NZBPO_SCHEDULERREFRESHINTERVAL', 0))

    if not storage_size_mb:
        print('[ERROR] StorageSizeGB is missing from the script configuration.')
        return PP_ERROR

    if not sleep_period_secs:
        print('[ERROR] SchedulerRefreshInterval is missing from the script configuration.')
        return PP_ERROR

    nzbget = nzbget_connect_xml_rpc()

    while True:
        groups = nzbget.listgroups()

        # Free space check - abort if there is no free space
        groups_total_size_mb = nzbget_groups_total_active_size_mb(groups)

        if groups_total_size_mb < storage_size_mb:
            # There is free space - pull nzbs in priority order to fill up the available space
            groups_to_resume = []
            remaining_size_mb = storage_size_mb - groups_total_size_mb

            for group in nzbget_groups_iter_nzbs_by_priority(groups):
                group_id = group['NZBID']
                group_size = group['RemainingSizeMB']
                group_status = group['Status']

                if group_status == 'PAUSED' and group_size <= remaining_size_mb:
                    groups_to_resume.append(group_id)
                    remaining_size_mb -= group_size

            if groups_to_resume:
                new_groups_total_size_mb = storage_size_mb - remaining_size_mb
                print('[INFO] groups_to_resume=%s old_group_size_mb=%d new_group_size_mb=%d' % 
                        (str(groups_to_resume), groups_total_size_mb, new_groups_total_size_mb))
                nzbget.editqueue('GroupResume', '', groups_to_resume)

        time.sleep(sleep_period_secs)

    return PP_SUCCESS


def main_queuescript():
    if os.environ.get('NZBNA_EVENT') not in ['NZB_ADDED']:
        return 0

    # Pause the NZB so that it can be unpaused in priority order after the space check
    nzbna_nzbid = int(os.environ.get('NZBNA_NZBID'))
    print('[INFO] Pausing newly-added NZB %d to allow scheduler to resume it when space is available' % nzbna_nzbid)

    nzbget = nzbget_connect_xml_rpc()
    nzbget.editqueue('GroupPause', '', [nzbna_nzbid])
 
    return PP_SUCCESS
    

def main():
    if 'NZBSP_TASKID' in os.environ:
        return main_schedulerscript()
    elif 'NZBNA_EVENT' in os.environ:
        return main_queuescript()

    print('[ERROR] Ran with unknown script type')
    return PP_ERROR


if __name__ == '__main__':
    sys.exit(main())

