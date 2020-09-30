#!/bin/bash

wget -O import.csv https://eng.nkom.no/leisure/radio-amateurs/radio-amateurs/radio-amateours-in-norway/_attachment/9935 && \
  ./fetch.py import.csv
echo -n "Finished "
date
