#!/bin/bash

set -e

SRCDIR="$(dirname $0)/../.."
DIR="$(readlink -f $(dirname $0))"
WORKDIR=$(mktemp -d -t hnl-test-XXX)

function gen {
  echo "--- Generating monitor for formula ---"
  echo $FORMULA
  echo "--------------------------------------"

  cd $DIR
  $SRCDIR/hnl.py --out-dir "$WORKDIR" "$@"

 #cd $WORKDIR
 #cmake --build . -j4
}
