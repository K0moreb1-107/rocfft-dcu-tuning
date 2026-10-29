# EXP129：按官方风格精简门控的实施方案

状态：方案完成，尚未实现。日期：2026-10-29。

## 起点、范围与证据

从用户指定的当前 EXP128 V6 延续，不切回 main 引入其他融合代码。保存提交 1d22a78fad885db364b3ad631eaddb2baf0fcf1f，标签 exp128-before-gate-simplification-20261029；新分支 exp-129-gate-simplification。源码 tree ed2dd2b7fa0f00c148bace51a28d9463d41b5bae 与已测构建 babe7b5379aa37892f56cd190de21190d1838f68 相同。库身份和既有测量见前一实验 checkpoint.json。保存点包含六份既有配置和一份既有验证脚本改动，这些管理改动不冒充新的设备验收。

源码根：rocm-libraries-rocm-7.2.2/projects/rocfft/。官方对照：official-rocm722-source/projects/rocfft/，版本 7.2.2。只访问 /public/home/zhangkewei/zr 及其子目录。

目标覆盖之前清单中的全部条件类别：融合调度与三入口、CC 分解、寄存器能力、历史特化、生成器复验、角色分派、缓存、buffer view 与设备边界。每一类都有处理决定，并非要求消灭所有条件。保留合法输入的原有选路、加载方式、生成代码、设备资源及回退；不改变尺寸表、GPU 数学、同步、物理布局、callback 语义或支持范围。收益主要为维护性和计划/RTC 准备开销，不承诺 GPU 耗时降低。

当前授权是保存旧版、创建新版并完成实现设计；本轮只写实验记录，不写生产实现，不构建或提交设备任务。

## 1. 官方组织方式与修改边界

依据官方 tree_node_real.cpp 的 SBCC_dim_available 和 fuse_shim.cpp 的 RTFuseShim::CheckSchemeFusable：先检查对象与布局，再检查实际能力，不满足就返回。构造职责仍留在原节点类中。公共公式在最接近使用位置的能力函数内计算一次。

新增公共抽象限制为确实复用的变换资格和内核能力判断；不引入通用门控框架、规则字符串、全局策略表、逐条件对象或每两个比较一个 helper。相同形状判断复用已有 StockhamGeneratorSpecs/生成器数据，不给 TreeNode 增加一套重复缓存字段。

## 2. 融合公共条件与调用次序

文件：library/src/tree_node_real.cpp、include/tree_node_real.h。

增加一个私有的公共资格判断 CanFuseCCReal()，分段检查：一维且没有附加维度；batch1、DP、OOP；输入输出 stride 都是单个 1 且偏移零；按方向检查 real/HI 两侧格式。三个入口的这些条件由调用层只检查一次。暂保留 dimension 与 length.size 两个含义不同的字段，不凭字段名称推断完全等价。步长比较可使用 size()==1 加 front()==1，确保没有临时 vector 且不会空向量访问。

共同资格不包含 gfx936/wave64、方向单选、白名单或 CC 类型，因为三条路径目前对它们的要求不同。不能取三路径条件交集，导致旧路径被额外收窄。

调度顺序必须保持：

```cpp
const bool try_cc_real
    = noSolution && ROCFFT_CC_REAL_FUSION && CanFuseCCReal();

// 保持原有先构造旧路径、后建立 cfft 的次序。
if(try_cc_real && !ROCFFT_CC_LOCAL_REAL_FUSION && TryBuildLocalRealTree(n))
    return;

// 这里保留原 solution map 和 cfft 的构造。

if(try_cc_real)
{
    if(ROCFFT_CC_LOCAL_REAL_FUSION && TryBuildCCLocalTree(*cfftPlan, n))
        return;
    if(ROCFFT_CC_LOCAL_REAL_FUSION && TryBuildLocalRealTree(n))
        return;
    if(TryFusePairedPost(*cfftPlan, n))
    {
        childNodes.emplace_back(std::move(cfftPlan));
        return;
    }
}
// 保留官方原有 small/single-leaf 和独立 pre/post 路径。
```

这是结构示意，不能把本来发生在旧路径之后的 cfft 建树提前；保留两个编译开关全部四种组合、solution map、非法环境值仅在实际尝试旧路径时读取的行为。

TryBuildCCLocalTree 内只留下本路径设备/尺寸策略、cfft.scheme、一次 Bluestein 排除、真实内核能力和构造。删除刚建 CC 的数量、类型、ebtype、因子正值、长度维数、乘积、反序检查。依据是 CC1DNode::BuildTree_internal 已设置和验证这些值，且调用在任何融合属性写入之前。除构造者已存在的检查外，不在消费者重新铺设等量 assert。

重要例外：TryFusePairedPost 对 first.length 与旧白名单 geometry 的比较并非全冗余。合法 CC 可以采用另一分解。只需比较一个独立因子是否等于 io.columns；另一个因子、row 的反序、large1D 由同一个 N 的 CC 构造推出。不能把白名单几何与当前 CC 几何的匹配一起删除。

## 3. 能力与资源计算

文件：tree_node_real.cpp、生成器列类。

用一个有明确用途的 CCRealKernelsAvailable(columns, rows) 成员能力查询或等价的文件内函数，集中原有 SBCC/SBRC 查询和资源判断，避免把所有条件重新拼成一条长式。仅保留实际所需的 aligned 参考配置及选出的 transpose 配置查询；未证明两种记录相同前，不用其中一个的资源值代替另一个，也不以之后 KernelCheck 会执行为由删掉早期可回退的能力判断。

采用局部常量 complex_bytes=16、lds_divisor=(half_lds?2:1)，复用字节数公式。当前 DP 范围不扩大。

对合法正列长 C：floor(C*TPB/h)>=C 等价于 TPB>=h（h=1或2）。因此一列缓存条件写 TPB >= (half_lds?2:1)，不再写乘除长公式。保留 q>=CC.TPB、direct-register 支持及两段共享存储上限。中间矩阵仍为 C*Q，不因精简多申请工作空间。

列生成器的同类条件先采用等价短式。不可直接删掉基类检查：StockhamKernelHermitianColumns 也继承 StockhamKernelFoldedPackedColumns；旧路径未经过新通用入口。若集中删除，则将所有调用路径接到同一最终几何检查，而不是只覆盖新入口。生成器 TPB 可由 WGS/TPT 推导，不能把 function_pool 声明 TPB 与派生 TPB 的一致性当成未经证明的前提。

## 4. RTC 策略：按角色决定，避免无效求值

文件：rtc_stockham_kernel.cpp、rtc_stockham_gen.cpp、include/real_block_io.h。

按 None/普通、四种 CC-local、HermitianColumns、LocalRealRows、PairedPostRows 分支组织。普通静态加载的便宜资格（node.scheme、tile、DP、embedded、callback、原生 direct-reg）先检查，通过才检查映射。node.scheme==BLOCK_RC 已蕴含 pool_scheme==BLOCK_RC，可消除重复 scheme 条件，但不能只保留 pool_scheme：其他转置方案也会映射到该 pool scheme。

不能简单把所有普通策略放入 else：现代码在 CC-local 强制加载设置之前计算的 sbrc_ordinary_twiddle_recurrence 未在该分支清零，可能被后续生成器和 RTC name 继续使用；LocalRealRows/PairedPostRows 则显式清零。重构必须保留这个区别。

实现采用各角色最终需要的输出字段表：direct_to_from_reg、static_initial_reg_load、linear、half_lds、real_io.load、sbrc_ordinary_twiddle_recurrence。每角色完整赋值，原来不改的值保留原配置。对 CC-local 的 recurrence 单独保留原始资格和根 N131072/512点精确形状条件，依据的是强制前的 kernel 属性，不能使用强制后的 static=true 重算。精确 {8,8,8}/L512/WGS512/TPT128 已蕴含相关 power2/乘积/整除条件，可直接复用形状谓词避免因子遍历。

根节点回溯只在有可能使用该 recurrence 的形状与角色中执行，且每次 generate_from_node 内只做一次。不要跨计划缓存设备、callback、环境变量或根属性。

real_io.load 在 RTC 决定一次后传入 specs，生成器不再重新选择另一种 load。保留 register 失败回 LDS 的范围。

## 5. 寄存器能力检查的边界

StockhamGeneratorSpecs 构造函数直接以 factors 乘积生成 length；当前唯一 CanRegisterInput 使用点是上述 RTC specs。对合法内部配置，重复计算 product==length 没有新的映射信息。删除该调用链中重复乘积遍历及 length/factors 重复参数，保留真正决定映射的工作组整除条件；非整除配置仍走原 LDS 路径。不要将现存对外或 tuning 配置的验证删除，也不要在未验证的入口假定 TPT 非零而新增除零风险。

CanRegisterPre 保留 first radix 偶数、有效 lanes、lanes<=64、二次幂及 k/TPT 整除 lanes：生成器 __shfl 的镜像配对依赖这些条件。统一输入为已经完成构造的 specs，RTC 查询一次；生成器中重复的 cc_local_register_pre 包装和运行时重复验算在确认唯一调用链后删除，必要的不变量仅在共有构造边界处理。

旧 LocalRealRows/PairedPostRows 构造检查拆成：路径独有的几何要求留在能力判断一次；由固定赋值推出的 role、N=2*C*Q、pitch、large1D 去掉重复复验。最终派生 WGS/TPT/TPB 的一致性和 callback 能力检查保留一处。显式 solution/tuned key 会跳过部分硬编码 tuning，不应让这类路径绕过必需验证。

## 6. 历史特化与死分支

文件：stockham_gen_base.h、stockham_gen_cc.h、stockham_gen_cc_real_columns.h、stockham_gen_cc_real_rows.h。

复用 256/512/1024 点相同 radix/TPT 形状谓词，在其基础上组合各优化自己需要的 DP/half-LDS/WGS/TPB/pass 条件；先确认集合相同再合并。不会将各优化范围并集，也不新增按 N 的名单。common_sbcc 等旧变量的名字不能作为 scheme 约束证据，当前部分表达式实际没有检查 scheme，重命名/提取时不得偷偷增加该限制。

use_wave_sync() 当前恒 false，局部 is_dp/is_sbcc 未参与返回；删除该函数与死分支，sync_threads() 直接生成现有 SyncThreads。register_local_exchange 当前调用者已判断能力，函数体不必再次相同查询；保留 pass2/1024/8,8,4,4/64线程与原交换次序。

ordinary recurrence、large recurrence、late-LDS、swizzle、packed output、single-row output 的必要条件保留，重复字段比较复用局部已命名值。大 twiddle 的 large1D<=2^18 是已有表覆盖安全条件，不能当实验门槛删除。设备端 direct/load/apply-large/base/steps 条件保持生成表达式。

## 7. 分解表、模式、角色与生命周期

文件：node_factory.cpp、include/node_factory.h；旧模式解析和现有 buffer/RTC 文件。

Get1DBlockComputeDivisor 只有一个调用者，当前 bool + mapEntryFound 表达三种状态。将查表就地组织在 Decide1DScheme：选精度表、查一次、分别处理缺项/有项不可执行/可执行。保留缺项且N<=524288的失败行为、不可执行映射的TRTRT回退、gfx906分支，以及所有表项。非法精度和表项合法性检查复用相应权威边界；没有证据证明表只读且已验证的项目，不擅自删运行检查。

旧两个 env 模式使用同一个轻量解析函数，调用时机和未设置默认值保持；不使用全局 static 缓存 getenv，因为后续计划可能改变环境。旧白名单保留在现有 ForLength 一处。

同一函数多次 role 判断可收敛为 switch；跨生成器选择、物理视图、twiddle 建立/销毁、参数传递等不同阶段的 role 分派保留。SmallPhaseLength 等值在单次使用中只求一次，不另存 TreeNode 重复字段。

不改 buffer view 计算的 real/complex 单位、用户/临时buffer归属、callback次数及回调后共轭、DC/Nyquist、镜像与尾块保护。缓存名继续编码最终影响生成代码的角色、几何、load、callback、phase/recurrence 信息。仅代码组织等价时不增加 v7 后缀；若 GPU 代码或策略真正改变，先判定超出等价精简，再单独登记版本，不能用改缓存名掩盖不一致。

## 8. 支持范围与不能混入的变更

gfx936/wave64、DP/batch1/OOP、零偏移、N>=65536且N<=2^24 暂集中保留。删除结构复验不扩大这些范围。不能凭目前最大测量 N2725888 推断2^24以上安全，或凭所有函数在CPU执行就删除GPU线程映射约束。

本轮不删除旧融合后端，不改常量表、不改变缺映射回退、不额外开放平台/布局/精度，不改 FFT 数学或设备同步。放宽支持范围是独立后续优化，需要对应索引、资源和设备证据，不与本次等价整理混在一起。

## 9. 实施拆分、验收与恢复

实施按四个可审阅部分推进：A 公共资格/调用顺序/CC不变量；B 资源公式和唯一能力判断；C RTC角色策略与寄存器检查；D 历史特化、分解表调用接口、模式和role组织。每部分记录改动与生成代码是否保持，不需要每一小步提交GPU任务。

主机验证使用前后真实实现对照，不另写一份同构门控当预言机：

- 四种 CMake 开关组合、无/有solution、默认/tuned配置的合法计划前后对照；未改分解表内容完全相同。
- 复用 EXP128 当前194默认N/388方向和283几何登记，按真实新旧生成器比较角色、几何、加载、共享存储、最终策略、RTC key 和完整源码；保留旧五几何、寄存器/LDS、非整除尾块、普通C2C和常见非适用配置样本。
- 对生成器构造会重新推导几何的非RTC入口做代表检查；不能只比较字段而跳过最终派生结果。
- 正常化仅允许纯文件位置等无语义差异；不得忽略任何算法表达式、地址、条件、同步或资源变化。发现GPU源码差异先解释，等价整理期望其保持；无需无目的重编译全部不变源码。
- 主机生成及计划对照不作为设备验收。后续经manage.py先纯构建，再独立验证；先从原登记中选择625/1331行等两个代表尺寸跑双方向数值与实际路径，通过再覆盖变化的分支最小集合。日常不擅自扩为完整callback/内存发布矩阵。
- 若需要性能比较，previous固定本次V6；复用已验安装；同一独占单卡紧邻交替，10次预热/30样本、中位数、保留全部样本与区间。记录两个加速比的分母和版本，禁止将不同批次拼成精简收益。额外计划/RTC时间单列，不混进FFT time_ms。
- 正式性能期望无GPU回归，不承诺涨幅；因果判断先看选路/代码一致性。数值、路径或生成代码意外变化时停止该部分，恢复到保存点对应文件并审阅差异；不 reset 用户工作区，不丢弃旧证据，不变更main或稳定标签。

本轮验证：仅版本身份、已有配置JSON/Python语法、差异格式和方案内部一致性；本轮没有构建、数值、设备或性能新结果。
