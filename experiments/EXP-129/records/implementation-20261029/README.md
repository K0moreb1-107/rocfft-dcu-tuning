# EXP129：门控精简实施与主机验证

日期：2026-10-29。用户确认依照官方代码的组织、思路和码风实施。分支 exp-129-gate-simplification，起点为保存的 EXP128 V6。实施随本记录提交；源文件、校验值及保存点见 implementation.json。

## 实际改动

- tree_node_real.cpp/.h：公共范围、布局与格式只检查一次；依据CC构造不变量删除数量、类型、ebtype、长度乘积及反序复验；内部构造helper改为protected。保留旧配对路径的单因子几何匹配、方向、设备、资源、fallback及LOCAL关闭时提前构造旧路径的顺序。
- 内核能力单独查询，资源公式只计算一次；一列缓存用TPB>=LDS分母表达。两个环境加载模式共用解析，不跨计划缓存环境值。
- node_factory.cpp/.h：移除单调用的多输出布尔helper，就地查表，保持成功、缺项失败、不可执行映射回退三态及gfx906分支；所有分解表内容保持。
- rtc_stockham_kernel.cpp/real_block_io.h：按角色设置加载策略，只对需要的普通路径验证静态映射，精确recurrence候选才回溯根；保留CC-local从强制前配置继承的recurrence和缓存语义。寄存器输入不再重算构造specs时已计算的因子乘积，保留线程几何和shuffle条件。
- stockham_gen_base.h/cc.h：复用确实相同的内核形状判断，避免临时vector；删除恒false波前分支及唯一调用点之后的重复exchange条件。不增加scheme限制，不合并不同特化的支持集合。
- 实数生成器：列缓存保留覆盖新旧继承路径的最终几何短式；删除已由RTC确定的逆行register-pre重复验算；paired后处理删除固定role/N/pitch复验，实际长度和线程几何仍保留。

没有新增门控框架或重复TreeNode策略字段。没有改变支持范围、旋转因子表覆盖条件、用户/临时buffer视图、callback语义、Hermitian/DC/Nyquist或尾块保护。不同阶段的role分派、最终派生几何检查仍按职责保留，不以缩短代码为由删除。

## 官方风格依据

逐项对照zr内official-rocm722-source的7.2.2源码：RTFuseShim::CheckSchemeFusable按scheme/布局/相位/性能条件分段返回；SBCC_dim_available集中内核与能力查询；NodeFactory保持直接查表及fallback。新增代码使用同类分段early-return、局部常量、内部helper和既有元数据，不引入策略DSL。遵循rocFFT自己的.clang-format中的4空格、Allman括号、100列及声明对齐。环境无clang-format工具，本轮人工核对改变段落与差异格式，未声称运行过自动格式化。

## 已完成的验证

| 检查 | 结果与证据边界 |
| --- | --- |
| 实际C++编译 | 8项通过：生成器、driver、RTC、NodeFactory和四种融合开关的real tree；编译日志保留，不等同完整库链接或设备执行 |
| 真实旧新融合/调度片段 | 41536例一致，覆盖四开关、solution旁路、stride/格式/设备/资源边界、旧异分解及非法env报错时机 |
| 真实planner分支 | 1024例一致，含缺项/非法映射/kernel缺失及gfx906 |
| 真实RTC策略片段 | 8847360组合、8个最终字段一致；含角色、callback、half/direct、tile及根形状 |
| 历史生成器谓词 | 768000状态、6个pass、4个方法一致 |
| 完整生成源码 | 283几何，默认2264+保留LDS566，共2830份；与重新运行的保存V6生成器输出逐字一致，内核名一致，未做归一化 |

主机片段对照直接抽取实际旧新源码，注册表和CC节点由最小mock提供；不覆盖完整公开计划和节点构造后半。生成对照只覆盖所登记矩阵；并不声称穷尽所有用户配置。完整记录见host-equivalence.json、planner-gates.json、rtc-policy-equivalence.json、generator-predicates.json，原始编译和生成代码在本实验artifacts下。可复核源码片段和程序随host-proofs保存。原始diff和提取片段保留原样，包括diff格式所需的空白；码风检查针对生产代码及新编写的脚本和说明，不格式化原始证据。

主机验证入口：python3 experiments/EXP-129/scripts/verify_gate_simplification.py。脚本独占新结果目录，拒绝覆盖本次证据；复跑须选择新目录。仅EXP129副本适配了CanRegisterInput的新内部签名，历史EXP128脚本及证据保持原样。

## 当前边界与下一步

本轮未执行完整库构建、GPU数值/路径验证或性能任务，没有新任务号或加速比，不晋升稳定版或推送。后续构建和验证按manage.py分开提交，先两尺寸的双方向数值及实际路径，通过后才覆盖变动分支；不擅自运行稳定发布完整矩阵。若需要测量，previous固定为保存V6，同卡相邻交替、10/30、中位数。

AGENTS.md及VkFFT的既有改动不纳入提交；main、旧标签和历史实验材料保持。
