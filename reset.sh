#/bin/sh

# This will reset the database data allowing Indigraphs to "re-process" it.
# Sometimes this is necesarry when you import a lot of data at once.
# If you want to reset graphite, run the script with -w as the only arg.

test "$1" = "-w" && rm -rf /opt/graphite/storage/whisper/indigraph
psql -d indigo_history -c 'delete from already_processed;'
rm -f /tmp/indigraphs.log

