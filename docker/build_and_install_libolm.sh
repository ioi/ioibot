#!/usr/bin/env sh
#
# Call with the following arguments:
#
#    ./build_and_install_libolm.sh <libolm version> <python bindings install dir>
#
# Example:
#
#    ./build_and_install_libolm.sh 3.1.4 /python-bindings
#
# Note that if a python bindings installation directory is not supplied, bindings will
# be installed to the default directory.
#

set -ex

# Download the specified version of libolm
git clone -b "$1" https://gitlab.matrix.org/matrix-org/olm.git olm && cd olm

cmake -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_BUILD_TYPE=Release -Bbuild .

cmake --build build

make -C build install

cd python

python3 -m pip install .
