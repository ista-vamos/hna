SRCDIR=$(dirname $0)/../..

set -e

FORMULA=$1
RESULT=$2
shift
shift
FILES=

for F in $@; do
	FILES="$FILES $(readlink -f $F)"
done

WORKDIR=$(mktemp -d -t hnl-test-XXX)
$SRCDIR/hnl.py --out-dir "$WORKDIR" "$FORMULA" --csv-header 'x: int, y: int' --alphabet='0,1,2,3' --debug

cd $WORKDIR
make check -j4

./monitor $FILES | grep "Formula is $RESULT"

rm -rf $WORKDIR
