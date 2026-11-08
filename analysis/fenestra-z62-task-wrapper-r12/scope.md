# Fenestra Z62 原厂创建封装 r12

- stage: static → dynamic → synthesis；仅第一阶段局部合同，不放行 Q1～Q6。
- target: 原 Z6II C1.70 MAIN/SUB，固定 r69 SHA；延续 r11 路线，原 Fenestra/自研 Z62-QEMU，不替换系统。
- imports-equivalent / E-imports: 裸 ARM/Thumb 成员无传统导入表；共享 Thumb 入口、相邻 veneer、创建封装到 ARM SVC #6 服务桩、内核创建/启动入口作为局部服务锚点。不是恶意软件或漏洞审计（flavor=null，severity=n/a_re）。
- tools: 本机 Python 3.12 / Capstone 5.0.7；IDA 技能的 tool-index.md、field-journal/precedent-reverse.md 不存在，已记录；不启动 IDA、不安装工具。参考 re-agent-workflow.md。
- write-root: 当前工程；临时文件只放本会话实际 PI_SCRATCH_DIR（<PI_SCRATCH>），不采用 guard 返回的旧 C 盘 scratch。
- network: offline；QEMU -nic none；GDB/QMP 127.0.0.1。
- immutable: 不改 r1～r11 绑定源码/测试/证据、原包/成员、固定 r69；README 仅追加。
- allowed: 原 boot-image/复位入口，读取寄存器/有界内存、硬件执行断点、原指令 vCont;s:CPU 隔离单步、暂停继续；读取 stop thread，不信陈旧 qC，ticks 后恢复停核。
- forbidden: 客体指令/PC/RAM/返回值/ready 补写、注入调用、补事件/完成逻辑、相机/USB/PTP/物理卡或磁盘/刷机/发布/提交。
- hypothesis: 原封装自然执行会将输入对象/回调/配置映射到内核配置与 TCB，再原指令存储返回字和 +4 回调字段，之后使用该返回字调用启动服务。只核同次关联，地址/句柄/CPU/名称不作稳定任务身份。
- dynamic acceptance: 两独立自有进程；所有纳入配对的阶段完整且自然发生，输入/源码/ROM/PC/ISA/停核/系统/内存窗口/断点/单步/QMP/日志/退出可重放；有限上限、quiet、未知模式或歧义不晋升。
- limitations: 不证明完整结构/所有权、任务退出删除复用/耗尽失败/System模式/业务完成、完整 SDK/卡/菜单/关机/候选/可刷镜像；r10 的 73 待配对未解决。默认 gate/transfer-reset/sequencer completion 仍启用，精确 r69 source 缺失。
- transition: 完整 Q1～Q6 全通过才冻结唯一镜像验 U1～U6；前两阶段及独立物理恢复/供电/cache-DMA/存储/时序缺口关闭前不上真机。绝对零风险要求未满足。

## Synthesis decision_delta

- 原服务800A0200/index0A指向1010B4E8/1003CEBC，与r10/index3首次启动入口不同。内部start/native_start/started标签仅指本封装该服务的调用/入口/返回，不晋升完整启动API。
- 独立入口读原未赋值配置+28字；同次配置/TCB、STR/STRD与服务0A返回93链局部成立，输入+10标签和原空名称模板分离。地址/标签/返回字不是稳定身份。
- 修新工具字段名、服务入口、零值假设、双侧停止覆盖问题；0.1.4核验器补同次SVC栈/r4，红绿复核。失败/诊断保留，旧绑定文件不改。
- 两正式PID38728/34372分别主1从41/主4从47，52未匹配内核停点另存；未扩大原准备/事件/时间上限。带断点仅0.004345/0.004989模型秒，不作完整生命周期或物理时序证明。
- carry_forward_refs: r11 scope/报告、当前PORT；r12 contract-strict.json/run6/run7/verification-nested-final.json；根目录r12报告。
- Q1～Q6仍未全通过；U1～U6未进入验收；相机/USB/PTP/物理卡磁盘/刷机未使用，真机门槛仍关闭，绝对安全未证。
