# r18 有界原厂业务回调观测范围

- 原始目标：完成 Nikon Z6II C1.70 原 Fenestra 移植；先自研 z62qemu 完整验证，再镜像/刷入验证，最后真机。绝对安全未证，三个阶段门槛不降低。
- 本轮 decision_delta：r17 已核同次创建—启动—共享 BX—目标首指令；其字段目标可能是循环调度层而非普通可返回函数。本轮独立观察 setter 入口→原 STRD 写对象+0x24/+0x28→同对象自然业务 BLX→真实返回→原 B 回循环。两种调度参数分别 message 和 object,message，不混用。
- carry_forward_refs：`analysis/fenestra-z62-task-chain-r17/scope.md`、`verification-final.json`、`deliverables-final.json`；所有 r1～r17 绑定源码/测试/证据不改，README 仅追加并冻结当前前缀。
- 输入：原主从 C1.70；`startup_contract.PROFILES` 长度/SHA核验。裸 ARM/Thumb 无动态导入表；E-imports 等价锚点为两组原 setter/STRD、对象+0x24读取/BLX及原 B 回循环，另存完整反汇编合同。仅 Python3.12/Capstone5.0.7 与现有可追溯 r13 EXE/8DLL，未用 IDA 服务。技能 precedent-reverse.md/tool-index.md 实际缺失，不冒称已读、不安装工具。
- 自研模型 `.build/fenestra-z62-model-r13-03`，非旧 r69 来源恢复；默认 gate/sequencer/transfer-reset completion 仍开，其他成功假设未清除。启动 boot-image 和 loader 复位初始化不是卡加载/认证/刷入。
- 所有采集无 controller/合成参数/卡/Fenestra；`-nic none`、GDB/QMP 127.0.0.1；不访问相机、USB/PTP、物理卡盘、外部服务，不刷机。
- 只读有界内存、硬件执行断点、原指令隔离单步；停核用停止包 thread，单步 vCont;s:<CPU>，ticks 后恢复原核。不修改原指令/运行PC/寄存器/RAM/返回值，不补调用/ready/成功事件。
- 固定上限：128 次 setter、128 次业务调用、1024 事件；15 秒单次 quiet；wall 30..300 秒，默认240；最低8..32个已返回调用；主从各有已返回样本并覆盖两种签名，活动setter/调用须排空。触界/quiet/未配对/未返回另存，不扩界或补调度晋升。
- 配对：setter 以同 role/类型/SP/原对象，store 核保存栈及 r4/r5/r6/r7，原 STRD 前后独立48字节仅+0x24..+0x2B变；call 以同 role/类型/对象最新已完成注册唯一关联；当前TCB/句柄/对象/调用SP仅同次活动配对，不当稳定任务身份或生命周期所有权。返回允许跨同role核，核相同TCB/句柄/对象、SP、r4..r11、Thumb返回点及原B效果。不将回调返回值视成功状态。
- 所有调用原字段、消息栈字、TCB、目标ROM独立读；BLX真实执行后核PC/ISA/LR/参数/系统及current；返回只证明到原循环，未证消息语义/业务正确、任务出口/删除复用、完整描述符/SDK/生命周期、硬件等效。
- 写入限工程正式相关文件与实际 PI_SCRATCH_DIR；guard旧C盘scratch不采用。仅自有Popen进程关闭和同目录samefile核验的自建Q:清理；退出0/QMP quit不是相机正常关机。
- Q1～Q6未全部通过前不冻结刷入候选；U1～U6未进入验收；真机关闭，absolute_safety_verified=false。
