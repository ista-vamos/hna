#!/bin/bash

set -e

cd vamos
make DYNAMORIO_SOURCES=OFF\
        LLVM_SOURCES=OFF\
        TESSLA_SUPPORT=OFF\
        LIBINPUT_SOURCES=OFF\
        WLDBG_SOURCES=OFF\
        $@

