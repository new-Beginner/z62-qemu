# Fenestra / Z62 创建—启动同进程联合观察 r16

> 2026-11-07 · 本地离线 · flavor=null · severity=n/a_re
>
> **完整移植尚未完成。第一阶段未放行，第二阶段未进入验收，真机关闭。不能保证刷入和运行“一定不出问题”。** 本轮交付是原厂任务局部合同与实证工具，不是完整 Fenestra 候选、可刷包或物理安全认证。

## 1. 本轮结果与限制

在原始 Z6II C1.70 主从、可追溯的自研 r13 QEMU、无卡/参数/控制器/Fenestra 候选条件下，两独立进程通过严格重放：**96次创建、25次自然成功index3启动、404事件中，17条创建对象→同TCB启动→原POP返回→真实首次共享入口联合链**。联合链主侧3条、从侧14条；不跨进程拼接r12、r15或r11证据。

另有79个已初始化创建对象在窗口内未观察到启动，8次启动未观察到对应封装创建，12个构造共享桩停点未匹配封装；它们全部单列，不能据此认定死锁、任务总数、错误或完整生命周期。所有25条启动均返回0；其中9条首次入口先于API返回、16条API先返回，但不要求每侧每次都出现两种顺序。

新增12项工具测试后，**201项专项＋11项候选工具＋38项显式夹具原断言通过，无跳过**。33类错误记录被拒绝。工具负例不是原厂错误模块/失败调用/刷入故障覆盖。

授权、环境与禁止操作见[scope](../../analysis/fenestra-z62-task-joint-r16/scope.md)。全程离线；`-nic none`、127.0.0.1 RSP/QMP；只读有界内存、硬件执行断点、原指令单核隔离单步、暂停/继续。不补写客体指令/PC/RAM/寄存器/返回值，不注入调用或成功事件。原boot-image预装及loader复位PC已显式标记，**不是实际介质早加载、认证、擦写或持久化**。没有相机、USB/PTP、物理介质操作、刷机、提交、推送或发布固件/密钥。

## 2. 三阶段验证项、标准与进入条件

### 第一阶段：完整原 Fenestra 在自研 z62qemu 验证

|项|必须通过的验证与标准|当前问题/修复结果|
|---|---|---|
|Q1 ARM32模块/SDK|原厂环境内完整模块格式、重定位、入口、copied-service SDK；合法与错误模块真实执行|仍只有合成loader/legacy v1日志，本轮未执行Fenestra候选。未通过|
|Q2完整启动/正常关机|主从ISA/栈/MMU/初始化，完整启动、正常关机及再启动均通过|新增的是早期任务局部联合链，非完整启动/关机；QMP退出不替代。未通过|
|Q3内存/任务/同步生命周期|创建—启动—业务返回/完成，System/flags/失败/耗尽/退出删除复用，堆释放合并复用及同步所有权|17条同进程局部链补齐部分关系；自然字段更新已捕获，但完整ABI/生命周期、r10的73待配对仍未解决。未通过|
|Q4空间/介质/cache-DMA|可保留代码数据空间及所有权、实际早加载容量、MMU/cache-DMA发布回收实跑|可读、空白、自然分配或映射不能证占用安全，合同仍缺。未通过|
|Q5完整服务与原厂集成|原任务/同步/卡文件、完整SDK、模块管理菜单、启动和正常关机集成候选|PORT（本地证据，未分发：`<WORKSPACE>/fenestra/z62/PORT.json`）仍experimental-loader-only，firmware_integrated=false。未通过|
|Q6模型可信度与完整矩阵|可追溯模型；同模型同配置原版/候选停用/启用、错误模块、启停异常压力和完整生命周期；关键模型缺口关闭|r13可追溯，但默认完成逻辑/其他成功假设和原菜单循环35/3F缺口仍在；没有完整候选矩阵。未通过|

**只有Q1～Q6全部通过，关键失败完成解释/修复并复测，完整候选可重建且冻结唯一SHA，才进入第二阶段。** 不能用测试数、末次idle、所读故障零、退出0或多个局部观察拼接替代。

### 第二阶段：同一冻结镜像与刷入流程

|项|全部必须通过的标准|当前状态|
|---|---|---|
|U1资格/边界|唯一SHA、型号版本及主从/控制器资格、长度地址正确；互换/截断/越界拒绝|没有完整冻结候选，未进入验收|
|U2真实原厂认证|真实B8/K8；原更新器接受合法镜像、拒绝篡改|未验证；CRC、seed、关系式或其他机型不替代|
|U3实际介质早加载|真实容量/加载边界、入口和主从发布顺序正确|未验证；boot-image预装不替代|
|U4擦写/持久化|实际写入范围、NOR/校准保留、读回重启持久化及冲突处理|未验证；合成参数/空白虚拟卡不是真机备份|
|U5中断/断电恢复|校验、擦除、写入、提交、重启各处中断/超时/断电恢复或回滚|未验证；QMP退出与宿主清理不替代|
|U6完整可重建|同一候选镜像、源码、模型、工具链/依赖/许可证可追溯重建；关键失败关闭|本轮没有固件镜像重建验收；一次模型构建不是两次位一致重建|

必须先放行第一阶段，再对**同一冻结镜像**通过所有U项。本轮11项候选工具测试不能视作刷入流程通过。

### 第三阶段：真机门槛

前两阶段全部通过，且独立关闭物理恢复、供电/存储、cache-DMA及硬件时序缺口后，才具备讨论受控真机验证的前提。当前门槛关闭。有限模拟器证据无法证明所有未来物理状态绝无故障，用户的绝对安全要求仍未满足/未验证，不改成“降低风险后放行”。

## 3. 原厂局部合同

### 原字节与导入等价锚点

裸ARM/Thumb无传统PE/ELF导入表。E-imports等价证据是原封装BLX创建SVC桩/index1、独立服务0A桩/表、index3服务表/原PUSH/POP/发布帧及共享LDR。原字节、完整局部指令和输入SHA见合同（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-joint-r16/contract-store.json`）。服务0A与index3不同，0A代码窗口没有直接BL到index3；本轮也不宣称证明整个间接调用图无连接。

|原锚点|master|slave|
|---|---|---|
|创建封装入口|103DEBC6|1006CB8A|
|构造完成原LDR|1010A6D4|1003C0A8|
|对象初始化后ADD SP|103DEC64|1006CC28|
|服务0A内核入口|1010B4E8|1003CEBC|
|自然index3输入|1010A91C|1003C2F0|
|原发布MOV|1010AAC4|1003C498|
|成功返回POP|1010AB88|1003C55C|
|首次共享LDR|103DEBBC|1006CB80|
|原对象+8更新STR|103DEC90|1006CC54|

使用本地Python/Capstone，未启动IDA或安装/下载工具。缺失的tool-index/precedent/ops Evidence参考文件不冒称已读；RE工作流、报告模板和Base规范已读取。普通固件分析不套恶意软件/攻击报告。

### 同进程关联与不外推的边界

1. 创建入口独立读输入配置28字节、对象32字节、未初始化配置+28原栈字、原name模板；原PUSH隔离执行并独立读48字节保存栈核对。
2. 原构造LDR前独立读配置56字节、TCB216字节、初始帧76字节及TCB+8；配置前三字→TCB+C/+10/+14、空内核名称与业务标签分离。原LDR效果核对。
3. 对象初始化后独立核句柄、回调、输入字段、模式和配置+1A半字；保留+28原字。ADD SP只表示该条原指令，**不是外层POP/调用者返回**。
4. 自然index3输入按原表公式定位同TCB，要求同role、同句柄/TCB/对象且初始化先于调用，歧义/复用拒绝。CPU不当任务ID，未观察删除复用，不称稳定生命周期身份。
5. 原启动PUSH写栈、发布帧、原POP真实返回与首次入口沿用r15纯局部核验；调用栈用native-RAM守卫，TCB/帧用原heap界。可读不证所有权。
6. 启动输入及首次共享入口再次独立读对象；首次入口r1=同创建对象，原LDR后r1=原回调输入。**未在这次联合链执行BX/业务回调返回或完成**，不拼r11成完整执行链。
7. 对象+8不假定永恒不变；必须有实际捕获的原STR写前/写后及寄存器效果，且32字节中仅+8变为r4。更新前前16字节必须符合上一已核快照，其后输入/入口前16字节仍严格核对。没有“任意变化均允许”的例外。

工具：联合合同（本地证据，未分发：`<WORKSPACE>/fenestra/z62/task_joint_contract.py`）、观测器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_task_joint.py`）、核验器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/verify_task_joint.py`）。TOOL最终0.1.1，创建/启动各128上限、2048事件、quiet15宿主秒、wall240秒不扩；默认gate/sequencer/transfer-reset完成逻辑仍开。实验开关关闭不是关闭全部辅助，ticks按既有48MHz模型口径而非物理时序。撤断点后运行不覆盖所有任务调用。

## 4. 实跑、问题及修复结果

|记录|PID|创建/启动/事件|联合链|结果|
|---|---:|---|---:|---|
|run-1.json 初版|57536|53/13/217|9（初版诊断）|初版可重放收据保留，不计最终0.1.1验收|
|run-2-repeat.json 初版|52572|93/32/394已保存事件|不计|对象+8与初始化值不符，失败，不晋升|
|run-3-store.json 最终|58336|52/12/212|8＝主1/从7|sample-bound-drained，待配对空，完整严格重放通过|
|run-4-store-repeat.json 最终|25872|44/13/192|9＝主2/从7|同上；独立进程|
|run-5-extended.json 诊断|55480|128/52/599已保存事件|不计|第129次创建入口触界，失败；不扩大界限|

最终两跑调用跟踪仅到主模型0.0040735833/0.0035971042秒，撤断点后分别到2.5452776458/3.8270953125秒；宿主31.266/46.156秒。末次idle不证明完整启动。最终两跑各6个未匹配构造桩、首次入口未匹配0、调用和活动创建待配对均0。未启动创建分别44/35、未观察创建的启动各4。

**问题1：工具错误地假定对象前16字节在创建后全部恒定。** 初版run2在主侧SWSRV样本观察对象+8从0x14到0x08，句柄/回调/对象/TCB不变。原字节查到附近`ac60`即STR r4,[r5,#8]。保留初版三文件、失败现场、诊断、红绿测试；最终工具新增原STR前后观察，不删字段核验、不改客体。最终两跑各实际核对两次从侧4→16更新；较长诊断前缀还捕获主侧20→8、12→8等写入。它们证明该字段确会被原指令更新，**不能跨进程追认初版run2那次未跟踪写入的确切原因**。未知写入仍拒绝。

**问题2：较长样本达到原固定上限。** run5目标24条，但创建达到128，第129次入口被拒。保留599事件、failure_event和前缀诊断（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-joint-r16/extended-prefix-check.json`），后者仅重建已保存事件、局部原指令效果与配对，**不是失败整跑的完整命令审计或验收**。QMP退出未获应答并记录WinError10054，进程退出0/自有进程关闭/映射移除；未强制宿主清理。此结果不冒称正常关机/恢复，也不解释r10的73待配对。

**编辑及工具执行问题如实保留**：合同最初缺模块红测；新增setter红测精确暴露缺锚/缺期望函数。一次行号编辑错放新增代码，读回定位后修正，AST和6合同测试通过才再次采集，错版没有运行；不是固件修复。一次诊断脚本把尚未发布帧当非空读取，产生TypeError，改用实际已有字段后完成诊断；未修改任何原样本。

run1～run4 QMP均应答、退出0并清理映射；run5未应答已单列。所有运行均无相机正常关机证据。源/原固件/模型没有补丁。原Fenestra仅保留既有两loader修改，许可与署名不变，不扩大商业许可。

## 5. Evidence → Finding → Path与复现

### Evidence

|E-id|source_ref|repro_command|content_hash|
|---|---|---|---|
|E-imports|contract-store.json：裸固件原SVC表/桩/STR/LDR等价锚点|单元测试中的collect|f1dd2b55d2e35437095b8c185cd02e5186e0e77092be6aea3f0d345a6941824f|
|E-joint-1|run-3-store.json|下方严格重放|9cc5b2c66e4dad94d63ba20e88f8e39bec6174d7991ac48b04272a56fb38feae|
|E-joint-2|run-4-store-repeat.json|下方严格重放|3f1d5567217d0b1c3f8606857a60878de6062b0974745a28a62754b1913e617c|
|E-replay|verification-final.json（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-joint-r16/verification-final.json`）：33类错误拒绝|下方严格重放|60f7a513e2076063f25962e9b2cc8304172ae52f2780ae5053d7af770f0d85e5|
|E-failure|run-2-repeat.json原字段变化失败|实录回归中的失败拒绝|7551491ff4fb655eda1dd6420c8cae6ad8f699f0b98b120bc5aa491a518e22d3|
|E-bound|run-5-extended.json，未验收|check-task-joint-r16.py已保存前缀诊断|e8b9847c7047cb879fb914450284b280f6cf6341368727f83d9d2daf1935cb81|
|E-current|来源与旧重放核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-joint-r16/verification-current.json`）|scratch中check-task-joint-r16.py|见最终交付清单|

### Findings与Path

|F-id|severity|evidence_ids|confidence|location|status|
|---|---|---|---|---|---|
|F1同进程创建—启动局部链|n/a_re|E-imports/E-joint-1/2/E-replay|高，仅样本|原封装/TCB/index3/共享LDR|17条局部通过，非完整ABI/生命周期|
|F2对象+8可自然更新|n/a_re|E-failure/E-joint-1/2/E-bound|高，限实际写入|原103DEC90/1006CC54|工具增加真实STR核验；未追认旧未跟踪写入|
|F3压力/完整移植门槛仍未通过|n/a_re|E-bound/E-current/PORT|高|阶段Q/U/真机|未完成；不刷机|

P1，path_type=callflow：原创建输入→配置/TCB/初始帧→对象初始化→同进程原句柄查表→index3发布→原POP/首次入口（相对顺序独立）→独立对象字段LDR。挂E-imports/E-joint/F1；终点不是BX、回调返回或业务完成。

P2，path_type=solve：字段不等失败→原字节找到候选STR→红测→加入原写入前后观测→两独立样本严格重放→扩展触界保留失败。挂E-failure/E-bound/F2/F3；不扩界、不伪造成功。

### 已执行的复现与检查

以下重放不启动QEMU；输出必须新名。工具固定旧输入/源码/模型身份，修改后会拒绝旧记录。工作目录为本项目根，TEMP/TMP/TMPDIR指向当前PI scratch。

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR" PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
```

以下命令已以verification-store-1.json与verification-final.json两个独立新输出执行并逐字节比较；再次执行自动使用新时间戳文件。

```bash
python -X utf8 -B fenestra/z62/verify_task_joint.py \
  --run analysis/fenestra-z62-task-joint-r16/run-3-store.json \
  --run analysis/fenestra-z62-task-joint-r16/run-4-store-repeat.json \
  --output "analysis/fenestra-z62-task-joint-r16/replay-$(date +%s).json"
```

测试日志位于本轮目录tests-full-1.log、tests-candidate-1.log；38项显式夹具见新夹具结果（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/r16-legacy-recheck-1.json`），不改旧断言/guard、不伪造历史树。五组r9/r10/r11/r12/r15fresh重放逐字节同旧输出。78,316完整源码（额外文件也拒）、61原配方、r13 EXE/8DLL、59份r15交付（README按原25,780字节前缀）核对通过。原r69精确源码仍未恢复；r14补PIXELS关系不追改r13原61配方。

新模型EXE SHA：`595af7c39fa5b1b86ada8cf4a4c40651dff6fc4f946de6b35e904ff4fe3b9d18`。主/从原成员SHA与长度见合同inputs，未改变。最终AST、文档链接、两段明确Git Bash语法、旧前缀/进程/交付摘要结果见最终检查（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-joint-r16/final-checks.json`），交付清单（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-joint-r16/deliverables-final.json`）。

### Timeline摘要（UTC+8）

- 20:04:48起run1初版；20:05:32起run2字段不等失败。
- 原字节定位STR，保存初版/失败/诊断及红绿记录；错位编辑在实跑前读回修正。
- 20:08:00起run3；20:08:35起run4；最终两独立运行通过局部严格重放。
- 20:10:28起run5较长样本，触创建上限，不晋升；保存退出未应答。
- 其后201＋11＋38回归、fresh重放、原完整源码与旧证据核对；最终无QEMU/Q:，未再启动任何相机/后台工作。

## 6. 剩余工作与整体结论

先完成原Fenestra ARM32完整SDK/原任务同步/卡文件/菜单及启动正常关机集成候选；补同次业务回调BX、返回/完成、早失败/System/flags/耗尽/退出删除复用、完整描述符/注册来源/所有权及堆释放/等待唤醒。解释r10的73待配对，不能把本轮较长样本或79未启动对象替代解释。

模型方面仍需恢复真实gate/sequencer/transfer-reset事务与完成源及其他成功假设，关闭原菜单循环35/3F关键失败，并完成可保留空间/实际介质加载/MMU/cache-DMA合同。同模型同配置原版/完整候选停用/启用、合法错误模块及异常压力/完整生命周期全矩阵通过后，才冻结唯一镜像进入U1～U6。

**本轮解决的是局部工具和同进程证据缺口，整体目标仍未完成。没有阶段越级，也没有真机刷入或绝对安全承诺。**
