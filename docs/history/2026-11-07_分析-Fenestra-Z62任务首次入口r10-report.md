# Fenestra Z62 任务首次入口 r10：原启动帧到真实入口

> 2026-11-07；原Fenestra＋自研Z62-QEMU；flavor=null；severity=n/a_re。
> **完整移植未完成，第一阶段未放行，第二阶段未进入验收，真机关闭；无可刷Fenestra包，绝对零风险未满足。**

## 1. 结果和范围

r9只观察创建/构造/原返回，本轮新增独立启动帧到首次入口合同、观察器、重放器和10项测试，r1～r9保持不变。两个原C1.70/固定r69进程各配对52个原厂SVC任务启动帧与实际首次入口，共104个。current槽、TCB原字、入口PC、ARM/Thumb、SP及r0/r1与发布前帧关系成立，并核对首条原指令的寄存器效果。**不是104个Fenestra任务、业务初始化完成、完整任务ABI或生命周期通过。**

正式样本含8个ARM入口和96个Thumb共享封装入口；78次启动参数非零，100次扩展字非零。共享封装先执行`LDR r1,[r1,#4]`；仅得到装载后的候选指针及寄存器效果，没有单独读取该字段或观察后续业务回调执行，不能用共享入口代替业务函数身份/完成证明。

115项专项、11项候选工具回归通过，无跳过。新版核验器两次重放逐字节一致，20类定向错误记录拒绝，r9旧证据重新重放通过。扩展目标128的运行失败于有限准备数量上限，192个已跟踪准备中仅119个到达入口、73个尚未配对；该记录不晋升通过，也不据此认定死锁。范围见[r10 scope](../../analysis/fenestra-z62-task-entry-r10/scope.md)。

## 2. 三阶段验证及转换条件

完整既有标准仍以[r9逐项Q1～Q6/U1～U6门槛](2026-11-07_分析-Fenestra-Z62任务创建r9-report.md#L14)为准，本轮没有删减或降低要求。

### 第一阶段：完整移植方案在自研z62qemu运行

| 项目 | 通过标准 | 本轮后状态 |
|---|---|---|
| Q1 ARM32模块/SDK | 格式/重定位/入口和完整copied-service SDK真实执行，合法/错误模块正确处理 | r1仅合成loader和legacy v1日志，完整原厂SDK未通过 |
| Q2 原厂启动/正常关机 | 主从ISA/栈/MMU/初始化、完整启动、正常关机和再启动均通过 | 仍只有局部早期/调度证据，首次任务入口不是完整相机启动 |
| Q3 内存/任务/同步生命周期 | 分配、自然释放、合并复用、flags、失败耗尽、创建启动/异常/删除、所有权/同步与完整生命周期通过 | r10只补104个SVC首次入口；启动API返回、System模式、删除/复用/完整ABI未验；73待配对诊断未解决 |
| Q4 空间/加载/cache | 可保留代码数据空间、所有权、实际加载容量、MMU/cache/DMA发布和回收明确并实跑 | 仍缺；不能把空白、清零、可执行映射当可占用插件空间 |
| Q5 完整原厂Fenestra服务 | 原厂任务/同步/卡文件、copied-service SDK、模块管理/菜单及启动关机集成真实运行 | 无完整原厂候选，不能用原厂任务观测冒充Fenestra集成 |
| Q6 对照/压力/模型可信度 | 同模型同配置原版/候选停用/启用、合法/错误模块、启停/异常/压力/完整生命周期全部通过，关键失败和模型来源/覆盖缺口关闭 | 未完成；精确r69源码仍缺，默认完成逻辑及硬件近似保留 |

**Q1～Q6全部通过、模型关键缺口关闭、完整候选可复现并冻结唯一SHA后，才进入第二阶段。当前不满足。** 不补PC/寄存器/RAM/ready/返回值/事件、不强制completion，不关闭身份/长度/机型检查填覆盖。

### 第二阶段：同一冻结镜像与真实刷入流程

| 项目 | 必须达到的标准 | 当前状态 |
|---|---|---|
| U1 资格与边界 | 唯一SHA、型号版本/主从控制器资格、长度地址正确；互换、截断、越界拒绝 | 无完整候选，未进入验收 |
| U2 原厂认证 | 真实B8/K8和原厂更新器合法接受、篡改拒绝 | 未验证；CRC/seed/别机型结果不替代 |
| U3 介质早期加载 | 实际介质到原厂加载容量、入口、地址、主从发布顺序正确 | 未验证；预装boot-image/复位PC不是刷入或介质加载 |
| U4 写入持久化 | 实际写入范围、NOR/校准保留、读回及重启持久化、冲突处理正确 | 未验证；合成参数/空白卡不等于原厂备份 |
| U5 中断断电恢复 | 校验/擦除/写入/提交/重启各阶段中断、超时、断电恢复/回滚均通过 | 未验证；QMP quit/退出0不算恢复 |
| U6 可追溯重建 | 同一候选源码、模型、工具链、依赖、许可证及镜像可复现，关键失败解释完成 | 未通过；固定EXE/后续参考源码不等于精确r69来源 |

**先通过第一阶段，再对同一冻结镜像通过全部U项；不能拼接不同版本的局部证据。第二阶段本轮未进入验收。** 11项离线候选工具测试不是原厂更新器/刷机验证。

### 第三阶段：真机

前两阶段全部通过，并独立关闭物理供电、存储、cache/DMA、硬件时序和可恢复路径缺口，才有讨论受控真机验证的前提。当前未连接相机/USB/PTP，未操作物理卡/磁盘或刷机。有限QEMU样本不能证明所有未来物理状态绝无风险，用户“刷入和运行一定不出问题”的要求仍未满足/未验证，不自行改成“降低风险”后放行。

## 3. 原厂合同和实际执行边界

原始成员是裸ARM/Thumb，无PE/ELF传统导入表。E-imports等价证据为原启动r1→r11、TCB/帧写入、调度发布调用及原恢复路径，见静态合同（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-entry-r10/contract-final.json`）。不能由无传统导入表否定文件或网络能力。

| 项目 | master | slave |
|---|---|---|
| 原ARM启动候选入口 | `0x1010A91C` | `0x1003C2F0` |
| 帧准备后、发布调用前观察点 | `0x1010AAC4` | `0x1003C498` |
| 正式样本ARM入口 | `0x10103BC8`、`0x10108E20` | `0x10035678`、`0x1003A7F4` |
| 正式样本Thumb共享入口 | `0x103DEBBC` | `0x1006CB80` |

合同工具（本地证据，未分发：`<WORKSPACE>/fenestra/z62/task_entry_contract.py`）及观察器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_task_entry.py`）执行：

1. 原发布前r4指TCB，r0等于TCB+BC等于TCB+B8−76；TCB216字节、初始帧76字节只读有界原堆。
2. 帧+0等于r11，帧+4等于TCB+C及现场r1；原码显示r11源于启动参数r1。**本轮没有在原启动API入口/返回同时采样，不能据此声称完整启动调用ABI或返回状态动态验收。**
3. 只接受原SVC初始帧：模式来自TCB+10的bits8..9，入口TCB+14 bit0对应Thumb；帧+40/+48对应CPSR/PC。System模式未通过。
4. 根据原帧在入口装执行断点，由原厂自然发布/调度，不注入启动调用。真实CPU取停机包thread而非陈旧qC；读模型ticks后恢复选中引擎。
5. 入口必须同引擎current局部槽指向目标TCB，原句柄字/入口/扩展字相符，PC/ISA/SP和r0/r1等于原帧。CPU不是任务ID，不要求启动核和运行核相同；地址/句柄不推广为跨生命周期稳定身份。
6. 每个停点撤断点后用vCont指定核隔离执行原指令，再恢复断点。发布点MOV仅r0←r4、PC+4；ARM首次PUSH按原寄存器列表核对SP/PC、其余通用寄存器不变；Thumb首次LDR仅r1和PC按指令形式变化、装入值在原成员地址范围。
7. **没有单独读取旧r1+4内存，也没有比较它和装入值；Thumb检查仅证明保存记录中的寄存器效果/地址候选，不是独立数据值证明，更未执行后续业务回调链。**

## 4. 实跑、问题与实际修复

| 记录 | PID | 主/从已配对入口 | 事件/未匹配 | 带断点末主模型秒 | 最终主模型秒 | 宿主秒 | 结论 |
|---|---:|---|---|---:|---:|---:|---|
| run-2（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-entry-r10/run-2-final.json`） | 22112 | 40/12 | 104/0 | 0.019204 | 2.514888 | 30.812 | 目标32，排空52，通过局部重放 |
| run-4（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-entry-r10/run-4-repeat.json`） | 53444 | 40/12 | 104/0 | 0.012904 | 3.777107 | 45.750 | 目标32，排空52，通过局部重放 |

两次正式窗口每侧各2个ARM入口，其余为共享Thumb入口。入口开始不等于任务退出/完整业务成功；TCB/句柄/样本数不是任务总数。撤断点后的模型目标窗口不是全过程跟踪，ticks按既有48MHz口径折算、不作物理计时精度验收。最终四核idle/current-ready零、所读故障零，只是末次采样；r10不监控堆释放，不证明完整相机启动/无Error。

| 问题 | 处理和修复结果 | 仍未解决 |
|---|---|---|
| 初版错误把发布前r5当原输入句柄 | run-1失败（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-entry-r10/run-1-final.json`）表明TCB+8=01000001而r5=0；原码在校验后重用r5。合同0.1.1改按此阶段语义核对，新增回归，双正式原厂运行通过；初版源码保留 | 原启动API入口/返回、完整错误语义未验证；没有改原厂状态或返回值 |
| 扩展目标128触及准备数量上限 | run-3诊断（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-entry-r10/run-3-repeat.json`）跟踪192准备/119入口/73未配对，约0.024145模型秒；保留失败和终止点原现场，不扩大上限、不补调度。另做相同小窗口独立复跑通过 | 73项是否随后执行、业务完成/完整调度覆盖未验，不能断言死锁或全部任务已启动。终止点另有原帧现场未纳入pair，不丢弃/晋升 |
| 只命中入口不足以说明单步效果 | 核验器0.1.1增加实际ARM PUSH/Thumb LDR寄存器效果检查，新增红/绿测试并重放原记录通过 | Thumb字段没有独立内存读值，后续业务回调未跟踪 |
| 精确模型/完整端口缺口 | 原C1.70、r69、旧源码证据不变；实验开关false，默认gate/transfer-reset/sequencer completion仍true | 精确r69源码未恢复，默认模型逻辑/物理近似未关闭，完整Fenestra端口和原厂硬件等待根因没有修复 |

失败/诊断和0.1.0旧核验输出保留，正式结论以`verification-step-final.json`、核验器0.1.1为准。四自有进程均QMP quit有应答、真实退出0；这只是宿主清理，不是相机正常关机/恢复。

## 5. 身份、复现与清理

加强核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-entry-r10/verification-step-final.json`）两次逐字节一致，SHA256=`75b01e2158211c67e0af0557f0c1a9555bdba59c76a5f37612fcfac4f5e91d65`；绑定原输入/固定r69/来源SHA、CPU/MMU/cache/故障、精确命令/读窗/断点过程、帧/入口/首步、时钟/QMP/退出，20类错误记录拒绝。工具负例不等于原厂错误模块/错误调用/断电验收，也不能证明能检测任意一致伪造。

环境（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-entry-r10/environment-current.json`）重新核对原整包/主从/控制器及r69 SHA不变；Fenestra仍b199dcdf、上游仅原两个加载器文件修改，参考4f43899工作树干净，精确r69 source不存在。r9重核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-entry-r10/create-r9-reverified.json`）通过。当前PORT（本地证据，未分发：`<WORKSPACE>/fenestra/z62/PORT.json`）仍loader-only，firmware_integrated/flash_safety_verified=false。原许可证CC BY-NC-SA 4.0及商业摄影例外/署名保留，不提交、推送或发布固件/密钥。

清理（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-entry-r10/cleanup-final.json`）在15:53:15（+08:00）Win32检查无QEMU/Q:，无活跃操作/委派。无相机、USB/PTP、物理卡/磁盘或刷机；本轮只预装原boot-image并初始化复位PC，无控制器/卡/合成参数/Fenestra代码。-nic none、GDB/QMP仅127.0.0.1，预装与宿主退出都不是刷入验证。

只读复现要求本地原输入、固定runtime及绑定源码存在，输出名必须不存在；下例使用新的输出名，重复时再换名。命令以实际正式输出名运行过，未启动真机或刷机：

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR"
export PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
python -X utf8 -B fenestra/z62/verify_task_entry.py \
  --run analysis/fenestra-z62-task-entry-r10/run-2-final.json \
  --run analysis/fenestra-z62-task-entry-r10/run-4-repeat.json \
  --output analysis/fenestra-z62-task-entry-r10/verification-recheck.json
```

动态参数为8～256目标入口、1～6模型秒、30～300宿主秒，另有明确有限准备/事件界限；Q:须未占用、自建samefile本工程别名并finally移除，不授权物理设备访问。115专项包含r10新增10项；候选11项仅为离线工具。

## 6. Evidence → Finding → Path 与全目标审计

| Evidence | source_ref / content_hash | repro_command |
|---|---|---|
| E-imports/E-static | contract-final和run内原指令/输入/SHA | task_entry_contract.collect及第5节重放 |
| E-runtime | run-2 SHA 2ccb04d3f7dc8dfa1a4b4a35ac18da193798f431bcb52884ee224a97e230e558；run-4 SHA dba721b55da1a95c9e6067eeb0966244f6e3bdd96dceaede8f4503c1941a5025 | 第5节verify_task_entry |
| E-diagnostic | run-1/run-3、初版源码、红测/失败及host日志 | 读取原记录；不晋升通过 |
| E-tests | tests-full-final/tests-candidate-final、verification-step-final | 第5节unittest/重放 |
| E-boundary | scope、PORT、environment-current、cleanup-final | 当前文件/命令/SHA/Win32只读检查 |

| Finding | severity / evidence_ids | confidence / location / status |
|---|---|---|
| F1 原SVC帧到首次入口参数关系成立 | n/a_re；E-static/E-runtime | high；104样本，局部通过，非业务完成或完整ABI |
| F2 共享入口首条LDR提供后续回调线索 | n/a_re；E-runtime | high（仅寄存器效果）；主103DEBBC/从1006CB80；字段数据值及回调执行仍未验 |
| F3 扩展观察未排空不能算启动通过 | n/a_re；E-diagnostic | high；73跟踪项尚未配对，保留未解决，不推断死锁 |
| F4 整体移植/刷入/绝对安全未满足 | n/a_re；E-boundary | high；PORT loader-only，阶段未放行，真机关闭 |

P1，path_type=callflow：原启动准备r0/r1帧 → 发布前只读快照/原MOV隔离步 → 原厂自然发布与调度 → 入口current/TCB/PC/ISA/SP/参数核对 → 首原指令隔离步与寄存器效果核验 → 排空撤断点 → 后续模型目标窗 → 自有宿主关闭；挂E-static/E-runtime/F1/F2，不扩展成业务回调、启动API返回或完整生命周期。

时间线（+08:00）：初跑暴露r5重用假设并保留；15:49:15～15:49:47正式run-2，随后扩展run-3触发上限；15:51:02～15:51:49独立run-4；其后115+11测试、20负例、双次加强重放及r9重核验；15:53:15清理检查。宿主起止不当模型时间。

| 原始要求 | 当前结论 |
|---|---|
| 完成原Fenestra原厂移植并保持路线 | 未验证：仍loader-only，没有完整原厂任务/同步/卡文件/SDK/模块管理/菜单及启动关机候选 |
| 先自研QEMU验证完整方案 | 未验证：原任务104首次入口不替代Q1～Q6、原版/停用/启用/合法错误模块/完整生命周期矩阵 |
| 再验证唯一镜像与完整刷入 | 未验证且未进入验收：U1～U6缺证，无完整候选可冻结 |
| 前两阶段全通过才上真机 | 本轮遵守：仅离线文件/QEMU，未接相机或刷机 |
| 真机刷入和运行一定不出问题 | 未满足/未验证；有限局部模拟器证据不能提供绝对保证 |
| 每阶段项目/标准/问题修复/转换条件 | 第2、4节逐项说明，失败和未执行不标通过 |

下一项需从共享入口的扩展描述符及原业务封装恢复业务回调/名称与注册计数关系，独立观察原启动返回、任务退出/删除复用、失败/flags/同步/所有权、完整等待链表/通知和硬件完成源。同时仍需精确可开发模型来源、可保留代码数据/cache发布、完整原厂Fenestra服务/候选及Q矩阵。所有第一阶段项目通过后才冻结镜像进入U项，前两阶段与独立物理恢复/安全条件未满足前不上真机。
