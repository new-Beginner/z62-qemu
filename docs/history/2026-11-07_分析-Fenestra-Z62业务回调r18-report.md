# Fenestra / Z62 原厂业务回调与有界失败 r18

> 2026-11-07 · 本地离线 · flavor=null · severity=n/a_re
>
> **完整移植未完成：第一阶段未放行，第二阶段未进入验收，真机关闭。不能保证真机刷入和运行“一定不出问题”。两次本轮采集均失败，不因局部前缀可核验而晋升通过。**

## 1. 结果和范围

本轮继续原Fenestra＋自研z62qemu路线，未替换成另一套插件系统。原C1.70主从、可追溯r13模型、无卡/参数/控制器/Fenestra候选，两个新进程各记录128次原厂注册后触及第129次注册断点。总计692个已存事件、256次注册、94次业务BLX调用中，**86次单参数回调到达原返回点，并实际执行原B回消息调度循环**；另8次调用在截断时仍未返回。两个双参数目标各跑均未返回，不能声称所有签名或整个实验通过。

本轮新增独立合同、只读观测器、完整验收器、失败前缀核验器及13项测试。227项Fenestra专项＋11项候选工具＋38项显式冻结夹具原断言全部通过、无跳过，39类错误记录拒绝；这些是工具/回归覆盖，不是原厂错误模块、完整端口、刷入故障或物理安全验收。

[scope](../../analysis/fenestra-z62-business-r18/scope.md)规定只读有界内存、硬件执行断点、原指令隔离单步；停核取停止包thread、单步vCont;s、读ticks后恢复原核。未写原指令/运行PC/RAM/寄存器/返回值/ready，未注入调用或成功事件。`-nic none`、GDB/QMP仅127.0.0.1；未接相机、USB/PTP、物理介质或外部服务，未刷机/提交/推送/发布固件或密钥。QEMU boot-image预装及loader复位初始化不等于介质早加载、认证或刷入。

只新增r18文件，r1～r17绑定源码、测试和证据保持；README仅追加，旧29,247字节前缀另核。自有PID6348/28024均QMP应答、退出0、关闭/Q:移除；这不是相机正常关机。失败发生前没有最终四核采样或guest目标验收，不冒称已达到guest2/3秒、末次idle或完整启动。默认gate/sequencer/transfer-reset completion仍开，其他成功假设仍在。

## 2. 三阶段验证项、标准和转换条件

### 第一阶段：完整原Fenestra在自研z62qemu验证

|项|必须满足的通过标准|当前问题与实际结果|
|---|---|---|
|Q1 ARM32模块/完整SDK|在原厂环境实际执行原Fenestra模块格式、重定位、入口、copied-service SDK；合法/错误模块均按合同处理|仍experimental-loader-only/legacy v1日志；本轮无完整候选。未通过|
|Q2完整启动/正常关机|主从ISA、栈、MMU、内存初始化以及完整启动、正常关机、再启动均核验|既有早期局部合同不能替完整启动；本轮触界中止，QMP quit非正常关机。未通过|
|Q3内存/任务/同步生命周期|创建—启动—业务返回/完成、System/flags/早失败/耗尽/退出删除复用；自然堆释放合并复用、通知/阻塞唤醒和所有权|本轮补86次单参数返回局部链；8次未返回、双参数返回未证，r10的73待配对未解释，完整生命周期/ABI仍缺。未通过|
|Q4空间/加载/cache-DMA|可保留代码数据空间及所有权、实际早加载容量、MMU/cache-DMA发布与回收实跑正确|可读/映射/自然分配不证所有权，尚无完整合同。未通过|
|Q5完整原厂集成|原任务/同步/卡文件服务、完整SDK、模块管理菜单、启动及正常关机集成候选均运行|PORT（本地证据，未分发：`<WORKSPACE>/fenestra/z62/PORT.json`）仍firmware_integrated/card_loading_verified/native_menu_verified=false，无完整候选。未通过|
|Q6模型可信度/完整矩阵|同一可追溯模型同配置原版/候选停用/启用，合法错误模块、启停异常压力、完整生命周期；关键模型问题关闭|r13可追溯，但真实完成事务/其他成功假设和菜单循环35/3F未解决，无完整候选矩阵。未通过|

**只有Q1～Q6全部通过、关键问题解释/修复并复测、完整候选可重建且冻结唯一SHA，才进入第二阶段。** 不以工具测试数、原厂局部观察、不同进程拼接或提高采样上限替代。r17的19条创建—启动—BX首指令链保留，本轮没有将它拼成创建—业务完成的同次联合证据。

### 第二阶段：同一冻结镜像与完整刷入流程

|项|验证项和通过标准|当前状态|
|---|---|---|
|U1唯一镜像/资格/边界|唯一SHA、型号版本、主从/控制器资格、长度和地址；互换/截断/越界必须拒绝|无完整冻结候选，未进入验收|
|U2真实原厂认证|真实B8/K8、原更新器接受合法镜像且拒绝篡改|未验证；CRC、seed、关系式或其他机型不能替代|
|U3实际介质早加载|实际介质容量、加载边界、入口和主从发布顺序正确|未验证；boot-image预装不是卡加载|
|U4擦写/持久化|实际写入范围、NOR/校准保留、读回重启持久化及冲突处理正确|未验证；合成参数/空白虚拟卡不是实机备份|
|U5中断/断电恢复|校验、擦除、写入、提交、重启各阶段中断/超时/断电均可恢复或回滚|未验证；宿主QMP退出/进程清理不替代|
|U6完整可重建|同一候选镜像/源码/模型/工具链/依赖/许可证可追溯重建，关键失败关闭|未进行固件镜像重建验收；一次模型构建非两次位一致重建|

先放行第一阶段，再验同一冻结镜像的U1～U6。11项候选工具测试并未取得真实认证或刷入流程证据。

### 第三阶段：真机门槛

前两阶段全部通过，且独立关闭物理恢复、供电/存储、cache-DMA和硬件时序缺口，才具备讨论受控真机验证的前提；当前全部不具备。有限模拟器覆盖不能证明所有未来物理状态绝无故障，用户的绝对安全要求仍未满足/未验证，不能改成“降低风险后即可放行”。本轮保持physical_gate_open=false、absolute_safety_verified=false。

## 3. 原业务调度与注册合同

### 静态身份与导入等价锚点

裸ARM/Thumb固件没有传统PE动态导入表。E-imports等价锚点为原setter的PUSH/参数保存/STRD/尾分支、literal中的调度入口、对象+0x24字段加载、BLX及回循环B；完整原字节/反汇编在contract-1（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-business-r18/contract-1.json`）。不是完整服务导入图或已发布SDK。成员长度/SHA由固定PROFILES核对，无新认证/密钥分析。

|种类|主调度器 / setter / STRD / BLX / 返回点|从调度器 / setter / STRD / BLX / 返回点|静态及调用实测参数|
|---|---|---|---|
|1|1035C940 / 1035C95E / 1035C974 / 1035C95A / 1035C95C|1005E9E4 / 1005EA02 / 1005EA18 / 1005E9FE / 1005EA00|callback(message)，BLX r1|
|2|103A2890 / 103A28B0 / 103A28C6 / 103A28AC / 103A28AE|1006A7F4 / 1006A814 / 1006A82A / 1006A810 / 1006A812|callback(object,message)，BLX r2；仅调用/入口，未证返回|

每个setter以入口r1/r2保存到r6/r7；原`STRD r6,r7,[r4,#0x24]`写对象+0x24/+0x28，再以原literal和B.W进入既有创建封装。调度器先经helper，再从+0x24取业务回调并BLX，返回后原B跳回start+12。helper的完整等待/消息合同、消息语义和对象所有权仍未验证。

使用本地Python3.12/Capstone5.0.7和既有只读协议，没有启动IDA或外部服务。技能tool-index.md、precedent-reverse.md与ops/evidence-finding-path.md实际缺失，不冒称已读或完成IDA survey；报告使用已读RE模板与vendor Base规范，flavor=null，不套恶意软件/漏洞叙事。

### 独立观测与核验

1. setter入口独立48字节对象、原PUSH的24字节真实栈写入；到STRD时用同role/类型/原SP/对象唯一配对，核r4/r5/r6/r7来自原入口、保存栈未变。
2. STRD前后各独立读48字节，只允许+0x24..+0x2B等于原r6/r7，其余字节及寄存器（除PC+4）一致。
3. 自然BLX前独立读对象48字节、消息栈字4字节、current两槽和当前TCB32字节。核TCB+C=对象、TCB+14=原共享入口、对象+4=本类调度器；字段+0x24/+0x28与同对象最新已观测注册一致。不从BLX结果反推字段。
4. 真实执行原BLX，核PC/ISA、LR=原返回点|1、全部参数/寄存器、目标ROM16字节、current与系统状态。94次实际字段目标均Thumb，无实际ARM字段目标；ARM分支只有合成工具测试。
5. 捕获原返回点时，按同role/类型/TCB/句柄/对象/调用SP唯一配对（允许同role跨核），核SP/r4..r11保持，再真实执行原B回循环。r0可能非零，仅记录，不认作成功状态。没有单步跟踪回调全部内部指令或最后一条返回指令，不能据此验消息语义、业务完成或并发安全。
6. 前缀核验器独立重建所有已存事件、注册和调用；核精确只读地址/顺序、断点/单步生命周期、CPU/ROM/系统/时钟、g/qC次数及QMP清理，并检查触界失败现场的未单步尾部。失败形状为g=qC=2×已存事件+1，无最终CPU快照；不伪造最终采样。
7. 完整验收器明确拒绝这两份原始失败记录。前缀工具另命名，full_run_passed/accepted_run/bounded_registered_business_return_verified均false；不删除pending或补字段使其通过。

代码：合同（本地证据，未分发：`<WORKSPACE>/fenestra/z62/business_contract.py`）、观测器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_business.py`）、完整验收器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/verify_business.py`）、失败前缀核验器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/verify_business_prefix.py`）。前三者采集后未修改，记录绑定摘要与当前相同；新增前缀工具有单独源码摘要。

## 4. 实跑、发现的问题与修复结果

|记录|PID|注册/已存事件|调用/到返回点/仍在调用|返回主/从|失败点主模型秒|整跑结论|
|---|---:|---|---|---|---|---|
|run-1.json|6348|128 / 344|46 / 42 / 4|36 / 6|0.0262760417|第129注册触界，失败|
|run-2-repeat.json|28024|128 / 348|48 / 44 / 4|38 / 6|0.0278262708|第129注册触界，失败|

两跑注册各主92/从36，94次调用全部关联本进程已观测注册，无未注册调用。86次已返回全部为种类1；每跑3个主侧及1个从侧调用仍在活动。地址、TCB、句柄不作跨进程稳定身份，表中次数不是任务总数或生命周期次数。

|问题|证据与原因范围|本轮修复/补证结果|
|---|---|---|
|共享BX字段目标可能只是调度任务，不能当一次性业务回调返回ABI|原共享BX不设置新LR；新静态/动态路径分离对象+4调度器和+0x24业务回调|补了注册输入→STRD→自然业务BLX→86次返回循环的局部证据；未改固件，也未证明完整SDK|
|采集未排空即触128注册上限|两个新PID均`ValueError: Registration bound exceeded`，各有4次未返回|未修复/未扩界；保留原失败及完整审计，前缀核验不晋升验收|
|双参数回调未返回|每跑master目标1038A99D/slave10067711，message=1；只有调用入口实测|未解决；原首64字节有队列循环和更深层BLX，详见pending-static，尚无内部动态根因证据，不能称死锁或正常等待|
|另外两个主侧单参数调用仍活动|1021E55F/message20、103BE827/message2；两跑均截断时未返回|未解决；静态候选含其他helper调用，不据此判业务完成/失败|
|没有完整端口和刷入证据|PORT仍loader-only；缺完整SDK/同步/文件/菜单及Q/U矩阵|未修复，第一阶段未放行，第二阶段和真机关闭|

固定边界：128注册/128调用/1024事件、quiet15宿主秒、wall240、minimum8；两种签名返回/双侧/全部活动排空的验收条件不变。没有扩大边界、筛除未返回调用、强配结果或注入事务。第二跑仅guest目标由2改3，但因触界未进入目标时窗，不能比较最终guest运行结果。

## 5. Evidence → Finding → Path

### Evidence

|E-id|source_ref|repro_command|content_hash（SHA256）|
|---|---|---|---|
|E-imports|contract-1（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-business-r18/contract-1.json`），固定成员身份及两类原指令/literal|business_contract.collect()（由专项测试调用）|fc59b17b2af0471a98244c8598f48b928cba61565608ae7c4b14ee70856264ed|
|E-run1|原失败1（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-business-r18/run-1.json`）、host日志（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-business-r18/run-1.host.log`）|observe_business.py，minimum8/guest2/wall240|f6d6f6ea515f20e98126defec054a27e371a79be6e6cf3b3e31e26f9bf8ade44|
|E-run2|原失败2（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-business-r18/run-2-repeat.json`）、host日志（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-business-r18/run-2.host.log`）|observe_business.py，minimum8/guest3/wall240|ed051f2e67c26e367fe9af1ada0af7903b86c4f4078f72cdbd1d55b7b51f9b53|
|E-prefix|严格前缀重放（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-business-r18/prefix-verification-1.json`）|下方离线重放命令，39类错误记录拒绝|7fb41d7f187530e6fb2c53c7b258cda331f1f536e97f347d56be07e2df63377b|
|E-pending|未返回目标原字节（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-business-r18/pending-static.json`）|check-business-r18.py读取已记录目标首64字节，仅静态|4d03f078190da07b77d7617ee7c30d273008f3f7168633aafb010f548e3d1cc1|
|E-current|来源/旧重放/清理（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-business-r18/verification-current.json`）|本会话scratch/check-business-r18.py，七组fresh重放|e117ac7268a0c4f0d8a4a9655b88c846f6b5823a4a0aa950ae77ff785935a61f|
|E-tests|227专项（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-business-r18/tests-full-1.log`）、11候选（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-business-r18/tests-candidate-1.log`）、38夹具（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-model-r14/r18-legacy-recheck-1.json`）|下方三项检查；fixture映射不改原断言/guard|逐文件摘要在最终交付清单记录，不以测试数替换运行验收|

### Findings与Path

|F-id|severity|evidence_ids|confidence|location|status|
|---|---|---|---|---|---|
|F1两层调度/业务回调需分开|n/a_re|E-imports/E-run1/E-run2/E-prefix|高（本段原字节与实测调用）|对象+4/+24，两类BLX|局部已核验，完整描述符/所有权未证|
|F2单参数自然返回循环86次|n/a_re|E-prefix/E-run1/E-run2|高（有限窗口）|原种类1返回点及B|局部前缀证据；非完整业务完成|
|F3活动调用及采样触界|n/a_re|E-run1/E-run2/E-pending|高（触界与未返回），低（内部根因）|128注册界、8条待返回实例|未解决；两整跑明确失败|
|F4完整端口/刷入/绝对安全缺口|n/a_re|E-current/PORT|高（当前状态）|第一/二/三阶段门槛|未完成/未验证，门槛关闭|

P1，path_type=callflow：E-imports原setter入口→E-run1/2原PUSH/STRD→同对象独立字段→原BLX及目标PC/ISA/LR/参数→E-prefix的86个原返回点→原B回循环，支持F1/F2。该路径不是r17创建/启动与本轮跨进程拼接的完整链。

P2，path_type=callflow：E-run1/2记录全部94调用→8调用仍活动→第129注册断点→原采集器抛错→QMP关闭自有进程，支持F3。E-pending仅提供后续动态调查的静态锚点，不把循环推断成故障根因。

### 复现与实际检查

下列从工程根运行，输出名必须不存在（不可覆盖旧封存证据）。本轮已实际执行相同参数的前缀重放及三项回归，分别生成prefix-verification-1/current、tests-full-1、tests-candidate-1、r18-legacy-recheck-1。下面给首次复现预留新输出名；重放不启动QEMU，不需Q:。

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR"
export PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B fenestra/z62/verify_business_prefix.py \
  --run analysis/fenestra-z62-business-r18/run-1.json \
  --run analysis/fenestra-z62-business-r18/run-2-repeat.json \
  --output analysis/fenestra-z62-business-r18/replay-manual-r18.json
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
python -X utf8 -B tools/z62_reconstructed_fixtures.py test \
  --work .build/fenestra-z62-fixtures-r14-01 \
  --output analysis/fenestra-z62-model-r14/r18-legacy-manual.json
```

首次红测`ModuleNotFoundError: No module named 'business_contract'`保留；实现后6合同绿，再增加7实录核验测试；无跳过。39类负例及一致改BLX前后r0仍由独立消息栈字拒绝、一致改STRD r6/结果仍由原setter输入拒绝，均为工具覆盖，不能替真实固件失败矩阵。

78,316完整源码含额外项检查、61原配方、r13 EXE/8DLL已复核；r17旧46交付保持（README最终仅保留旧前缀），r9/r10/r11/r12/r15/r16/r17七组fresh重放与原结果逐字节一致。旧r69精确来源未恢复；r14补PIXELS当前关系不追改r13原61；一次模型构建不能声称两次位一致重建。Fenestra仍b199dcdf、tracked仅原两个loader修改，donor4f43899 tracked干净；许可证/商业例外边界保留。

时间线（UTC）：13:16:49首跑开始，13:18:11复跑开始；13项实录/合同测试8.089秒、全227项80.308秒、11项2.250秒、夹具38项0.159秒；13:26:19来源/七组重放与清理复核。最后封存检查及逐文件SHA单独记录，不把活跃重定向日志纳入清单。

## 6. 未完成工作与下一步

- 先单独设计有界的未返回目标内部执行/队列/等待/嵌套BLX观察，恢复真实完成/返回条件；不扩大本次上限、补调度或把失败前缀晋升通过。当前没有证据确认这8次是死锁，也没有证据确认正常业务完成。
- 完整描述符/注册所有权、同次创建—启动—业务完成、退出删除复用、早失败/System/flags/耗尽/同步、自然堆释放/合并复用仍缺；r10的73待配对不能用本轮或r17未见启动对象替代解释。
- 恢复真实gate/sequencer/transfer-reset事务及其他成功源，修菜单循环35/3F；r14不同completion同样idle但轨迹不同的反例仍有效。
- 原Fenestra ARM32完整copied-service SDK、任务/同步/卡文件、模块管理菜单及完整启动/正常关机集成候选，以及空间/加载/MMU/cache-DMA合同和完整矩阵仍未完成。
- Q1～Q6全过后才冻结同一镜像验U1～U6；此前不进入真机。不能用局部86次返回、工具全绿或风险接受替用户的绝对安全要求。
