#!/bin/bash

set -e

SRCDIR="$(dirname $0)/../.."
DIR="$(readlink -f $(dirname $0))"
WORKDIR=$(mktemp -d -t hnl-test-XXX)


export ASAN_OPTIONS=detect_leaks=0

function gen {
	FORMULA="$1"
	shift

	echo "--- Generating monitor for formula ---"
	echo $FORMULA
	echo "--------------------------------------"

	cd $DIR
	$SRCDIR/hnl.py --out-dir "$WORKDIR" "$FORMULA" $@ --csv-header 'x: int, y: int' --alphabet='0,1,2,3' --debug --build-type=Debug -D SANITIZE=ON

	cd $WORKDIR
	make check -j4
}

N=1
function run {
	RESULT=$1
	shift

	FILES=
	for F in $@; do
		case $F in
			# absolute path
  			/*) FILES="$FILES $F" ;;
			# relative path, assume the file is in DIR
  			 *) FILES="$FILES $DIR/$F" ;;
		esac
	done

	echo "--- TEST $N ---"
	$WORKDIR/monitor $FILES | grep "Formula is $RESULT" ||\
		(
			echo "-- Test $N FAILED --";
			echo "$WORKDIR/monitor $FILES"
			echo "Expected: $RESULT"
			exit 1
		)

	N=$(($N + 1))
}

