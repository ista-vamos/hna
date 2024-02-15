cmake_minimum_required(VERSION 3.9)
project(hna)

enable_testing()

if (NOT EXISTS vamos/CMakeFiles.txt)
    execute_process(COMMAND git submodule update --init --recursive -- vamos
    WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}
    COMMAND_ERROR_IS_FATAL ANY)
endif()

if (NOT EXISTS ${PROJECT_SOURCE_DIR}/vamos/vamos-buffers/cmake/vamos-buffers/vamos-buffers.cmake)
    #message(FATAL_ERROR "Please build VAMOS first (./build-vamos.sh)")
    message(STATUS "Seems like VAMOS was not build, trying to build it")
    execute_process(COMMAND ./build-vamos.sh
    		    WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}
 		    COMMAND_ERROR_IS_FATAL ANY)
endif()

set(vamos-buffers_DIR ${PROJECT_SOURCE_DIR}/vamos/vamos-buffers/cmake/vamos-buffers)
set(vamos-common_DIR ${PROJECT_SOURCE_DIR}/vamos/vamos-common/cmake/vamos-common)
set(vamos-sources_DIR ${PROJECT_SOURCE_DIR}/vamos/vamos-sources/cmake/vamos-sources)

find_package(vamos-buffers REQUIRED)
find_package(vamos-sources REQUIRED)
find_package(vamos-common REQUIRED)

# make sure the paths are absolute
get_filename_component(vamos-buffers_DIR ${vamos-buffers_DIR} ABSOLUTE)
get_filename_component(vamos-buffers_SRCDIR ${vamos-buffers_DIR}/../.. ABSOLUTE)
get_filename_component(vamos-sources_SRCDIR ${vamos-sources_DIR}/../.. ABSOLUTE)
get_filename_component(vamos-common_SRCDIR ${vamos-common_DIR}/../.. ABSOLUTE)

if(NOT CMAKE_BUILD_TYPE)
        if (vamos_buffers_BUILD_TYPE)
	        message(STATUS "Build type not set, using the same as vamos-buffers.")
	        set(CMAKE_BUILD_TYPE ${vamos_buffers_BUILD_TYPE} CACHE STRING "" FORCE)
        else()
	        message(STATUS "Build type not set. Setting default RelWithDebInfo.")
	        set(CMAKE_BUILD_TYPE "RelWithDebInfo" CACHE STRING "" FORCE)
        endif()
endif()

if (NOT ${vamos_buffers_BUILD_TYPE} STREQUAL ${CMAKE_BUILD_TYPE})
        message(WARNING "Build type (${CMAKE_BUILD_TYPE}) is different from "
                        "vamos-buffers' build type (${vamos_buffers_BUILD_TYPE}). "
                        "That can cause troubles with linking if IPO is enabled at "
                        "vamos-buffers and not in this project "
                        "(vamos_buffers_IPO=${vamos_buffers_OPTION_ENABLE_IPO})")
endif()

OPTION(ENABLE_IPO "Enable interprocedural optimizations" ${vamos_buffers_IPO})

if (ENABLE_IPO)
	cmake_policy(SET CMP0069 NEW)
	include(CheckIPOSupported)
	check_ipo_supported()
	set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)
endif(ENABLE_IPO)


get_target_property(vamos-buffers_vamos-buffers-lib vamos-buffers-lib LOCATION)
get_target_property(vamos-buffers_vamos-buffers-ringbuf vamos-buffers-ringbuf LOCATION)
get_target_property(vamos-buffers_vamos-buffers-shmbuf vamos-buffers-shmbuf LOCATION)
get_target_property(vamos-buffers_vamos-buffers-streams vamos-buffers-streams LOCATION)
get_filename_component(vamos-buffers_LIBRARIES_DIRS_lib ${vamos-buffers_vamos-buffers-lib} DIRECTORY)
get_filename_component(vamos-buffers_LIBRARIES_DIRS_core ${vamos-buffers_vamos-buffers-ringbuf} DIRECTORY)
get_filename_component(vamos-buffers_LIBRARIES_DIRS_shmbuf ${vamos-buffers_vamos-buffers-shmbuf} DIRECTORY)
get_filename_component(vamos-buffers_LIBRARIES_DIRS_streams ${vamos-buffers_vamos-buffers-streams} DIRECTORY)

get_filename_component(vamos-common_DIR ${vamos-common_DIR} ABSOLUTE)

configure_file(${CMAKE_CURRENT_SOURCE_DIR}/config.py.in
	       ${CMAKE_CURRENT_SOURCE_DIR}/config.py)


#add_custom_target(gen-readme
#                  COMMAND pandoc -f markdown -t HTML -o README.html README.md
#                  COMMAND pandoc -f markdown -t pdf -o README.pdf README.md)
