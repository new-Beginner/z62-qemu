# Fenestra / Z62 双参数队列回调 r19 验证报告

> 2026-11-07 · 本地离线 · flavor=null · severity=n/a_re
>
> **完整移植尚未完成。第一阶段未放行，第二阶段未进入验收，真机关闭；不能保证真机刷入和运行“一定不出问题”。本轮只补原厂服务的有限动态合同，不交付可刷镜像。**

## 1. 本轮结果与范围

沿用原 Fenestra＋自研 z62qemu 路线。原 C1.70 主从、可追溯 r13-03 模型、无卡/参数/控制器/Fenestra 候选，两个独立进程各观察到 **5 次双参数外层调用、5 次内层 BLX、5 次内层返回、5 次原 POP 返回和 5 次外层回循环**，合计 90 个事件、10 条自然返回链。每条链核对独立索引读取、原 STR 推进消费索引、槽地址、间接函数字段及保存栈；没有注入返回、补成功事件或扩大旧上限。

本轮解释了一个证据边界：**在新的较长有限窗口中，可以观察到这些双参数路径自然返回；短窗口内未返回不能直接定性为死锁。** 但不能跨进程追认 r18 的旧活动调用后来已经完成。r18 两整跑仍为第129注册触界失败，86次单参数局部返回、8次活动的原结论不变；本轮未监听注册，也未把 r17 创建启动链拼成创建—业务完成全链。

- 新增 队列合同（本地证据，未分发：`<WORKSPACE>/fenestra/z62/queue_contract.py`）、观测器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_queue.py`）、独立重放器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/verify_queue.py`）及14项测试。
- 241项Fenestra专项＋11项候选工具＋38项冻结夹具原断言通过、无跳过；40类记录错误拒绝，另有一致改参数、索引及POP/返回反例测试。工具负例不是原厂错误模块/断电恢复验收。
- [范围](../../analysis/fenestra-z62-queue-r19/scope.md)：仅原指令硬件断点、只读有界内存、隔离单步。停核取停止包thread；`vCont;s:<CPU>`；读ticks后恢复原停核。未修改运行中客体指令/PC/RAM/寄存器/返回值，未注入调用/消息/完成事件。
- `-nic none`，RSP/QMP仅127.0.0.1；未连接相机、USB/PTP、物理介质或外部服务，未刷机/提交/推送/发布固件、密钥。
- boot-image预装、loader复位PC初始化明示，不是实际介质加载、认证、擦写或持久化证据。默认gate/sequencer/transfer-reset completion仍true；其他模型成功假设尚在。
- 旧50份r18交付在追加README前完整核验；前置收据（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/prior-check.json`）冻结README旧31,001字节/SHA `ce1b2184c806aedc73dd9c3ced1c2663f40088f3c7d4febe00f22de411b47d81`。r1～r18绑定文件不改，README仅追加。

## 2. 三阶段验证项、标准与进入条件

### 第一阶段：原 Fenestra 在自研 z62qemu 完整验证

|项|必须满足的通过标准|当前发现、修复/补证结果|
|---|---|---|
|Q1 ARM32模块与完整SDK|在原厂环境实际执行原Fenestra模块格式、重定位、入口和copied-service SDK；合法/错误模块按完整合同处理|仍experimental-loader-only/legacy v1日志；本轮只是原厂队列观测，没有完整候选。未通过|
|Q2完整启动/正常关机|主从ISA/栈/MMU/内存初始化、完整启动、正常关机与再启动均验证|已有早期局部合同；本轮到2.089/3.076模型秒，原厂局部返回不等于完整启动；QMP quit不是正常关机。未通过|
|Q3内存/任务/同步生命周期|同次创建—启动—业务完成、System/flags/早失败/耗尽/退出删除复用、自然释放合并复用、通知/阻塞唤醒及所有权|新增10次双参数队列自然返回；没有同次创建注册来源/业务语义/完整生命周期；r10的73待配对仍未解释。未通过|
|Q4空间、加载、cache-DMA|可保留代码/数据空间及所有权、实际早加载容量、MMU/cache-DMA发布回收合同实跑正确|可读/可执行/自然分配不证插件保留空间；本轮没有补齐。未通过|
|Q5完整原厂集成|原任务/同步/卡文件、模块管理菜单、完整SDK、启动及正常关机集成候选均运行|PORT（本地证据，未分发：`<WORKSPACE>/fenestra/z62/PORT.json`）仍firmware_integrated/card_loading_verified/native_menu_verified=false；无完整候选。未通过|
|Q6模型可信度及完整矩阵|同一可追溯模型同配置原版/完整候选停用/启用；合法错误模块、启停异常压力和完整生命周期矩阵；关键模型问题关闭|r13来源可追溯，r14已证默认完成逻辑影响轨迹；真实事务/其他成功假设及菜单35/3F未解决；无完整候选矩阵。未通过|

**只有Q1～Q6全部通过，关键问题修复且同配置复测，完整候选可追溯重建并冻结唯一SHA，才能进入第二阶段。** 不用有限返回、工具测试数、idle、不同进程拼接或放宽上限替代。

### 第二阶段：同一冻结镜像与完整刷入流程

|项|验证项与通过标准|当前状态|
|---|---|---|
|U1唯一镜像/资格/边界|唯一SHA、型号版本、主从/控制器资格、长度地址边界；互换/截断/越界必须拒绝|无完整冻结候选；未进入验收|
|U2真实原厂认证|真实B8/K8、原更新器接受合法镜像并拒绝篡改|未验证；CRC/seed/关系式及其他机型不替代认证|
|U3实际介质早加载|实际容量、加载边界、入口和主从发布顺序正确|未验证；boot-image预装不是卡加载|
|U4擦写/保留/持久化|写入范围正确、NOR/校准保留、读回重启持久化及冲突处理正确|未验证；合成参数/空白虚拟卡不是实机备份|
|U5中断/断电恢复|校验、擦除、写入、提交、重启各阶段中断/超时/断电均可恢复或回滚|未验证；宿主进程退出不替代|
|U6完整可重建|同一候选镜像/源码/模型/工具链/依赖/许可证可追溯重建；关键失败关闭|未进行完整固件镜像重建验收；一次模型构建不等于两次位一致重建|

**先放行第一阶段，再验同一冻结镜像U1～U6。** 本轮11项候选工具测试没有取得原厂认证、写入或恢复证据。

### 第三阶段：真机进入条件

前两阶段全部通过，并独立关闭物理恢复、供电/存储、cache-DMA和硬件时序缺口，才具备讨论受控真机验证的前提。当前均不具备，`physical_gate_open=false`。有限模拟器测试无法覆盖所有未来物理状态，不能证明真机绝无故障；用户绝对安全要求仍未满足/未验证，不改为“接受风险即可放行”，`absolute_safety_verified=false`。

## 3. 静态及动态合同

### E-imports 等价锚点

原C1.70为裸ARM/Thumb成员，没有传统PE导入表。本轮等价锚点是原kind2调度BLX、队列函数PUSH/LDRD/STR/BLX/POP和literal参数字，完整原字节在contract-1（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/contract-1.json`）。不是完整服务图，不据此宣称没有文件/网络能力。本轮未新增密钥或认证分析。

|原指令点|master|slave|本轮核验|
|---|---|---|---|
|外层BLX / 返回B|103A28AC / 103A28AE|1006A810 / 1006A812|独立对象+0x24字段、消息栈字、TCB/current及参数；原BLX/LR/ISA，返回后原B回调度循环|
|目标PUSH|1038A99C|10067710|原PUSH `{r4,r5,r6,r7,r8,lr}`，24字节实际栈写入|
|LDRD索引|1038A9B0|10067724|object+0x30两原字独立读取，实际装入r1/r0|
|消费索引STR|1038A9C6|1006773A|原第二字由i改为(i+1)%192；8字节窗口中除此字外不变，寄存器除PC外保持|
|内层BLX / 返回B|1038A9D8 / 1038A9DA|1006774C / 1006774E|独立object+0xC638字段、slot及原literal参数；原BLX与返回B|
|目标POP|1038A9DC|10067750|独立保存栈，原POP恢复r4..r8/SP/PC/ISA；原返回地址等于外层返回B|

静态地址关系为queue=object+0x30、slot=object+0x38+i×0x108、192槽、目标字段object+0xC638。所有实际消费索引均0→1，第一次索引读为(1,0)，返回内层后的第二次索引读为(1,1)，随后退出。**191→0回绕只有合成工具测试，没有实际原厂回绕/多消息/并发生产者样本。** 第一字仅按代码关系作为生产侧候选，不证明完整队列协议或所有权。

两侧literal在1038AA88/100677FC，原值均`0x42070001`。内层调用实际r0等于此不透明参数字、r1等于独立推导槽地址、r2等于独立字段目标；该字不是已证明可解引用的RAM指针，也未读取其“指向内容”。

### 观测与重放方法

1. 仅两侧上述8类点，共16个硬件执行断点；不监听无关注册，不提高r18注册界。
2. 按同role、当前TCB、调用SP唯一关联；对象/句柄/TCB+0xC/共享入口/对象+4/字段目标交叉核，CPU可在同role内变化，不当稳定任务身份。
3. 所有点独立读对象48、TCB32；外层调用另读消息栈字；队列点独立读索引8和字段4，STR/内层调用另读槽264；保存栈逐次比对。可读仅为边界守卫，不证明所有权。
4. 实际执行原PUSH/LDRD/STR/BLX/B/POP并核寄存器、系统/故障状态，原目标ROM16/current独立读取；不由结果反推字段或源索引。内层目标全Thumb，实际ARM目标未覆盖。
5. 断点保持到固定模型时间窗结束；每次最多15宿主秒接收后仅暂停取ticks，未达目标继续；不是撤断点运行后补记覆盖。模型秒按48MHz既有口径，暂停/断点会扰动调度，不当物理时序或性能。
6. 预先固定8外层调用、32索引STR、256事件、240宿主秒；两跑各5/5/45，没有触界。所有未返回项保留，本轮实际pending为空；并未将此泛化为全部业务永远返回。
7. 重放器独立重建全事件、外层/内层调用与摘要；核原字节/CPU/只读地址顺序/断点生命周期/隔离单步、g=2×events+4、qC=2×events、暂停与QMP序列。`local_queue_window_replayed=true`只针对局部窗口，完整端口及阶段标志全false。

## 4. 实际运行、问题与修复结果

|记录|PID|外层主/从|事件 / 索引读 / STR|内层返回 / POP / 外层返回|目标 / 末次主模型秒|宿主秒|
|---|---:|---|---|---|---|---:|
|run-1（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/run-1.json`）|37984|2 / 3|45 / 10 / 5|5 / 5 / 5|2 / 2.0885594792|32.141|
|run-2-repeat（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/run-2-repeat.json`）|56128|2 / 3|45 / 10 / 5|5 / 5 / 5|3 / 3.0759242500|47.360|

每条链均message=1、消费槽0后内层返回、第二次读索引相等、原POP与外层B实执行。每跑内层5个Thumb目标及持续时间如下（模型秒，包含调度/等待/模型影响，非物理性能或函数语义）：

|role / 内层目标字|run1持续|run2持续|实际原调用参数|
|---|---:|---:|---|
|master / 104F15E1|0.025143292|0.023761292|r0=42070001，r1=该对象slot0|
|slave / 100B5D2B|1.073065688|1.087367417|同上；较长但两份均自然返回|
|slave / 101293BF|0.001662792|0.005309625|同上|
|master / 103CFAEF|0.000000333|0.000001208|同上|
|slave / 10135A59|0.000079354|0.000186208|同上|

地址相同不作跨进程稳定身份。完整对象、槽SHA、时间和独立来源复核见environment-current（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/environment-current.json`）。本轮只核调用边界及自然返回，没有跟踪内层全部指令、消息业务结果、注册/创建来源或删除复用。

|发现的问题|根因/证据边界|实际修复或补证结果|
|---|---|---|
|r18双参数只见调用，短窗无法判断后续|旧两跑在约0.026/0.028主模型秒触注册界；原失败不含最终guest期限验收|新独立较长窗口补10条内部队列—内层返回—POP—外层循环链；不能跨进程宣称旧8调用已返回或旧实验通过|
|工具误把literal参数当RAM指针|首轮静态合同测试报`ValueError: Queue literal global outside bounded original memory`；实际literal=42070001|修正为“原ROM literal范围＋不透明参数字”，不解引用；保留初版（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/queue_contract.initial.py.txt`）及失败日志（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/tests-contract-green-1.log`），6项重测通过后才动态采集|
|记录可能遗漏/改错寄存器、索引或步进|仅看摘要不足|40类记录变异全部拒绝，另核一致改内层r0/r1/r2、索引及POP/返回8类效果；14项新测试通过。不是防任意一致伪造证明|
|尚无完整原Fenestra候选|原上游tracked仍仅既有两个loader改动；PORT仍loader-only|未修复。没有新增完整SDK/卡文件/菜单/关机候选或可刷镜像；第一阶段未放行|
|模型及完整生命周期缺口|默认completion影响轨迹、35/3F、System/flags/释放/同步/退出删除复用等未关闭|本轮不改模型成功源或固件，只补合同；完整阶段门槛不变|

两个进程均QMP quit acknowledged、退出0、关闭、Q:移除，没有forced_host_cleanup；最终无QEMU/Q:及后台任务。这仅为宿主清理，不是相机正常关机/断电恢复。所读故障零/末次idle也不足完整启动证明，r14反例仍有效。

## 5. Evidence → Finding → Path

### Evidence

|E-id|source_ref|repro_command|content_hash（SHA256）|
|---|---|---|---|
|E-imports|contract-1（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/contract-1.json`），原成员身份及指令/literal|queue_contract.collect()，专项测试调用|a169501f1946d30ab45714fb6694d7dc6eacf52498f4613a7f832d8c53bb3648|
|E-run1|run-1（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/run-1.json`）|observe_queue.py，guest2，固定wall240|f7b543f8dd07439568bcb67d7de86759e00aecba5048e6118a632efb377a4dd9|
|E-run2|run-2（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/run-2-repeat.json`）|observe_queue.py，guest3，固定wall240|ae0dc1ebb7e4a227a38070f2c34ad0907a99a630d4adf5331a3443dc18af83ee|
|E-replay|verification-1（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/verification-1.json`）及verification-current（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/verification-current.json`），逐字节相同|下方重放命令、40类记录错误拒绝|eb7b05b88c5fb79fb10752b8e4be03fa51209af0dd948d66a4b28fb64f96906e|
|E-source|environment-current（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/environment-current.json`），78316全源码/61配方/EXE8DLL、8旧重放、旧50交付|check-queue-r19.py，当前PI scratch；未改旧文件|4348db73719a14af3d9dd380a31b50b4becc7557453e84054187fe6c0655cfbf|
|E-tests|专项（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/tests-full-1.log`）、候选工具（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/tests-candidate-1.log`）、原断言夹具（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-queue-r19/tests-legacy-1.log`）|下方回归命令；241＋11＋38，零跳过|逐项摘要由交付清单封存|
|E-old-failure|r18本轮fresh前缀重放（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-business-r18/r19-queue-prefix-replay.json`）|旧prefix verifier，仍full_run_passed/accepted_run=false|7fb41d7f187530e6fb2c53c7b258cda331f1f536e97f347d56be07e2df63377b|

### Findings

|F-id|severity|evidence_ids|confidence|location|status|
|---|---|---|---|---|---|
|F1双参数队列可自然返回|n/a_re|E-imports/E-run1/E-run2/E-replay|high，仅本有限窗口|两侧queue回调及外层kind2调度|10条局部链通过；不是业务语义/完整ABI|
|F2长内层调用不等于死锁|n/a_re|E-run1/E-run2/E-source|high，限新进程|slave目标100B5D2B，约1.073/1.087模型秒|自然返回已观察；未追踪其内部等待根因|
|F3旧失败不可晋升|n/a_re|E-old-failure/E-source|high|r18两个原失败与本轮新进程|旧结论不变，不能跨进程拼接|
|F4整体端口/刷入安全未证|n/a_re|E-source/E-replay|high|PORT及Q/U门槛|第一阶段未放行、第二阶段未进入、真机关闭|

**P1，path_type=callflow**：自然kind2 BLX（独立对象/消息/TCB）→ 原PUSH → LDRD两索引 → 原STR消费0→1 → 独立slot/字段/literal参数 → 原内层BLX → 自然到内层返回点并原B回队列 → LDRD索引1=1 → 原POP → 外层原B回调度循环。对应E-imports/E-run1/E-run2/E-replay、F1/F2。

**P2，path_type=solve**：r18“未返回”保持未知 → 静态提取内部192槽与嵌套调用 → 新独立有限观测、不监听注册/不扩旧界 → 两窗口自然返回 → 排除“仅凭短窗就判死锁”的推断，但不消除Q1～Q6缺口。对应E-old-failure/E-source、F3/F4。

### 时间线与决策增量

- UTC 13:51:50：冻结r18旧50交付与README31,001字节前缀；新合同测试因缺模块红。
- 采集前：静态合同发现不透明literal指针假设错误，保留初版/失败；修正后6项绿，才启动动态采集。
- UTC 13:56:38.666227起：PID37984，2秒目标，45事件、5条自然返回；独立重放通过后才第二跑。
- UTC 13:57:31.207538起：PID56128，3秒目标，同样45事件/5条返回；局部重放及40错误类拒绝。
- 后续：14新测试、241＋11＋38回归；UTC 14:04:54.442273来源收据完成，78316源/61配方/8历史重放/旧50交付通过。
- decision_delta：由“内部队列/内层返回未知”更新为“本新有限窗口10条完整队列返回链”；不再把该静态目标称为只见入口，但旧r18同次结果、注册来源、内层等待语义及完整阶段仍未证。
- carry_forward_refs：[scope](../../analysis/fenestra-z62-queue-r19/scope.md)、[r18报告](2026-11-07_分析-Fenestra-Z62业务回调r18-report.md)、PORT（本地证据，未分发：`<WORKSPACE>/fenestra/z62/PORT.json`）。

## 6. 复现与未完成工作

工程根运行；本机Python3.12.0/Capstone5.0.7；实际PI scratch在D盘当前会话，不使用guard返回的旧C盘scratch。技能tool-index/precedent/ops证据契约文件实际缺失已检查；已读RE工作流、报告模板和vendor Base，未启动IDA或安装工具。无恶意软件/攻击链，IOC/ATT&CK不适用。原Fenestra许可证及署名保持，不新增无限商业许可假设。

离线重放不启动QEMU；输出使用全新时间戳，不能覆盖已有证据：

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR" PYTHONDONTWRITEBYTECODE=1
stamp=$(date +%Y%m%d-%H%M%S)
python -X utf8 -B fenestra/z62/verify_queue.py \
  --run analysis/fenestra-z62-queue-r19/run-1.json \
  --run analysis/fenestra-z62-queue-r19/run-2-repeat.json \
  --output "analysis/fenestra-z62-queue-r19/replay-$stamp.json"
```

本轮实际已运行的全量回归命令；fixture输出必须仍在r14目录且全新：

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR" PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
stamp=$(date +%Y%m%d-%H%M%S)
python -X utf8 -B tools/z62_reconstructed_fixtures.py test \
  --work .build/fenestra-z62-fixtures-r14-01 \
  --output "analysis/fenestra-z62-model-r14/r19-legacy-$stamp.json"
```

确需重采时，先确认无Win32 QEMU/Q:占用，并核固定r13来源；以下仅启动本地模拟器，不接相机，仍保持同一上限：

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR" PYTHONDONTWRITEBYTECODE=1
stamp=$(date +%Y%m%d-%H%M%S)
python -X utf8 -B fenestra/z62/observe_queue.py \
  --output "analysis/fenestra-z62-queue-r19/resample-$stamp-1.json" --guest-seconds 2
python -X utf8 -B fenestra/z62/observe_queue.py \
  --output "analysis/fenestra-z62-queue-r19/resample-$stamp-2.json" --guest-seconds 3
```

剩余工作不是“等采样完成”：本轮自有进程均已退出，没有后台等待。需要真实实施完整copied-service SDK、原任务/同步/卡文件、模块菜单/正常关机集成候选；补同次创建注册—启动—消息业务完成、失败/System/flags/耗尽/退出删除复用，解释r10的73待配对；补自然堆释放/合并复用及等待返回/通知唤醒合同；恢复真实完成事务并关闭35/3F及其他成功假设；补空间/早加载/cache-DMA合同及完整候选矩阵。旧r69精确来源仍缺，r13新来源不冒充旧身份。

在这些Q项全部通过之前，**不冻结可刷候选、不启动第二阶段验收、不连接真机刷机**；其后也必须完成同一镜像U1～U6及独立物理恢复条件。10次有限返回、全部工具绿和QMP清理不能代替这些条件，更不能变成绝对安全承诺。
