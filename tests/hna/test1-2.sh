#!/bin/bash

set -e

source prelude.sh

echo "automaton:"   >  /tmp/hna1.yml
echo "    init: q0" >> /tmp/hna1.yml
echo "    nodes:"   >> /tmp/hna1.yml
echo "        q0: 'forall t1,t2: x(t1) <= x(t2)' " >> /tmp/hna1.yml
echo "    edges:"   >> /tmp/hna1.yml
echo "        - edge: q0  q0"   >> /tmp/hna1.yml
echo "          action: reset"  >> /tmp/hna1.yml

gen /tmp/hna1.yml

echo "x,y"  > /tmp/1.csv
echo "1,1" >> /tmp/1.csv
echo "2,2" >> /tmp/1.csv
echo "1,3" >> /tmp/1.csv
echo "1,1" >> /tmp/1.csv

run accepts /tmp/1.csv

echo "x,y"  > /tmp/2.csv
echo "1,3" >> /tmp/2.csv
echo "2,3" >> /tmp/2.csv
echo "1,3" >> /tmp/2.csv
echo "1,3" >> /tmp/2.csv

echo "x,y"  > /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "2,3" >> /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "1,3" >> /tmp/3.csv

run accepts /tmp/1.csv /tmp/2.csv /tmp/3.csv

echo "x,y"  > /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "2,3" >> /tmp/3.csv
echo "1,1" >> /tmp/3.csv

run rejects /tmp/1.csv /tmp/2.csv /tmp/3.csv

rm /tmp/{1,2,3}.csv

## -----------------------

echo "x,y"  > /tmp/1.csv
echo "1,1" >> /tmp/1.csv
echo "2,2" >> /tmp/1.csv
echo "1,3" >> /tmp/1.csv
echo "1,1" >> /tmp/1.csv
echo "reset" >> /tmp/1.csv
echo "1,1" >> /tmp/1.csv
echo "2,2" >> /tmp/1.csv
echo "1,3" >> /tmp/1.csv
echo "1,1" >> /tmp/1.csv

run accepts /tmp/1.csv



echo "x,y"  > /tmp/2.csv
echo "1,3" >> /tmp/2.csv
echo "2,3" >> /tmp/2.csv
echo "1,3" >> /tmp/2.csv
echo "1,3" >> /tmp/2.csv
echo "reset" >> /tmp/2.csv
echo "1,3" >> /tmp/2.csv
echo "2,3" >> /tmp/2.csv
echo "1,3" >> /tmp/2.csv
echo "1,3" >> /tmp/2.csv



echo "x,y"  > /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "2,3" >> /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "1,3" >> /tmp/3.csv
echo "reset"  > /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "2,3" >> /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "1,3" >> /tmp/3.csv


run accepts /tmp/1.csv /tmp/2.csv /tmp/3.csv

echo "x,y"  > /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "2,3" >> /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "reset"  > /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "2,3" >> /tmp/3.csv
echo "1,1" >> /tmp/3.csv


run rejects /tmp/1.csv /tmp/2.csv /tmp/3.csv

# ------------------
#
echo "x,y"  > /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "2,3" >> /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "1,3" >> /tmp/3.csv
echo "reset"  > /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "2,3" >> /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "1,3" >> /tmp/3.csv
echo "reset"  > /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "2,3" >> /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "1,3" >> /tmp/3.csv
echo "reset"  > /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "2,3" >> /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "1,3" >> /tmp/3.csv

run accepts /tmp/1.csv /tmp/2.csv /tmp/3.csv


rm /tmp/{1,2,3}.csv

echo "Test SUCCESSFUL"
