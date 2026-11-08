# Fenestra / Z62 可追溯模型重建 r13

> 2026-11-07 · 本地离线 · flavor=null · severity=n/a_re
>
> **整体移植尚未完成，不能刷机或上真机。** 本轮实际完成了一份有完整新来源清单、可继续开发的 Z62 模型构建，并以原 C1.70 做了两次有界运行。它不是旧 r69 精确构建来源的恢复，也不是完整 Fenestra 原厂集成或刷入安全证明。

## 1. 结果先看

- 新工具 [重建入口](../../tools/rebuild_fenestra_z62_model.py) `0.1.2`，输出独立目录 `.build/fenestra-z62-model-r13-03`。新 EXE 为 10,253,669 字节，SHA256 `595af7c39fa5b1b86ada8cf4a4c40651dff6fc4f946de6b35e904ff4fe3b9d18`。
- 实际从固定离线包、参考 donor、r1/r4/r5 转换及 23 个后续层重新生成；31 个 donor 文件、61 个配方文件、78,316 个完整源码文件摘要已保存，含明确预建的空 Meson 锁文件。编译前后源码逐文件一致，不忽略额外文件。
- 第三轮 1,315 个编译/链接步骤、生成 SD/SDHCI/Nikon 设备选项、EXE 与 8 个非系统 DLL、版本/机型/属性帮助检查通过；当前工具链和配方未变。参见 构建清单（本地证据，未分发：`<WORKSPACE>/.build/fenestra-z62-model-r13-03/model-build.json`）、完整准备清单（本地证据，未分发：`<WORKSPACE>/.build/fenestra-z62-model-r13-03/prepared.json`） 和 编译日志（本地证据，未分发：`<WORKSPACE>/.build/fenestra-z62-model-r13-03/compile.log`）。
- 新 基线观察器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_model_baseline.py`） `0.1.0` 在两个独立进程运行原主从，无卡、参数、控制器或 Fenestra 候选。四核所采原代码匹配、所读故障寄存器为零；仅到约 1.437/1.878 主模型秒，不能当完整启动、正常关机、菜单或模块业务运行。
- 159 项 Fenestra 专项测试、11 项离线候选工具测试通过，无跳过；r9～r12 原固定 r69 证据重放通过。额外旧设备组 38 项中 30 通过、8 项因缺少原历史源码夹具报错，**该组没有通过**。
- 69 份 r12 旧不可变交付文件长度与 SHA 不变；共享 README 仅追加。原固件、旧 r69 和 r1～r12 绑定源码未改。当前核验见 verification-current.json（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/verification-current.json`）。

授权与范围见 [scope](../../analysis/fenestra-z62-model-r13/scope.md)：只做原 Fenestra 路线的第一阶段前置，不下载、不联系外部服务、不连接相机/USB/PTP、不操作物理卡/磁盘、不刷机、不改客体指令/返回值/RAM/PC、不注入调用或补成功事件。loader 的既有复位初始化不是刷入证据。

## 2. 三阶段验证标准与转换条件

### 第一阶段：自研 z62qemu 中的完整移植

| 项目 | 通过标准 | 当前证据、问题与修复结果 |
|---|---|---|
| Q1 ARM32 模块/SDK | 原厂环境下完整模块格式、重定位、入口、copied-service SDK 与合法/错误模块真实执行 | 仍只有合成加载器/legacy v1 日志；本轮未加载 Fenestra。未通过 |
| Q2 启动/关机 | 主从 ISA/栈/MMU/初始化及完整启动、正常关机、再启动通过 | 本轮只采原代码/时钟/调度窗口；末次 idle、QMP quit/退出0不算完整启动/关机。未通过 |
| Q3 内存/任务/同步生命周期 | 创建/启动API入口返回、System、退出删除复用、耗尽/flags/同步/所有权，堆自然释放/合并复用均通过 | r12仅局部创建/字段/服务0A，不是index3启动API；r10的73待配对仍缺解释；本轮未填这些缺口。未通过 |
| Q4 空间/加载/cache-DMA | 可保留代码数据空间/所有权、真实早期介质加载容量、发布回收合同已恢复并实跑 | 可读地址、原堆分配、清零或映射可执行均不能直接充当插件空间。未通过 |
| Q5 完整 Fenestra 原厂服务 | 原任务/同步/卡文件、完整 SDK、模块管理/菜单及启动关机集成真实执行 | PORT（本地证据，未分发：`<WORKSPACE>/fenestra/z62/PORT.json`）仍 `experimental-loader-only`；没有完整原厂候选。未通过 |
| Q6 完整矩阵/模型可信度 | 同模型同配置原版/候选停用/启用，合法/错误模块、启停/异常/压力/完整生命周期通过；关键模型来源/近似缺口关闭 | 本轮建立新模型源码→构建→有限原厂运行关系；未重现旧r69精确来源，默认completion/物理近似及8项旧夹具覆盖仍缺。完整候选矩阵未运行。未通过 |

**进入第二阶段：Q1～Q6 全部通过，关键模型近似/失败已解释并关闭，完整候选可复现冻结为唯一 SHA。当前不满足，不进入第二阶段验收。** 新模型不自动继承旧运行验收，也不将不同模型/进程的局部记录拼成完整生命周期。

### 第二阶段：同一冻结镜像和完整刷入流程

| 项目 | 必须达到的标准 | 当前状态 |
|---|---|---|
| U1 唯一镜像/资格/边界 | 唯一 SHA，型号版本、主从控制器、长度地址正确；互换/截断/越界拒绝 | 无完整候选，未进入验收 |
| U2 原厂认证 | 真实 B8/K8，原更新器接受合法镜像且拒绝篡改 | 未验证；CRC、seed、表关系、其他机型结果不替代 |
| U3 实际介质早期加载 | 介质容量、加载边界、入口、主从发布顺序实测正确 | 未验证；boot-image预装与复位PC不等于介质加载/刷入 |
| U4 写入/保留/读回/持久化 | 实际擦写范围、NOR/校准保留、读回/重启持久化与冲突处理通过 | 未验证；空白虚拟卡、合成参数不算原机备份 |
| U5 中断/断电/恢复 | 校验、擦除、写入、提交、重启各阶段的中断/超时/断电恢复或回滚通过 | 未验证；模拟器宿主退出0不是更新恢复 |
| U6 完整可追溯重建 | 同一候选镜像、源码、模型、工具链依赖/许可证均可重建，关键失败已解释 | 本轮只有新模型的一次成功构建及来源清单，不是固件镜像验收或第二次位一致构建。未进入验收 |

**只能在第一阶段放行后，针对同一冻结候选通过全部 U 项；不能拼接不同候选/模型的局部证明。** 11项候选工具测试并非原厂认证、擦写、持久化或恢复验收。

### 第三阶段：真机

前两阶段全部通过，并独立关闭物理供电/存储/cache-DMA/时序和可恢复路径缺口，才具备讨论受控真机测试的前提。当前不满足，真机开关关闭。本轮未连接相机或刷机。有限模拟器测试不能证明所有未来物理状态绝无故障，用户要求的“刷入和运行一定不出问题”仍未满足/未验证，不能自行改成“降低风险”后放行，也不能作绝对承诺。

## 3. 来源恢复与实际问题

### 3.1 为什么不是旧 r69 恢复

旧 `.build/z62-output-lineage-2026.11.03-r69` 仍只保有 runtime；其原 source、r66/r69完整父构建清单并未找回。旧构建器严格依赖父清单和 immutable guard，不能跳过后直接续建。本轮新增入口从完整离线 QEMU 包重建所有现存转换，生成**新的来源身份**，没有伪造旧manifest。

- QEMU 10.2.4 离线包：141,137,724 字节，SHA256 `821b545b92f165e57dddccac5077d76d4d436a226595b8813ad59306bbfd0746`。
- Z62 donor：`4f4389944fc339d107f22f5f7ca3f90cc34b78de`，开始/准备结束核对固定 HEAD 和 tracked 工作树。
- reference 更新另外通过本地 git 对象读取固定 Z72 两个源文件并核摘要，未联网。
- r4原转换允许新的 `.build` 源树；r5无纯render接口，独立复制其转换体，AST逐语句比对原体（只做名称限定）且保留全部固定输入/唯一锚点核验，不改原适配器的目录保护。
- 后续23层复用原render和冻结输入SHA；最终包含输出来源层。不修改任何冻结摘要凑通过。每层单独保存在新 work 的 `layer-00.json` 至 `layer-23.json`。

### 3.2 故障、定位、修复与验证

| 问题 | 实际证据 | 修复/结果 |
|---|---|---|
| 工具链迁到中文物理路径后，Meson链接器探测 `TypeError: can only concatenate str (not "NoneType") to str` | 首轮日志（本地证据，未分发：`<WORKSPACE>/.build/fenestra-z62-model-r13-01/compile.log`）；原始stderr字节（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/meson-diagnostic-5-raw.json`）确认链接器中文路径用本机编码、Meson按UTF8解码时读线程异常 | Q:别名也会被工具解析回物理路径，两次诊断保留。新增受保护的实际ASCII scratch工具链副本，50,034文件复制前后摘要一致；未改Meson/设备/原工具链。第二、三轮编译均完成 |
| 第二轮链接已完成，但源码收尾发现额外 `subprojects/.wraplock`，拒绝成功manifest | 第二轮失败（本地证据，未分发：`<WORKSPACE>/.build/fenestra-z62-model-r13-02/build-failure.json`）；Meson本地wrap.py明确使用DirectoryLock创建此文件 | 新准备阶段显式排他创建空锁并计入完整源码清单。不删除文件或忽略额外项，不修改第二轮记录。第三轮完整比对通过 |
| 旧设备回归组8项缺失原父源码fixture | 完整失败日志（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/tests-devices-final.log`） | **未修复/未通过**。缺r5/r6/r7/r8/r47b/r48/r52/r53旧树中的输入文件；不伪造旧目录、不删测试。新链render实际通过不能冒充旧组通过 |
| 测试新增代码一度插进原条件块 | 编辑后立刻读回发现，未运行错误版 | 恢复正确测试结构；随后红绿及最终全测通过，不涉及客体 |

新工具 `0.1.0/0.1.1` 配方和失败目录保留；最终 `0.1.2` 用第三个新目录。新scratch路径保护接口和空锁接口均有先失败、后通过的测试；stage红测（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/tests-stage-red.log`）、lock红测（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/tests-lock-red.log`）、14项绿测（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/tests-lock-green.log`）。

## 4. 新模型原厂实跑与覆盖边界

| 记录 | PID | 宿主继续窗口 | 末次主/从模型秒 | 核验结果 |
|---|---:|---|---|---|
| baseline-1（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/baseline-1.json`） | 43660 | 2 / 15 秒 | 1.437467 / 1.435964 | 四核原代码/头身份、所读故障零、时钟单调、只读命令、QMP应答/退出0；通过有限窗口 |
| baseline-2（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/baseline-2.json`） | 32440 | 2 / 20 秒 | 1.878002 / 1.876498 | 独立进程同上；通过有限窗口 |

两跑都是原C1.70主从，`-nic none`，QMP/GDB仅 `127.0.0.1`；没有卡/参数/控制器/候选。Q:先查未占用、建立后samefile核对、finally仅移除自建映射。四核的原PC/代码窗口、寄存器、current/ready与栈有界只读；未注入/替换客体状态。

末次PC分别位于主 `10107074..10107090` 和从 `10038A48..10038A68` 的原空闲轮询附近。采样不等于全过程跟踪；原代码身份和所读故障零也不证明无其他错误。`0x04266008`按既有48MHz口径折算为模型秒，不是物理时序，宿主秒不能充当客体覆盖。

实验completion/RAW/frame-sync开关两侧均false，但 `gate-completion`、`transfer-reset-completion`、`sequencer-completion` 两侧仍true；**本轮没有关闭或证明这些默认逻辑等效真实硬件**。也没有运行菜单循环、传感器/拍照/录像、Fenestra模块或正常相机关机。QMP quit和退出0只算自有宿主进程关闭。

## 5. 测试和旧证据保全

- 最终专项日志（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/tests-full-final.log`）：159通过、无跳过；142旧专项＋14重建测试＋3基线回放/负例测试。
- 候选工具日志（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/tests-candidate-1.log`）：11通过、无跳过，仅离线工具。
- 基线核验器拒绝13类定向错误记录，包括错误模型/清单/源、缺样本、scope、原代码/故障/时钟、调试写命令、命令行及quit应答。它们不是原厂错误模块、硬件故障或断电恢复验收。
- 旧r9/r10/r11/r12证据重新核验结果分别为 create（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/create-r9-reverified.json`）、entry（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/entry-r10-reverified.json`）、callback（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/callback-r11-reverified.json`）、wrapper（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/wrapper-r12-reverified.json`）。仍使用旧绑定runtime；没有用新EXE重写历史来源。
- 旧设备组38项的8个fixture错误仍列未通过，不与上述159项混算。
- 当前核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/verification-current.json`）验证69份旧交付、78,316源码、61配方、50,034工具链文件和所有8个DLL；保存两跑身份/时钟/只读命令及清理。原 r69 SHA 仍 `37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9`。
- 新工具链全量复制证明另存 copy清单（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r13/toolchain-copy-verified.json`）；运行依赖由原 `stage_windows()` 的native objdump递归导入扫描取得，见构建清单中的8个DLL，不猜依赖。未发布或打包固件、密钥、缓存；未提交/推送。

## 6. 复现与时间线

以下为本轮实际执行的Git Bash命令。输出已存在时会拒绝覆盖；独立复现须为新work和scratch工具链选择新的后缀，不能删掉旧目录续建。临时文件只写当前PI scratch或工程。无需下载；先满足固定离线包、本地git对象和已安装工具链前提。

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR"
export PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B tools/rebuild_fenestra_z62_model.py stage-toolchain --work "$PI_SCRATCH_DIR/msys-r13-01"
python -X utf8 -B tools/rebuild_fenestra_z62_model.py prepare --work .build/fenestra-z62-model-r13-03
python -X utf8 -B tools/rebuild_fenestra_z62_model.py compile --work .build/fenestra-z62-model-r13-03 --msys "$PI_SCRATCH_DIR/msys-r13-01" --jobs 8
```

```bash
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
```

```bash
python -X utf8 -B fenestra/z62/observe_model_baseline.py --output analysis/fenestra-z62-model-r13/baseline-1.json --windows 2 15
python -X utf8 -B fenestra/z62/observe_model_baseline.py --output analysis/fenestra-z62-model-r13/baseline-2.json --windows 2 20
```

关键时间（本机+08）：17:39首轮Meson探测失败；随后以原字节/直接调用/两种别名定位并保留5份诊断；第二轮链接完成但锁文件检查失败；18:03:15第三轮开始编译，18:09:51成功写构建清单；随后两独立原厂基线和全测/旧证据重放；18:19:11当前来源/输入/进程复核记录落盘。完整细节以记录时间和日志为准，构建步骤数与运行窗口不混算。

工具：Windows原生Python3.12、项目MSYS2 UCRT64安装副本（GCC16.2.0、Python3.14.10、Ninja1.13.2，实际版本全文/文件摘要见新work `toolchain-current.json`）、QEMU10.2.4、原有Capstone/只读RSP/QMP。不调用缺失的`tool-index.md`/`ops/evidence-finding-path.md`，不冒充已读；报告按实际可用E/F/P模板组织，无需自举或联网。QEMU及依赖许可证保留在源码/运行依赖目录；Fenestra原许可证和商业摄影例外不变，不视为无限制商用。

## 7. Evidence → Finding → Path 与全目标审计

| Evidence | source_ref / content_hash | repro_command |
|---|---|---|
| E1 新源码/构建 | 新work的prepared/model-build/compile.log；EXE SHA `595af7c3…fe3b9d18`，prepared SHA `adaed724…550884`，完整值见清单 | 第6节prepare/compile；现存目录只读核验，拒覆盖 |
| E2 两原厂有限基线 | baseline-1/2；记录SHA `8dd7dd1c544aa3a40820dd1a9a18b1111ed3482e8f17815e8a2cd02f8ea8feaf` / `0ce410cd135f172e04301e2eeba60d9c7f42cee41cc41d1b23ddda5efd49be6f` | 第6节两观察命令；check_record只读重放 |
| E3 工具回归/旧保全 | tests-full-final、tests-candidate-1、tests-devices-final、四重放和verification-current；当前核验SHA `fb1e67b962b53630284ff33ec9a8850cf3368aeb781092f36efbcafdfbf3fc6f` | 第6节unittest及四旧核验器的新输出 |
| E4 真实失败及修补 | r13-01/02 build-failure、5诊断、stage/lock红绿日志，原记录不改 | 原失败配方保存在各work recipe；不续建失败目录 |

| Finding | severity | evidence_ids | confidence | location | status |
|---|---|---|---|---|---|
| F1 新模型的源码→编译→有限原厂运行关系成立 | n/a_re | E1/E2 | 高，仅本次模型 | r13-03 | 局部通过，非旧r69身份恢复 |
| F2 默认completion与完整Fenestra/生命周期覆盖仍缺 | n/a_re | E2/PORT/旧r10诊断 | 高 | qtree/PORT | 未关闭，不放行第一阶段 |
| F3 中文工具链编码故障和Meson锁清单问题已在新构建入口修复 | n/a_re | E4/E1 | 高 | 新重建工具 | 修补后完整构建通过；非原厂业务修复 |
| F4 旧设备原样回归存在8项缺失夹具错误 | n/a_re | E3 | 高 | 旧设备测试 | 未通过，不能隐去或替换为成功 |

P1（path_type=callflow）：固定离线包+donor→原reference/r4/r5→23冻结render层→显式锁与完整源清单→ASCII工具链副本→离线编译/依赖扫描→两次原厂有限基线。对应E1/E2/E4，仅为模型开发前提，不进入刷入路径。

全目标审计：完整原Fenestra端口**未验证**；完整QEMU候选/错误模块/生命周期矩阵**未验证**；冻结镜像/真实刷入/恢复**未验证且尚未进入验收**；阶段顺序和无真机操作**遵守**；绝对真机安全要求**未满足/未验证**；阶段标准/问题/实际修补和转换条件**已列明**。

后续仍须恢复完整任务启动/退出删除/同步/堆释放与等待通知合同、解释r10待配对，恢复可保留空间和MMU/cache-DMA/真实加载合同，完成原Fenestra SDK/卡文件/模块管理菜单/启动关机候选，在新模型独立关闭关键近似并做完整Q矩阵；Q全过后才冻结镜像验U全项。在此之前不连接相机，不生成供实机刷写的包，不作绝对安全承诺。
