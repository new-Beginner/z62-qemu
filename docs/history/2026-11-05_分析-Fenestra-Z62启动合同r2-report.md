# Fenestra Z62 原厂启动合同 r2

**不能刷机，不能上真机。完整移植仍未完成，`firmware_integrated=false`、`flash_safety_verified=false`。**

## 1. 结论与范围

本轮为 Fenestra ARM32 移植恢复了 Z6II C1.70 自身的早期启动、初始化表、页表与指令状态合同，并在用户已有自研 r69 Z62-QEMU 上实际观察了原厂主/从镜像。最终两个独立进程均到达复制前、复制后、Thumb 运行时及 ARM 内核入口；四段早期复制共 820,912 字节逐字节一致。它比上一轮无固件加载器试验增加了原厂环境证据，但**没有把 Fenestra 集成进原厂固件**，也没有找到已经证明可安装、可持久保留的代码空间。当前不生成更新包、不接触物理相机，后续仍须补齐平台 ABI、生命周期及更新/恢复证据。

- 原始目标：A，一直Fenestra，并且使用自己开发的z62qemu验证是否可行，然后确定刷入没问题以后再上真机，主要保证真机一定要没问题。
- 授权与边界：[scope.md](../../analysis/fenestra-z62-startup-r2/scope.md)。仅本地离线固件分析与 QEMU；GDB/QMP仅本机环回，无外部网络或USB/PTP/物理卡操作。
- 报告类型 `flavor=null`：固件逆向，不是恶意软件或漏洞利用报告。
- 保留原4份固件输入、r69 可执行文件、旧实验记录和用户既有改动。Z62 子模块保持干净，未提交/推送。

## 2. 样本与方法

| 项目 | 值 |
|---|---|
| 主成员 | `artifacts/z62-reference-1.70/master.bin`；38,750,138字节；SHA256 `bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4` |
| 从成员 | `artifacts/z62-reference-1.70/slave.bin`；8,832,194字节；SHA256 `3fd8c2cbdf57fadb03f6d69b596b58a8703efdd61ae82572d5afeea0241a9ed5` |
| 成员基址 | `0x10020000`；下文地址均为运行地址，文件偏移需减去该基址 |
| QEMU | `.build/z62-output-lineage-2026.11.03-r69/runtime/qemu-system-arm.exe`；SHA256 `37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9` |
| 工具 | Python 3.12、Capstone 5.0.7；已有 RSP/GDB 客户端、QMP |
| 导入表等价锚点 E-imports | raw ARM/Thumb 镜像无 ELF/PE 导入目录；改查原始 literal、直接分支、经 r3 的 Thumb 分发表及运行时/内核调用。见 `contract-1.json` 的 `imports_equivalent` 和 `instruction_windows`，不据此否定文件/网络能力 |

每次执行先按 SHA256 绑定原始输入与 QEMU。模型 `master/slave-boot-image` 预装完整成员，QEMU loader 初始化各核复位 PC；随后原厂 EG 指令自行前进。**相机更早的引导加载器没有执行**，因此预装完整镜像不能证明相机实际会加载相同长度或接受修改镜像。

本次不加载控制器、校准参数、卡或插件。调试器只使用 Z1 执行断点、原指令单步、读寄存器和读内存，不写运行中的 PC/RAM/返回值。结束用 QMP quit；这是正常结束自有模拟器，不是相机正常关机证明。断点扰动时序，不作性能验收。

## 3. Z62 自身合同

### 3.1 早期入口与页表

| 合同 | master | slave |
|---|---|---|
| ARM EG 启动入口 | `0x1002BC88` | `0x1002BC88` |
| 原 TTBR0 / DACR | `0x10030000` / `0x55555555` | 同左 |
| VBAR | `0x10100000` | `0x10034100` |
| core0 SVC 栈顶 | `0xC2B68000` | `0xC18E8000` |
| ARM 运行时 veneer | `0x104393A4` | `0x10167090` |
| Thumb 运行时 | `0x104393AC` | `0x10167098` |
| ARM 内核入口 | `0x100200AC` | `0x100200AC` |
| 初始化记录 | 20条：4复制、16清零 | 15条：4复制、11清零 |
| 表声明的全部复制字节 | 1,518,352 | 197,644 |
| 成员有效载荷尾端，不含CRC | `0x125147B8`，exclusive | `0x1088C4C0`，exclusive |

最终观察点的 secure 寄存器为 TTBR0=`0x10030000`、TTBCR=0、DACR=`0x55555555`、SCTLR=`0x00C5107D`，VBAR 与各自原厂 literal 一致。MMU、I/D cache 位均开启，AFE/TRE=0；所记录 CPU 的 secure/non-secure DFSR/IFSR 都为0。两角色原始16KiB页表读回均与自身成员逐字节一致。这些是模拟器观察值，不是物理硅片或缓存一致性验收。

### 3.2 复制与清零不能混淆

早期 ARM 循环位于 `0x1002BE74`、`0x1002BED0`、`0x1002BF2C`；第三段 literal 长度为0。另有 `0x10034000` 开始的16字节记录表，声明第三、第四段的非零长度及大量清零区间。表分发代码 `0x10020038` 根据 handler 字段置 Thumb 位，再经 r3 跳转；处理函数为 `0x1002006C` 和 `0x10020088`。

| 角色 | 源 → 目标 | 表中长度 | 早期内联长度/本次动态内容检查 |
|---|---|---|---|
| master | `0x123A1C14 → 0xC1800000` | `0xAEDB8` | 同表长度，全部一致 |
| master | `0x12450A00 → 0xC2B90000` | `0x105C` | 同表长度，全部一致 |
| master | `0x12451A80 → 0xC2B91080` | `0x46884` | 内联为0；仅64字节头部样本前后相同 |
| master | `0x12498340 → 0xC6100000` | `0x7C478` | 无对应早期内联；未作内容执行验收 |
| slave | `0x1085C054 → 0xC1000000` | `0x17DC8` | 同表长度，全部一致 |
| slave | `0x10873E40 → 0xC1910000` | `0xAD4` | 同表长度，全部一致 |
| slave | `0x10874940 → 0xC1910B00` | `0x13B70` | 内联为0；仅64字节头部样本前后相同 |
| slave | `0x108884C0 → 0xC6000000` | `0x4000` | 无对应早期内联；未作内容执行验收 |

本窗口没有捕获到 `0x10020038` 的执行，不能将表存在解释为“整表自然启动分发已经通过”，也不推断后续内核绝不会使用它。清零记录中的源字段不表示需要读取那段文件；提取器不会按其巨大长度分配缓冲。

### 3.3 代码空间门槛仍关闭

- Z62 地址、长度及栈与 Z7II 不同；上游 Z7II 资料仅作定位线索，本轮结论来自 Z62 原字节及其运行。
- 原页表包含 `0x13C00000` 等成员尾端以后的映射；**映射不是有加载内容、有物理容量或已保留空间的证据**，不能沿用上轮无固件探针的合成地址作为安装方案。
- 初始化表明确声明的复制/清零区间不能因当前内容为零就当作空闲；本轮没有恢复运行时分配器、所有权和生命周期。
- 尚无启动完成/正常关机钩子、卡文件 ABI、线程与缓存维护的完整适配，也没有生成 Fenestra 集成候选。

## 4. Evidence → Finding → Path

### Evidence

| E-id | source_ref | repro_command | content_hash |
|---|---|---|---|
| E0 | `analysis/fenestra-z62-r1/verification-round2.json` | 既有 `verify_evidence.py`，参数见上一阶段 README | 文件内绑定原构建/两次运行及原始输入 |
| E1 / E-imports | `analysis/fenestra-z62-startup-r2/contract-1.json` | `startup_contract.py --output <新analysis路径>` | SHA256 `1488f89470586902cde6453536361a6b7e349545a76f2b17dd99ee504d16b5e7` |
| E2 | `run-5-final.json` | `observe_startup.py --output <新analysis路径>` | SHA256 `7eea3723de330226272caf2fb15055dd898f8b8837459ed45abd1fc1913b992b` |
| E3 | `run-6-repeat.json` | 同上，独立新进程 | SHA256 `6797ab443c376305f604fd9f429eb8c3c413f3b4a4e54485043865789006725c` |
| E4 | `analysis/fenestra-z62-startup-r2/verification.json` | `verify_startup.py`，完整参数见第5节 | SHA256 `6f99f257063f1d0ee7048fb60aded768a138471ae637ac0bf8317369dd5d8ab6` |
| E5 | `fenestra-tests-final.log` / `candidate-tests-final.log` | 第5节 unittest 命令 | SHA256分别为 `d1d0d8a594075db3a6c4f3572784ef69fa084f40f85569aea5857b119c0dd0b4` / `a6922dafb1639e434eba39f7e25f1b1d768f64da92b283c54f6c1f750975c03f` |

E2/E3/E5 的短文件名均相对 `analysis/fenestra-z62-startup-r2/`。各运行文件还绑定工具源码与 QEMU 日志 SHA256，E4 重新计算静态合同并检查原4份输入和干净子模块。

### Findings

| F-id | severity | evidence_ids | confidence | location | status |
|---|---|---|---|---|---|
| F1 Z62专属启动合同已恢复 | n/a_re | E1 | high（静态） | 主/从入口、literal、记录表、页表 | verified_static |
| F2 原厂早期复制/指令切换实际执行 | n/a_re | E2,E3,E4 | high（限定QEMU窗口） | 四段复制、两角色运行时及内核入口 | verified_bounded |
| F3 原参数/控制器/卡不是本早期窗口前提 | n/a_re | E2,E3 | high（仅此窗口） | 两份有效命令行 | verified_bounded；不推广到启动完成 |
| F4 不能据映射/空白认定安全代码空间 | n/a_re | E1,E4 | high（证据不足结论） | 成员尾端及声明的初始化区间 | installation_space_unverified |
| F5 Fenestra集成与刷机安全未成立 | n/a_re | E0,E4及PORT.json | high（当前状态） | 平台服务/候选/更新/恢复缺口 | unverified |

P1，`path_type=callflow`：EG ARM入口 → 早期三循环（仅前两段非零） → 各自 ARM veneer → Thumb运行时 → 原厂运行时调用 → ARM `0x100200AC`。静态窗口保留原指令，动态 E2/E3 确认关键点到达；**不延伸为启动完成、菜单或关机链**。

### Timeline 摘要

1. 重新核验上一阶段加载器、原输入与QEMU身份，结果通过。
2. 静态提取两角色原字节；新增7项解析器测试。首次测试因样例 AP 预期值写错失败；核对bit15和bits11:10，修正并补AP[2]样例后通过。
3. `run-1.json`：持续同地址执行断点重触发，观察不完整；进程正常退出。修复调试器移除/单步/重装流程。
4. `run-2.json`：主侧到达内核入口，但 `qC` 保留旧 Hg 选择，读错多核停止对象；不计双侧通过。改用停止包的 `thread:` 并补测试。
5. `run-3.json` / `run-4-repeat.json`：窗口通过，保留为旧仪表版本记录。随后明确复位PC与运行中调试器写入的字段语义，并扩充源码绑定。
6. 最终 `run-5-final.json` / `run-6-repeat.json`：两个独立进程（57816/22400），各9次观察、四段内容检查通过，均exit0且已关闭。E4核验通过；17+11项测试全部通过、无跳过。
7. 卡读ABI只读委派未返回可采纳结果，已停止，不将其视为定位或适配完成。

## 5. 复现

在工程根的 Git Bash 执行，要求原私有成员、固定QEMU、Capstone，以及已验证指向本工程的 ASCII `Q:/` 别名。各输出名称必须尚不存在；示例不覆盖当前证据。

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR"
export PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
python -X utf8 -B fenestra/z62/startup_contract.py --output analysis/fenestra-z62-startup-recheck/contract.json
python -X utf8 -B fenestra/z62/observe_startup.py --output analysis/fenestra-z62-startup-recheck/run-a.json
python -X utf8 -B fenestra/z62/observe_startup.py --output analysis/fenestra-z62-startup-recheck/run-b.json
python -X utf8 -B fenestra/z62/verify_startup.py \
  --static analysis/fenestra-z62-startup-recheck/contract.json \
  --run analysis/fenestra-z62-startup-recheck/run-a.json \
  --run analysis/fenestra-z62-startup-recheck/run-b.json \
  --output analysis/fenestra-z62-startup-recheck/verification.json
```

验证器的 `bounded_early_startup_verified=true` 只覆盖上述窗口，不是用户整个目标完成。运行失败时保留JSON和日志，不删身份检查，不写客体状态推进。

## 6. 全目标验收与后续

| 要求 | 当前结果 |
|---|---|
| 坚持A，移植Fenestra到Z6II C1.70 | 未完成：ARM32加载器通过，尚缺完整原厂平台适配/候选 |
| 用用户自研Z62-QEMU验证修改固件/插件可行性 | 部分证据：无固件模块探针及本轮原厂早期窗口；尚无集成候选A/B |
| 确定刷入无问题前不进入真机 | 本轮遵守：未接触相机、无可刷包 |
| 真机一定没有问题 | 未验证，不能作绝对保证；QEMU不能覆盖全部物理、更新、断电和恢复风险 |

继续离线恢复：内核实际初始化调用链、可证明的内存保留与代码加载边界、原厂任务/分配/卡读ABI、启动完成和正常关机窗口；再做Fenestra最小平台适配及独立候选原版/停用/激活A/B。更新摘要B8/K8、主从资格、NOR/持久化、缓存/DMA、断电/恢复及压力测试仍独立待证。缺证期间真机门槛保持关闭。
