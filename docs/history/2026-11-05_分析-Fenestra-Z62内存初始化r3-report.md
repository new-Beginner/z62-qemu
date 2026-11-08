# Fenestra Z62 内存初始化合同 r3

**仍不可刷机、不可上真机。原厂内存初始化通过，不等于 Fenestra 已集成或可安全分配并执行插件。**

## 1. 概述与范围

继续A路线，直接从 Z6II C1.70 原字节恢复 RTOS 内存初始化链，并在用户已有自研 r69 Z62-QEMU 上实际观察。最终两个独立进程均验证主/从池初始化前后、堆链表初始化返回、服务组返回，共各8个主核检查点。RAM页表副本、原厂池状态、首尾块头、四组空链表、成功返回及栈恢复均符合原代码。另定位了两角色的块分配/释放静态候选，但未执行其调用验证；完整 ABI、生命周期及插件代码发布仍缺证。没有生成 Fenestra 集成候选或更新包，也未访问物理相机。

原目标保持：A，一直Fenestra，并且使用自己开发的z62qemu验证是否可行，然后确定刷入没问题以后再上真机，主要保证真机一定要没问题。

- 范围：[scope.md](../../analysis/fenestra-z62-memory-r3/scope.md)。仅原文件只读分析、单测和本机环回 GDB/QMP；无USB/PTP、物理卡、相机或外部网络操作。
- 报告类型 `flavor=null`。前两阶段 ARM32 加载器及原厂早期启动证据已重新核验，不替代当前或后续集成验证。
- 模型预装完整主/从成员并初始化复位PC；原厂随后自然执行。本轮不注入调用，不改运行中的PC/RAM/指令/返回值/ready。
- 无控制器、参数、卡和插件。相机更早引导加载器未执行；结束用QMP quit，不是相机正常关机验证。断点扰动时序。

## 2. 样本及等价接口锚点

| 项目 | 当前身份 |
|---|---|
| 原始 master | 38,750,138字节；SHA256 `bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4` |
| 原始 slave | 8,832,194字节；SHA256 `3fd8c2cbdf57fadb03f6d69b596b58a8703efdd61ae82572d5afeea0241a9ed5` |
| 自研QEMU | 既有r69；SHA256 `37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9`，未重编 |
| 工具 | Python 3.12、Capstone 5.0.7、既有RSP客户端及QMP |
| E-imports等价锚点 | raw ARM/Thumb成员无ELF/PE导入目录；本轮追踪原厂ARM BL、PC-relative literal和RTOS配置存储；完整原指令窗口保存在合同JSON，不据无导入目录推断能力缺失 |

原4份输入均经最终核验保持不变，Z62子模块仍为 `4f4389944fc339d107f22f5f7ca3f90cc34b78de` 且干净；Fenestra仍固定b199dcdf，仅保留前期两处加载器修改。没有提交/推送或清理用户既有改动。

## 3. Z62专属内存合同

下列均为运行地址，成员文件偏移需减去 `0x10020000`；不能直接套用Z7II的地址或容量。

| 项目 | master | slave |
|---|---|---|
| RTOS入口 | `0x10103C18` | `0x100356C8` |
| 服务组入口 | `0x10108F9C` | `0x1003A970` |
| RTOS配置对象 | `0xC2B2B5D8` | `0xC18A0354` |
| 原厂RAM页表副本/活动TTBR0 | `0xC2B54000` | `0xC18D4000` |
| 堆起点 | `0xC2BE0000` | `0xC1930000` |
| 堆终点（exclusive） | `0xC6100000` | `0xC6000000` |
| 池元数据起点 | `0xC2BE0000` | `0xC1930000` |
| 池数据区起点 | `0xC2C15000` | `0xC1977000` |
| 池块计数字段 | 27,094 | 36,114 |
| 块大小 | `0x800` | `0x800` |
| 池配置对象 | `0xC18AD8D4` | `0xC1016904` |
| 池状态对象 | `0xC2B2F67C` | `0xC18A43C4` |
| 堆控制对象 | `0xC18AD8EC` | `0xC101691C` |
| 池初始化入口 → 原厂返回点 | `0x10108494 → 0x1010902C` | `0x10039E68 → 0x1003AA00` |
| 堆初始化入口 → 原厂返回点 | `0x10108B54 → 0x10109040` | `0x1003A528 → 0x1003AA14` |
| 服务组返回RTOS | `0x10103C5C` | `0x1003570C` |

原厂 `0x100202F4` 从literal写入配置对象的`+0x28/+0x2C`；RTOS前段再将它们写入池配置的起止字段。池初始化也有查询覆盖上限的分支，不能推广为所有配置恒定；本次观察前后值与上述literal路径一致。

几何计算复核原 `UDIV`、对齐和移位：先将起点向上对齐8字节，计算 `pool_end = align_down_2048(start + floor((end-start-8)/0x808)*8 + 0x807)`，计数为 `floor((end-pool_end)/0x800)`。这是原厂元数据解释，不是可用容量、所有权或物理DRAM芯片容量认证。主/从是独立地址空间，不能把这些软件区间相加当作实际内存总量。

每次动态观察均确认：

- 进入池初始化时边界对象与静态合同一致，LR为原厂返回点。
- 活动TTBR0为各自RAM副本；副本16KiB与原始页表逐字节一致，TTBCR=0、DACR=`0x55555555`；MMU和I/D cache保持开启。
- 观察CPU的secure/non-secure DFSR/IFSR均为0，VBAR为主`0x10100000`/从`0x10034100`。
- 池状态为`[count,count,start,pool_end]`；首24字节为`[4,4,1,0,(count<<2)|1,0]`，尾块头为`[(count<<2)|1,0]`；配置游标推进到end。
- 堆控制为`[0,0x800]`，原厂四组属性值`0/0x10/0x300/0x310`的两个链表均自引用。没有据属性名推断缓存或权限语义。
- 原厂返回r0=0；池/堆返回SP恢复到进入池时的值，服务组返回再恢复8字节。没有替换返回值或污染RAM制造保护字。

## 4. 分配与释放仅为静态候选

| 静态候选（ARM状态） | master | slave |
|---|---|---|
| 块分配入口 | `0x10108154` | `0x10039B28` |
| 释放封装入口 | `0x101082F4` | `0x10039CC8` |

候选由原字节前缀、完整ARM反汇编窗口和各自池状态literal交叉确认。分配代码将r0保留为块数，与空闲段长度比较并以`<<11`换算地址；r1的bit16会被检查。它不是字节级`malloc(size)`；不能传入插件字节数后假设正确。释放封装先把自身池状态装入r1，随后有范围/对齐、已用位、邻块合并和管理调用；不能只截取内部函数或当作一般`free`调用。

**未验证**：合法/零/超大请求、标志全集、错误/内部/重复释放、失败返回与副作用、同步及可调用上下文、不同core、并发、缓存/DMA一致性、代码写入后的cache维护及插件执行。候选是ARM地址，不应随意加Thumb位；上一阶段插件入口为Thumb并不意味着原厂接口也为Thumb。

## 5. Evidence → Finding → Path

所有短证据名相对 `analysis/fenestra-z62-memory-r3/`。

| E-id | source_ref | repro_command | content_hash |
|---|---|---|---|
| E1 / E-imports | `contract-2-final.json` | 第6节memory_contract命令 | SHA256 `db3947f39df0f3b9a2fa08a0f8c52170e9b56d1cf236390d85880d4bc98d9707` |
| E2 | `run-3-final.json` | 第6节observe_memory命令 | SHA256 `5565f2979165fbd3018a47610ac7b9d8bea8b04fc8205af9f79659c60616d75f` |
| E3 | `run-4-repeat.json` | 同上，独立新进程 | SHA256 `1d4c58f36d91fd0f3a38e227c7ddbac6d8092e12bb92850813705c70137d14be` |
| E4 | `verification.json` | 第6节verify_memory命令 | SHA256 `c54fe23085ed4f723258111ad11bf8680e149f8170222a503d4fd41f5e15a461` |
| E5 | `fenestra-tests-final.log`、`candidate-tests-final.log` | 第6节unittest命令 | SHA256 `6284cb1d1b9da9b843643fa863a281577d88854e1493eb7e776b455377a561d5`、`57072ce3f9877cd543934d83ce0344083c1566b0668169df8323eb5e014ff82f` |

E4重算当前合同、源码、QEMU、日志、原4份输入和子模块身份。还在内存中变异有效记录，要求遗漏检查点、错误返回、TTBR、池计数、块头、链表、范围标志、seen集合、CPU线程、SP、PC和LR共12种记录全部拒绝；没有修改原运行记录或客体。E5为22项Fenestra测试和11项候选回归，全部通过、无跳过。`startup-reverified.json`、`loader-reverified.json`是前两阶段证据重新核验，不是本轮重新运行插件。

| F-id | severity | evidence_ids | confidence | location | status |
|---|---|---|---|---|---|
| F1 Z62堆边界与初始化来源 | n/a_re | E1,E2,E3 | high，限本配置 | 原配置writer、RTOS、池对象 | verified_bounded |
| F2 主/从原厂内存初始化实际完成 | n/a_re | E2,E3,E4 | high，限模拟器窗口 | 池/链表/服务返回点及RAM页表 | verified_bounded |
| F3 块分配/释放不是可直接替代的malloc/free | n/a_re | E1 | high静态；完整ABI未知 | 第4节四个ARM候选 | candidate_only |
| F4 Fenestra集成与刷机安全仍缺证 | n/a_re | E4、当前PORT.json | high（当前缺口状态） | ABI/生命周期/更新/恢复 | unverified |

P1，`path_type=callflow`：原EG启动 → 原厂缓存维护/页表复制切换 → RTOS配置填充 → 核零服务组 → 池初始化 → 堆控制/四组空链表初始化 → 返回RTOS。E1确认调用与literal，E2/E3验证池前后及服务返回。**不延伸为完整调度、启动完成、关机、插件加载或更新流程。**

Timeline：先从Z62原字节恢复调用链和配置；新增5项合成测试；`contract-1.json`及`run-1.json/run-2-repeat.json`验证初始化，均正常退出；补入API静态候选后生成最终合同并以PID30900/53404独立复跑；E4核验及12种记录拒绝检查通过。旧合同/运行记录保留，不与最终源码身份混用。

## 6. 复现

工程根Git Bash，要求原私有固件、固定r69、Capstone和已验证的ASCII `Q:/`工程别名。输出需使用新目录；不会覆盖现有证据。

```bash
export TEMP="$PI_SCRATCH_DIR" TMP="$PI_SCRATCH_DIR" TMPDIR="$PI_SCRATCH_DIR"
export PYTHONDONTWRITEBYTECODE=1
python -X utf8 -B -m unittest discover -s tests -p 'test_fenestra_z62*.py' -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_candidate.py -v
python -X utf8 -B fenestra/z62/memory_contract.py --output analysis/fenestra-z62-memory-recheck/contract.json
python -X utf8 -B fenestra/z62/observe_memory.py --output analysis/fenestra-z62-memory-recheck/run-a.json
python -X utf8 -B fenestra/z62/observe_memory.py --output analysis/fenestra-z62-memory-recheck/run-b.json
python -X utf8 -B fenestra/z62/verify_memory.py \
  --static analysis/fenestra-z62-memory-recheck/contract.json \
  --run analysis/fenestra-z62-memory-recheck/run-a.json \
  --run analysis/fenestra-z62-memory-recheck/run-b.json \
  --output analysis/fenestra-z62-memory-recheck/verification.json
```

## 7. 原目标审计与下一步

| 原目标要求 | 当前结果 |
|---|---|
| A路线移植Fenestra到Z62 | 未完成：ARM32加载器已有局部验证，原厂平台服务/完整候选未完成 |
| 自研Z62-QEMU验证修改固件及插件 | 部分证据：分离的加载器、早期启动和内存初始化；尚无集成候选A/B |
| 确定刷入无问题前不进入真机 | 本轮遵守；未接触相机、无可刷包 |
| 确定刷入/恢复安全，主要保证真机一定没问题 | 未验证，不能从有限QEMU试验推出绝对无风险 |

下一步首先观察上述原厂分配/释放的真实调用、参数、返回与元数据变化，核实生命周期和同步；随后才考虑有界原厂调用试验和Fenestra内存适配。任务/卡读ABI、启动完成/正常关机、cache发布、模块管理/菜单、独立候选原版/停用/激活A/B及压力仍需完成。更新摘要B8/K8、主从资格、真实加载容量、NOR/持久化、断电/恢复仍独立缺证，真机门槛继续关闭。
