# 正式性能测量增加节点独占申请

日期：2026年10月8日。

已按用户要求修改服务器上的统一提交入口。今后正式性能任务明确申请节点独占，在独占作业中仍只使用一张计算卡进行测量。兼容提交入口会转交统一入口，因此同样生效。

## 修改方式

正式性能任务的提交命令增加 `--exclusive`。这一参数要求作业独占节点；冻结配置及提交预览同步记录 `resources.node_exclusive=true`。

独占作业可能拥有节点上的多张卡，因此作业脚本通过一个执行步骤（srun）请求一张卡及原配置的处理器核数。当前配置是8个处理器核。程序检查步骤只分配一张卡，并继续检查运行时实际只看到一张卡及其唯一标识。来源记录同时保存作业分配、步骤分配及测量所选设备，避免把作业拥有多张卡误判为多卡测量。

节点独占来自批量提交命令（sbatch）的 `--exclusive`；执行步骤中的同名参数用于限定步骤资源。参数含义见[批量提交官方说明](https://slurm.schedmd.com/sbatch.html#OPT_exclusive)及[执行步骤官方说明](https://slurm.schedmd.com/srun.html)。

## 文件位置

下列路径均位于服务器 `/public/home/zhangkewei/zr` 内。本地保存了同版本副本，点击链接可查看。

| 服务器文件及行号 | 修改内容及本地副本 |
| --- | --- |
| `/public/home/zhangkewei/zr/tools/workspace_manager/manager.py:145` | [提交预览及配置记录独占要求](C:/Users/ZR/Documents/Codex/2026-10-03/tong/outputs/节点独占测量设置20261008/source/tools/workspace_manager/manager.py:145) |
| `/public/home/zhangkewei/zr/tools/workspace_manager/manager.py:177` | [正式性能提交增加节点独占参数](C:/Users/ZR/Documents/Codex/2026-10-03/tong/outputs/节点独占测量设置20261008/source/tools/workspace_manager/manager.py:177) |
| `/public/home/zhangkewei/zr/jobs/workspace_task.slurm:10` | [正式测量进入单卡执行步骤](C:/Users/ZR/Documents/Codex/2026-10-03/tong/outputs/节点独占测量设置20261008/source/jobs/workspace_task.slurm:10) |
| `/public/home/zhangkewei/zr/tools/fft_measurement/common.py:25` | [共用作业与步骤的单卡检查](C:/Users/ZR/Documents/Codex/2026-10-03/tong/outputs/节点独占测量设置20261008/source/tools/fft_measurement/common.py:25) |
| `/public/home/zhangkewei/zr/tools/fft_measurement/run.py:23` | [实际运行使用单卡检查并保存分配信息](C:/Users/ZR/Documents/Codex/2026-10-03/tong/outputs/节点独占测量设置20261008/source/tools/fft_measurement/run.py:23) |
| `/public/home/zhangkewei/zr/tools/workspace_manager/test_manager.py:100` | [覆盖独占预览、单卡步骤及错误分配的自检](C:/Users/ZR/Documents/Codex/2026-10-03/tong/outputs/节点独占测量设置20261008/source/tools/workspace_manager/test_manager.py:100) |
| `/public/home/zhangkewei/zr/AGENTS.md:29` | [更新后续正式性能测量要求](C:/Users/ZR/Documents/Codex/2026-10-03/tong/outputs/节点独占测量设置20261008/source/AGENTS.md:29) |
| `/public/home/zhangkewei/zr/docs/technical/FFT_MEASUREMENT_PROTOCOL.md:277` | [测量规范中的资源隔离说明](C:/Users/ZR/Documents/Codex/2026-10-03/tong/outputs/节点独占测量设置20261008/source/docs/technical/FFT_MEASUREMENT_PROTOCOL.md:277) |
| `/public/home/zhangkewei/zr/docs/technical/WORKSPACE_MANAGEMENT.md:246` | [统一入口的操作要求](C:/Users/ZR/Documents/Codex/2026-10-03/tong/outputs/节点独占测量设置20261008/source/docs/technical/WORKSPACE_MANAGEMENT.md:246) |

本次修改只调整正式性能测量的资源隔离及分配记录。构建和快速正确性验证沿用原有申请方式。变换实现、已验证安装库、冻结计时程序、50次计时、八轮交错顺序和结果公式保持原样。历史任务保留其原始资源申请记录。

## 验证结果

提交管理自检26项、测量规范自检22项，合计48项全部通过；代码差异格式检查及作业脚本语法检查通过。

实际提交预览显示节点独占要求，仍为15种情形、720个进程、3次预热及每进程50次计时。预览没有预占运行目录或构建目录。

调度器预检查（`sbatch --test-only`）返回成功，接受独占节点参数，并显示按节点的128个处理器核估算资源。该检查仅评估请求，不创建实际作业；输出中的模拟作业编号也不是本次提交的性能任务。

真实独占作业中的单卡步骤、运行时设备可见性及分配记录，需在下一次获准提交的性能任务中核实。本次未提交新的性能任务。

冻结测量源码校验值：`849d011336601e6cffb1959e89590847e26160f7b3e256482a5eb37289e333da`。

EXP125已验证安装库校验值：`243849fd7f03849ce5d8378ae36324b9607f8c53e4b964e3e95dad859b86a677`。

服务器备份及验证记录：`/public/home/zhangkewei/zr/experiments/EXP-125/records/measurement-node-exclusive-20261008/`。其中保存修改前的八个文件、修改前后校验值、自检输出、提交预览及调度器预检查输出。
