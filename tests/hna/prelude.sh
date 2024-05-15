#!/bin/bash

set -e

SRCDIR="$(dirname $0)/../.."
DIR="$(readlink -f $(dirname $0))"
WORKDIR=$(mktemp -d -t hna-test-XXX)


export ASAN_OPTIONS=detect_leaks=0

function gen {
	AUT_FILE="$1"
	cd $DIR
	$SRCDIR/hna.py --out-dir "$WORKDIR" "$AUT_FILE" --csv-header 'x: int, y: int' --alphabet='0,1,2,3' --debug --build-type=Debug -D SANITIZE=ON


	cd $WORKDIR
	make check -j4
}

TEST_NUM=0

function run {
	echo " ---- TEST $TEST_NUM ----"
	TEST_NUM=$(($TEST_NUM + 1))

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

	$WORKDIR/monitor $FILES | grep "HNA $RESULT"
}

