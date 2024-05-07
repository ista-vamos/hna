#include <catch2/catch_test_macros.hpp>
#include <set>

#include "hna/codegen/templates/cpp/prefixtree.h"


TEST_CASE( "Basic operations", "[prefixtree]" ) {
  PrefixTree<char> T;
  REQUIRE(T.insert(std::string("abc")).second);
  auto *ab = T.get(std::string("ab")); 
  REQUIRE( ab );
  REQUIRE( ab->value() == 'b' );
  REQUIRE( ab->has_children()  );
  REQUIRE( !ab->insert('c').second);
  REQUIRE( ab->insert('d').second);
  REQUIRE( T.get(std::string("abd")) );
  REQUIRE( !T.insert(std::string("abc")).second);
  REQUIRE( !T.insert(std::string("abd")).second);
  REQUIRE( T.insert(std::string("abe")).second);
  REQUIRE( !ab->insert('e').second);
  REQUIRE( ab->get('e')->value() == 'e');
  REQUIRE( ab->insert(std::string("abc")).second);
  REQUIRE( T.get(std::string("ababc")));
  REQUIRE( !T.insert(std::string("ababc")).second);

 //std::set<std::string> tmp;
 //std::set<std::string> S = {"abc"};
 //std::vector<char> vals;
 //for (auto& V : T.iterate(vals)) {
 //  tmp.push_back(to_string(V));
 //}



  REQUIRE(T.get());
}
