#!/bin/bash

set -e

SRCDIR="$(dirname $0)/../.."
DIR="$(readlink -f $(dirname $0))"
WORKDIR=$(mktemp -d -t hnl-test-XXX)

function gen {
	FORMULA="$1"
	cd $DIR
	$SRCDIR/hnl.py --out-dir "$WORKDIR" "$FORMULA" --csv-header 'x: int, y: int' --alphabet='0,1,2,3' --debug

	cd $WORKDIR
	make check -j4
}


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

	cd $WORKDIR
	./monitor $FILES | grep "Formula is $RESULT"
}

