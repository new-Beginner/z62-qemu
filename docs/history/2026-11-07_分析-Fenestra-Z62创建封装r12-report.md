# Fenestra Z62 创建封装 r12：字段来源、配置与服务 0A

> 2026-11-07；原 Fenestra＋自研 Z62-QEMU；flavor=null；severity=n/a_re。
> **整体移植未完成。第一阶段未放行，第二阶段未进入验收，真机关闭；没有可刷 Fenestra 包，不能保证真机刷入和运行绝对不出问题。**

## 1. 本轮结果和边界

新增独立合同、只读观察器、核验器及 17 项测试，不改 r1～r11 绑定源码/证据、原 C1.70 或固定 r69。两个独立原厂进程核对 **93 条创建封装→内核创建→原字段写入→服务 0A 返回**九阶段链。主侧 5 条、从侧 88 条；52 个未匹配的共享内核停点单独保留，不算成功调用。142 项专项和 11 项离线候选工具测试通过，无跳过；加强核验器拒绝 33 类定向错误记录。

本轮补的是原厂接口局部证据，不是原厂固件修复或完整 Fenestra 后端。没有将插件注入原厂任务，没有验证任务退出/删除复用、耗尽失败、完整同步、卡文件、copied-service SDK、模块管理/菜单、正常关机或完整生命周期。PORT（本地证据，未分发：`<WORKSPACE>/fenestra/z62/PORT.json:3`） 仍为 `experimental-loader-only`。范围与禁止事项见 [scope](../../analysis/fenestra-z62-task-wrapper-r12/scope.md)。

## 2. 各阶段验证项、标准和进入条件

### 第一阶段：在自研 z62qemu 验证完整移植

| 验证项 | 通过标准 | 当前状态、问题和实际修补 |
|---|---|---|
| Q1 ARM32 模块/SDK | 原厂环境中完整模块格式、重定位、入口及 copied-service SDK 真实执行；合法和错误模块处理正确 | 仍仅 r1 合成加载器/legacy v1 日志；完整原厂 SDK 未通过 |
| Q2 启动/关机 | 主从 ISA/栈/MMU/初始化和完整启动、正常关机、再启动均通过 | 仅局部原厂合同；QMP quit、末次 idle 或服务返回 0 不算正常启动/关机 |
| Q3 内存/任务/同步生命周期 | 自然释放、合并复用、flags/耗尽失败、创建启动/异常/删除、同步/所有权及完整生命周期通过 | r12 补字段写入和服务 0A 的局部创建关联；不是完整启动 API。堆释放/生命周期、r10 的 73 待配对仍未解决 |
| Q4 可保留空间/真实加载/cache-DMA | 代码数据空间及所有权、介质早期加载容量、MMU/cache/DMA 发布回收合同明确且实跑 | 未通过；可读地址、原堆分配、清零和可执行映射不能当插件可占空间 |
| Q5 完整原厂 Fenestra 服务 | 任务/同步/卡文件、完整 SDK、模块管理/菜单、启动关机集成真实执行 | 没有完整原厂候选，本轮没有加载 Fenestra |
| Q6 完整矩阵/模型可信度 | 同模型同配置原版/候选停用/启用、合法/错误模块、启停/异常/压力/完整生命周期均通过；关键模型来源/近似缺口关闭 | 未完成。精确 r69 source 缺失；默认 completion/硬件近似和旧关键失败仍保留 |

**Q1～Q6 全部通过、完整候选和模型关键缺口关闭，并可复现地冻结唯一 SHA 后，才进入第二阶段。当前不满足。** 不补调用、事件、ready、成功返回或 guest PC/RAM，不关闭原厂身份/型号/长度检查填覆盖。

### 第二阶段：冻结镜像和完整刷入流程

| 验证项 | 必须达到的标准 | 当前状态 |
|---|---|---|
| U1 镜像资格/边界 | 唯一 SHA，型号版本、主从控制器资格、长度地址正确；互换/截断/越界拒绝 | 无完整候选，未进入验收 |
| U2 原厂认证 | 真实 B8/K8、原厂更新器合法接受且篡改拒绝 | 未验证；CRC/seed/其他机型结果不替代 |
| U3 真实介质早期加载 | 实际介质、容量、入口、地址和主从发布顺序正确 | 未验证；boot-image 预装/复位 PC 不是介质加载或刷入 |
| U4 写入/读回/持久化 | 写入范围正确、NOR/校准保留，读回/重启持久化和冲突处理通过 | 未验证；合成参数/空白卡不是原厂备份 |
| U5 中断/断电/恢复 | 校验、擦除、写入、提交、重启各阶段的中断/超时/断电恢复或回滚均通过 | 未验证；QMP 退出 0 不算更新恢复 |
| U6 可追溯重建 | 同一候选、源码、模型、工具链、依赖、许可证、镜像可重建；关键失败解释完成 | 未通过；固定 EXE 或后续参考源码不是精确 r69 来源 |

**只能在第一阶段放行后，对同一冻结镜像通过全部 U 项。不能拼接不同候选/模型的局部证据。** 11 项候选工具测试只是离线工具回归，不是原厂认证、写入或恢复验收。

### 第三阶段：真机

前两阶段全部通过，并独立关闭物理供电、存储、cache-DMA、硬件时序和可恢复路径缺口，才有讨论受控真机验证的前提。本轮未连接相机/USB/PTP，未操作物理卡/磁盘或刷机。有限模拟器测试不能证明所有未来物理状态绝无问题；用户的绝对保证要求仍**未满足/未验证**，不自行改成“降低风险”后放行。

## 3. 恢复出的局部原厂合同

裸 ARM/Thumb 成员没有传统导入表。E-imports 等价锚点是原封装、SVC #6 服务桩/原分发表、内核配置与 TCB、字段 STR/STRD；不由此推断完整文件/网络/任务能力。静态来源见 合同（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-wrapper-r12/contract-strict.json`）；实现见 task_wrapper_contract.py（本地证据，未分发：`<WORKSPACE>/fenestra/z62/task_wrapper_contract.py`）、观察器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/observe_task_wrapper.py`） 和 核验器（本地证据，未分发：`<WORKSPACE>/fenestra/z62/verify_task_wrapper.py`）。

| 位置 | master | slave |
|---|---|---|
| Thumb 创建封装入口 | `103DEBC6` | `1006CB8A` |
| ARM 创建服务桩 | `101044EC` | `10035F78` |
| 原内核创建入口 | `1010A268` | `1003BC3C` |
| 构造完成、原 LDR 前 | `1010A6D4` | `1003C0A8` |
| 返回字 STR / 回调 STRD | `103DEC3C` / `103DEC44` | `1006CC00` / `1006CC08` |
| 相邻服务 veneer | `103DEBC0` | `1006CB84` |
| 服务 0A 内核入口 | `1010B4E8` | `1003CEBC` |
| 服务返回、原 ADD SP 前 | `103DEC64` | `1006CC28` |

地址均为十六进制。共享入口 `103DEBBC/1006CB80` 的原字节仍是 `49680847`。`103DEBC4` 落在前条 B.W 的尾半字，不能将从该处误反汇编出的 CBNZ 当真实函数分支。

九阶段为入口、创建调用前、内核创建入口、构造完成、创建返回、字段写入前、服务调用前、服务 0A 内核入口、服务返回。工具沿用 `start/native_start/started` 三个内部标签表示最后三项，**不代表 r10/index3 的首次启动 API**。原服务号 `0x800A0200` 指向分发表项 0A；r10 的 `1010A91C/1003C2F0` 是表项 3。该区别已由原服务桩/分发表和实际命中入口核对。

同次封装入口 r0 为对象地址、r1 为回调输入、r2 为 28 字节输入配置。以下只描述本次观察到的复制关系，不是完整结构或所有权 ABI：

- 本地配置 SP = 入口 SP − 104。配置首字为对象地址，flags 为 `1/0x20001`，入口为原共享 Thumb 入口，后两字取输入配置 `+4/+8`。模式字节 0/1/2 的样本均有，但不能把它们等同 System 模式或完整 flags 矩阵。
- 配置 `+0x28` 没有被封装初始化。在入口 SP−64 独立读其原字，再要求创建调用/内核入口/构造完成时保持相同；93 例中 85 例非零。不解释该字的完整语义，不将其强置零。
- 内核配置前三字、初始帧和 8 字节名称与 TCB `+C/+10/+14`、保存 SP/CPSR/PC、`+CC` 相符。两次 SVC 入口 SP 均为本地配置 SP−36，r4 指回本地配置 SP；仅为这 93 例的同次关联，不是完整异常/系统调用 ABI。
- 原 STR 将本次 TCB `+8` 返回字写对象 `+0`；原 STRD 将入口 r1 写对象 `+4`，输入 `+4` 写对象 `+8`。两条指令前后对象 32 字节逐字核对，不是调试器补写。
- 输入 `+8` → 对象 `+C`，模式字节 → 对象 `+10`，输入 `+C` → 对象 `+14`。输入配置 `+1A` 的半字自然更新为本次返回字低 16 位；其余输入字节保持。
- **输入配置 `+10` 的 8 字节标签与内核名称不同。** 当前标签包括 `DBGUART`、`PKGB1/2`、`WTDG` 等；封装使用独立原名称模板，93 例传入内核/复制到对象 `+18` 的名称均为空。该结果解释当前样本的来源，不能倒推出全部 r9 空名或完整业务任务名单。
- 最后调用服务 0A 时，内核入口 r0 为该返回字、r1 为 1，返回到封装的 r0 为 0。未跟踪服务全部分支、外层封装 POP 返回、回调业务完成或退出删除复用。

地址、标签、句柄字和 CPU 仅用于同次配对，不是跨主从/进程/删除重建的稳定身份。r12 没有在同一运行里接续 r11 的首次回调链，不能把两个不同运行拼成完整生命周期证明。

## 4. 实跑、问题与修补结果

| 正式记录 | PID | 主/从链 | 事件/未匹配内核停点 | 带断点末主模型秒 | 最终主模型秒 | 宿主秒 |
|---|---:|---|---|---:|---:|---:|
| run-6（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-wrapper-r12/run-6-final.json`） | 38728 | 1 / 41 | 404 / 26 | 0.004345479 | 2.550106417 | 31.516 |
| run-7（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-wrapper-r12/run-7-repeat.json`） | 34372 | 4 / 47 | 485 / 26 | 0.004989125 | 3.852386792 | 46.813 |

目标 24、原准备阈值 56（正式核验要求低于该值）、事件上限 1792、宿主上限 180 秒均未放宽；需双侧覆盖且全部配对完成才停止，因此得到 42/51 条。均 `sample-bound-drained`、pending 空、最终客体目标达到。带断点窗口仅约 0.0043/0.0050 主模型秒，之后撤断点运行不是全过程跟踪。ticks 按既有 48MHz 模型口径折算，不是物理时序验收。末次四核 idle/所读故障零不证明完整启动或没有所有固件 Error。

| 发现的问题 | 保留的证据 | 实际修补与复核 |
|---|---|---|
| 新代码使用不存在的 `op_str` 字段 | `tests-first.log` 的 KeyError | 改用旧接口 `operands`，原边界/BLX 测试通过；未运行客体 |
| 误把封装服务等同 r10 入口 | `run-1-final.json`，PID35460，19 事件后阶段顺序失败 | 从原 `800A0200` 与表项 0A 恢复入口；新增红绿回归，不删除缺失阶段凑通过 |
| 误认为未赋值栈字应为零 | `run-2-final.json`，PID53096，17 事件后配置比对失败 | 增加入口独立原字读取，完整配置逐字保持核验；新增红绿回归，未强写零 |
| 只以总样本数停止导致双侧覆盖不足 | 覆盖诊断（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-wrapper-r12/coverage-diagnostic.json`）：run4 主9/从15，run5 主0/从24 | 保留 0.1.2 诊断。0.1.3 将既有双侧要求接入停止条件，未扩大上限；新两跑均满足 |
| 核验器只凭返回字/参数，漏检一致改变前后 SP 的服务现场 | `tests-nested-red.log`：ValueError not raised | 0.1.4 增加同次 SVC 栈/r4 关系，定向负例拒绝，原两跑重新通过；观察器和记录不改 |
| 版本/导入行编辑差错 | 差异检查后按当前正文恢复 | 错版未用于运行/核验；最终 AST、全量测试和源绑定重放通过 |

所有失败/诊断、三轮初版源码快照和旧 0.1.3 核验器保留，没有把诊断晋升正式通过。**修的是研究工具和证据缺口，不声称修复了原厂业务问题。** r10 的 73 待配对没有解决；没有扩大其旧上限、补调度或抹除旧失败。

当前权威结果是 0.1.4 加强核验（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-wrapper-r12/verification-nested-final.json`），SHA256 `c3e3847cc8c8b7215fea3d0ab372212ef6d109e96b6188c7a270b41acf254258`。旧 `verification-1.json/verification-repeat.json` 为 0.1.3、32 类负例，不能冒充新版。工具错误记录测试不是原厂错误模块、故障调用或断电验收，也不证明能检测任意一致伪造。

## 5. 环境、清理与复现

当前环境（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-wrapper-r12/environment-current.json`） 重新核对原整包/主从/controller、r69 EXE 摘要及 Fenestra/参考仓库状态，与 r11 一致。Fenestra 固定 `b199dcdf`，仅原两个 loader 文件修改；参考 `4f43899` 干净。精确 r69 source 仍不存在，未重编或更换模型。两侧默认 gate/transfer-reset/sequencer completion 仍 true；实验开关 false 不等于无完成逻辑。

旧文件核对（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-wrapper-r12/old-r11-files-after.json`） 的 32 份不可变文件长度/SHA 一致（共享 README 仅追加，不纳入旧不可变集合）。r9/r10/r11 旧记录已重新核验：创建（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-wrapper-r12/create-r9-reverified.json`）、首次入口（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-wrapper-r12/entry-r10-reverified.json`）、字段回调（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-wrapper-r12/callback-r11-reverified.json`）。

清理记录（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-z62-task-wrapper-r12/cleanup-final.json`） 于 17:05:39 检查 Win32 无 QEMU、Q: 不存在；六个自有进程均 QMP quit 有应答/退出 0。没有委派或后台等待。只使用本地无网 QEMU、127.0.0.1 GDB/QMP；没有控制器/卡/参数/Fenestra 候选、相机/USB/PTP/物理卡磁盘/刷机。QMP 退出只证明宿主清理，不是相机正常关机/恢复。

在工程根、保留固定原输入和 runtime 的环境中，重放不需要 Q: 或 QEMU 进程，输出名必须不存在：

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR" PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B fenestra/z62/verify_task_wrapper.py \
  --run analysis/fenestra-z62-task-wrapper-r12/run-6-final.json \
  --run analysis/fenestra-z62-task-wrapper-r12/run-7-repeat.json \
  --output analysis/fenestra-z62-task-wrapper-r12/verification-reproduction.json
```

回归命令（本轮已执行，142+11 均通过、无跳过）：

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR" PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
```

重新动态观察的等价安全入口（新输出、无现有 QEMU/Q: 才运行；本轮实际两跑见 `runs-host-4.json`）：

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR" PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B - <<'PY'
from pathlib import Path
import json, subprocess, sys
root=Path.cwd();sys.path.insert(0,str(root/'fenestra/z62'))
from observe_task_wrapper import run
q=Path('Q:/');assert not q.exists()
ps="[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); $p=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'qemu-system-*' } | Select-Object ProcessId); ConvertTo-Json -InputObject $p -Compress"
p=subprocess.run(['powershell.exe','-NoProfile','-Command',ps],capture_output=True,check=True)
assert json.loads(p.stdout.decode('utf-8-sig'))==[]
outputs=[root/'analysis/fenestra-z62-task-wrapper-r12'/n for n in ('run-reproduction-1.json','run-reproduction-2.json')]
assert all(not p.exists() and not p.with_suffix('.qemu.log').exists() for p in outputs)
owned=False
try:
    subprocess.run(['subst.exe','Q:',str(root)],check=True);owned=True;assert q.samefile(root)
    for p,target in zip(outputs,(2,3)):run(p,24,target,180)
finally:
    if owned:
        assert q.samefile(root);subprocess.run(['subst.exe','Q:','/D'],check=True)
PY
```

工具源码只接受有界只读窗口和原指令隔离单步；停止包取实际 CPU，ticks 后恢复原核。有限上限/quiet/未知模式/歧义仍保存为诊断，不保证不同调度必然得到相同样本量。重跑结果仍须核验，不能仅看观察器 `completed`。

## 6. Evidence → Finding → Path 与全目标审计

| Evidence | source_ref / content_hash | repro_command |
|---|---|---|
| E-imports | `contract-strict.json`，SHA `427f56fc4b430c31e1736f8a2c4074fe481e74762b1a688412b466dba1f92e68`；裸成员服务等价锚点 | `task_wrapper_contract.collect()`，或上述动态入口内的 collect |
| E-run6 | `run-6-final.json`，SHA `1608c5f5df2a870cf976e3f712517495e3e3eb73d2349765d65b9bdc8e1f72db` | 上述 verify 命令 |
| E-run7 | `run-7-repeat.json`，SHA `597f123d2824eab57d6638f4cddf820be1ffbfca8342383d35a776410d3ea24f` | 上述 verify 命令 |
| E-verify | `verification-nested-final.json`，上述加强结果 SHA；绑定核验器自身和继承核验器 | 上述 verify 命令 |
| E-test | `tests-full-strengthened.log` / `tests-candidate-final.log`，142/11 通过；负例红测另存 | 上述 unittest 命令 |
| E-env | `environment-current.json` / `cleanup-final.json`；以原文件摘要为准，不当物理安全证明 | 检查脚本已执行；Win32 只读进程/映射查询 |

| Finding | severity / evidence_ids / confidence | location / status |
|---|---|---|
| F-fields | n/a_re；E-imports/E-run6/E-run7/E-verify；high（仅本样本） | 原 STR/STRD：入口回调和原返回字来源局部成立，完整结构/所有权未证 |
| F-labels | n/a_re；E-run6/E-run7/E-verify；high（仅本样本） | 输入配置 +10 标签与原名称模板/TCB+CC 分离，非完整业务名单 |
| F-service | n/a_re；E-imports/E-run6/E-run7/E-verify；high（仅本样本） | 原服务 0A 与 r10/index3 区分，服务参数/返回及同次 SVC 栈成立，完整启动 API 未证 |
| F-gates | n/a_re；E-env、PORT、Q/U 缺项；high（范围结论） | 完整移植/完整模拟器方案/刷入/绝对安全均未通过，阶段转换关闭 |

P-1，path_type=callflow：原封装输入 → 原栈配置 → SVC 创建入口/构造 → 原 STR/STRD → 服务 0A 入口/返回；关联 E-imports/E-run6/E-run7/F-fields/F-service。没有把未观察的回调返回、业务完成或刷写加入路径。

Timeline：初版读字段错误红测 → 两个动态失败与原码重审 → 24 样本覆盖诊断 → 17:01:10/17:01:43 两正式进程 → 两跑闭合并清理 → SVC 栈漏检负例红绿 → 142+11 回归及加强重放。失败不是成功证据，修补前后版本分开保留。

| 原目标要求 | 审计结果 | 证据范围/缺口 |
|---|---|---|
| 完成原 Fenestra Z62 移植 | unverified | PORT 仍 loader-only，无完整原厂候选；不能以原厂任务观察冒充端口 |
| 第一阶段完整方案实跑通过 | unverified | 本轮仅 93 条局部链，Q1～Q6 未全通过，完整矩阵/生命周期/模型缺口仍缺 |
| 之后验证冻结镜像及刷入 | unverified | 无候选可冻结，U1～U6 未进入验收 |
| 前两阶段通过前不上真机 | met（本轮） | 本轮全部命令/只读 RSP/QMP、范围和清理证据；真机未连接/刷写 |
| 真机刷入和运行一定不出问题 | unverified | 有限局部模拟器证据不能保证所有物理状态绝无问题，未用降低风险代替 |
| 分阶段列标准/问题/实际修补/转换条件 | met（本轮） | 第2节完整门槛、第4节失败及修补；未把未执行项标通过 |

下一步仍需恢复完整原厂启动 API/同步/内存释放与生命周期、解释 r10 的 73 待配对、恢复可保留空间与 cache-DMA/加载合同和可开发模型来源，再实现完整 Fenestra 服务及候选。只有 Q 项全通过才处理 U 项；物理条件未齐且绝对安全要求未满足前不上真机。保留原上游许可证、商业摄影例外及署名；没有提交、推送或发布固件/密钥/缓存。
