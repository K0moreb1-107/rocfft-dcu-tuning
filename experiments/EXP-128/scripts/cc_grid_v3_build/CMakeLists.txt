cmake_minimum_required(VERSION 3.16)
project(rocfft_v3_grid LANGUAGES CXX)
if(NOT CC_GRID_GROUP MATCHES "^[0-3]$")
  message(FATAL_ERROR "CC_GRID_GROUP must be 0, 1, 2, or 3")
endif()
set(GRID_PYTHON "/public/software/apps/anaconda3/2023.09/bin/python")
set(GRID_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/../build_cc_grid_v3.py")
add_custom_target(rocfft-rtc-gen
  COMMAND ${CMAKE_COMMAND} -E echo "Reusing the verified v3 runtime generator objects")
add_custom_command(OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/grid-install/lib/librocfft.so.0.1"
  COMMAND "${GRID_PYTHON}" -B "${GRID_SCRIPT}" --group "${CC_GRID_GROUP}"
          --output "${CMAKE_CURRENT_BINARY_DIR}"
  DEPENDS "${GRID_SCRIPT}"
  VERBATIM)
add_custom_target(rocfft ALL
  DEPENDS "${CMAKE_CURRENT_BINARY_DIR}/grid-install/lib/librocfft.so.0.1")
install(DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/grid-install/" DESTINATION ".")
