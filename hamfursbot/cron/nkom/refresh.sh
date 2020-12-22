#!/bin/bash
DB_URL="https://www.nkom.no/frekvenser-og-elektronisk-utstyr/radioamator/_/attachment/download/5a85721a-223f-42ea-bd49-b71541d93815:4f27f874d8ef314474493bf52aec658d939d967d/Liste%20over%20norske%20radioamat%C3%B8rer%20(CSV).csv"
wget -O import.csv $DB_URL && \
  ./fetch.py import.csv
echo -n "Finished "
date
