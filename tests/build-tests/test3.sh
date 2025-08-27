#!/bin/bash

set -e

source prelude.sh

gen 'forall t1. exists t2. forall t3: in(t1) <= in(t2) && in(t3) = out(t1)' --data 'in: uint64_t, out: uint64_t'
gen 'exists t1. forall t2. exists t3: in(t1) <= in(t2) && in(t3) = out(t1)' --data 'in: uint64_t, out: uint64_t'
gen 'exists t1. exists t2. forall t3: in(t1) <= in(t2) && in(t3) = out(t1)' --data 'in: uint64_t, out: uint64_t'

echo "Test SUCCESSFUL"
