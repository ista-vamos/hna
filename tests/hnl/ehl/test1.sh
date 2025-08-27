#!/bin/bash

set -e

source prelude.sh

gen "forall t1,t2: x(t1) <= x(t2)"

echo "x,y"  > /tmp/1.csv
echo "1,1" >> /tmp/1.csv
echo "2,2" >> /tmp/1.csv
echo "1,3" >> /tmp/1.csv
echo "1,1" >> /tmp/1.csv

run TRUE /tmp/1.csv

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

run TRUE /tmp/1.csv /tmp/2.csv /tmp/3.csv

echo "x,y"  > /tmp/3.csv
echo "1,1" >> /tmp/3.csv
echo "2,3" >> /tmp/3.csv
echo "1,1" >> /tmp/3.csv

run FALSE /tmp/1.csv /tmp/2.csv /tmp/3.csv

rm /tmp/{1,2,3}.csv

echo "Test SUCCESSFUL"
