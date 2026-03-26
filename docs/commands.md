NVIDIA DGX Spark Magic Factory — Commands
==========================

All commands should be run with sudo:

    sudo is preferred because the app may need to:
    - Fix file ownership in data/ (chown) when files were created by a
      different user or a previous sudo run
    - Kill processes owned by root (e.g. if started with sudo previously)
    - Stop Docker containers (docker often requires root unless the user
      is in the docker group)
    - Use lsof to find processes bound to a port (needs elevated privileges
      for full process visibility)

Commands
--------

sudo bin/start.sh        Start the app (opens browser, runs in background)
sudo bin/stop.sh         Stop the app and all related services
sudo bin/restart.sh      Restart the app (stop + start; starts fresh if not running)
sudo bin/show.sh         Show running services and open the UI
sudo bin/uninstall.sh    Remove the app and all its data
