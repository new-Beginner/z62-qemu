# Fenestra Z62 任务字段回调 r11：独立字段值、原 BX 和目标首指令

> 2026-11-07；原 Fenestra＋自研 Z62-QEMU；flavor=null；severity=n/a_re。
> **完整移植未完成，第一阶段未放行，第二阶段未进入验收，真机关闭。没有可刷 Fenestra 包，不能保证真机绝对零风险。**

## 1. 结果与范围

本轮新增独立 r11 合同、只读观察器、重放器及 10 项测试，不改 r1～r10 来源绑定文件。两个原 C1.70/固定 r69 进程各配对 52 个发布前帧与实际首次入口，其中各 48 个共享 Thumb 入口继续观察独立字段读取、原 LDR、原 BX 和字段目标首条原指令。**共 96 条字段到目标首指令链成立，不是 96 个 Fenestra 任务、完整业务回调完成或完整生命周期通过。**

此前 r10 没有独立读取字段，也没有观察 BX；本轮补上这两个局部证据缺口。96 次原目标均为 Thumb，目标首指令包括 PUSH、PUSH.W、SUB SP、ADD.W 和 MOVS；其中 84 次 PUSH 的实际栈数据也逐字比对。没有观测目标返回、后续业务完成、完整名字/注册表、System 模式、启动 API 返回或任务删除复用。

125 项专项、11 项离线候选工具回归全部通过，无跳过；新记录两次重放逐字节一致，30 类定向错误记录拒绝，r9/r10 旧记录重新核验通过。当前 PORT（本地证据，未分发：`<WORKSPACE>/fenestra/z62/PORT.json:3`） 仍是 `experimental-loader-only`，不能用本轮原厂任务观察冒充完整 Fenestra 端口。范围与限制见 [scope](../../analysis/fenestra-z62-task-callback-r11/scope.md)。

## 2. 三阶段验收和转换门槛

### 第一阶段：完整原厂 Fenestra 端口在自研 z62qemu 验证

| 验证项 | 通过标准 | 本轮后实际状态 |
|---|---|---|
| Q1 ARM32 模块与完整 SDK | 格式/重定位/入口、完整 copied-service SDK 真实执行，合法及错误模块正确处理 | r1 仍只合成 loader/legacy v1 日志，完整原厂 SDK 未通过 |
| Q2 原厂启动/正常关机 | 主从 ISA/栈/MMU/初始化和完整启动、正常关机、再启动通过 | 只有局部启动/调度合同；首次入口或首指令不是相机启动/关机成功 |
| Q3 内存/任务/同步生命周期 | 分配、自然释放、合并复用、flags/耗尽失败、创建启动/异常/删除、同步/所有权和完整生命周期通过 | r11 补 96 次字段→目标首指令；目标返回/业务完成/完整 ABI 未验；r10 的 73 个待配对诊断未解决 |
| Q4 空间、加载、cache/DMA | 可保留代码/数据及所有权、真实加载容量、MMU/cache/DMA 发布和回收明确并实跑 | 仍缺；可读地址、清零和可执行映射不等于可占用插件空间 |
| Q5 完整原厂 Fenestra 服务 | 原厂任务/同步/卡文件、copied-service SDK、模块管理/菜单和启动关机集成真实运行 | 无完整原厂候选，原厂目标首指令不是 Fenestra 服务运行 |
| Q6 对照、压力与模型可信度 | 同模型同配置原版/候选停用/启用、合法/错误模块、启停/异常/压力/完整生命周期通过，关键失败及模型来源/覆盖缺口关闭 | 未完成；精确 r69 source 仍缺，默认 completion/硬件近似和关键失败保留 |

**全部 Q1～Q6 通过、模型关键缺口关闭、完整候选可复现并冻结唯一 SHA 后，才能进入第二阶段。当前不满足。** 不写客体状态、不补事件/调用/成功返回、不强制 completion、不关闭型号/身份/长度检查填覆盖。

### 第二阶段：同一冻结镜像与真实刷入流程

| 验证项 | 必须达到的通过标准 | 当前状态 |
|---|---|---|
| U1 镜像资格与边界 | 唯一 SHA；型号/版本/主从控制器资格、长度/地址正确；互换、截断、越界拒绝 | 无完整候选，未进入验收 |
| U2 原厂认证 | 真实 B8/K8 和原厂更新器合法接受、篡改拒绝 | 未验证；CRC/seed/其他机型结果不能替代 |
| U3 介质早期加载 | 实际介质到原厂加载容量、入口、地址、主从发布顺序正确 | 未验证；boot-image 预装/复位 PC 不是介质加载或刷入 |
| U4 写入与持久化 | 实际写入范围、NOR/校准保留、读回/重启持久化和冲突处理正确 | 未验证；合成参数或空白卡不等于原厂备份 |
| U5 中断、断电与恢复 | 校验/擦除/写入/提交/重启各阶段中断、超时、断电恢复/回滚通过 | 未验证；QMP quit/退出 0 不算恢复 |
| U6 可追溯重建 | 同一候选源码、模型、工具链、依赖、许可证、镜像可复现，关键失败解释完成 | 未通过；固定 EXE 和后续参考源码不是精确 r69 来源 |

**第一阶段先全部放行，再对同一冻结镜像通过所有 U 项。不能拼接不同版本的局部证据放行。第二阶段本轮未进入验收。** 11 项候选工具测试不是原厂认证/更新/刷机测试。

### 第三阶段：真机

前两阶段全部通过，并独立关闭物理供电、存储、cache/DMA、硬件时序和可恢复路径缺口，才有讨论受控真机验证的前提。本轮没有连接相机/USB/PTP，没有操作物理卡/磁盘或刷机。有限模拟器观察不能证明所有未来物理状态绝无风险；用户“刷入和运行一定不出问题”的绝对要求仍未满足/未验证，不能自行改成“降低风险”后放行。

## 3. 原指令、数据流与实际执行

裸 ARM/Thumb 无传统 PE/ELF 导入表。E-imports 等价证据是原帧/TCB、共享入口 LDR/BX 和字段目标指令，不由此推导完整文件/网络能力或完整任务 ABI。来源见 合同（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-callback-r11/contract-final.json`） 和 实现（本地证据，未分发：`<WORKSPACE>/fenestra/z62/task_callback_contract.py`）。

| 原厂位置 | master | slave |
|---|---|---|
| 发布前观察点 | `0x1010AAC4` | `0x1003C498` |
| 共享 Thumb 入口 | `0x103DEBBC` | `0x1006CB80` |
| 原入口字节 | `49 68 08 47` | `49 68 08 47` |
| 指令 | `LDR r1,[r1,#4]; BX r1` | 同左 |
| 每跑共享样本/不同字段目标值 | 38 / 12 | 10 / 7 |

12/7 只是该角色/进程样本内不同原字段值数量，不是完整业务任务总数或跨生命周期身份。

观察器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_task_callback.py`） 执行以下有界路径：

1. 沿用 r10 SVC 发布前帧→真实 current-TCB 首次入口合同，核对原输入、ROM、真实停核、ISA/SP 和 r0/r1；不注入创建/启动。
2. 在共享入口执行 LDR 前，独立读取原 r1 起 8 字节；仅把 +4 原字作为字段目标。地址边界沿用原 RAM/成员范围，仅是读取防护，不证明结构、所有权、分配或保留空间。
3. 撤断点，用 `vCont;s:<CPU>` 隔离执行原 LDR；装入 r1 必须等于独立读出的 +4 原字，其他寄存器仅 PC+2。
4. 再隔离执行原 BX，核实际 PC/ARM/Thumb、SP/r0/其他通用寄存器；读取目标 16 字节与原成员逐字相同，current 两槽保持，MMU/cache/所读故障状态不变。
5. 原目标仅执行首条已解码指令，并核其全部通用寄存器效果；PUSH/PUSH.W 还独立读取实际写入的栈字。未知指令严格拒绝，不扩展成通用模拟器或跳过检查。
6. CPU 由停止包 `thread:` 确定，不信陈旧 qC；读 ticks 后恢复原核。全过程没有调试器写客体内存/寄存器/PC/返回值或补 ready/事件。

实际例：从侧原 r1=`0xC167B7D8`，独立 8 字节 `04 00 00 01 83 36 05 10`；LDR 后 r1=`0x10053683`，BX 后 PC=`0x10053682`、Thumb 保持、r0=`0`。原首指令 `2D E9 F0 5F` 的 PUSH.W 使 SP 从 `0xC3EFD3A0` 到 `0xC3EFD378`，40 字节栈写入逐字吻合。**不把首字 `0x01000004` 命名为已验证的完整描述符字段或稳定身份。**

每跑 48 次目标首指令：38 次 Thumb PUSH、4 次 PUSH.W、4 次 ADD.W、1 次 SUB SP 和 1 次 MOVS。共 84 次实际 PUSH 栈写入、8 次 ADD.W、2 次 SUB SP、2 次 MOVS。原普通 ARM 首次入口仍各 4 个，但本轮 **没有实际 ARM 字段目标/BX 切 ARM 样本**；工具对此的支持不能代替原厂覆盖。

## 4. 实跑、发现的问题和修补结果

| 原始记录 | PID | 主/从首次入口 | 字段目标样本 | 带断点末主模型秒 | 最终主模型秒 | 宿主秒 |
|---|---:|---|---:|---:|---:|---:|
| run-1（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-callback-r11/run-1-final.json`） | 55752 | 40 / 12 | 48 | 0.015004125 | 2.535561563 | 31.000 |
| run-2（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-callback-r11/run-2-repeat.json`） | 55384 | 40 / 12 | 48 | 0.014185354 | 3.777181479 | 45.937 |

均目标 32 后排空至 52，104 事件、未匹配入口 0、pending 空；严格 `sample-bound-drained`。撤断点后的目标窗不是全过程业务/生命周期跟踪。ticks 按既有 48MHz 模型口径折算，宿主时间和模型时间不作物理计时验收。末四核 idle/current-ready 零及所读故障零只是末次采样；本轮不监控堆释放或全部原厂 Error。

| 问题 | 本轮处理/修补结果 | 未解决边界 |
|---|---|---|
| r10 LDR 只有装载后候选，无独立字段原值 | 新 r11 在原 LDR 前读取 8 字节，96 次装载结果与 +4 原字逐次一致 | 完整结构、字段初始化/更新生命周期和所有权未验 |
| r10 没有跟踪 BX 或候选处实际执行 | 新 r11 核 96 次原 BX 的真实目标与 ISA，并执行/核对原目标首指令；84 次 PUSH 栈写入核对 | 目标返回、后续业务初始化完成和完整业务名称/注册数未验 |
| 工具不能以摘要/运行结束冒充局部通过 | 新核验器逐项核源/ROM/真实 CPU、帧/字段/指令效果、精确读窗/断点/单步、时钟/QMP/退出；30 类错误记录拒绝 | 工具负例不是原厂错误模块/错误调用/断电测试，也不能证明检测任意一致伪造 |
| 新模块和核验器尚未实现时的红测 | 两份缺模块失败日志保留；实现后 10 新测试及完整 125+11 回归通过 | 只是工具实现，不是原厂固件缺陷修复 |
| r10 扩展窗口 73 项未配对和完整端口/模型缺口 | 旧失败保留、不降低标准；r11 没改客体、没补调度或扩大旧上限 | 73 项未解释；精确 r69 source、内存/任务/等待生命周期及完整候选仍缺 |

本轮两次运行没有新增观察器失败或客体补写，不虚构固件 bug 或声称修复了原厂业务。r1 整数 EABI/对齐修复、r9 读时钟恢复选核、r10 r5 阶段语义等既往工作不改写成这轮新修复。

## 5. 证据、复现与清理

核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-callback-r11/verification-1.json`） 与 `verification-repeat.json` 逐字节一致，SHA256=`65db8446f2531f870a6bf81d63576627be4541c8026da745e91745f44d8d6089`；正式结论保留完整 ABI/业务完成/生命周期/结构所有权/集成/刷机安全 false。r10 重放（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-callback-r11/entry-r10-reverified.json`）、r9 重放（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-callback-r11/create-r9-reverified.json`） 通过。47 份旧不可变文件 SHA/长度一致，共享 README 后续仅追加，不把旧 README 摘要误称仍相同。

当前环境（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-callback-r11/environment-current.json`） 重新核对原整包/主从/控制器/r69 SHA 不变；Fenestra 固定 b199dcdf，仅原两个 loader 文件修改；参考 4f43899 工作树干净。精确 r69 source 不存在，默认 gate/transfer-reset/sequencer completion=true 保留，实验开关 false 不能称“无任何完成逻辑”。本轮只用原 boot-image，无控制器/卡/参数/Fenestra 候选；不重编或替换模型。

清理（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-callback-r11/cleanup-final.json`） 于 16:24:50（+08:00）检查 Win32 无 QEMU、Q: 不存在；两自有进程 QMP quit 有应答且真实退出 0。它们只是宿主清理，不是相机正常关机或恢复。无后台委派/运行等待，无相机/USB/PTP/物理卡/磁盘/刷机。原许可证 CC BY-NC-SA 4.0、商业摄影例外和署名边界保留，不提交/推送或发布原固件/密钥。

本机 Python 3.12、Capstone 5.0.7、Git Bash；未启动 IDA、下载工具或调用外部服务。技能缺失的 tool-index/precedent 不冒充已读。复现需本地固定原输入、runtime 和绑定源码存在；输出名必须不存在，重复时另选新名。以下两类命令以实际输出名执行过，示例给新输出名：

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR"
export PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
python -X utf8 -B fenestra/z62/verify_task_callback.py \
  --run analysis/fenestra-z62-task-callback-r11/run-1-final.json \
  --run analysis/fenestra-z62-task-callback-r11/run-2-repeat.json \
  --output analysis/fenestra-z62-task-callback-r11/verification-recheck.json
```

动态 `observe_task_callback.run` 支持目标 8～256、1～6 模型秒、30～300 宿主秒，以及既定有限准备/事件上限；正式两跑为 32/2/180 和 32/3/180。Q: 仅自建 samefile 本工程别名、finally 撤销；这些参数不授权访问物理设备或扩大客体写入能力。

## 6. Evidence → Finding → Path 与全目标审计

| Evidence | source_ref / content_hash | repro_command |
|---|---|---|
| E-static/E-imports | contract-final、原成员身份和原 LDR/BX 指令；来源 SHA 在运行记录 | task_callback_contract.collect；第5节重放 |
| E-runtime-1 | run-1 SHA `edd756a37f237d631451431bc8d5e7069e36e77e70dc93a08da0ff02c7d53da0` | 第5节 verify_task_callback |
| E-runtime-2 | run-2 SHA `ef7a4c7a0fb4d5077e13d7258aed819ea5752041f8d9fa1d25f990e46a42a541` | 同上 |
| E-tests | tests-new-green/tests-full-1/tests-candidate-1、verification-1/repeat，含红测记录 | 第5节 unittest 和重放 |
| E-boundary | scope、PORT、environment-current、cleanup-final、旧文件摘要 | 当前文件/SHA/精确命令/Win32 只读检查 |

| Finding | severity / evidence_ids | confidence / location / status |
|---|---|---|
| F1 +4 原字段与原 LDR/BX 到目标关系成立 | n/a_re；E-static/E-runtime-1/2 | high；96 条有界链，局部通过，不是完整描述符 ABI |
| F2 目标原首指令实际执行且效果吻合 | n/a_re；E-runtime-1/2 | high；96 条，84 次栈字；不含后续业务/返回/完整生命周期 |
| F3 完整端口、模型来源、镜像刷入和绝对安全缺证 | n/a_re；E-boundary | high；PORT loader-only、阶段均未放行 |

P1，path_type=callflow：原发布前帧 → 自然调度/首次入口及 current-TCB 核对 → 独立读取 r1 起 8 字节 → 原 LDR 隔离步 → 原 BX 隔离步 → 原字段目标/ISA/参数核对 → 原目标首指令隔离步及实际栈字 → 排空撤断点 → 后续模型目标窗 → 宿主关闭。挂 E-static/E-runtime-1/2、F1/F2，不外推业务完成或刷机成功。

时间线（+08:00）：新增合同/核验红测→实现后10测试绿；16:20:46～16:21:18 run-1；16:21:18～16:22:06 独立 run-2；随后双重放/30负例、125+11回归、r9/r10重核验；16:24:50环境/清理检查。完整测试、源码/链接/示例语法及交付摘要的最终结果另存本目录 `final-checks.json` / `deliverables-final.json`，不将计划当执行证据。

| 原始要求 | 当前结论与原因 |
|---|---|
| 完成原 Fenestra 原厂移植并保持路线 | 未验证：仍 loader-only，没有完整原厂任务/同步/卡文件/SDK/模块管理/菜单及启动关机候选；路线未替换 |
| 先用自研 QEMU 验证完整方案 | 未验证：96 条原厂字段链只是 Q3 局部证据，Q1～Q6/对照/错误模块/完整生命周期矩阵未齐 |
| 再验证镜像与刷入流程 | 未验证且未进入验收：U1～U6 缺证，无完整候选可冻结 |
| 前两阶段全部通过才能上真机 | 本轮遵守：仅离线文件/QEMU，没有相机或刷机 |
| 真机刷入和运行一定不出问题 | 未满足/未验证；不能由有限 QEMU 样本提供绝对保证 |
| 每阶段的验证项/通过标准/问题修复/转换条件 | 第2、4节逐项列明；没有把未执行或旧失败标通过 |

下一步仍需恢复字段初始化/业务封装与名称/注册计数关系、启动 API 完整入口返回、System 模式、退出/删除复用、失败/flags/同步/所有权、自然堆释放/合并/复用及完整等待链表/通知/硬件完成源；并恢复可开发可追溯模型来源、可保留空间/cache-DMA-MMU 合同和完整原厂 Fenestra 服务/候选。全部 Q 项通过才冻结镜像进入 U 项；前两阶段和独立物理恢复条件未满足前不上真机。
