# Fenestra Z62 原厂块池调用 r4 分析报告

**仅离线前置研究，不可刷机，不可把试验模块放入真机。Fenestra 完整移植、集成固件和真机安全均未验证。**

分析日期：2026-11-05；flavor = null（普通固件逆向）。目标不变：坚持 A/Fenestra，使用用户自研 Z62-QEMU 验证，证据不足时不上真机。

## 1. 执行摘要与范围

本阶段新增原厂块池自然调用观察与独立重放核验。暂停前两个独立 r69 进程，每次均配对主侧293次、从侧108次成功分配；恢复目标后核对记录与当前源码绑定，并完成独立核验。观察样本中的指针对齐/边界、块数与元数据变化、callee-saved 寄存器/栈恢复、原页表及MMU/cache状态符合检查。每次释放调用与分配失败样本均为0，因此**不能把结果当作完整 malloc/free、所有权生命周期或并发安全认证**。当前没有在原厂固件中运行 Fenestra，仍无可刷包。

详细授权、输入范围、网络边界和时间线见[scope](../../analysis/fenestra-z62-pool-r4/scope.md)。只用环回 GDB/QMP，不接触相机、USB/PTP或物理卡；不注入调用，不补写客体寄存器/内存，不修改原厂指令，不伪造返回或ready状态。QEMU预装完整原始镜像、初始化复位PC的启动方式，与相机更早加载器的执行证明相互独立。

## 2. 输入与工具身份

| 对象 | 身份或范围 |
|---|---|
| Z6II C1.70主成员 | 38,750,138字节；SHA256 `bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4` |
| 从成员 | 8,832,194字节；SHA256 `3fd8c2cbdf57fadb03f6d69b596b58a8703efdd61ae82572d5afeea0241a9ed5` |
| 自研 r69 QEMU | SHA256 `37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9`；既有原生Windows产物，没有重编或改写 |
| Z62参考源码 | `4f4389944fc339d107f22f5f7ca3f90cc34b78de`，重新核验为干净工作树 |
| Fenestra上游副本 | `b199dcdfbb0ef536c6269ae5a9d97c376d488b8b`，仍仅原有加载器头文件与模块C源码两处修改；未改用其他插件系统 |
| 工具 | Python 3.12、Capstone 5.0.7、Git Bash、RSP Z1执行断点与QMP；不需要本阶段重新编译交叉工具链 |

四份原始输入（整包、主、从、控制器）的尺寸及哈希均按原始基线（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-feasibility/source-check.json`）重新检查。控制器文件虽然参与身份核验，**没有加载进本阶段QEMU**；参数、卡、插件也未加载。

## 3. 静态合同与自然调用

### 3.1 导入等价锚点 E-imports

目标是运行基址 `0x10020000` 的裸 ARM/Thumb 成员，没有 PE IAT。采用原始直接调用、ARM块池封装、literal池状态引用和原始LR返回地址作为依赖等价证据；不能据此否定固件其他文件/网络能力。本阶段依赖原厂自身同步和管理函数，尚未恢复其完整可调用上下文。

静态合同（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/contract-final.json`）复用未修改的r3解析器，另核对原返回地址计算中的 `0xFFFFF800` literal。数据指针关系为 `pool_data + (index-1)*0x800`；`r0`是2KiB块数，不是字节数。

| 运行地址/对象 | master | slave |
|---|---|---|
| ARM分配入口 | `0x10108154` | `0x10039B28` |
| ARM释放封装（本窗口未命中） | `0x101082F4` | `0x10039CC8` |
| 自然分配返回点 | `0x10108774` | `0x1003A148` |
| 池状态 | `0xC2B2F67C` | `0xC18A43C4` |
| 数据起点 | `0xC2C15000` | `0xC1977000` |
| 元数据块数 | 27,094 | 36,114 |

这是Z62自身合同，不照搬Z7II/Z6地址。分配与释放入口为ARM，不能因Fenestra模块是Thumb就随意给原厂入口加1。合成测试中的Thumb返回配对，也不是原厂ARM/Thumb互操作已经验收。

### 3.2 动态结果

| 检查 | run-6-final，PID52784 | run-7-repeat，PID27128 |
|---|---|---|
| 分配入口/返回配对 | 主293/293，从108/108 | 主293/293，从108/108 |
| 事件数/未配对/忽略断点 | 802 / 0 / 0 | 802 / 0 / 0 |
| 自然释放/分配失败 | 0 / 0 | 0 / 0 |
| CPU覆盖 | 主01/02，从03/04 | 主01/02，从03/04 |
| 处理器模式 | 观察入口均SVC `0x13` | 同左 |
| r1标志集合 | `0`、`0x300`；bit16均0 | 同左 |
| 同一角色重叠调用 | 0，不构成并发压力测试 | 同左 |
| 宿主观察耗时 | 18.828秒 | 18.937秒 |
| 结束原因 | 单次继续15秒无新断点 | 同左 |
| 进程退出码 | 0 | 0 |
| QMP quit应答 | 未收到，保存连接重置说明 | 同左 |

RSP的01..04是CPU编号，不是RTOS任务ID。配对依据同时包含角色、CPU、恢复后的SP、原始LR目标和指令状态；重放时重新计算，而不相信保存的摘要。迁移或未配对的调用不会被静默算作成功。

主侧请求块数集合为 `2,3,4,5,6,9,14,16,49,55,257,8193,10881`；从侧没有其中49与257两个值。未覆盖1块、0块、超大/溢出、耗尽和失败路径。主侧已观察请求总量42,123,264字节，范围 `0xC2C15000..0xC5441000`；从侧40,052,736字节，范围 `0xC1977000..0xC3FA9800`。这些是原厂请求样本，**不是插件可占用空间、物理DRAM容量或专门压力测试证明**。

每个已配对分配均核对池计数变化、对应已用块头/长度、bit16标签、返回对齐/边界、r4..r11和SP恢复。活动RAM页表、MMU/I/D cache及停止CPU故障寄存器也经检查。只在没有观察到同角色重叠调用时检查单次计数差；工具合成交错用例不把多次变化归给单次调用。样本区间在没有释放的有界流内互不重叠，不等于全局生命周期或其他未捕获路径安全。

断点、单CPU原指令单步会扰动调度和时序；没有新断点与没有活动定时器警告，均不能证明原厂完整启动、正常功能或无Error。

## 4. 调试与失败现场

1. **传统单步跨核问题**：`run-1`停在未登记位置；`run-2-step-diagnostic`实际记录请求CPU03单步，却先返回CPU01的分配断点。r69对应QEMU源码的传统 `handle_step` 调用 `gdb_continue()`，系统模式下恢复所有CPU；只清除实际停止CPU的单步标志可能留下其他CPU状态。单独 `Hc` 不能保证只有该CPU运行。
2. **最小修正**：只在新观察器内改用 `vCont;s:<CPU>`，先移除共享断点、执行指定CPU的一条原指令、检查停止CPU和PC，再重装。旧r1/r2/r3工具保持不变，避免破坏其源码/证据绑定；旧单步建议不能外推到高密度跨核观察。
3. **退出传输与保存问题**：`run-4-long`的流关闭异常遮蔽了JSON保存，原零字节JSON、QEMU log和控制台日志保留，不计通过。`run-5-long-diagnostic`保存了真实原始异常：QMP quit连接重置，但进程退出码0。最终版分别记录应答状态、退出码和句柄关闭问题，不把缺失应答伪造为收到。
4. **清理边界**：最终两个进程均退出0，且2026-11-05 23:27:29的只读进程检查（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/cleanup-final.json`）没有QEMU进程。检查没有终止其他用户进程。QMP清理不是相机正常关机验收。

## 5. Evidence → Findings → Path

### 5.1 Evidence

| E-id | source_ref | repro_command | content_hash（SHA256） |
|---|---|---|---|
| E-static / E-imports | 合同（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/contract-final.json`） | `pool_calls.collect()`，由原输入生成，核验时重建比较 | `cc2747814a73b6ef90f5a4796a775b5259d92aa2a089a7971543537ea332dd8e` |
| E-run-a | run-6（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/run-6-final.json`） | 见下一节有界观察命令；完整QEMU/RSP命令保存在记录中 | `63377c9c099a27bed7cc0bff58bc6b4206fdbcf845277a95a398574b2b063229` |
| E-run-b | run-7（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/run-7-repeat.json`） | 同配置、独立进程复跑 | `d0d98db7e5449c592f10235968532f3ff984e345cb483d1bf5ccb9900d170c9b` |
| E-verify | 最终核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/verification-final.json`） | `verify_pool.py --run … --run … --output …`，完整命令见下一节 | `7831294cfeb01686e332aacd3a9d0e9f669c2b753e5e6d2384356cd1e56ef426` |
| E-tests | 专项单测日志（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/python-tests-final.log`） | 下一节unittest专项命令，43项无跳过 | `7ea3398866d235106063935b8fd002c301a1f656633fabd61968dc8d60b541ed` |
| E-regression | 候选回归日志（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/candidate-regression-final.log`） | 下一节unittest候选命令，11项无跳过 | `1593e3af7cc71c8f1ab7cc382d8b4f21b4e6e3a9fb198b7305954d6840b0a5e6` |

### 5.2 Findings

| F-id | severity | evidence_ids | confidence / location | status |
|---|---|---|---|---|
| F-alloc | n/a_re | E-static、E-run-a/b、E-verify | high；两角色ARM分配入口与原始返回点 | 有界自然分配样本已核验，不是完整ABI |
| F-debug | n/a_re | E-run-a/b、E-tests及保留的run-1/2现场 | high；新观察器隔离单步 | 修正并复跑；旧工具不被追溯改写 |
| F-release-gap | n/a_re | E-run-a/b、E-verify | high；释放入口命中数0 | 未验证释放、合并、重复释放和生命周期 |
| F-flags-gap | n/a_re | E-verify | high；仅标志0/0x300、SVC模式、无重叠样本 | 完整标志、错误输入、并发和其他上下文未知 |
| F-integration-gap | n/a_re | E-verify及当前PORT状态 | high；未装插件、无集成候选 | Fenestra固件集成与真机安全未验证 |

### 5.3 Path与时间线

**P-pool，path_type=callflow**：原厂初始化（r3独立证据）→原厂自然调用ARM分配入口→读取参数/原LR/SP/池状态→原指令隔离单步并继续→原LR处配对返回→读取块头和池计数→独立重放与负例核验（E-verify，F-alloc）。释放分支未被自然执行观察，不能补入已验收路径。

时间线与失败版本顺序见[scope时间线](../../analysis/fenestra-z62-pool-r4/scope.md#L37)。本阶段没有恶意样本/外部攻击链，IOC和ATT&CK不适用。

## 6. 复现与附件

需要完整本地研究环境：原始C1.70文件、已验证指向工程的ASCII Q:别名、固定r69及原厂合同。普通源码克隆不包含这些二进制；不要绕过尺寸/哈希或身份检查。所有输出名必须不存在；以下命令对应已执行参数，复跑时只改输出文件名。

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR"
export PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
python -X utf8 -B fenestra/z62/observe_pool.py \
  --output analysis/fenestra-z62-pool-r4/run-6-final.json \
  --max-stops 1000 --wall-seconds 120
python -X utf8 -B fenestra/z62/observe_pool.py \
  --output analysis/fenestra-z62-pool-r4/run-7-repeat.json \
  --max-stops 1000 --wall-seconds 120
python -X utf8 -B fenestra/z62/verify_pool.py \
  --run analysis/fenestra-z62-pool-r4/run-6-final.json \
  --run analysis/fenestra-z62-pool-r4/run-7-repeat.json \
  --output analysis/fenestra-z62-pool-r4/verification-final.json
```

主要源码：配对与元数据核验（本地证据，未分发：`<WORKSPACE>/fenestra/z62/pool_calls.py`）、只读运行器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_pool.py`）、独立核验器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/verify_pool.py`）、[配对合成单测](../../tests/test_fenestra_z62_pool.py)、[核验器合成单测](../../tests/test_fenestra_z62_pool_verifier.py)。

17种证据记录变异（遗漏、PC、CPU、SP、callee-saved寄存器、计数、块头、页表、故障、范围标志、pending、ledger、摘要、指令、调试写命令、配置、单步CPU）全部拒绝。它们**不是原厂分配器错误输入动态测试**。合成零返回/非法释放/交错场景仅验收观察工具自身逻辑。

加载器重核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/loader-reverified.json`）、启动重核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/startup-reverified.json`）、内存初始化重核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-pool-r4/memory-reverified.json`）均通过，各自保留原范围。r1的无固件模块执行、r2的早期启动、r3的内存初始化与本阶段自然分配样本，不能合称“Fenestra已在原厂固件集成运行”。没有提交、推送或发布。

## 7. 整体目标审计与后续门槛

| 原目标要求 | 本阶段判断 | 仍缺什么 |
|---|---|---|
| 坚持Fenestra移植 | 路线保持；完整移植未验证 | ARM32完整平台服务、代码/内存保留、任务/卡读/cache发布、模块卡载/管理/菜单、启动完成/正常关机 |
| 用自研Z62-QEMU验证可行性 | 局部样本通过；固件集成未验证 | 独立原C1.70集成候选，同配置原版/停用/激活A/B，正常/错误模块、内容、生命周期和压力 |
| 确定刷入无问题以前不上真机 | 本阶段遵守 | 继续不连接/刷机，不把局部测试提升为真机门槛已满足 |
| 确定刷入及恢复安全，主要保证真机没问题 | 未验证，不能承诺绝对无风险 | 更新容器/摘要B8/K8、型号及主从资格、真实加载容量、NOR/持久化、cache/DMA、断电与恢复 |

下一步先在可解释的原厂运行条件下捕获释放/复用，核实上层分配封装、同步及任务上下文；当前窗口没有释放时，不通过注入成功返回来“补齐”。随后才考虑有界调用试验及Fenestra内存适配。未证的生命周期、可执行代码发布和更新/恢复安全继续作为真机门槛。所有总体安全字段仍为false，目标保持未完成。
