# Fenestra Z62 原厂块池观察 r4：范围

## 授权目标

用户原始目标：A，一直Fenestra，并且使用自己开发的z62qemu验证是否可行，然后确定刷入没问题以后再上真机，主要保证真机一定要没问题。

本阶段仅恢复并观察 Z6II C1.70 自身的块池调用，为 Fenestra ARM32 平台服务提供前置证据；不是把目标缩小为分配器测试，也没有改用其他插件系统。

## in_scope

- 离线读取原 C1.70 主/从成员，复用既有 r69 Z62-QEMU，使用原厂自然执行的入口、原始 LR 返回点和只读寄存器/池元数据观察。
- 新增观察、重放核验、合成单测和报告；保留旧源码、原始固件、旧构建及全部成功/失败记录。
- 检查入口/返回配对、块数、返回指针的对齐和边界、观察样本的块头/计数变化、callee-saved 寄存器与栈恢复，以及原页表和 MMU/cache 状态。
- 时限最多120秒、最多1,000次停止；单次继续15秒没有断点即结束有界窗口，不推断原厂启动完成或系统无错误。

## out_of_scope / 安全门槛

- 不连接相机，不执行 USB/PTP、物理卡写入、固件更新、刷机或恢复操作。
- 不修改原厂指令，不由调试器写入客体寄存器或内存，不注入调用，不伪造返回、ready 状态或忽略异常推进。
- QEMU 模型预装完整原始主/从镜像，并用模型 loader 初始化复位 PC；没有执行相机更早的加载器。两者不能与运行中调试器补写状态混为一谈。
- 不加载控制器、参数、卡或 Fenestra 插件。原厂堆不是已证明可自由占用的区域，页表可执行也不是插件代码发布/cache一致性证明。
- QMP quit 与退出码0只属于宿主模拟器清理，不代表相机正常关机，更不代表刷机或断电恢复安全。
- 没有生成可刷候选。`allocator_call_abi_verified`、`allocation_lifetime_verified`、`plugin_execution_in_heap_verified`、`firmware_integrated`、`flash_safety_verified` 均保持 false。

## network_profile

仅本机环回 GDB/QMP；QEMU `-nic none`。本阶段不联系外部网络服务。

## 证据与工具

- 最终独立核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/verification-final.json`）
- 静态合同（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/contract-final.json`）
- 进程清理检查（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/cleanup-final.json`）

Python 3.12、Capstone 5.0.7、Git Bash、项目内原生 Windows r69 QEMU 和已验证的 Q: 工程别名。PI scratch 使用宿主给出的 D: 会话路径，而非 guard 插件误报的 C: 路径。技能 `tool-index.md` 与独立 Evidence/Path 参考缺失，已读取实际存在的 RE 工作流和报告模板；本阶段使用已验证的 Capstone/GDB/QMP，不安装或启动额外 IDA 服务。

## 时间线摘要

1. 读取原厂 ARM 块池函数及状态引用，新增自然调用配对器和只读 RSP 命令限制。
2. `run-1`、`run-2-step-diagnostic` 定位传统 `s` 恢复其他 CPU、跨核断点抢先和残留单步状态；保留失败记录。
3. 改为 `vCont;s:<CPU>`，`run-3-vcont` 完成较短分配观察，未看到释放。
4. `run-4-long` 的 QMP 流关闭异常遮蔽保存，保留零字节 JSON、QEMU log 和控制台日志；不计通过。`run-5-long-diagnostic` 保存完整原始退出传输异常。
5. 最终观察器分别记录 QMP 应答状态和真实退出码，`run-6-final` / `run-7-repeat` 各配对401次分配、0次释放，均退出0。用户暂停时停止工作。
6. 目标恢复后核对原始记录与当前源码绑定，补充独立核验及17种记录变异拒绝检查；43项专项单测和11项候选加载回归通过，前三阶段证据重新核验。
7. 2026-11-05 23:27:29 本机进程只读检查无 QEMU；无活跃等待或自动恢复任务。
