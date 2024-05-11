
#add_test(NAME test1
#	 COMMAND ./test.sh "forall t1, t2: x(t1) <= x(t2)" TRUE test1.csv)

add_test(NAME test1 COMMAND ./test1.sh)
