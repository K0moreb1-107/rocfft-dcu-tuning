# EXP129 门控精简：代码等价性检查

结论：在 rocFFT 正常构造的有效节点／生成器配置下，未发现本次门控精简导致优化漏命中、误命中、回退顺序或生成内核变化。已覆盖的全部差分检查为零差异。本次没有修改生产源码，也没有新增构建、设备验证或性能任务。

对照为实际 V6 源码与当前门控精简源码：V6 的 babe7b5379aa37892f56cd190de21190d1838f68 与保存点 1d22a78fad885db364b3ad631eaddb2baf0fcf1f 的 rocFFT 子树完全相同；当前 HEAD 与实现提交 c4de21bc379612ce420949575d8acc2cc9336177 的 rocFFT 子树完全相同。逐项核对了全部 11 个生产文件。

## 本次重新执行的检查

| 检查 | 结果 | 范围 |
|---|---:|---|
| 完整融合构造函数及步长／距离赋值 | 41,536 组一致 | 比较实际旧新完整函数：子节点、role/load、尺寸、buffer限制、输出布局、stride/dist、分支、异常；注册表与节点基础设施使用相同最小模型 |
| 规划器查表和回退 | 1,024 组一致 | 命中、无映射、有映射但内核不可用、非法映射、gfx906分支 |
| RTC角色与加载策略 | 8,847,360 组，0 差异 | 8个最终字段；覆盖角色、精度、callback、direct/half LDS、tile、root形状、加载模式 |
| 生成器优化谓词 | 768,000 个状态、6 个pass，0 差异 | 普通／大旋转因子递推、late LDS、寄存器局部交换；空因子下原本非法的back访问不作比较 |
| 已保存的生成源码 | 2,830 份逐字一致 | 283个登记几何：默认2,264份、保留LDS 566份；同时重新核验保存的哈希；本次未重新生成 |
| 对照程序与真实代码绑定 | 通过 | RTC策略及四个谓词的测试片段与实际旧新源码token一致；V6旧头文件逐字一致 |

本次补强了原验证的不足：原来的规划检查只比较门控前缀；本次把完整构造函数、子节点字段和赋参函数纳入差分比较。模型没有代替完整公开API，已在证据中明确边界。

## 每类删减的依据

| 改动 | 等价性依据 |
|---|---|
| 公共维度、batch、精度、placement、stride、offset和格式条件上移 | 三条融合路径仍只经BuildTree_internal进入；helper改为protected；统一CanFuseCCReal逐项保留原条件，方向判定保持 |
| 删除CC子节点数量、scheme和反序长度复验 | CC1DNode::BuildTree_internal明确创建CC、RC两个子节点，检查分解乘积并设置反序长度；调用发生在RecursiveBuildTree之后 |
| 删除CC子节点Bluestein复验 | CC构造将同一fuseBlue显式传给两子节点；检查父CC的标记与原来检查两子节点等价 |
| 删除ebtype和large1D复验 | 新节点默认EmbeddedType::NONE，CC构造不改它；列节点large1D显式取完整复数长度n/2 |
| LDS资源和列缓存条件短式 | 对正长度且乘法不溢出的有效配置，floor(length*TPB/D)<length等价TPB<D，D仅为1或2；CC-local保留前置资源检查，历史固定几何范围有限；登记矩阵另外逐项验证无溢出、无差异 |
| 合并两个环境加载模式解析 | 未设置/registers/lds/非法值的结果与错误文本不变；仍在原路径内解析，不缓存跨计划环境值；无关路径不新增错误 |
| planner删除多输出helper | 保留“映射可用／缺映射／已有映射不可用”三态；缺映射的旧尺寸失败和gfx906特例保留 |
| CanRegisterInput删除因子乘积检查 | StockhamGeneratorSpecs构造函数直接以因子乘积初始化length；RTC使用注册内核的同一factors构造，不在该判断前重写length；线程及workgroup整除条件保留 |
| 普通SBRC静态加载短式 | 非空正因子构造保证乘积与首因子整除；保留power-of-two、线程和workgroup条件；node.scheme为BLOCK_RC时pool_scheme同为BLOCK_RC |
| RTC改为按role分派 | 8个最终策略字段逐组相同；PackedInverseRows保留CanRegisterPre失败时LDS回退；FoldedSpectrumRows保留线程几何回退；callback分支不放宽 |
| 只在精确候选中回溯128K根 | length512/factors888/workgroup512/TPT128已蕴含旧静态映射；普通SBRC公共条件、根长度/维度条件和清零角色保留 |
| 合并内核形状判断 | 长度、TPT和因子向量逐项相等；显式比较因子个数，保持原vector相等语义；各优化自己的额外条件不合并或扩大 |
| 删除wave同步死分支 | 原use_wave_sync恒为false，因此原输出一直是SyncThreads；当前仍相同 |
| 删除register_local_exchange内部重复检查 | 唯一调用点已经检查相同谓词和pass位置；生成语句未改 |
| 删除PackedInverseRows内部register-pre复验 | 唯一register_input调用点要求io.load为Registers；RTC已用原CanRegisterPre选择该值，失败时仍走LDS |
| 删除paired-post构造器的role/N/pitch复验 | 唯一创建分支以PairedPostRows角色分派；ForLength建立N=2*C*Q，TryFusePairedPost显式pitch=rows；真实长度和线程几何检查保留 |

## 对优化命中的判断

普通SBCC的大／普通旋转因子递推、late LDS、寄存器局部交换，普通SBRC静态寄存器加载及128K递推，实数CC的四个role及其寄存器／LDS选择，历史LocalReal/PairedPost路径和规划器特殊回退，均在上述条件核对中保持原集合。没有发现需要为保留优化而补回的门控。

这里的等价性针对正常构造且满足注册内核约束的内部状态。手工伪造错误因子乘积、错误role/pitch或破坏CC树结构，再直接调用内部生成器，可能不再得到旧防御性拒绝；这些被删条件原本重复上游构造保证。不能把“任意损坏的内部对象仍完全同表现”写成此次结论，也不需要为此重新堆回门控。

本报告是代码层面的检查，不以性能波动判定门控正确性，也不声称有限组合枚举穷尽全部公开API输入。完整库构建及此前数值／实际路径验证仍是独立证据。

证据入口：experiments/EXP-129/records/code-equivalence-review-20261029/audit.json、source-contracts.json、matrix-invariants.json、proofs/。检查脚本：experiments/EXP-129/scripts/audit_gate_equivalence.py。复跑需换新结果目录以保留本次证据。

登记矩阵列长度×每块行数最大值：4096，小于2^32。

原始提取片段保留原样，不做格式归一化；空白格式检查针对新写的脚本、报告和结构化记录。
