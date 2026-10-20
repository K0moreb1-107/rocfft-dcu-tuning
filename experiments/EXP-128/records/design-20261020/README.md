# EXP128后处理方案与复核证据

后处理主方案见《后处理融合方案与修改位置.md》；前处理起点调整见《前处理方案继承与起点差异.md》。
《前处理原方案-EXP127起点参考.md》是旧起点原文，只继承已核对适用的数学与配置结论。

从EXP125稳定标签77fd0040建立新分支，FFT源码未修改；未执行设备验证或性能测试。
模型覆盖279种合法目录组合，797个数学用例；结果、资源表及版本凭据均在本目录。
模型目录是已核对普通配置内容一致后的最小输入，不代表279个默认公开计划均已命中。

复现主机模型（需要NumPy，不使用设备；输出目录显式指定）：

```sh
cd /public/home/zhangkewei/zr/experiments/EXP-128/records/design-20261020
/public/software/apps/anaconda3/2023.09/bin/python -B post_model.py \
  --source-root /public/home/zhangkewei/zr/rocm-libraries-rocm-7.2.2/projects/rocfft \
  --catalog model-inputs.json \
  --out-dir /public/home/zhangkewei/zr/experiments/EXP-128/artifacts/preflight/design-20261020/model-replay
```

该命令以本次EXP125起点为源目录；后续分解表发生修改时，模型的当前映射统计也会随之变化，应与本目录凭据区分。
最小端点重打包编译原型及汇编位于 experiments/EXP-128/artifacts/preflight/design-20261020/。
编译命令及输出见 carrier-load-probe.result.json；它不构成完整内核正确性或性能验收。
本目录不保存大规模参考数组。
