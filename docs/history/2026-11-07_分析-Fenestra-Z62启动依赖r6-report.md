# Fenestra Z62 启动依赖 r6：调度器空闲不等于完整启动

> 日期：2026-11-07；目标：Nikon Z6II C1.70 / Fenestra；flavor=null；severity=n/a_re。
> **整体移植未完成，第一阶段未放行，第二阶段未进入验收，真机阶段关闭。没有可刷 Fenestra 包。**

## 1. 本轮结果

继续排查 r5 最小配置在自然分配后无新断点的问题，新增独立只读诊断及重放工具，没有修改 r1～r5 工具、原厂固件或 QEMU 程序。五份新版原厂运行记录共13个暂停样本、52份引擎CPU快照完成重放；三种配置分别为最小配置、仅加载原控制器、原控制器加通信链路。延长观察覆盖约9.68/10.85秒的主引擎模型时钟口径；末次样本均位于调度器空闲轮询、待运行和当前项均为零，所读引擎故障寄存器均为零。**这只解释了采样时的状态，尚未识别具体任务的等待对象，不能判定完整启动、无 Error 或内存生命周期成功。**

修正了两项观测问题：宿主秒数不能冒充客体秒数；没有显式打开 laboratory 辅助不能冒充模型没有任何完成逻辑。71项 Fenestra 专项和11项候选工具回归通过、无跳过，12类变造记录被拒绝。没有进入更新器、刷机流程或真机验证。

范围见 [scope](../../analysis/fenestra-z62-boot-r6/scope.md)；既有完整阶段门槛见 [r5报告](2026-11-07_实施-Fenestra-Z62阶段门槛与字节堆r5-report.md)。本报告中本地链接的目标均为当前工程文件；源码路径行号用于定位，不表示参考模型源码已恢复为r69编译源码。

## 2. 三阶段验收与转换条件

| 阶段 | 验证项和通过标准 | 当前结果与进入下一阶段条件 |
|---|---|---|
| 1：自研z62qemu验证完整移植 | Q1 ARM32模块格式/重定位/真实执行/错误拒绝；Q2原厂启动、页表与内存初始化；Q3分配/释放/失败/合并/复用/flags/同步/任务上下文；Q4代码数据所有权、加载容量与cache发布；Q5原厂任务/文件/模块服务及菜单；Q6同模型同配置原版/候选停用/候选启用对照，合法/错误模块、启动/正常关机、生命周期/压力均通过，无未解释关键失败 | r1～r5只提供局部加载器、初始化和自然分配证据；本轮仅新增启动状态诊断。Q3完整ABI、Q4～Q6仍缺。**所有Q项通过、关键模型身份/覆盖缺口关闭且冻结唯一候选SHA后，才能进入阶段2。** |
| 2：冻结镜像和刷入流程 | U1机型/版本/主从控制器资格、唯一SHA和长度边界；U2真实B8/K8认证，合法接受/篡改拒绝；U3介质到原厂早期加载的实际容量/入口/地址；U4写入范围、NOR/校准保留、读回和重启持久化；U5校验/擦除/写入/提交/重启各处中断、断电、恢复/回滚；U6源码/工具链/依赖/许可证与镜像可追溯复现 | **未进入验收**。候选工具的11项测试不是原厂更新器认证；QEMU整镜像预装不是实际更新/早期加载证明。必须第一阶段通过且U1～U6针对同一冻结镜像全部通过，才有讨论真机的前提。 |
| 3：真机 | 前两阶段全部通过；独立关闭物理差异、供电、存储、cache/DMA与可恢复路径缺口；满足用户安全门槛后才可进入受控实机验证 | **关闭，未连接或操作真机/USB/PTP/物理卡。**有限测试不能证明所有未来物理状态绝无风险，不能把“已降低风险”改称满足“一定不出问题”，也不能借此越过用户门槛。 |

## 3. 身份、配置与原始输入

- Fenestra固定 `b199dcdfbb0ef536c6269ae5a9d97c376d488b8b`；上游副本仍仅原来的两个加载器文件修改。Z62参考源码固定 `4f4389944fc339d107f22f5f7ca3f90cc34b78de`，工作树干净。
- 固定自研r69 EXE：`.build/z62-output-lineage-2026.11.03-r69/runtime/qemu-system-arm.exe`，SHA256 `37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9`；没有重编或替换模型。
- master/slave仍为原始C1.70，完整SHA在 静态合同（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-boot-r6/static-contract-1.json`）；controller为524290字节，SHA256 `9c65cad554ed02f83d37fbc825a8eb9efe79e3f32f98894dd5dd73edee416983`。
- 精确r69历史source/build tree仍未恢复。已核对的 `third_party/z62-qemu/qemu` 是**参考源码**，不是当前EXE可重建证明；并行源码调查超出时间盒后停止，没有采纳未收敛结论。
- 全部运行保持 `-nic none`，GDB/QMP仅`127.0.0.1`；预装完整原主/从镜像、四核loader初始化复位PC。无参数、卡、battery-peer、合成flash/I2C/GPIO、frame-sync/frame-start、laboratory completion或Fenestra代码。
- RSP仅读和继续/中断暂停；QMP仅能力协商、查询、`info qtree`、`info cpus`、`info registers -a`及宿主quit。没有调试器写寄存器/内存、调用注入或原厂补丁。

## 4. 启动输入分类

下表是本轮已读取实现的分类，不能把另一机型历史运行结果或参考源码直接当成r69/Z62实跑证据。

| 输入/功能 | 已核对实现与边界 | 本轮是否采用 |
|---|---|---|
| 原始controller-firmware | 原控制器文件；参考模型创建Cortex-M4和独立地址空间。不是补丁或合成校准。原始文件身份不等于控制器完整外设验证 | 两种控制器配置采用 |
| controller-link | 参考模型连接SPI对端和原始输出GPIO/ack线路，不直接补写引擎ready RAM；协议时序仍是模型选择，不能称物理等效 | 仅controller-link配置采用 |
| controller-battery-peer | 参考代码明确为synthetic battery peer，读取模型root中的nonce；不能当实机电池或原厂备份 | 未采用 |
| laboratory_devices | `resident.bin`是0xC000零填充加`MAKE`；I2C寄存器初值由宿主构造，并非恢复的控制器flash | 未采用 |
| initialize_inputs | 经qtest设置7个控制器GPIO的电源/运行/释放快门电平；它是外部引脚fixture，不是寄存器/内存调试写。`frame_sync=True`另切换同步使能线 | 未采用，不整体调用 |
| master-boot-aux / parameters | NOR提取器要求64MiB文件，按表截取17/18/32组并检查ENDM；这不自动证明校准内容。现有synthetic_parameters主要为零及少量候选值，明确不是NOR/真实校准 | 均未采用 |
| boot-image / boot-aux加载 | 参考 `boot_store_reset` 向地址空间装入字节并复位CPU到入口，这是预装模型合同，**不是实际介质加载、认证、刷入或持久化** | 仅原始boot-image |
| 主屏实验 | 控制台条件分支启用metadata/input/mode/frame/init completion、frame-start等；会按模型条件生成状态/中断，不能据此证明真实任务完成源 | 未采用 |
| 默认模型逻辑 | 运行时qtree显示两侧gate/transfer-reset/sequencer completion均true；参考源码还包含输入使能时生成代表性事件模式等近似。未显式开laboratory不等于不存在默认辅助 | 保持既有默认值，完整记录并限制结论 |

关键实现定位：控制台启动（本地证据，未分发：`<WORKSPACE>/third_party/z62-qemu/tools/z62_console.py:34`）、fixture与GPIO（本地证据，未分发：`<WORKSPACE>/third_party/z62-qemu/tools/z62_probe.py:51`）、[合成参数](../../tools/run_reference_console.py#L68)、SPI/GPIO链路（本地证据，未分发：`<WORKSPACE>/third_party/z62-qemu/qemu/nikon-z72.c:2973`）、合成电池（本地证据，未分发：`<WORKSPACE>/third_party/z62-qemu/qemu/nikon-z72-controller.c:610`）、模型预装（本地证据，未分发：`<WORKSPACE>/third_party/z62-qemu/qemu/nikon-z72.c:2451`）、默认完成属性（本地证据，未分发：`<WORKSPACE>/third_party/z62-qemu/qemu/nikon-z72.c:2117`）、代表性输入事件（本地证据，未分发：`<WORKSPACE>/third_party/z62-qemu/qemu/nikon-z72.c:1163`）。

## 5. 原厂静态和动态证据

### 5.1 原厂调度器地址合同

这是原始ARM/Thumb镜像，没有PE导入表；E-imports等价锚点为原始MPIDR读取、literal加载、条件分支及原始调用/返回上下文，不是外部函数名猜测。

| 原始地址 | master | slave |
|---|---|---|
| 调度入口 | `0x10107060` | `0x10038A34` |
| 空闲轮询 | `0x10107070..0x10107094` | `0x10038A44..0x10038A68` |
| 当前项数组 | `0xC2B2A934` | `0xC189F6B0` |
| 待运行项数组 | `0xC2B2A944` | `0xC189F6C0` |
| 本角色核0系统栈位置 | `0xC2B2C67C` | `0xC18A13C4` |

原指令从MPIDR取核号，按4字节步长选择待运行项；读到零后切回IRQ开放的SVC状态并循环。非零分支会再调用调度辅助函数，不能仅凭数组存在推断完整RTOS任务ABI。工具每次暂停读取两元素数组，两核视图必须一致。**CPU编号不是RTOS任务ID；不推断任务表、锁/事件对象、死锁或完整生命周期。**

### 5.2 新版实跑

窗口为每段宿主秒数；模型秒数按既有计数器 `0x04266008 / 48000000` 口径计算，原始ticks保存在JSON，不是物理计时精度验收。

| 记录 | PID | 宿主窗口 | 最后主/从模型秒数 | 末次采样 |
|---|---:|---|---|---|
| run-3-minimal-final | 53620 | 1/5/15 | 1.747868 / 1.746364 | 四核空闲；两数组零 |
| run-4-controller-final | 27748 | 1/5/15 | 1.828890 / 1.826894 | 同上 |
| run-5-controller-link-final | 50276 | 1/5/15 | 1.835546 / 1.833550 | 同上 |
| run-6-minimal-long | 53308 | 60/60 | 9.678983 / 9.677479 | 同上 |
| run-7-controller-link-long | 56864 | 60/60 | 10.850019 / 10.848023 | 同上 |

- 五进程互相独立，均真实退出0且收到QMP quit应答；这是宿主清理，不是相机正常关机。
- 52份引擎快照附近代码均与对应原成员逐字节一致，活动TTBR/MMU/cache状态与已知原厂状态相符，所读四项故障寄存器为零。
- 早期部分主CPU仍执行任务，两数组非零；不能把后续采样空闲说成整个期间没有任务执行。
- 控制器运行记录保存了第5CPU的HMP寄存器；本轮没有验证其完整故障状态、协议、flash、校准和外设。不把某次PendSV/线程模式样本当控制器启动验收。
- r6**不监控堆入口**，所以不能宣称长窗分配/释放次数为零。r5已有“释放样本为零”的边界保留，但不能外推到r6长窗。
- 初诊run-1/run-2采用0.1.0，`completion_helpers_enabled`名称过宽，保留现场及 初版源码（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-boot-r6/source-initial.py.txt`），不参与新版通过判定。0.1.1改为`laboratory_completion_enabled=false`，另明确`default_model_completion_logic_disabled=false`。

### 5.3 问题、处理与复核

| 问题 | 处理 | 复核/未解决部分 |
|---|---|---|
| “无新堆断点”缺少现场状态 | 新增全引擎CPU、调度器数组、时钟、代码/栈快照 | 已定位采样时空闲循环；任务的具体等待对象仍未知，原厂问题未修复 |
| 21宿主秒误当足够运行窗 | 记录模型ticks并加60/60宿主秒对照 | 覆盖到约9.68/10.85模型秒，不是完整启动或所有超时覆盖 |
| “completion关闭”措辞过宽 | 核对qtree并分开laboratory与默认完成逻辑；修正新记录字段 | 12类记录变异拒绝；默认硬件近似仍存在，未关闭模型真实性缺口 |
| 反汇编窗口包含literal数据 | 完整解析器拒绝后缩小到已确认指令边界 | 保存的静态合同仅包含核对过的原指令；未把数据解码当调用 |
| r69精确源码树缺失 | 固定EXE身份不变，不静默换模型；源码分类明确参考身份 | 未恢复精确可重建源码，不算修复 |
| 工具编辑未显示行锚点被拒绝 | 读取实际小窗口后纠正行号，再更新 | 新版运行前7项工具测试通过；未误改旧证据 |

## 6. 验证与复现

- 观察器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_boot_wait.py`）：0.1.1，最多4窗、总运行窗≤120宿主秒；不开放任意机型/设备/辅助选项。
- 重放器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/verify_boot_wait.py`）：重算原指令/数组地址/时钟、核对来源SHA、精确命令、RSP与QMP、CPU角色/拓扑、HMP/RSP PC及退出日志。
- 核验结果（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-boot-r6/verification-final.json`）：五记录通过；sample/window/pc/scheduler/array/fault/scope/command/rsp/qmp/clock/model共12类变造记录拒绝。它们是**核验工具负例，不是原厂错误输入验收**。
- 71项专项日志（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-boot-r6/python-tests-final.log`）、11项候选回归日志（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-boot-r6/candidate-regression-final.log`）。新增11项，其余60项为旧专项回归；无跳过。原候选工具通过不等于刷入或认证通过。

以下只读重放不需要Q:，要求完整本地原固件、固定runtime及当前源码。输出名必须尚不存在；重复执行时显式选择新的结果名：

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR"
export PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
python -X utf8 -B fenestra/z62/verify_boot_wait.py \
  --run analysis/fenestra-z62-boot-r6/run-3-minimal-final.json \
  --run analysis/fenestra-z62-boot-r6/run-4-controller-final.json \
  --run analysis/fenestra-z62-boot-r6/run-5-controller-link-final.json \
  --run analysis/fenestra-z62-boot-r6/run-6-minimal-long.json \
  --run analysis/fenestra-z62-boot-r6/run-7-controller-link-long.json \
  --output analysis/fenestra-z62-boot-r6/verification-recheck.json
```

动态入口为`observe_boot_wait.py --profile minimal|controller|controller-link --windows ... --output ...`；只接受先核对`samefile(ROOT)`的临时Q:本工程别名，不自动覆盖盘符。每份完整命令和逐次暂停回复保存在记录中。本轮两次短窗初诊及五份新版运行的自有进程均关闭，自建别名在各批次finally移除。

## 7. Evidence → Finding → Path 与时间线

| Evidence | source_ref / content_hash | repro_command |
|---|---|---|
| E-static / E-imports | `static-contract-1.json`含原成员SHA、工具/参考源码SHA及原指令 | 由原成员重新运行`scheduler_points()`和`instructions()`；定位不等于公开RTOS服务ABI |
| E-runtime | 五份0.1.1运行JSON、对应qemu/console日志；各文件SHA在核验结果及最终清单 | 第6节重放命令 |
| E-negative | `verification-1.json`的12类变异；`test_fenestra_z62_boot_wait_verifier.py` | 第6节专项单测 |
| E-scope | `scope.md`、`PORT.json`、每份记录false字段与精确启动命令 | 读取状态并重放核验，不信任文档自述完成标志 |

| Finding | evidence_ids | confidence / location / status |
|---|---|---|
| F1：采样时是调度器空闲而非所读引擎异常 | E-static、E-runtime | high；主10107070/从10038A44附近；已定位，等待根因仍待追踪 |
| F2：宿主时间不足以代表客体观察覆盖 | E-runtime | high；model_clock_ticks；观测工具已改进，完整生命周期未验证 |
| F3：显式实验开关与默认模型完成逻辑必须分开 | E-runtime、E-scope | high（运行时属性）；参考模型语义非r69逐字节源码证明；字段已纠正，模型缺口仍在 |
| F4：当前不具备下一阶段放行条件 | E-scope | high；PORT仍experimental-loader-only；未放行 |

P1，path_type=callflow：原始MPIDR核号 → 原literal确定待运行数组 → 每核读取当前槽 → 零值分支开放IRQ并循环 → 暂停采样核对PC/数组/原代码 → 不推断未知任务等待对象；挂E-static/E-runtime/F1。

时间线（本地+08:00）：13:53最小初诊；13:55原控制器初诊；13:58开始新版三配置批次；14:00开始两配置长窗；其后保存五记录重放、12类变异和71+11测试。并行参考源码调查停止且不采纳未完成结论；没有在等待的QEMU运行。

## 8. 整体审计与下一项实际工作

| 原始要求 | 当前结果 |
|---|---|
| 完成原Fenestra移植，而非替代插件系统 | 未验证：仍为ARM32 loader-only，没有原厂Fenestra集成候选 |
| 先用自研z62qemu验证完整方案 | 未验证：本轮诊断通过不等于完整方案通过，未完成原版/停用/启用/错误模块/全生命周期矩阵 |
| 然后验证镜像及刷入流程 | 未验证且未进入验收：真实认证、早期加载容量、NOR/持久化和断电恢复缺证 |
| 前述全部通过才上真机 | 本轮遵守：全部为本地文件和QEMU，无相机访问、刷机或物理卡 |
| 真机刷入及运行一定不出问题 | 未满足/未验证，有限模拟器观察不能给绝对保证 |
| 每阶段项目、标准、问题/修复、转换条件 | 已在第2、5节及r5阶段报告列明；未执行项没有改称通过 |

下一项是恢复可追溯的开发模型来源，并从Z62原厂调度/任务入口识别实际等待对象；必要时在**新的独立模型/工具/证据版本**下补自然释放/合并/复用与同步上下文。不能直接复用r5的15宿主秒无断点退出逻辑作为客体期限，也不能用合成ready、completion、参数或其他机型地址填覆盖。之后才能处理可保留代码/数据所有权、cache发布、任务/文件服务和完整Fenestra原厂候选。未提交、推送或发布固件/密钥。
