# Z62 视频配置中的来源、MAIN、WORK 与实际 setter：r55

日期：2026-11-03，`flavor=null`。范围见 [scope](../../analysis/z62-video-contract-r55/scope.md)。本阶段增加可运行的离线配置解码工具，核对既有r53实际原厂快照及目标自身代码；没有新设备、IRQ、视频像素处理或默认入口变更。

## 已确认的结果

视频不能只将旧预览的1002行白名单改为846。现有四个RAW地址仍被使用，但配对模块的1516×854／row2288与上游1514×1006／row2272不同。其MAIN committed slot8为1508×846／row1520，切换到普通地址；WORK同时开启，拥有独立两组地址表。4个phase索引实际重复使用2个地址对，不能当作4个独立帧逐一覆盖。

[新解码器](../../tools/inspect_z62_paired_contract.py)已在10份原厂快照上完成解码、错误0，完整结果为 r53-layouts.json（本地证据，未分发：`<WORKSPACE>/analysis/z62-video-contract-r55/r53-layouts.json`）。这是配置与地址事实，不证明MAIN／WORK已经产生新像素。

## 1. 从目标自身重新定位

直接尝试Z7II参考VA的首批导出保留于 首批manifest（本地证据，未分发：`<WORKSPACE>/analysis/z62-ghidra/paired-video-r55/manifest.json`）。其中1036a2ac在Z62为MMU相关片段，1036aac2为数值运算片段，102be8a0出现bad-instruction；结构审查为false。不能将“Ghidra进程exit0／导出完成”当作找到了正确setter。这次候选失败未被覆盖。

随后从目标载荷的20380000、20380488字面量与其Thumb引用重新定位，得到下列Z62地址。不是用一个固定机型地址差整体平移。

| Z62 master VA | 原始行为 | 后续模型可使用的事实 |
|---|---|---|
| `1036C3B0` | 两个4字节源值经103C82F6读取并旋转16位，写paired+44／48 | 源布局字段由自己的参数包产生，不是统计grid行数 |
| `1036C3F4` | 写88、94、98、9C、A0、A8、8C、84 | chunk／continuous调度字段是一组，不能把9C独自当RAW高度 |
| `1036C7BA` | 四组4地址写310／330／320／340，源包+40半字写30C | source ring与row stride绑定；四组的角色不能只凭相邻地址猜 |
| `1036CC0A` | 将9字节包分别写414、424、410、420、404、408、428、42C | WORK 408/410与MAIN 420/428是独立的成对字段；424不等于使能 |
| `1036CC9C` | selector=0选择430..46C／470，其他值选择488..4C4／4C8 | 两个输出族均有4组4地址，stride来自源包+40半字，不能合并两个族 |
| `1036CE56` | 按三个选择参数只更新上述族中的一组4地址 | 局部地址更新不代表其他组也已更新或有新帧 |

所有MMIO地址还加上对象byte4乘40000的bank偏移。该偏移和setter写法已对照导出的原Thumb指令；语义仍只覆盖表中限定事实。Ghidra的全局`semantics_verified`保持false，没有宣称所有伪代码或物理像素方程已恢复。

新导出分别位于 target（本地证据，未分发：`<WORKSPACE>/analysis/z62-ghidra/paired-video-r55-target/manifest.json`）、fields（本地证据，未分发：`<WORKSPACE>/analysis/z62-ghidra/paired-video-r55-fields/manifest.json`）、source（本地证据，未分发：`<WORKSPACE>/analysis/z62-ghidra/paired-video-r55-source/manifest.json`）。三个命令均实际exit0、原始载荷未改、结构审查通过；数据库／源／指令清单独立保留。IDA bundled starter此前未找到本体，本阶段复用固定Ghidra11.4.2／Java21，没有安装或修改IDA。

## 2. 三种时段的配置

| 数据域 | 初始照片 | 视频／返回初期保留配置 | 返回照片稳定配置 |
|---|---|---|---|
| 上游RAW格式字段 | 1514×1006／2272 | 相同 | 相同 |
| paired source字段 | 1514×1006／2272 | 1516×854／2288 | 1514×1006／2272 |
| MAIN slot8 | 1510×1002／1536 | 1508×846／1520 | 1510×1002／1536 |
| MAIN地址类别 | 特殊40000000／40008000端口 | 普通地址候选 | 特殊端口 |
| WORK使能对 | 0／0 | 1／1 | 0／0 |
| MAIN使能对 | 1／1 | 1／1 | 1／1 |

初始与返回时，旧WORK指针可以仍留在寄存器中。解码器不会把这些保留值解释为活动历史帧；短到440字节的旧paired采样也会明确拒绝，因为无法覆盖整个MAIN族。

r53视频样本的MAIN首环Y地址在`EDB82C00／EF5A6A00`间交替，UV相差1,285,920字节，恰等于slot8的1520×846。WORK首环在`F0FCA800／F11F7C00`间交替，两平面地址相差642,960字节，stride字段1520。WORK第二环与首环相同；MAIN第二环为零。此前将两个族都称为镜像的描述已按原始JSON和r59实际诊断纠正。这些是已写出的地址关系；不能据此判定WORK物理格式、有效高度、帧历史有效期或当前phase。

QEMU冻结profile确有`DD700000..FFFC2800`的frame-buffer-pool-lab，包含上述高地址。大RAM窗口内还可能有覆盖映射，CPU VA与物理DMA视图也要分开，因此后续实际读取仍须查目标会话的地址空间和RAM属性，不能仅扩大高地址白名单。

## 3. 工具与验证

4项专项先红后绿，DC26668的初始缺失失败保留，DC7692最终4项／0.017秒、exit0。它们分别阻止：地址集合相同掩盖stride差异；将两个别名缓冲误认四帧；将关闭WORK的保留寄存器误当活动历史；截断采样或成对使能不一致时默认为成功。测试使用独立字面量夹具，没有修改冻结模型。

DC32932已在r53的10份实际快照上运行并exit0。工具生成的JSON保存pipeline原始SHA、解析器SHA、全部phase地址对、stride、slot8、独立使能及未知标记；`actual_pixel_production_verified=false`、`new_device_implemented=false`始终明确。

新增工具后全量DC29200实际567项／234.254秒／exit0；4项专项和10份解码不验收视频功能。完整全量stdout未另存，计数及耗时为当次工具输出转录。

在工作区根复现，输出文件须不存在：

```powershell
.build/tools/video-r26/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -p test_z62_paired_contract.py -q
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/inspect_z62_paired_contract.py --pipeline analysis/z62-photo-results-r53/return-1/pipeline.json --output analysis/z62-video-contract-r55/layouts-new.json
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/decompile_z62.py --output analysis/z62-ghidra/paired-video-r55-target-new --functions 1036c4d4 1036c7ba 1036c8e0 1036cc0a 1036cc9c 1036ce56 1036cfe0
```

## 4. 下一实现的前提

下一步要追踪1516×854来源包的构造／实际读取范围，解释它与1514×1006上游的转换和stride关系；不能直接按新stride读取旧RAW。随后分开实现有真实来源代数的MAIN输出和WORK历史／取消生命周期，再连接结果路由。C级软件算法可以独立开启，但需要真实读／算／写、独立存储和明确近似，不用固定完成或旧帧重播替代。

原厂视频、全分辨率图像、音频、实体照片／视频拨杆身份仍未验收。r53／r54的返回照片改善不能外推为这些功能完成。

## 5. Evidence → Finding → Path

| E-id | source_ref | repro_command | content_hash |
|---|---|---|---|
| E-imports | 裸ARM master载荷；无PE／ELF动态导入表 | 既有载荷校验与Ghidra导出命令 | 含CRC SHA256 `bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4` |
| E1 | 首批／target／fields／source四组manifest、C与ASM | 各manifest保存精确command | 各manifest保存输入／脚本SHA；原始未改 |
| E2 | r53 pipeline及`r53-layouts.json` | 本文inspect命令 | 新JSON的`pipeline_sha256`／`source_sha256` |
| E3 | `tests/test_z62_paired_contract.py`，DC26668／DC7692／DC32932 | 本文unittest及inspect命令 | 实际执行的源码位于工作区；完整专项stdout未另存 |

| F-id | severity | evidence_ids | confidence | location | status |
|---|---|---|---|---|---|
| F1 | n/a_re | E1 | 高 | Z7II候选VA与Z62入口 | 首批拒绝，已从自身字面量重新定位 |
| F2 | n/a_re | E1/E2/E3 | 高 | source／MAIN／WORK三域 | 布局分离与别名事实确认，实际像素生产未知 |
| F3 | n/a_re | E2 | 高 | 上游／paired不同stride | 转换来源尚待追踪，未扩大设备接受范围 |

P1，`path_type=callflow`：目标原始字节与字面量→自身Thumb setter→既有原厂配置快照→独立布局解码→下一数值／生命周期合同。时间线为首批VA候选否定→重新定位→三组独立导出→四项专项先红后绿→十份实际快照解码。没有将静态导出当作新固件执行。

主要参考：[nightglasses/z7ii-qemu固定0e53ea5](https://github.com/nightglasses/z7ii-qemu/tree/0e53ea5a6d4f3fc635d63c195a92e943370ac5e9)的`docs/devices/pairs/modes.md`、`requests.md`与`gate/processing.md`。只借鉴输入资格、环／别名、生命周期及分离生产者的方法，本阶段没有复制其设备实现或将其VA／PDAF／AF结果移植到Z62。原有署名和许可不改。
