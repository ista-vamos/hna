find_package(Catch2 3)

function(_add_test name source)
	add_executable(${name} ${source})
	target_link_libraries(${name} PRIVATE Catch2::Catch2WithMain)
	target_include_directories(${name} PRIVATE ${CMAKE_SOURCE_DIR})
	add_test(${name} ${name})
endfunction()

if (Catch2_DIR)
	_add_test(prefixtree prefixtree.cpp)
	#	_add_test(prefixtreeautomaton prefixtreeautomaton.cpp)
else()
	message(WARNING "Catch2 not found, not compiling tests")
endif()

add_subdirectory(hnl)
add_subdirectory(hna)
