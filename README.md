# nzbget-capped-download-queue

CappedDownloadQueue extension script for NZBGet.

This script is a combination Queue & Scheduler script. Both components must be used.
The Scheduler component is enabled by default and runs on startup - no time schedule is needed as it will continue to run once started.

This script caps the download queue to a configured size (in GB) with `StorageSizeGB`.
All downloads will be paused when added and will be resumed (in priority order) up to the configured size.

By default, the scheduler task will check for paused downloads that need to be unpaused every 15 seconds (configurable with `SchedulerRefreshInterval`).

The utility of this script is twofold:

1. Running out of storage - causing NZBGet to get into a pause loop if you unpause it - is not possible if configured with a reasonable storage limit.
This allows you to freely run with any of the `*PauseQueue` options disabled to freely allow any downloading/post-processing/unpacking.
Normally, NZBGet would continue to download new NZBs forever until it runs out of space (and then pauses). This controls that so it doesn't get to that point.

2. Downloads, once started, will run until completion due to the fact that only a limited number of downloads can run at the same time.
The case where in-progress downloads can get bumped and cause NZBGet to run out of disk space is not possible as the full space needed is reserved for all in-progress downloads with this script.

This can be utilized in conjunction with the StickyDownloadQueue script to allow more sticky downloading within the currently resumed downloads.

