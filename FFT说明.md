## 账号：

Host Z100L
  HostName 172.28.9.53
  User yuanxl
  Port 7022

密码：yuanxiaole

## 服务器联网教程：

https://zhuanlan.zhihu.com/p/688754897


## 准备工作

将DTK-26.04-SugonOS8.9-x86_64.tar.gz， rocm-libraries-rocm-7.2.2.tar.gz，解压到 ~/zr目录中


DTK说明：
https://developer.sourcefind.cn/ 

ROCM-libraries:
https://github.com/ROCm/rocm-libraries


## rocFFT 编译修复

**若重新解压缩rocm-libraries-rocm-7.2.2.tar.gz，需要手动设置动态链接：**


**1. 找到文件 `/rocm-libraries-rocm-7.2.2/projects/rocfft/cmake/std-filesystem.cmake：`**

**2. 找到下面一行**
```text
target_link_options( ${target} PRIVATE "SHELL:-lstdc++fs -static-libstdc++ -Xlinker --exclude-libs=ALL")
```
**3. 替换为**

```text
target_link_libraries(${target} PRIVATE stdc++fs)
```

否则链接阶段会报错：

```text
error: unable to find library -lstdc++
```

## 启用环境

conda activate fft

source ~/zr/dtk-26.04/env.sh 



## 编译rocfft以及hipfft



**直接运行 ~/zr/build.sh 进行编译：**
* 编译日志：~/zr/logs
* build目录： ~/zr/build
* install目录： ~/zr/install
* 编译需要的额外文件：~/zr/extern




## 编译cpp文件 可以使用以下指令：
```text
hipcc test.cpp \
  -o test \
  -I$HOME/zr/install/include \
  -L$HOME/zr/install/lib \
  -lrocfft -lhipfft -lm -lstdc++fs -std=c++17
```
