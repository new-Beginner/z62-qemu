# Fenestra Z62 任务创建 r9：原厂配置、初始帧与返回关系

> 2026-11-07；Nikon Z6II C1.70；原 Fenestra + 自研 Z62-QEMU 路线；flavor=null；severity=n/a_re。
> **完整移植仍未完成。第一阶段未放行，第二阶段未进入验收，真机关闭；没有可刷 Fenestra 包，不能保证真机绝对零风险。**

## 1. 本轮交付与范围

新增独立任务创建合同、观察器、核验器及11项测试，不改r1～r8源码和证据。原C1.70在两个固定r69进程中，自然完成90/256次调用配对，共346次：入口配置 → 初始帧构造点 → 原厂返回。配置首三字与TCB+C/10/14、8字节名称复制、初始CPSR/PC/模式、保存SP、返回句柄和保存寄存器关系均重放成立。354次共享返回桩命中因不匹配待返回调用而单独保留，未计入创建成功。

这是原厂集成的一项前置合同，不是Fenestra运行成功、完整任务ABI、全部注册任务清单或稳定生命周期身份。名称字段多数为空，两进程中只有各引擎一次`InitTask`非空，不能恢复全部业务名称；重复名称、跨主从相同句柄、跨进程相同地址不能合并成同一身份。未注入创建/删除或故障调用，未修复原厂硬件等待根因。

105项专项和11项候选工具回归通过、无跳过；两份正式记录重放两次、输出逐字节一致，23类定向错误记录拒绝。旧r8记录重新重放通过。范围与授权见[r9 scope](../../analysis/fenestra-z62-task-create-r9/scope.md)，当前PORT（本地证据，未分发：`<WORKSPACE>/fenestra/z62/PORT.json`）仍`experimental-loader-only`、`firmware_integrated=false`、`flash_safety_verified=false`。

## 2. 三阶段项目、标准及转换门槛

### 第一阶段：自研 z62qemu 上的完整移植方案

| 项目 | 通过标准 | 当前结果/缺口 |
|---|---|---|
| Q1 ARM32模块、原Fenestra SDK | 格式、重定位、入口及完整copied-service SDK真实执行；合法/错误模块正确接受/拒绝 | r1只有合成loader、legacy v1日志；完整SDK/原厂模块运行未通过 |
| Q2 原厂启动与正常关机 | 精确主从ISA/栈/MMU/初始化正确，原厂启动完成、正常关机与再次启动均验证 | r2/r3早期窗口、r6空闲采样不是完整启动/关机 |
| Q3 内存、同步、任务生命周期 | 分配、自然释放、合并/复用、flags、失败/耗尽、同步/所有权、任务创建/启停/异常/删除和回收均通过 | r9补346次自然构造关系；没有完整API、删除复用或故障矩阵；r7/r8不等于完整等待登记/唤醒 |
| Q4 代码/数据、加载与cache | 可保留空间和所有权、真实早期加载容量、cache/DMA/MMU发布、退出回收合同明确并实跑 | 空白、清零、可执行映射、成员尾端外地址都不能作可占用空间；仍缺证 |
| Q5 完整原厂Fenestra服务 | 原厂任务/同步/卡文件、模块管理、菜单、copied-service服务、启动/正常关机集成真实运行 | 没有完整候选；未改用其他插件系统冒充 |
| Q6 完整对照/压力与模型可信度 | 同一自研QEMU同配置原版/候选停用/启用、合法/错误模块、启停/异常/压力/完整生命周期均通过；关键失败及模型来源/覆盖缺口关闭 | 未完成；精确r69源码仍缺，默认完成逻辑和物理近似缺口保留 |

**只有Q1～Q6全部通过、关键模型缺口关闭、完整候选可复现并冻结唯一SHA，才能进入第二阶段。当前不满足。** 不通过改原指令、补PC/返回值/ready/事件或强制completion填覆盖；不关闭机型、身份或长度检查。

### 第二阶段：唯一冻结镜像与完整刷入流程

| 项目 | 通过标准 | 当前结果 |
|---|---|---|
| U1 资格和地址边界 | 唯一SHA、型号/版本、主从/控制器资格和长度地址正确；互换、截断和越界拒绝 | 无完整候选，尚未进入验收 |
| U2 原厂更新认证 | 真实B8/K8，原厂更新器合法接受、篡改拒绝 | 未验证；CRC/seed/别机型表不是认证证明 |
| U3 实际介质早期加载 | 介质到原厂的容量、入口、地址和主从发布顺序正确 | 未验证；boot-image预装和复位PC初始化不是介质读取/刷写 |
| U4 写入与持久化 | 实际写入范围、NOR/校准保留、读回、重启持久化及冲突处理正确 | 未验证；合成参数、空白虚拟卡不能代替原厂备份 |
| U5 中断、断电和恢复 | 校验/擦除/写入/提交/重启各阶段中断、超时、断电恢复/回滚均通过 | 未验证；QMP quit/宿主退出0不是恢复 |
| U6 可追溯重建 | 同一候选源码、工具链、模型、依赖、许可证和镜像完整可复现，关键失败已解释 | 未通过；固定EXE及后续参考源码不是精确r69重建身份 |

**先通过第一阶段，再对同一冻结镜像全部通过U1～U6。不能拼接不同版本的局部结果。当前第二阶段未进入验收。** 本轮11项候选工具回归不算原厂更新器/认证/刷入验收。

### 第三阶段：真机

前两阶段全部通过，另外关闭物理供电、存储、cache/DMA、硬件时序和独立可恢复路径的关键缺口，才有讨论受控真机验证的前提。当前没有相机/USB/PTP/物理卡/磁盘访问或刷机。有限模拟器样本不能证明所有未来物理状态绝无风险，**用户要求的“刷入和运行一定不出问题”仍未满足/未验证**；不能自行改成“风险较低”后放行。

## 3. 原厂字节合同及可见性

输入是已解包裸ARM/Thumb成员，无PE/ELF传统导入表。E-imports等价锚点为当前原BL、literal、配置load/TCB store、名称复制、初始CPSR/PC与返回序列；静态合同（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-create-r9/contract-final.json`）保留完整原函数指令及输入身份。没有因无导入表而断言无文件或网络能力。主从各自以指令锚点定位，不套另一机型地址或任务数。

| 检查点 | master | slave |
|---|---|---|
| ARM创建入口 | `0x1010A268` | `0x1003BC3C` |
| 初始帧构造完成、原LDR句柄之前 | `0x1010A6D4` | `0x1003C0A8` |
| 名称有界复制调用前 | `0x1010A5AC` | `0x1003BF80` |

合同（本地证据，未分发：`<WORKSPACE>/fenestra/z62/task_create_contract.py`）与观察器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_task_create.py`）核对：

1. 入口r0指向56字节配置，记录原SP/LR/r4～r11；真实CPU取停止包`thread:`，原镜像头识别主从。读取边界仅是地址防护，不是内存所有权证明。
2. 配置+0/+4/+8进入TCB+C/+10/+14；这些是原字关系，不把首字、flags或优先级扩展命名成完整公开ABI。
3. 配置+30最多8字节，经原有界复制函数写TCB+CC。遇NUL补零，满8字节不强加NUL；不证明名称唯一或业务名称完整。
4. 9个保存寄存器和20字节局部栈共56字节，构造点SP应为入口SP−56；r5仍指配置，r4是有界216字节控制块。
5. 初始帧为原栈顶TCB+B8−76，TCB+BC及现场r0应指向该帧。原flags的bits8..9产生模式，帧+40为原选择的SVC/System及入口Thumb位，+48为清bit0入口，+30保存原模式字；非SVC时还核对+34与TCB+B4。未赋值帧字不猜参数或状态。
6. 构造点隔离执行原`LDR r4,[r4,#8]`，只允许r4按原字装入、PC+4；入口隔离执行原PUSH，只允许SP−36、PC+4。返回桩单步仅核对真实停核/原ROM，不声称已逐条解释任意返回后指令。
7. 原返回按角色、CPU、恢复SP和原LR唯一配对；核对ARM/Thumb返回ISA、r4～r11/SP、原r0等于构造时及返回时TCB+8。共享桩不匹配停点保留全部现场，不强配。

TCB+8因本轮证据可称**本次自然调用的原厂返回句柄字**，不能据此断言跨删除/重建稳定任务ID、全局唯一或完整任务生命周期。构造/返回成功也不证明该任务入口已被调度执行、完成业务初始化或正常退出。没有追踪所有注册计数、删除/复用、完整等待链表或硬件完成。

## 4. 实跑、失败与实际修复

| 记录 | PID | 主/从配对调用 | 断点事件/未匹配桩 | 带断点末主模型秒 | 最终主模型秒 | 宿主秒 | 结论 |
|---|---:|---|---|---:|---:|---:|---|
| run-3（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-create-r9/run-3-final.json`） | 54868 | 37/53 | 563/293 | 0.004706 | 2.546566 | 32.296 | 采样目标64，排空后90调用，正式重放通过 |
| run-5（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-create-r9/run-5-repeat.json`） | 55968 | 189/67 | 829/61 | 0.029718 | 3.819426 | 49.031 | 目标256、排空256调用，正式重放通过 |
| run-4诊断（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-create-r9/run-4-extended.json`） | 35352 | 275/92 | 1421/320 | 1.266643 | 3.764941 | 51.563 | 目标384未达，quiet-bound，不晋升正式采样通过 |

- 正式两跑346次均为成功原返回，错误返回0；不是全部创建总数或失败路径验收。控制块地址和返回字在各跑各侧样本内各不重复，不外推全局/全生命周期唯一。
- 正式样本原配置flags只见`0x1/0x41/0x20001`，不足以证明全部flags、权限或跨核同步行为。8次ARM入口、338次Thumb入口只是配置/帧类别，**没有在本轮跟踪这些新任务入口执行**。
- 342次名称为空、4次为`InitTask`，不是业务任务名单。扫描旧28字节可读名称表的298/99候选仍不能当任务总数或直接与TCB配对。
- ticks按既有48MHz口径折算模型秒，不是物理计时精度验收。撤断点后达到目标模型秒，不是全过程创建/删除/等待跟踪；断点显著扰动时序。
- 最终四核采样处于原调度空闲，current/ready零，所读故障零；不是完整启动/无Error证明，r9没有监控堆释放。

| 发现的问题 | 实际处理与复测 | 未解决部分 |
|---|---|---|
| 新合同名称复制偏移误写`+388` | 原主从字节确认`+344`；静态测试由失败变通过，未改固件 | 只核对8字节内核字段，不恢复全部业务名称 |
| 初版读模型时钟后选中CPU01，导致从侧配置/TCB被从错误引擎读取成全零 | `selected_ticks`在finally恢复原停核；新增回归；保留run-1失败（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-create-r9/run-1-diagnostic.json`）和初版源码副本；新版双正式运行核对通过 | 没有因此修改原厂指令、RAM或返回值 |
| 共享服务返回桩在不同调用栈命中，初版错误要求每次都必须匹配创建返回 | 按角色/CPU/SP/LR配对；无匹配只保留unmatched-return，核验器重算无匹配条件；保留run-2失败（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-create-r9/run-2-final.json`）及clock-fixed源码副本 | 不把未匹配停点命名成具体业务API或伪造返回 |
| 新测试插入位置和核验器两处行编辑位置错误 | 差异检查发现后重读纠正，AST/测试再通过；错误版本未用于正式运行 | 属工具编辑问题，不称原厂缺陷修复 |
| 扩展目标384在367调用后静默 | 保留quiet诊断、不降低该次标准；另跑目标256的独立新记录通过 | quiet不证明全任务注册结束或完整启动 |
| 精确r69源码、默认完成逻辑、完整Fenestra端口仍缺 | 固定原EXE、重核SHA；记录两侧默认gate/transfer-reset/sequencer completion仍true | 未恢复精确源码、未关闭物理近似，完整移植/硬件等待根因没有修复 |

新版TOOL为`fenestra-z62-task-create/0.1.2`。两次失败和quiet记录均保留；`completed`只表示观察器收尾完成，不把它当本轮采样或总体目标通过。所有五进程QMP quit有应答并真实退出0，仅是自有宿主清理。

## 5. 复核、身份与复现

最终核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-create-r9/verification-final.json`）绑定原输入、固定r69和观察器/依赖源码，重算每次入口/构造/返回、原ROM/CPU/MMU/cache/故障、原PUSH/LDR寄存器效果、精确命令、读窗、断点周期、时钟、QMP/真实退出及摘要。两输出逐字节一致，23类错误记录拒绝。它不能证明能检测任意一致伪造，工具负例也不是原厂错误模块、错误创建/释放或断电验收。

当前环境（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-create-r9/environment-current.json`）逐一重核原包/主从/控制器和r69SHA；Fenestra固定b199dcdf且上游仍仅原两加载器文件修改，参考4f43899工作树干净，精确r69 source不存在。未重编或替换模型。旧r8重核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-create-r9/wait-store-r8-reverified.json`）通过；共享README追加不冒充旧摘要。

清理记录（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-create-r9/cleanup-final.json`）于15:35:10（+08:00）用Win32_Process检查无QEMU、Q:不存在；五运行均退出0。无活跃委派或运行等待，无相机、USB/PTP、物理卡/磁盘或刷机。无Fenestra候选、控制器、合成参数或虚拟卡装入本轮QEMU；GDB/QMP仅127.0.0.1，`-nic none`。原boot-image及四核复位PC初始化不是介质读取、镜像认证或刷写。保留无关用户改动，不提交、推送或发布固件/密钥；原Fenestra CC BY-NC-SA 4.0及商业摄影例外、署名保留。

只读复现要求当前原输入、固定runtime及绑定源码存在，输出名必须不存在；重复时选新名称。以下命令已用现有正式输出名执行，本例选择新的输出名：

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR"
export PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
python -X utf8 -B fenestra/z62/verify_task_create.py \
  --run analysis/fenestra-z62-task-create-r9/run-3-final.json \
  --run analysis/fenestra-z62-task-create-r9/run-5-repeat.json \
  --output analysis/fenestra-z62-task-create-r9/verification-recheck.json
```

动态观察器要求先确认Q:未占用，仅以samefile核对的本工程别名运行并finally移除；参数范围8～512目标调用、1～6目标模型秒、30～300宿主秒，另有有限事件和并发排空界限。此要求不授予物理设备访问。105专项中11项为r9新增，候选11项仍只验证离线工具。

## 6. Evidence → Finding → Path 与整体目标审计

| Evidence | source_ref / content_hash | repro_command |
|---|---|---|
| E-imports/E-static | contract-final及正式run内contract；原裸ARM/Thumb函数/输入身份，SHA见交付清单 | task_create_contract.collect与第5节重放 |
| E-runtime | run-3/run-5及qemu/host/console日志，SHA见verification-final | 第5节verify_task_create |
| E-diagnostic | run-1/run-2错误现场、源码副本、run-4 quiet记录、红测与首次失败日志 | 读取对应原记录，不将其晋升通过 |
| E-tests | tests-full/tests-candidate日志、23类记录变造 | 第5节unittest/重放 |
| E-boundary | PORT、scope、environment-current、cleanup-final及最终文件检查 | 当前文件、SHA/Win32只读检查 |

| Finding | severity / evidence_ids | confidence / location / status |
|---|---|---|
| F1 原厂自然构造与返回局部关系成立 | n/a_re；E-static/E-runtime | high；主1010A268/从1003BC3C；346调用，非完整ABI |
| F2 内核名称不足以识别业务任务 | n/a_re；E-runtime | high；TCB+CC只有空名/InitTask；完整身份/唯一性/生命周期未证 |
| F3 共享返回桩不能单凭PC配对 | n/a_re；E-diagnostic/E-runtime/E-tests | high；无匹配354停点单独保留；修复工具配对，不改固件 |
| F4 完整移植、刷入及绝对安全未满足 | n/a_re；E-boundary | high；PORT仍loader-only；Q/U门槛未通过、真机关闭 |

P1，path_type=callflow：原厂自然调用 → 原入口配置快照 → 原PUSH隔离步 → 原配置/名称/栈分配及帧构造自然执行 → 构造点TCB/帧快照 → 原LDR句柄隔离步 → 同次原返回核对 → 未匹配共享桩另记 → 排空撤断点 → 目标模型窗 → 自有宿主关闭；挂E-static/E-runtime/F1/F3。不延伸成任务业务执行、完整启动/关机或硬件成功。

时间线（+08:00）：15:28初跑暴露选核问题，之后修复并保留第二次共享返回桩失败；15:30:41启动正式run-3，15:31:15关闭并启动run-4，15:32:08关闭；15:32:49～15:33:40独立run-5；随后105+11回归、双重重放、23类负例与r8重核验；15:35:10 Win32清理检查。宿主具体起止见runs-host-3/4，不当模型时长。

| 原始要求 | 当前审计 |
|---|---|
| 完成原Fenestra原厂移植并保留路线 | 未验证：仍loader-only，缺完整原厂任务/同步/卡文件/SDK/模块管理/菜单及启动/关机候选 |
| 先用自研z62qemu验证完整方案 | 未验证：346自然创建关系不是Q1～Q6及原版/停用/启用/合法错误模块/完整生命周期矩阵 |
| 再验证冻结镜像及完整刷入流程 | 未验证且未进入验收：没有可冻结完整候选，U1～U6缺证 |
| 前两阶段全通过才进入真机 | 本轮遵守：仅本地离线，不接相机或刷机，未越阶段 |
| 真机刷入与运行一定不出问题 | 未满足/未验证，有限模型样本无法给绝对保证 |
| 各阶段项目、标准、发现的问题、修复结果和转换条件 | 第2、4节逐项列明，未知/未执行不标通过 |

后续仍需恢复可追溯开发模型来源、从原厂注册/业务封装和计数恢复身份关系，独立补删除复用/失败/flags/同步/所有权、完整等待登记链表/返回通知与硬件完成源；r9不把名称空白或顺序当身份。再补可保留代码数据/cache发布、卡文件/SDK/菜单/启动关机完整端口和Q矩阵。Q门槛全部通过后才进入同一冻结镜像U项验收，前两阶段及独立物理恢复/安全条件未关闭前不上真机。
