#include <catch2/catch_test_macros.hpp>
#include <set>

#include "hna/codegen/templates/cpp/prefixtreeautomaton.h"


TEST_CASE( "Basic operations", "[prefixtreeautomaton]" ) {
  PrefixTreeAutomaton<char> T;

  REQUIRE(T.insert(std::string("abc")).second);
  REQUIRE(T.insert(std::string("a")).second);
  REQUIRE(!T.get(std::string("")));
  REQUIRE( T.get(std::string("a")));
  REQUIRE(!T.get(std::string("ab")));
  REQUIRE( T.get(std::string("abc")));
  REQUIRE(!T.get(std::string("abcd")));

  REQUIRE(T.insert(std::string("ab")).second);
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

  REQUIRE(T.get());
}
