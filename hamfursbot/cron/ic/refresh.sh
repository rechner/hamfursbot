#!/bin/bash

process () {
  cd /code/cron/ic
  unzip amateur_delim.zip
  ./fetch.py amateur_delim.txt
  echo -n "Finished "
  date
} 
  
cd /code/cron/ic
rm *.zip *amat*.txt
wget http://apc-cap.ic.gc.ca/datafiles/amateur_delim.zip && process
