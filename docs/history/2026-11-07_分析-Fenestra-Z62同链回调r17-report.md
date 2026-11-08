# Fenestra / Z62 同链创建—启动—回调首指令 r17

> 2026-11-07 · 本地离线 · flavor=null · severity=n/a_re
>
> **整体移植未完成：第一阶段未放行，第二阶段未进入验收，真机关闭。不能保证真机刷入与运行“一定不出问题”。** 本报告的19条局部链不是完整Fenestra候选、可刷包、完整业务生命周期或物理安全认证。

## 1. 结果摘要与范围

本轮在原Z6II C1.70主从、可追溯自研r13 QEMU、无卡/参数/控制器/Fenestra候选条件下，用两个独立进程实际补齐了**同次创建对象→同TCB自然index3启动→原POP返回/首次共享LDR→原BX→目标首指令**的联合观察。原POP返回和任务首次执行的相对顺序分别记录，不预设同步。

两跑合计128次创建、27次启动、510个事件内，**19条同进程联合链通过严格重放：主侧5条、从侧14条**。其中15次PUSH实际栈写入逐字核对，4次首指令为ADD.W；19个字段目标均Thumb，无实际ARM字段目标样本。新增13项工具测试后，214项Fenestra专项＋11项候选工具＋38项显式夹具原断言全部通过，无跳过；45类错误记录被拒绝。工具负例不是原厂错误模块、失败调用、断电或刷入故障覆盖。

[范围与授权边界](../../analysis/fenestra-z62-task-chain-r17/scope.md)：只读有界RSP、硬件执行断点、原指令隔离单步、暂停/继续；`-nic none`、仅127.0.0.1。未补写客体代码/PC/RAM/寄存器/返回值/ready，未注入调用或成功事件。原boot-image预装及loader复位PC已标记，不能替代实际介质加载、认证、擦写或持久化。没有相机、USB/PTP、物理介质、刷机、提交、推送或发布固件/密钥。

**限制**：跟踪只到主模型0.0041405/0.0046264167秒；撤断点后的2.5677900417/3.8296424375秒不是全过程跟踪。默认gate/sequencer/transfer-reset完成逻辑仍开，其他成功假设和原菜单循环35/3F仍未关闭；idle、故障零、QMP退出和退出0不等于完整启动、正常关机或恢复。

## 2. 三阶段验证、标准与转换条件

### 第一阶段：完整原Fenestra在自研z62qemu验证

|项|必须全部满足的通过标准|当前问题与修复结果|
|---|---|---|
|Q1 ARM32模块与完整SDK|原厂环境内模块格式/重定位/入口/copied-service SDK，合法及错误模块实际执行|仍experimental-loader-only、legacy v1日志；本轮观察原厂任务，未执行完整Fenestra候选。未通过|
|Q2完整启动与正常关机|主从ISA/栈/MMU/初始化、完整启动、正常关机和再启动均通过|仅早期局部任务链；QMP quit不是相机关机。未通过|
|Q3内存/任务/同步生命周期|创建—启动—业务返回/完成、System/flags/失败/耗尽/退出删除复用、自然堆释放合并复用与同步所有权|新补19条同进程BX/首指令链、实际STR与PUSH核验；回调返回/业务完成/完整ABI仍缺，r10的73待配对未解释。未通过|
|Q4空间/加载/cache-DMA|可保留代码数据空间及所有权、实际早加载容量、MMU/cache-DMA发布回收实跑|可读/自然分配/映射不证所有权；完整合同未证。未通过|
|Q5完整原厂集成|原任务/同步/卡文件服务、完整SDK、模块管理菜单、启动及正常关机集成候选|当前PORT（本地证据，未分发：`<WORKSPACE>/fenestra/z62/PORT.json`）仍firmware_integrated=false，无完整候选。未通过|
|Q6模型可信度与完整矩阵|可追溯模型；同模型同配置原版/候选停用/启用、合法错误模块、启停异常压力/完整生命周期；关键模型失败关闭|r13来源可追溯，但真实事务/完成源、默认完成假设及35/3F缺口仍在；无完整候选矩阵。未通过|

**Q1～Q6全部通过，关键问题解释/修复并复测、完整候选可重建且冻结唯一SHA后，才能进入第二阶段。** 测试数或多个不同进程局部结果不能拼成完整端口。本轮没有降低此门槛。

### 第二阶段：同一冻结镜像和刷入流程

|项|必须通过的验证与标准|当前状态|
|---|---|---|
|U1唯一镜像与资格/边界|唯一SHA、型号版本和主从/控制器资格、长度地址；互换/截断/越界拒绝|无完整冻结候选，未进入验收|
|U2真实原厂认证|真实B8/K8，原更新器接受合法镜像并拒绝篡改|未验证；CRC、seed、关系式或其他机型不替代|
|U3实际介质早加载|实际容量、加载边界、入口及主从发布顺序正确|未验证；boot-image预装不替代|
|U4擦写及持久化|实际写入边界、NOR/校准保留、读回重启持久化、冲突处理|未验证；合成参数/空白虚拟卡不是实机备份|
|U5中断/断电恢复|校验、擦除、写入、提交、重启各处中断/超时/断电恢复或回滚|未验证；宿主QMP退出/进程清理不替代|
|U6完整可重建|同一候选镜像/源码/模型/工具链/依赖/许可证可追溯重建，关键失败关闭|未进行固件镜像重建验收；一次模型构建不是两次位一致重建|

先放行第一阶段，再对同一冻结镜像通过U1～U6；本轮11项候选工具测试不能当作刷入流程通过。

### 第三阶段：真机门槛

前两阶段全部通过，且独立关闭物理恢复、供电/存储、cache-DMA与硬件时序缺口后，才具备讨论受控真机验证的前提。当前不具备这些条件。有限模拟器覆盖不能证明所有未来物理状态绝无故障，用户的绝对安全要求仍未满足/未验证；不将其改成“降低风险后即可放行”。

## 3. 新合同及证据链

### 静态锚点与导入等价证据

裸ARM/Thumb固件无传统PE导入表；E-imports以原wrapper/index1创建SVC、独立0A表/桩、index3/PUSH/POP/帧及共享LDR/BX、字段目标原字节为等价锚点。没有据此宣称完整业务导入图。合同包含主从成员固定SHA/长度及原局部指令；不涉及新认证或密钥恢复。

|锚点|master|slave|
|---|---|---|
|创建封装|103DEBC6|1006CB8A|
|原构造LDR|1010A6D4|1003C0A8|
|初始化后ADD SP（非外层返回）|103DEC64|1006CC28|
|自然index3输入|1010A91C|1003C2F0|
|原发布MOV|1010AAC4|1003C498|
|成功POP|1010AB88|1003C55C|
|共享LDR/BX，字节49680847|103DEBBC/103DEBBE|1006CB80/1006CB82|
|原对象+8 STR，字节ac60|103DEC90|1006CC54|

使用本地Python3.12/Capstone5.0.7与既有只读协议。tool-index.md、precedent-reverse.md仍缺失，本轮已实际检查，不冒称已读或完成IDA survey；没有安装/启动IDA或外部服务。报告采用已读RE模板及Base规范；ops参考历史缺失不冒称已读，E/F/P字段按现有模板落实。普通固件分析flavor=null。

### 同次关联与实际指令核验

1. 复用r16已冻结纯合同：输入配置、未初始化+28原栈字、原PUSH/配置/TCB/帧、对象初始化及自然index3/POP/首次入口。调用栈native-RAM、TCB/帧原heap界；可读不证所有权。
2. 只按同role、同句柄/TCB/对象及初始化先于输入唯一配对。歧义/复用拒绝；CPU/TCB/标签不当跨进程稳定任务身份。
3. 对象+8仍必须由实际捕获的原STR前后核验更新快照，未知变化拒绝。本轮6次：5次4→16、第二组主侧1次20→8；不跨进程追认旧r16失败中的未跟踪写入。
4. 共享入口LDR前，独立读取r1起8字节，与本次创建对象前8字节及原输入回调交叉核；不是从LDR结果反推字段。
5. 原LDR隔离执行后核全部寄存器；再用`vCont;s:<CPU>`执行原BX，依据停止包thread核CPU，核PC/ISA/参数。时钟读取后恢复原核，不信陈旧qC。
6. 独立读目标原ROM16字节、current两槽和系统寄存器；核同TCB不变。执行原首指令后核全部寄存器/系统；PUSH再读实际栈内存并逐字核预期。未知首指令拒绝。
7. 核验器独立重建事件/对象/快照/创建/启动/回调，核精确读地址顺序、断点与两步生命周期、寄存器次数、CPU/ROM/时钟/QMP/日志和自有清理。寄存器g=2×事件+2×回调+4，qC=2×事件+2×回调；禁止软件断点、写命令、带地址继续和传统s。

代码：合同（本地证据，未分发：`<WORKSPACE>/fenestra/z62/task_chain_contract.py`）、只读观测器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_task_chain.py`）、严格核验器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/verify_task_chain.py`）。TOOL0.1.0；创建/启动各128、事件2048、quiet15宿主秒、wall240，minimum8未扩界。

## 4. 实跑、问题与修复结果

|记录|PID|创建/启动/事件|同链（主/从）|回调首指令及实际PUSH|跟踪末主模型秒/撤断点后秒|
|---|---:|---|---|---|---|
|run-1.json|25708|53/13/219|9（2/7）|PUSH3/PUSH.W4/ADD.W2；7次栈写入|0.0041405 / 2.5677900417|
|run-2-repeat.json|49592|75/14/291|10（3/7）|PUSH4/PUSH.W4/ADD.W2；8次栈写入|0.0046264167 / 3.8296424375|

两跑均sample-bound-drained，活动创建/启动pending为空；每跑未匹配构造桩6、未匹配首次入口0。**创建未在窗口见启动44/65，共109；启动未见封装创建各4，共8**，明确另列，不解释为死锁/任务总数或完成生命周期。27次启动均自然返回0；10次任务首次入口先于API返回，17次API先返回。

例：两跑各seq31从侧，同次对象C167B7D8独立8字节为`0400000183360510`，字段目标10053683；原BX到Thumb PC10053682，原PUSH.W SP C3EFD3A0→C3EFD378，40字节实际栈读取一致。此后业务返回/完成未跟踪；示例中的零LR不被擅自改写或推导可返回ABI。

**本轮解决的缺口**：r16联合链止于共享LDR，不能与r11旧进程拼成同链回调证据；新增独立r17观测/核验工具，在两个新原厂进程内实际补至BX与首指令。未改原固件或模型，也不是完整移植修复。原缺失模块红测精确报`ModuleNotFoundError: No module named 'task_chain_contract'`；实现后6合同测试通过，再采集两跑和新增7项实录回归。没有本轮新实跑失败被隐藏或晋升。

**仍未修复的问题**：回调返回/完成、退出删除复用、完整描述符/注册来源/所有权、System/flags/失败/耗尽/同步及r10的73待配对；真实硬件事务/完成源与35/3F；完整Fenestra候选及刷入恢复。两独立进程QMP均应答、退出0、自有进程关闭/Q:移除，无强制宿主清理；不冒称正常关机。

## 5. Evidence → Finding → Path及复现

### Evidence

|E-id|source_ref|repro_command|content_hash|
|---|---|---|---|
|E-imports|contract-1.json（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-chain-r17/contract-1.json`），原SVC/表/LDR/BX等价锚点|下方合同单测|37a1e914722a38a90478200629eb07224efc25b01a0bfc5c3910a3f724c95710|
|E-run1|run-1.json（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-chain-r17/run-1.json`）|下方严格重放|4c0dcc4facff9c5b0639586368673405cddc2bad31df75a4a3d7f9e815de1e49|
|E-run2|run-2-repeat.json（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-chain-r17/run-2-repeat.json`）|下方严格重放|c60bfc8bcd2870e53bb95b14d33ea37e91b9b9a72939c0df819725c12aee8d0c|
|E-replay|verification-final.json（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-chain-r17/verification-final.json`），45类错误拒绝|下方严格重放|16e2515c13e9c03ec37f4daafeb5c322b41cc8a313660812a499edeec4de7f06|
|E-current|verification-current.json（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-chain-r17/verification-current.json`），完整来源/六组旧重放/PORT/清理|scratch中check-task-chain-r17.py，已执行|b84b34e4363ca711d6193f9b7306ce0d1956027633b8d43168c27dfa50fa7e7e|

### Findings与Path

|F-id|severity|evidence_ids|confidence|location|status|
|---|---|---|---|---|---|
|F1同链实际BX/首指令|n/a_re|E-imports/E-run1/E-run2/E-replay|高，限样本|创建对象/TCB/index3/共享入口/字段目标|19条局部通过，非业务完成|
|F2字段变化不忽略|n/a_re|E-run1/E-run2/E-replay|高，限实际原STR|103DEC90/1006CC54|6次原写入核验，未知变化仍拒绝|
|F3完整端口/刷入/绝对安全未证|n/a_re|E-current/PORT及阶段表|高|Q/U/真机门槛|未完成，继续第一阶段，不刷机|

P1，path_type=callflow：同次创建输入→原配置/TCB/初始帧→对象初始化→同role句柄查表→index3发布→原POP与首次共享入口（允许两种先后）→独立字段LDR→原BX→目标首指令及实际PUSH。挂E-imports/E-run1/2/F1/F2；终点不是回调返回或完整任务完成。

P2，path_type=solve：r16止于LDR的证据缺口→新合同红测→独立观测/核验→两新进程→45类错误记录/实际栈等额外回归→完整来源及旧交付核对。挂E-replay/E-current/F1/F3；不拼旧进程、不放宽上限。

### 已执行的复现检查

工作目录为工程根；以下为离线重放，不启动QEMU；输出自动新名，源码/模型/原输入身份改变会拒绝旧记录。

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR" PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
python -X utf8 -B fenestra/z62/verify_task_chain.py \
  --run analysis/fenestra-z62-task-chain-r17/run-1.json \
  --run analysis/fenestra-z62-task-chain-r17/run-2-repeat.json \
  --output "analysis/fenestra-z62-task-chain-r17/replay-$(date +%s).json"
```

214＋11测试日志在本轮目录tests-full-1.log/tests-candidate-1.log；38原断言结果见显式新夹具结果（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/r17-legacy-recheck-1.json`），不改旧断言/guard或伪造旧树。两次完整重放verification-1/final逐字节一致；额外测试核实际栈字、精确读序、两步/寄存器缺失、独立字段不符、旧r16不能替代新证据及重复PID拒绝。

完整78,316源码含额外项检测、61原配方、EXE/8DLL、56份r16交付核对；README旧27,398字节前缀SHA3d0074bbba4fc778020842ff0e944548ba480dc650a0c982ab0c8cf8aed3adf9保持。六组r9/r10/r11/r12/r15/r16 fresh重放逐字节同旧，仅新增输出。原FenestraHEAD b199dcdf及既有两loader修改、donor4f43899保持；CC BY-NC-SA4.0及例外/署名不扩权。新模型EXE SHA595af7c39fa5b1b86ada8cf4a4c40651dff6fc4f946de6b35e904ff4fe3b9d18；旧r69精确来源仍缺，r14补PIXELS关系不追改r13原61配方，一次模型构建不是二次位一致重建。

Timeline（UTC+8）：20:38:05合同绿测/旧证据快照；20:38:28起第一跑；20:39:23起第二跑；随后214＋11＋38回归及两次严格重放；20:45:05来源/旧重放/清理收据。最终文档/语法/摘要及进程清理另由本轮final-checks.json、deliverables-final.json封存，不将其当启动或刷入证据。

## 6. 继续工作

先补同次回调返回/业务完成、完整描述符/注册/所有权、早失败/System/flags/耗尽/退出删除复用/同步；补自然堆释放/合并复用、登记返回/链表/通知/唤醒，解释r10的73待配对。恢复真实gate/sequencer/transfer-reset事务与完成源、关闭其他成功假设及35/3F，核空间/实际加载/cache-DMA合同；完成原Fenestra ARM32完整copied-service SDK、原任务/同步/卡文件、模块管理菜单及启动/正常关机集成候选。

只有Q1～Q6及完整候选矩阵全部通过，才能冻结唯一镜像进入U1～U6；前两阶段与独立物理条件未齐不上真机。**本轮局部交付完成不等于总目标完成，不作绝对安全承诺。**
