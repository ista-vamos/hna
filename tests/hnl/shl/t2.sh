#!/bin/bash

set -e

source prelude.sh

# x in input, y is output
#
gen "forall t1,t2: (!(x(t2) <= x(t1)) || y(t2) <= y(t1)) && (!(x(t1) <= x(t2)) || y(t1) <= y(t2)) " --reduction reflexive,symmetric

echo "x,y"  > /tmp/4.csv
echo "1,1" >> /tmp/4.csv
echo "1,1" >> /tmp/4.csv
echo "3,1" >> /tmp/4.csv
echo "2,2" >> /tmp/4.csv
echo "1,3" >> /tmp/4.csv
echo "1,1" >> /tmp/4.csv
echo "2,2" >> /tmp/4.csv
echo "1,3" >> /tmp/4.csv
echo "0,1" >> /tmp/4.csv

echo "x,y"  > /tmp/5.csv
echo "1,2" >> /tmp/5.csv
echo "1,1" >> /tmp/5.csv
echo "3,1" >> /tmp/5.csv
echo "2,2" >> /tmp/5.csv
echo "1,3" >> /tmp/5.csv
echo "1,0" >> /tmp/5.csv
echo "2,2" >> /tmp/5.csv
echo "1,3" >> /tmp/5.csv
echo "0,1" >> /tmp/5.csv
echo "0,1" >> /tmp/5.csv
echo "0,1" >> /tmp/5.csv
echo "0,1" >> /tmp/5.csv

run FALSE /tmp/4.csv /tmp/5.csv


echo "Test SUCCESSFUL"
