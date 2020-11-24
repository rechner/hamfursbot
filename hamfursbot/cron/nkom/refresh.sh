#!/bin/bash
DB_URL="https://www.nkom.no/frekvenser-og-elektronisk-utstyr/radioamator/_/attachment/download/5a85721a-223f-42ea-bd49-b71541d93815:c7aa67e268185b33eca25f50c56d31c5587eee69/Liste%20over%20norske%20radioamat%C3%B8rer%20(CSV).csv"
wget -O import.csv $DB_URL && \
  ./fetch.py import.csv
echo -n "Finished "
date
