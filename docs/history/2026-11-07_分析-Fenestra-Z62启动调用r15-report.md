# Fenestra / Z62 原厂启动调用 r15

> 2026-11-07 · 本地离线 · flavor=null · severity=n/a_re
>
> **完整移植未完成；第一阶段未放行，第二阶段未进入验收，真机关闭。** 本轮补齐的是原 C1.70 自然成功 SVC 启动 API 的局部输入—发布—返回—首次入口链，不是 Fenestra 原厂集成或可刷包。不能保证真机刷入和运行“一定不出问题”。

## 1. 结果与范围

在可追溯的 r13 新模型、原始 Z6II C1.70 主从、无卡/参数/控制器/Fenestra 候选条件下，两个独立进程得到 **17＋52＝69 条同次调用链**，276 个事件，均无待配对或未匹配首次入口。每条均核对：原句柄查表→同次 TCB→原启动参数/76 字节帧→原返回 POP 实际执行→该 TCB 的真实首次入口及原首指令寄存器效果。没有预设返回与任务首次执行的先后：16 条任务先进入、53 条 API 先返回。

初次运行因新工具误将原厂启动 SVC 栈限定为堆地址而失败，已通过现场回归测试修正；失败和初版源码保留。修复的是工具地址守卫，不是客体固件或模型。189 项 Fenestra 专项、11 项候选工具测试、38 项显式新夹具下的历史断言通过，无跳过；并不代表原厂错误模块或刷入测试通过。

范围与授权见 [scope](../../analysis/fenestra-z62-task-launch-r15/scope.md)。RSP/QMP 仅 127.0.0.1、`-nic none`；只读、有界内存、硬件执行断点、原指令单 CPU 隔离单步。不修改客体指令、PC/RAM/寄存器、返回值或 ready，不注入调用/事件。启动时原 boot-image 预装和 loader 复位 PC 单独标记，**不是实际介质加载或刷入**。全程未连接相机/USB/PTP/物理卡磁盘，未提交/推送/发布固件或密钥。

## 2. 三个阶段的验证标准

### 第一阶段：完整原 Fenestra 移植在自研 z62qemu 可行

| 项目 | 必须通过的验证 | 当前结论 |
|---|---|---|
| Q1 模块与 ARM32 SDK | 原厂环境内完整模块格式、重定位/入口、copied-service SDK、合法及错误模块真实执行 | 仍仅合成 ARM32 loader/legacy v1 日志；本轮没有运行 Fenestra。未通过 |
| Q2 启动/正常关机 | 主从 ISA/栈/MMU/初始化、完整启动、正常关机及再启动 | 69 条早期启动调用不是完整启动或正常关机。未通过 |
| Q3 内存/任务/同步生命周期 | 创建/启动输入返回、System/flags/失败、退出删除复用/耗尽、同步/所有权、堆自然释放合并复用 | 本轮新增自然成功 SVC 启动同次链；其余未齐，r10 的73待配对未解释。未通过 |
| Q4 空间/加载/cache-DMA | 可保留代码数据空间及所有权、实际早期介质加载容量、MMU/cache-DMA 发布回收合同实跑 | 可读/清零/可执行映射/自然分配不能证明插件空间可占用。未通过 |
| Q5 完整原厂服务与集成 | 原任务/同步/卡文件、完整 SDK、模块管理菜单、启动和正常关机集成 | PORT（本地证据，未分发：`<WORKSPACE>/fenestra/z62/PORT.json`）仍 `experimental-loader-only`、`firmware_integrated=false`。未通过 |
| Q6 模型可信度与候选矩阵 | 可追溯模型；同模型同配置原版/候选停用/启用、合法错误模块、启停/异常/压力/完整生命周期；关键模型近似缺口关闭 | r13 来源已建立；默认完成逻辑和其他成功假设仍在，原菜单循环/35/3F缺口未关闭，无完整候选矩阵。未通过 |

**Q1～Q6 全部通过、关键失败解释/修复并复测、完整候选可复现地冻结唯一 SHA 后，才能进入第二阶段。** 不能用工具测试数、末次 idle、所读故障零、QMP 退出0或跨进程拼接片段替代。

### 第二阶段：只验同一冻结镜像及完整刷入流程

| 项目 | 必须通过的标准 | 当前结论 |
|---|---|---|
| U1 唯一候选资格与边界 | 镜像唯一SHA、型号版本/主从/控制器资格、长度地址正确；互换/截断/越界拒绝 | 无完整候选，未进入验收 |
| U2 原厂认证接受/拒绝 | 真实 B8/K8，原更新器接受合法镜像、拒绝篡改 | 未验证；CRC/seed/关系式或其他机型不替代 |
| U3 实际介质早加载 | 实际容量、加载边界、入口和主从发布顺序正确 | 未验证；boot-image预装不替代 |
| U4 擦写与持久化 | 实际写入范围、NOR/校准保留、读回/重启持久化、冲突处理 | 未验证；合成参数/空白虚拟卡不是原机备份 |
| U5 各更新阶段中断恢复 | 校验、擦除、写入、提交、重启各处中断/超时/断电恢复或回滚 | 未验证；QMP退出与进程清理不是更新恢复 |
| U6 完整可重建 | 同一候选镜像、源码、模型、工具链依赖/许可证可追溯重建，关键失败关闭 | 本轮没有固件候选或镜像重建验收；一次模型构建不是第二次位一致重建 |

只有第一阶段先放行，再对**同一冻结镜像**通过全部 U 项，才满足第二阶段门槛。11 项候选工具测试不等于 U1～U6 已通过。

### 第三阶段：真机条件

前两阶段全过，并独立关闭物理恢复路径、供电/存储、cache-DMA 与硬件时序缺口，才具备讨论受控真机验证的前提。当前条件不满足，真机门槛关闭。有限模型样本不能证明所有未来物理状态绝无故障；绝对安全要求仍未满足/未验证，不能改成“降低风险后放行”。

## 3. 原 API 局部合同

### 3.1 原字节与导入等价锚点

这是裸 ARM/Thumb 固件，无常规 PE/ELF 导入表；E-imports 等价证据为原服务分发表 index3、句柄表 literal、函数完整代码/字面量、启动帧 STR 及三个返回 POP。原字节/地址与主从输入 SHA 均保存在 最终合同（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-launch-r15/contract-final.json`）。没有启动 IDA、安装工具、下载源码或联系外部服务；使用现有 Python/Capstone。skill 引用的缺失 `tool-index.md`、`precedent-reverse.md`、`ops/evidence-finding-path.md`未冒充已读；报告遵循现有 E/F/P 模板及 `flavor=null` Base 结构。

| 锚点 | master | slave |
|---|---|---|
| 原 index3 输入 | `1010A91C` | `1003C2F0` |
| 发布前 MOV | `1010AAC4` | `1003C498` |
| 早返回 POP 1/2 | `1010A978` / `1010A9B8` | `1003C34C` / `1003C38C` |
| 成功尾部 POP | `1010AB88` | `1003C55C` |
| TCB 表指针/数量全局 | `C18AD81C` / `C18AD820` | `C1016850` / `C1016854` |

完整代码区长度 `0x270`，其后字面量分开存储，避免将 literal 当作指令。初次探索窗口跨越此边界触发 `Incomplete instruction window`，据原始字节缩到真实边界；没有放宽严格解码。

### 3.2 同次关联与实际效果

- 原表公式：`index = input.r0 & 0xffff`；`TCB = table_base + (index-1)*216`。在输入处独立读表指针/数量（现场均512，只是配置数量字段）及216字节TCB，核 `TCB+8 == input.r0`。不据此命名稳定任务身份或总数，也没有测试所有无效句柄。
- 原 `PUSH {r4-r12,lr}`：隔离执行后 SP−40、PC+4，并独立读40字节逐字核对原输入寄存器。不是调试器写栈。
- 同次内核栈唯一配对输入→发布→返回；不把 CPU 号当任务ID。发布处核原 r11 等于输入 r1、帧前两字为启动参数/TCB+C，TCB/76字节帧/SP/CPSR/入口一致；原 MOV 只改变 r0/PC。
- 返回处独立读40字节保存栈，与原输入 r4-r12/LR一致；实际执行原 POP，核恢复寄存器、SP、PC/ISA及返回目标32字节原ROM。本次69条均经成功尾部返回0；**两个早返回仅静态恢复，未动态覆盖。**
- 首次入口按同一角色/current-TCB/原PC唯一配对，核PC/SP/ISA/r0/r1及原首指令寄存器效果；实际包含8个ARM入口、61个Thumb入口。共享Thumb LDR没有在本轮另读原r1+4，不重做r11的字段/BX链，也不证明完整回调返回、业务完成或所有权。
- 从事件流重新构建调用链，逐项核对内存读序、硬件断点生命周期、停止包CPU、`vCont;s:<CPU>`、前后系统寄存器、原ROM、时钟、QMP和清理。31类定向错误记录拒绝；另测一致改输入前后r1不能偷换发布参数、一致改栈地址不能绕过真实读取日志、同PID不算独立。

新源码：合同（本地证据，未分发：`<WORKSPACE>/fenestra/z62/task_launch_contract.py`）、观测器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_task_launch.py`）、核验器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/verify_task_launch.py`）。两次有效运行绑定工具 `0.1.1`、25份源码，以及r13构建清单/EXE/8 DLL；不静默替换旧r9～r12的r69模型。

## 4. 实际运行、问题与修复

### 4.1 三个自有进程

| 记录 | PID | 主/从完整链 | 事件/未匹配/待配对 | trace末主模型秒 | 最终主模型秒 | 宿主秒 |
|---|---:|---|---|---:|---:|---:|
| run-1失败（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-launch-r15/run-1.json`） | 53320 | 0/0 | 首输入失败，保留failure_event | 不作为通过证据 | 无最终采样 | 不作为通过证据 |
| run-2（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-launch-r15/run-2.json`） | 51476 | 5/12＝17 | 68/0/0 | 0.0052224583 | 2.5034515625 | 30.578 |
| run-3重复（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-launch-r15/run-3-repeat.json`） | 37960 | 40/12＝52 | 208/0/0 | 0.0156760417 | 3.7783999167 | 46.531 |

run-2参数16/2/180，run-3参数32/3/180（目标调用数/主模型秒/宿主wall）；均在排空样本后撤断点运行，**全过程调用跟踪只到trace末，不是跟踪到最终模型秒**。两种先后均在两跑两侧观察到：run-2主2/3、从4/8，run-3主7/33、从3/9（任务先进入/API先返回）。所有实际API返回目标均为ARM：主 `101051A0/101076CC`，从 `10036B74/100390A0`；Thumb返回语义只有合成工具测试，不冒充实际样本。

3进程均收到QMP quit应答、退出0，移除自建Q:；QMP不是相机正常关机。暂停前19:16:38保存 当前核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-launch-r15/verification-current.json`），恢复后先核无QEMU/Q:。后续最终检查另记录，不覆盖此前记录。

### 4.2 发现的问题及实际修复

1. **原启动栈不是堆栈地址范围。** 首次InitTask输入SP=`C2B67FF0`，r0=`01000001`，r1=0；新工具的 `bounded_ram`只允许堆区，报 `Unbounded original input stack/return`。保留 `*.initial.txt`及红测（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-launch-r15/tests-stack-red.log`），为输入/发布/返回的调用栈改用既有native-RAM有界地址守卫，TCB/任务帧仍限定原堆区；版本0.1.1。绿测（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-launch-r15/tests-stack-green.log`）及两独立实跑通过。**可读地址守卫不证明分配/所有权/完整栈ABI。**
2. **夹具重跑输出目录不合原工具guard。** 初次把结果指定到r15目录，原工具拒绝 `Use new r14 test output`。未改旧工具/guard，保留拒绝日志（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-launch-r15/legacy-1.host.log`），改用允许目录内全新 `r15-legacy-recheck-1.json` 后38项断言通过。它只追加新结果，不改r14既有文件，不恢复历史完整构建树。
3. 未修复或宣称修复模型硬件完成协议、原菜单循环/35/3F、堆释放、通知链、完整Fenestra原厂集成或刷入认证/恢复。默认 gate/sequencer/transfer-reset completion 仍开，其他成功假设仍存在。r14已证明不同轨迹也能同样末次idle/所读故障零；本轮末次idle不能用作完整启动验收。

## 5. 复验、完整性与证据链

### 5.1 回归与可复验入口

暂停前执行并保留：189专项（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-launch-r15/tests-full-1.log`）、11候选工具（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-launch-r15/tests-candidate-1.log`）、38显式夹具断言（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/r15-legacy-recheck-1.json`）。新增14测试，不改旧测试断言；工具负例不替代客体故障矩阵。重放r9～r12结果与r14对应结果逐字节相同。新重放结果（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-launch-r15/verification-fresh.json`）与第一次结果相同，SHA `8f057f502a8e61767f6ab8c47a4d4f71eaefe2975fd6d32f9cffa6af3d6dfe31`。

工程根下，可重新执行只读测试；TEMP仅当前PI scratch：

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR" PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
```

下例仅重放已保存记录，不启动QEMU。输出必须不存在，重跑需选新名字；不得覆盖旧结果：

```bash
python -X utf8 -B fenestra/z62/verify_task_launch.py \
  --run analysis/fenestra-z62-task-launch-r15/run-2.json \
  --run analysis/fenestra-z62-task-launch-r15/run-3-repeat.json \
  --output analysis/fenestra-z62-task-launch-r15/verification-user-replay.json
```

完整性检查重新核对78,316源码文件（额外文件也拒绝）、原61配方、EXE/8DLL及当前19精确夹具映射；暂停前r14清单169文件全相同。共享README后续只追加，最终检查核旧24,079字节前缀。旧r69精确来源仍未恢复，r13原配方未独立列PIXELS的历史边界不改变；旧测试仅在显式新夹具下通过。Fenestra上游仍`b199dcdf`，保留原两loader修改，Z62 donor tracked干净；不清理或覆盖大量无关用户改动。

### 5.2 Evidence → Finding → Path

| E-id | source_ref / repro_command | content_hash |
|---|---|---|
| E-imports | 最终合同的index3表/原代码/literal；`task_launch_contract.collect()` | `fffcb9aae0f7b9b248c8b68cd95e22653a2597bcae311c4446992dec1323da3b` |
| E-run2 | run-2原日志、事件、读写审计；上面的重放命令 | `f910a90f4c2c2c24ed1a75599cfc6ea611ec70b712bf2adf72c1334c0b55c9ea` |
| E-run3 | run-3-repeat原日志、事件、读写审计；上面的重放命令 | `be935751a748a044954fb5f0eb9b021865f2af6d5edccf02f8bc6244639085bb` |
| E-fail | run-1、初版源码、栈红绿测试；`unittest discover -s tests -p test_fenestra_z62_task_launch.py -v` | run-1 `d77b447db1b9e8209f606125af32e2dbdaf7049ccefe1d4331e54eb7f4bc3a5a` |
| E-current | verification-current完整源码/旧交付/模型/PORT/进程核验 | `d2513ee4f6fff4a4dfaec17485f09303ef1e7848c9afcf8f6d17e2d734940854` |

| F-id | severity | evidence_ids | confidence | location | status |
|---|---|---|---|---|---|
| F-input-return | n/a_re | E-imports/E-run2/E-run3 | high，仅此样本 | index3输入、发布、原POP、首次入口 | 局部自然成功SVC链通过；完整ABI未证 |
| F-order | n/a_re | E-run2/E-run3 | high，仅此样本 | entered/returned事件顺序 | 两种顺序均实际观察，不假设同步返回 |
| F-stack | n/a_re | E-fail/E-run2/E-run3 | high | 新工具调用栈地址守卫 | 工具修正并回归，客体/模型未改 |
| F-gates | n/a_re | E-current/PORT及第2节 | high，状态结论 | Q/U/真机门槛 | 完整目标未完成，三个阶段均未放行 |

P-index3，`path_type=callflow`：原表index3→自然输入句柄/r1→原PUSH及TCB查表（E-imports/E-run2/E-run3）→同次发布帧→原调度；实际任务首次入口与原API返回允许两种相对顺序→原POP恢复/目标ROM与首次入口核验（F-input-return/F-order）。不延伸到未观察的回调完成/退出删除。

时间线（UTC+8）：19:08:56首次失败进程；19:10:06修正后run-2开始；19:11:04独立run-3开始；19:16:38完整源码/旧证据核验保存；之后用户暂停，恢复时先核进程/文件再补本文，未将暂停期间当运行覆盖或重新启动后台任务。

## 6. 未完成项与下一步

- 接续原创建封装/对象字段/服务0A到同次index3及业务回调返回/完成，恢复完整描述符/注册来源/所有权；不能把r12和本轮不同进程拼成生命周期。补System、flags/耗尽/失败、退出删除/复用、同步；解释r10的73待配对。
- 补自然堆释放/合并复用和完整等待登记返回/通知/唤醒；恢复真实gate/sequencer/transfer-reset事务与完成源，关闭原菜单循环/35/3F及其他模型成功假设缺口。
- 明确可保留代码数据空间、实际介质早加载、MMU/cache-DMA发布回收；实现原Fenestra完整SDK/原任务同步/卡文件/模块管理菜单/启动正常关机候选，完成同候选完整矩阵。
- Q1～Q6全过才冻结唯一镜像验U1～U6；前两阶段及独立物理恢复条件未齐前不上真机。总体移植/QEMU完整可行性/完整刷入/绝对安全仍unverified；阶段顺序遵守、分阶段标准及局部问题修补已说明。
