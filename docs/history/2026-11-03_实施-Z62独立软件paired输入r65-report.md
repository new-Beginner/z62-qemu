# Z62 独立软件paired输入 r65

日期：2026-11-03。普通工程实现报告，flavor=null。授权及边界见[scope](../../analysis/z62-paired-ingress-r65/scope.md)。仅本地开发和仿真，无相机／物理盘／GitHub发布。

## 本次结果

已经构建默认关闭的C级paired输入，完成实际四槽RAW、MAIN／WORK／预览数值和生命周期原生验证。原厂完整55.070计数器秒窗口中，返回照片的新场景经消费标签、RAW／NV12／LCD区域核验通过；视频仍0批，严格恢复false。新增输入解除对旧RAW stream直接供数的依赖，但视频还存在可原生复现的旧通知所有权缺陷，正以独立r66修正。未知的物理重武装协议没有被冒充为已还原，AF算法和默认交互入口未修改。

| 部分 | 层级 | 当前结论 |
|---|---|---|
| 新paired帧源 | C | 原生数据与生命周期通过 |
| 场景邮箱与packed12 | 既有C复用 | 不另维护界面或第二份场景状态；原始标签保留 |
| MAIN／WORK／预览算子 | 既有C复用 | 新数据实际送达，ramp及白场检查通过；未修改数学实现 |
| 原厂paired请求 | A | r64b写入时序提供启动与关闭顺序线索 |
| 原厂LCD消费／严格恢复 | A/C，部分通过 | 返回照片新来源通过，视频仍失败；严格双流水恢复false |
| 统计新来源、原厂编码存卡、镜头／AF | D | 本次未完成 |

## 实现边界

新`z62-paired-ingress`默认off，明确要求旧RAW停止选项、preview及results。它读取paired已提交的四个地址，先检查全部源／相关输出的真实RAM和别名，然后通过内部BQL API读取现有scene mailbox。四槽真实写入成功后才发布新的输入代次；源自身不发IRQ、不写RAW启动锁存、统计结果或guest ready／队列。既有软件ISP继续计算和DMA自己的输出，随后才产生其完成通知。

P-input，path_type=callflow：paired08请求 → `paired_ingress_tick`核对请求、旧RAW和背压 → `paired_ingress_spans`预检 → `z62_paired_scene_copy`读取已验证场景 → 四次RAW DMA → `z62_paired_scene_used`及新来源代次 → `video_source_notify/preview_schedule` → 既有ISP数值计算／MAIN、WORK、预览DMA → 既有结果完成。

外部场景epoch、publication、frame和time不被投递次数重写。新增计数和DMA虚拟时间与外部帧标签分别保存。软件节奏33,333,333ns、1514×1006实验packed12以及视频origin(0,76)格式桥均非物理校准。统计未被强开，未知word18、68100和68104的真实含义仍未知。

## Evidence → Finding

| E-id | source_ref | repro_command | content_hash |
|---|---|---|---|
| E-order | r64b过滤日志（本地证据，未分发：`analysis/z62-mmio-write-r64/live-filter-1/mmio-write.log`） | [r64b复核命令](../profiles/README-Z62-MMIO-TRACE.md) | 6464a5a0c6ba0d877ab1771eb3b367840849362cf2ef9bfc5685d6ed71695f5e |
| E-build | 构建清单（本地证据，未分发：`.build/z62-paired-ingress-2026.11.03-r65/paired-ingress-build-manifest.json`） | [构建／复核说明](../profiles/README-Z62-PAIRED-INGRESS.md) | EXE 1e224c3f13d4919d36c4c0c1724d0d65bd283041b609286c305ba1728de5eccd |
| E-red | 旧内核负向（本地证据，未分发：`analysis/z62-paired-ingress-r65/missing-native.json`） | 对r64b执行新的native probe | 缺属性的exit1；内嵌当时probe和EXE SHA |
| E-native | 最终native-3（本地证据，未分发：`analysis/z62-paired-ingress-r65/native-3.json`） | README中的native命令，输出新名 | probe及3份console SHA内嵌，并收于E-verify |
| E-compat | 旧套件兼容（本地证据，未分发：`analysis/z62-paired-ingress-r65/compat-1/native-compat-check.json`） | `python -X utf8 -B tools/probe_z62_mmio_filter_compat.py --qemu .build/z62-paired-ingress-2026.11.03-r65/runtime/qemu-system-arm.exe --output analysis/my-new-r65-compat` | 20份日志SHA内嵌，并收于E-verify |
| E-verify | 复核回执（本地证据，未分发：`analysis/z62-paired-ingress-r65/verified-native-1.json`） | README中的verify命令 | 34份源／artifact SHA，24层身份与15项native门槛 |
| E-live | 原厂完整窗口（本地证据，未分发：`analysis/z62-paired-ingress-r65/live-1/paired-ingress-lifecycle.json`）和像素证据（本地证据，未分发：`analysis/z62-paired-ingress-r65/live-1/video-isp-lifecycle.json`） | README中的trace命令 | 内嵌build／source SHA；照片PNG ff4c2d010cc3a9e4a339ea8c4a1cea0a8506fedb581426b0a6060470000e80d2 |
| E-handoff | 最小交接复现（本地证据，未分发：`analysis/z62-paired-ingress-r65/handoff-1.json`） | `python -X utf8 -B tools/probe_z62_paired_ingress_handoff.py --output analysis/my-new-handoff.json` | 内嵌当时probe／EXE SHA，保留exit1 |

| F-id | severity | evidence_ids | confidence | location | status |
|---|---|---|---|---|---|
| F-order | n/a_re | E-order | 高，限写入尝试 | entries56249／56256／56610 | 视频flags3先于paired08，关闭时再清0，不需要放宽flags条件 |
| F-data | n/a_re | E-build,E-native,E-verify | 高，限C模型 | 新header及RAW／MAIN／WORK／预览缓冲 | 实际数据、独立数值oracle及不同白场响应通过 |
| F-isolation | n/a_re | E-native,E-compat | 高，限原生夹具 | RAW latch／两个输入源／结果背压 | 旧端口保持停止、源互斥、默认off、拒绝与生命周期通过 |
| F-factory | n/a_re | E-live | 高，限区域像素与来源标签 | 原厂LCD与严格恢复 | 返回照片通过，视频和严格恢复失败；未作整机验收 |
| F-handoff | n/a_re | E-handoff,E-live | 高，限C模型原生缺陷；原厂对应仍待修正版验证 | paired_ingress_tick背压条件 | 无完成pending、旧RAW已停，旧通知仍阻止新数据；r66独立修正中 |

## 验证与开发记录

1. 新native probe先对旧r64b运行，DC57024 exit1／0.84秒：缺少独立paired软件输入属性。
2. 新adapter从逐文件核对的r64b副本构建，父源与EXE保留。DC21316 exit0／449.42秒；24层身份现场核对通过。仅三份既有hw/arm文件变化，新增API和模型两份header，既有视频数学header及RAW停止实现不变。
3. 新配置4项专项通过。一次单独测试因未加tools搜索路径产生ImportError，修正测试导入；最终DC55156全量609项／211.885秒／exit0，完整stdout未另存。
4. DC53528 native-1 exit1／26.42秒：原始RAW数据比对通过后，错误检查首槽之前的不可写池外哨兵失败。原夹具已明确82C00000首地址没有可写前置RAM；只修正probe复用其限定guard，不改C内核。旧失败和两份正常关闭日志保留。
5. DC15840 native-2 exit0／47.91秒；为排除仅publication变化但像素陈旧，追加真正不同的白场和旧RAW共存检查。DC56752 native-3 exit0／49.44秒：每槽2,285,632字节完整比对，全部有效前后guard、MAIN／WORK／预览oracle通过；第二白场实际写出Y235／UV128、WORK均值4095及色差0。新源工作时旧RAW frames／accepted和完成保持0；新选项ON时旧RAW真实DMA及视频数值也通过。
6. 同一native还验证了缺场景、晚出现的非法第四源地址不发生部分预检写入、源别名拒绝、pending背压、flags清0停止、仅恢复flags不重启、显式paired请求再消费、slave隔离和reset。三份QEMU均exit0并关闭，console归档。
7. DC23784兼容exit0／21.33秒：STOP ON、过滤trace ON、新paired默认OFF，旧统计／视频数值、DMA和拒绝检查通过，20份日志归档。不能把此项写成新源ON时统计流水线已经恢复。
8. 初次E-verify复核exit0／3.09秒，五份生成源变化、源／日志哈希及15项native门槛一致。完整原厂55秒场景已启动；运行期间不改模型、probe、观察器或其父工具。
9. DC39688原厂窗口已exit0／1047.30宿主秒，55.070计数器秒／126停顿、1232条master控制环完整且无序号缺口，正常detach／cleanup／关闭；PID6340只读确认不存在。3次QMP超时均恢复、控制零重放，无宿主附加，具备功能评估资格。返回照片49.287秒实际消费epoch89／pub3／frame1414／time47157000000，期望一致；4处RAW、12处NV12、4处LCD区域灰40匹配，PNG已视觉检查。最终新源296批／2,706,188,288 RAW字节；旧RAW和统计停779，视频0批、严格恢复false。
10. DC58244最小交接复现exit1／18.31秒。唯一额外条件是先产生1个真实旧RAW通知而不启动ISP；清除RAW完成，再提交新paired请求，core flags3、命令／结果／paired pending均0，仍source frames0／blocked1、video reason source。它定位出r65把未调度、非本源所有的旧通知当成背压的缺陷。没有清软件ready或绕过旧完成；已另建r66，只允许真实新DMA成功后替代该通知并记录retired计数，仍保留所有真实pending及已调度工作保护。r65绑定源／内核不修改。

## 使用、参考与后续

使用[独立验收入口](../profiles/README-Z62-PAIRED-INGRESS.md)，继续维护[能力表](../CAPABILITY-COVERAGE.md)与[Goal检查点](../GOAL-Z62-QEMU.md)。原生测得的payload／输出并非完整相机；需要用新场景消费标签和原厂LCD像素核验原厂窗口，再针对统计新来源推进完整恢复。完整系统快照、音频、原厂媒体存卡、镜头协议及AF多帧闭环仍缺。

本次复用了工作区既有QEMU10.2.4、scene mailbox、软件视频算子和原生oracle；上游参考归属见nightglasses固定源码参考图（本地证据，未分发：`analysis/nightglasses-z7ii-0e53ea5/reference-map.md`）及[此前参考报告](2026-11-02_构建与参考-nightglasses-Z7II-QEMU-report.md)。本次新请求顺序和地址来自Z62自己的原厂轨迹，没有直接照搬Z72寄存器地址。Tornado NKN仍只作为此前PC维修协议资料，不是本次输入模型或AF算法源码。未改变这些项目的原作者归属或许可证。

## 文档核对

- [x] 授权、证据、结论、调用路径、失败记录和复现命令齐备。
- [x] 明确C级替代和物理未知，保留旧失败及绑定源码。
- [x] 原生数据通过与原厂照片部分通过、视频失败分开。
- [x] 完整Goal保持active，不把此工具用于宣称刷入相机不会黑砖。
