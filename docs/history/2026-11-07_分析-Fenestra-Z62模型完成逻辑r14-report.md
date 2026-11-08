# Fenestra / Z62 模型完成逻辑与冻结夹具 r14

> 2026-11-07 · 本地离线 · flavor=null · severity=n/a_re
>
> **第一阶段仍未放行，第二阶段未进入验收，真机关闭。** 本轮补齐了缺失源码夹具下的测试覆盖，并实际确认默认完成逻辑影响原固件的请求轨迹；没有完成原厂 Fenestra 端口、冻结固件镜像或验证刷入。绝对真机安全要求仍未满足。

## 1. 本轮结果

- 新增 [冻结夹具工具](../../tools/z62_reconstructed_fixtures.py)，从固定离线包/donor/现存转换链重新生成 23 层输入。每层输入均匹配原 `INPUTS/INPUT_SHA`；最终 34 个相关生成文件与实际编译的 r13 完整源码摘要一致。没有恢复或写入旧版本源码目录。
- 原设备组 38 项断言在新夹具下两次全部通过，无跳过；每次只对 19 个精确缺失输入文件提供 20 次只读映射，测试源文件、断言及设备 guard 不变。**这不是原历史完整构建树恢复，也不是未加夹具的旧测试命令已通过。** 详见 第一次结果（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/legacy-with-fixtures-1.json`）、重复结果（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/legacy-with-fixtures-2.json`）。
- 补核 r13 配方清单未单独列出的 `PIXELS` 头文件。当前摘要 `16dde4812b2c415927813d995926afc1a0bdc9e8be9137a66e0f3fbcb407c07c` 与 r13 已生成源码一致；新依赖清单共 63 文件（r13 原 61＋该头文件＋本轮夹具工具）。补充记录不冒充 r13 原时间点已冻结这个独立输入。
- 新 完成逻辑观察器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_completion_ablation.py`） 用原 C1.70、新 r13 同一 EXE，完成 7 个独立有界进程：默认和三开关关闭各两次，另三个单开关关闭各一次。只改变启动时模型属性，不修改运行中客体状态。
- 默认两次的 gate/sequencer/transfer-reset 模式匹配请求次数均为 **13/15/7**，三开关关闭两次均为 **10/2/0**。两者末次都可处于原空闲轮询、所读故障为零，但请求轨迹和寄存器状态不同。**“空闲＋无所读故障”不能当完整启动验收。**
- 175 项 Fenestra 专项、11 项候选工具、38 项新夹具下原断言均通过，无跳过；旧 r9～r12 证据重新核验通过。r13 旧交付 83 文件、r12 旧交付 69 文件（均排除只追加的共享README）长度/SHA不变；完整 r13 源码 78,316 文件重新核对。参见 当前核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/verification-current.json`）。

范围见 [scope](../../analysis/fenestra-z62-model-r14/scope.md)。全程无下载/外部服务、相机/USB/PTP、物理卡磁盘或刷机；没有 guest 指令、PC/RAM/寄存器/返回值补写或注入调用/事件。未提交、推送、打包或发布固件/密钥。

## 2. 各阶段的验证项与转换条件

### 第一阶段：完整移植在自研 z62qemu 上可行

| 项目 | 必须达到的通过标准 | 本轮后状态 |
|---|---|---|
| Q1 ARM32 模块与 SDK | 原厂环境中完整模块格式、重定位/入口、copied-service SDK及合法/错误模块真实执行 | 仍仅合成加载器/legacy v1 日志；本轮没运行 Fenestra。未通过 |
| Q2 启动/关机 | 主从 ISA/栈/MMU/初始化、完整启动、正常关机、再启动均通过 | 本轮七次仅有限原厂采样，反证 idle/故障零不足。未通过 |
| Q3 内存/任务/同步 | 完整创建/启动API入口返回、System、退出删除复用、耗尽/flags/同步/所有权、堆自然释放/合并复用及完整生命周期 | r12仍只是局部服务0A，非index3首次启动；r10的73待配对、释放与通知链未解决。未通过 |
| Q4 空间/加载/cache-DMA | 可保留代码数据空间/所有权、真实早期介质加载容量、MMU/cache-DMA发布回收合同明确且实跑 | 未恢复完整合同。可读/清零/映射可执行或自然分配不证明插件可占空间。未通过 |
| Q5 完整原厂服务 | 任务/同步/卡文件、完整SDK、模块管理菜单、启动/正常关机集成真实执行 | PORT（本地证据，未分发：`<WORKSPACE>/fenestra/z62/PORT.json`）仍 `experimental-loader-only`，无完整候选。未通过 |
| Q6 模型可信度和完整对照矩阵 | 可追溯模型；同模型同配置原版/候选停用/启用、合法错误模块、启停/异常/压力/完整生命周期通过；关键近似缺口关闭 | 新夹具覆盖已补；默认完成逻辑影响原固件轨迹被重复观察到，但物理协议未证、其他成功假设仍有。完整候选矩阵没做。未通过 |

**只有 Q1～Q6 全部通过、关键模型失败/近似缺口关闭、完整候选可复现地冻结唯一 SHA，才进入第二阶段。当前不满足。** 不能用工具测试数、末次空闲、日志无异常或 QMP 退出0代替；不把不同进程/模型的片段拼成完整生命周期。

### 第二阶段：同一冻结镜像的完整刷入验证

| 项目 | 必须达到的标准 | 当前状态 |
|---|---|---|
| U1 镜像资格/边界 | 唯一SHA、型号版本、主从控制器资格、长度地址正确；互换/截断/越界拒绝 | 无完整候选，未进入验收 |
| U2 原厂认证 | 真实B8/K8，原更新器接受合法镜像并拒绝篡改 | 未验证；CRC/seed/关系式/其他机型结果不替代 |
| U3 实际介质早加载 | 实际容量、加载边界、入口与主从发布顺序正确 | 未验证；boot-image预装/复位PC不是介质加载或刷入 |
| U4 实际写入/持久化 | 擦写范围、NOR校准保留、读回重启持久化、冲突处理通过 | 未验证；合成参数/空白虚拟卡不是原机备份 |
| U5 中断/断电/恢复 | 校验、擦除、写入、提交、重启各阶段中断/超时/断电恢复或回滚通过 | 未验证；自有QEMU退出0不是相机更新恢复 |
| U6 完整可重建 | 同一候选镜像、源码、模型、工具链依赖/许可证可追溯重建，关键失败解释完成 | 本轮只有源码夹具/原厂有限对照，不是固件镜像重建或第二次位一致构建验收 |

必须先放行第一阶段，再只对**同一冻结镜像**通过全部 U 项；不得拼接不同镜像/模型的局部证据。本轮11项候选工具回归不是原厂认证、实际擦写或恢复。

### 第三阶段：真机

前两阶段全部通过，且独立关闭物理恢复路径、供电/存储、cache-DMA和硬件时序缺口，才具备讨论受控真机验证的前提。当前真机门槛关闭，本轮未连接相机/刷机。有限模拟器证据不能证明所有未来物理状态绝无故障；“真机刷入和运行一定不出问题”仍未满足/未验证，不能自行改成降低风险后放行，也不能作绝对保证。

## 3. 夹具重建与来源补核

### 3.1 修复的是测试输入覆盖，不是旧构建身份

r13 原设备组 8 项错误均为旧父源码夹具不存在。新增工具只在 `.build/fenestra-z62-fixtures-r14-01` 写入**最小源码夹具**，不是完整可编译 QEMU 树：

1. 核 QEMU10.2.4 离线包 SHA `821b545b92f165e57dddccac5077d76d4d436a226595b8813ad59306bbfd0746`，核 r13 31 个 donor 和原61文件配方。
2. 从固定包读取3个原始源码文件，从donor取原C/H，复用唯一host兼容修正及原reference/r4/r5转换。
3. 在每个后续23层render前保存输入，并逐个核原INPUTS/INPUT_SHA；不改任何冻结摘要或旧guard。
4. 最终34个相关文件逐字节摘要对应r13实际编译源；独立 fixture清单（本地证据，未分发：`<WORKSPACE>/.build/fenestra-z62-fixtures-r14-01/fixture-manifest.json`）保存依赖与输入。
5. 测试适配器只截获19个精确缺失路径的 `Path.read_bytes`，提供经过同一原摘要核验的新输入；其他读写/测试断言不变，退出后恢复方法。两次均38项通过。

没有写回 r5/r6/r7/r8/r47b/r48/r52/r53 的旧源码树；不声称原历史环境恢复。旧 r69 精确源码/构建清单仍未恢复，旧 runtime 和旧证据没有换成 r13。

### 3.2 PIXELS 依赖遗漏的边界

r13工具仅收集 `HEADER/HEADERS`，没有把 `z62_grid_geometry_device.PIXELS` 单独列入61文件配方；但它生成的文件已在完整78,316源码清单中冻结并参与编译核验。r14扫描导出文件Path常量，补入 [像素头](../../qemu/z62-mode-geometry/nikon-z62-mode-grid-pixels.h)，要求当前字节与 r13 `prepared.json` 中 `hw/arm/nikon-z62-mode-grid-pixels.h` 摘要一致；随后重建的34个最终相关文件仍一致。

这补齐**当前重建依赖关系**，不是追改r13清单或证明当时未记录输入的全部历史状态。原r13工具/配方保持不变。新63项依赖包含61原配方、像素头和新夹具工具。

### 3.3 本轮工具问题与修复

- 夹具工具读回时发现一行无用的模块属性赋值，未运行即删除；正式清单绑定删除后的版本。
- 首轮新测试把所有 `=on` 都当作成功辅助逻辑，误命中 QMP `server=on`/日志 `timestamp=on`。保留 失败日志（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/tests-ablation-command.log`），将断言限定到 `-global` 后的设备属性；绿测（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/tests-ablation-command-green.log`）后才启动实跑。未改观察器/模型以迎合测试。
- 7项夹具保护测试核对旧/嵌套路径拒绝、原输入SHA、PIXELS、manifest篡改/逃逸和输出不可覆盖；7项命令/trace测试加2项实录重放测试通过，另拒绝17类定向错误记录。这些不是原厂故障模块或断电恢复验收。

## 4. 默认完成逻辑：源码与七次原厂实跑

### 4.1 不是“全部成功源关闭”

本次编译的模型源码（本地证据，未分发：`<WORKSPACE>/.build/fenestra-z62-model-r13-03/source/qemu-10.2.4/hw/arm/nikon-z72.c:1335`）中：

- gate：`0x04287010=0xA1`，还需release_config、gate_completion、表+8 bit0；模型修改bank状态并拉IRQ250。
- sequencer：`0x04251028+channel×0x30`，命令掩码 `0x10000003`，还需master_role、size4、sequencer_completion；模型执行seq_transfer并更新状态/IRQ。**slave模式匹配写入不等于满足该master条件。**
- transfer reset：`0x20100004=0`且transfer_reset_completion时，模型锁存+0x18 bit0并更新IRQ102；源码明确数据传输仍未建模。
- 另有不由这三个开关控制的boot_completions等逻辑和“只读结果零为成功”的假设。因此组名严格是 `three-off`，不是无辅助逻辑/真实硬件环境。

三个模型属性在进程启动命令行显式关掉；无运行中QOM写入、guest修改或注入调用。每跑qtree独立核两侧属性，实验RAW/laboratory/frame-sync等仍false。

### 4.2 已执行的固定矩阵

使用同一r13 EXE SHA `595af7c39fa5b1b86ada8cf4a4c40651dff6fc4f946de6b35e904ff4fe3b9d18`、原C1.70主从、无控制器/参数/卡/Fenestra。每进程固定宿主窗口2/15秒，日志上限32MiB；已有MMIO写trace默认事件，逐行严格解析。7跑合计81,934条写尝试、11,078,934字节trace，均未触上限。

| 记录 | PID | 末次主模型秒 | gate / sequencer / transfer-reset 模式匹配写尝试 |
|---|---:|---:|---|
| default-1（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/default-1.json`） | 30696 | 1.427641 | 13 / 15 / 7 |
| default-2（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/default-2.json`） | 57336 | 1.435136 | 13 / 15 / 7 |
| three-off-1（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/three-off-1.json`） | 32536 | 1.443249 | 10 / 2 / 0 |
| three-off-2（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/three-off-2.json`） | 25168 | 1.441372 | 10 / 2 / 0 |
| gate-off（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/gate-off-1.json`） | 26684 | 1.432562 | 10 / 15 / 0 |
| transfer-off（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/transfer-off-1.json`） | 33132 | 1.460797 | 12 / 15 / 2 |
| sequencer-off（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/sequencer-off-1.json`） | 37060 | 1.443387 | 13 / 2 / 5 |

这是**请求地址/值模式的写尝试数，不是完成次数**。trace在设备回调前产生，不证明接受、成功或物理硬件协议。sequencer默认15包括master14/slave1，关闭后2包括master1/slave1；不能将slave那一次算为master完成源。完整记录保留角色、值、size和行号，host trace前缀不当guest虚拟时刻。

### 4.3 为什么不能用末次空闲判定可行

所有组末次PC都位于主 `10107070..10107094`、从 `10038A44..10038A68` 原空闲轮询附近，current槽均0、原代码窗口匹配，所读DFSR/IFSR为0。但默认与three-off的请求数及独立MMIO快照不同：例如master gate+0xC默认为8、three-off为0；three-off的transfer寄存器窗口全零，默认已经配置过。

默认/three-off各两次保持同类请求数和相关寄存器状态；不能以不同宿主速度的总写数差当精确guest期限或等量指令覆盖。`0x04266008`仍按既有48MHz模型口径折算；1.4模型秒不足以推出其他更长超时窗口的结论。本轮没有验证所有任务完成/失败、错误码35/3F根因、菜单循环、正常关机或任何Fenestra业务。

因此只能确认：**这些默认模型逻辑会影响本配置原固件的可见请求轨迹；关闭它们也不能凭idle/故障零宣称完整启动通过。** 尚未恢复真实硬件事务/完成源合同，不能据此给物理协议打通过，也没有编造新的完成事件“修好”固件。

7跑均只读RSP/QMP、`-nic none`、端口127.0.0.1；Q:创建前核空闲、samefile核对、仅清理自建映射。日志守卫只在超预算时可终止保留Popen身份的自有进程；本次未触发，均QMP应答/退出0。退出0仅为宿主清理，不是相机正常关机。

## 5. 测试、重放与证据保全

- 175专项（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/tests-full-final.log`）＝159旧专项＋7夹具保护＋9完成逻辑测试；11候选工具（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/tests-candidate-final.log`）；38项新夹具重复组（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/fixtures-tests-2.log`），均通过且无跳过。
- r9/r10/r11/r12旧固定runtime的fresh核验分别为 create（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/create-r9-reverified.json`）、entry（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/entry-r10-reverified.json`）、callback（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/callback-r11-reverified.json`）、wrapper（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/wrapper-r12-reverified.json`）。旧r13源码/配方/EXE/8个DLL核验通过，无替换。
- 当前核验保存83份r13、69份r12旧文件摘要（共享README只追加另核前缀）、78,316源码、63依赖、23层夹具、34最终源文件、19精确映射及七独立PID。核验SHA `ce6a5e94009c25b88ec6659e092199a31a09a50cba8a92b3425b358ed6d72a67`。

## 6. 可复现命令、时间线与 Evidence → Finding → Path

以下记录本轮实际Git Bash命令。输出存在会拒覆盖；独立复现需选择新后缀，并保持已固定输入/观察器版本。示例不连接相机、不需要下载。

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR"
export PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B tools/z62_reconstructed_fixtures.py create --work .build/fenestra-z62-fixtures-r14-01
python -X utf8 -B tools/z62_reconstructed_fixtures.py test --work .build/fenestra-z62-fixtures-r14-01 --output analysis/fenestra-z62-model-r14/legacy-with-fixtures-1.json
```

```bash
python -X utf8 -B fenestra/z62/observe_completion_ablation.py --profile default --output analysis/fenestra-z62-model-r14/default-1.json
python -X utf8 -B fenestra/z62/observe_completion_ablation.py --profile three-off --output analysis/fenestra-z62-model-r14/three-off-1.json
```

```bash
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
```

时间线（本机+08）：先核旧fixture缺失与PIXELS遗漏，重建23层夹具并两次跑原断言；命令测试误判修正后，18:35:07起默认/three-off首对，接续两重复和三个单开关组，最后组18:37:41开始；18:41:13保存当前源码/实跑/保全核验，随后fresh重放r9～r12。精确窗口/创建时间在JSON，host时间不当guest期限。

工具为原生Windows Python3.12、固定QEMU10.2.4/r13 EXE、现有只读RSP/QMP和trace解析器；本轮未重编设备、未用IDA或网络服务。源码研究/构建夹具不新增固件认证或硬件安全结论。原Fenestra/QEMU及依赖许可证、署名和适用例外均保留。

| Evidence | source_ref / content_hash | repro_command |
|---|---|---|
| E1 冻结夹具 | fixture-manifest＋legacy-with-fixtures-1/2；完整SHA在当前核验 | 本节create/test |
| E2 七进程对照 | 七JSON与各`.trace.log`，记录与trace SHA保存于当前核验 | 本节观察器命令，profile明确；check只读重放 |
| E3 回归/保全 | tests-full-final/tests-candidate-final/fixtures-tests-2及verification-current，后者SHA见第5节 | 本节unittest和旧核验器新输出 |

| Finding | severity | evidence_ids | confidence | location | status |
|---|---|---|---|---|---|
| F1 缺失输入的断言覆盖由原SHA匹配新夹具补齐 | n/a_re | E1/E3 | 高，仅输入和断言覆盖 | 新fixture工具 | 局部通过，不是旧构建身份恢复 |
| F2 当前PIXELS依赖对应已编译源字节，原清单遗漏未追改 | n/a_re | E1/E3 | 高，当前关系 | 新63文件依赖清单 | 已补核，非追溯性保证全部历史状态 |
| F3 默认完成逻辑影响原厂请求轨迹，idle/故障零不足 | n/a_re | E2 | 高，仅本配置/窗口 | 三开关源分支与原厂trace | 未恢复物理协议，不放行Q6 |
| F4 原Fenestra完整集成、刷入与绝对安全仍缺 | n/a_re | E2/PORT | 高 | Q/U门槛 | 未验证 |

P1（path_type=callflow）：固定源→23层原SHA输入→新夹具→不改断言的38项补验（E1/E3）；P2（path_type=callflow）：同EXE/原固件→启动时三属性对照→只读快照/写尝试trace→重复差异→拒绝将idle充当完整启动（E2）。均不进入刷入路径。

全目标审计：完整原Fenestra端口、完整自研QEMU候选/错误模块/生命周期矩阵、冻结镜像认证擦写恢复和绝对真机保证均**未验证**；阶段顺序及不碰真机**遵守**；阶段验证项/标准/问题/实际修补/转换条件**已列明**。后续必须恢复真实完成源/完整任务同步堆与等待生命周期、可保留空间/真实加载/cache-DMA合同，完成原SDK/卡文件/模块管理菜单/启动关机候选及Q全矩阵，之后才可冻结唯一镜像进入U全项。不能以本轮覆盖数或模型属性关闭替代这些要求。
