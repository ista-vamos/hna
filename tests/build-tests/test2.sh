#!/bin/bash

set -e

source prelude.sh

gen 'forall t1. exists t2: in(t1) <= in(t2)' --data 'in: uint64_t, out: uint64_t'
gen 'forall t1. exists t2: (!(in(t1) <= in(t2) && in(t2) <= in(t1)) || (out(t1) <= out(t2) && out(t2) <= out(t1)))' --data 'in: uint64_t, out: uint64_t'

echo "Test SUCCESSFUL"
