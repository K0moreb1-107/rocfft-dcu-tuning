# hiprtcConfig.cmake
#
# 自动从当前环境中查找 HIP/DTK 安装位置。
# 要求在运行 cmake 前已经执行：
#     source /opt/dtk-*/env.sh

# ------------------------------------------------------------------------------
# 防止重复加载
# ------------------------------------------------------------------------------

if(TARGET hiprtc::hiprtc)
    set(hiprtc_FOUND TRUE)
    return()
endif()

# ------------------------------------------------------------------------------
# 查找 libamdhip64.so
# ------------------------------------------------------------------------------

find_library(HIPRTC_LIBRARY
    NAMES amdhip64
    HINTS
        ENV ROCM_PATH
        ENV HIP_PATH
        ENV HIP_ROOT_DIR
        ENV DTK_HOME
    PATH_SUFFIXES
        lib
        lib64
        hip/lib
    REQUIRED
)

# ------------------------------------------------------------------------------
# 查找 hiprtc.h
# ------------------------------------------------------------------------------

find_path(HIPRTC_INCLUDE_DIR
    NAMES hip/hiprtc.h
    HINTS
        ENV ROCM_PATH
        ENV HIP_PATH
        ENV HIP_ROOT_DIR
        ENV DTK_HOME
    PATH_SUFFIXES
        include
        hip/include
    REQUIRED
)

# ------------------------------------------------------------------------------
# 创建 imported target
# ------------------------------------------------------------------------------

add_library(hiprtc SHARED IMPORTED)

set_target_properties(hiprtc PROPERTIES
    IMPORTED_LOCATION "${HIPRTC_LIBRARY}"
    INTERFACE_INCLUDE_DIRECTORIES "${HIPRTC_INCLUDE_DIR}"
    INTERFACE_COMPILE_DEFINITIONS "__HIP_PLATFORM_AMD__"
)

# 命名空间 target
add_library(hiprtc::hiprtc ALIAS hiprtc)

# ------------------------------------------------------------------------------
# 兼容变量
# ------------------------------------------------------------------------------

set(hiprtc_FOUND TRUE)
set(HIPRTC_FOUND TRUE)

set(hiprtc_LIBRARY "${HIPRTC_LIBRARY}")
set(hiprtc_LIBRARIES hiprtc::hiprtc)
set(hiprtc_INCLUDE_DIR "${HIPRTC_INCLUDE_DIR}")
set(hiprtc_INCLUDE_DIRS "${HIPRTC_INCLUDE_DIR}")

set(HIPRTC_LIBRARY "${HIPRTC_LIBRARY}")
set(HIPRTC_LIBRARIES hiprtc::hiprtc)
set(HIPRTC_INCLUDE_DIR "${HIPRTC_INCLUDE_DIR}")
set(HIPRTC_INCLUDE_DIRS "${HIPRTC_INCLUDE_DIR}")