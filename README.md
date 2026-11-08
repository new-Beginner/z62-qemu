# z62-qemu

尼康 **Z6II / Z62 C1.70** 的 QEMU 系统仿真实验工程。运行原始固件，连接机身输入、虚拟场景、软件镜头、近似成像、虚拟存储和调试工具，逐步建设固件研究平台。

**当前发布范围为 2026-11-08 / r110 + Fenestra r19（源码快照 `2026.11.08-r110-fenestra-r19`），不是完整相机或可刷固件。** 默认仍为 r69 QEMU 内核、r75 交互入口；r104 的受限四帧预览已有原厂 LCD 证据，r105–r110 继续诊断菜单返回后采集未重新武装。Fenestra 仅 ARM32 loader-only 与原厂局部合同研究，r20 只有范围检查，没有 SDK 实现。源码发布不改变任何真机安全门槛。

本项目基于他人的公开成果继续开发。直接基础包括 [xiaoqingfeng0526/nikon-z62-qemu](https://github.com/xiaoqingfeng0526/nikon-z62-qemu)、[JKWTCN/z72-qemu](https://github.com/JKWTCN/z72-qemu)、WonderLantern Z6/Z7 及其贡献者；近期内核研究还参考了 [nightglasses/z7ii-qemu](https://github.com/nightglasses/z7ii-qemu)。保留原作者、QEMU 和各依赖的许可证与署名，不把他人成果称为从零实现。

**r105–r110 新增诊断，不是恢复修复：**状态驱动菜单恢复、宿主故障捕获、原厂 APPLV 与请求资格追踪。r109 取得65对调用／返回，原厂自身将 C1821EB8 从0写为1；r110 的离线核验确认请求转换和参数查询的局部分支，但采集重启根因未证明，仍不能称两轮恢复或旧超时修复。原字节、333个输入包及失败分类保留。见[r105报告](docs/history/2026-11-04_研究-Z62状态驱动菜单返回与采集停用r105-report.md)、[r106／r107范围更正](docs/history/2026-11-04_研究-Z62应用索引写入与观察范围r106-r107-report.md)、[r108／r109原厂重入](docs/history/2026-11-04_研究-Z62管理器通知与APPLV实际重入r108-r109-report.md)及[Fenestra阶段边界](docs/profiles/README-FENESTRA-Z62.md)。本次发布范围和隐私策略见[发布说明](docs/history/2026-11-08_发布-Z62最新源码与验证边界-report.md)。

## 已实现、部分实现与缺失

层级：**A** 原始固件执行；**B** 有证据支持的设备/传输行为；**C** 显式软件替代；**D** 未实现或未验收。软件输出不能当作原厂 ISP、编码器或物理相机等价实现。

| 能力 | 当前状态 | 层级及主要限制 |
|---|---|---|
| C1.70 原厂/候选加载 | 同布局容器、成员边界和 CRC 检查，隔离运行及实际 ARM 指令执行已有验证 | A/B；不补齐完整 ROM/NOR，不验证实机升级与断电恢复 |
| 原厂 LCD、菜单、基础机身输入 | 菜单、导航和部分半按返回已有原始执行证据 | A/B；不是所有启动/菜单/拍摄循环均已完成 |
| 双段快门、拨轮、模式盘、ISO、AF-ON、Fn、摇杆、录像键等 | 输入通路与部分应用行为已验证 | A/B；输入到达不代表 AF、拍照或录像完成；拨轮不永久绑定快门/光圈 |
| RAW、有限/连续统计、近似 ISP、原厂 LCD 显示 | 受限描述符配方下实际 DMA、软件运算和显示 | B/C + A 消费；没有完整传感器/ISP 数学模型、全分辨率和硅片时序 |
| 虚拟场景、曝光、手动镜头 | 图像会随模型参数变化，来源/帧号/虚拟时间可追踪 | C；单平面近似、未校准，不是完整 Z 卡口协议或原厂 AF |
| JPEG、实验性 NEF、成组目录卡 | 独立解码、持久保存、回放、前后切换、2×放大和删除已验证 | C；JPEG 640×424；NEF 1514×1006、12 有效位存入 14 位，不等价原厂全分辨率 NEF |
| 已提交 ISP 来源上的照片操作 | r74 API 闭环、r75 实际网页控件和关闭重开检查通过 | C + A 输入/预览；来源确认不等于原厂编码或存入原厂 SD/DCIM |
| 软件视频 | 异步编码、进度、取消、H.264/MP4 保存、解码/时间/来源审计及回放已有有界验证 | C；640×424、VFR、静音；不同版本的已通过窗口分开记录，不称长稳或完整原厂录像 |
| 照片/视频模式往返 | **部分实现，完整交互验收失败** | 原厂选择值已能交付；未全按对照能确认视频新帧，拍照后切换及录像后返回仍有缺口 |
| 原厂采集/就绪/内核状态观测 | 已定位满队列拒绝、拍摄前就绪等待超时，读到实际内核事件 CB 和原始返回 | A + 宿主诊断；断点扰动，不是功能修复 |
| CaptureWork 独立采集后端 r89/r91 | MAIN／linear16、冻结 LUT／transfer、有限 RAW12 配方、bank/ring、DMA 后事件、ACK 背压；r91 原厂窗口有 13 次 DMA 与 13 组 CPU 确认 | A 原厂受控执行＋B 有限传输＋C 数值模型；保存 6 帧共 9,138,504 样本核对一致，下游统计／预览仍为 0，LCD 全黑；默认关闭 |
| CW 连续统计与采集组 r92–r95 | 实际 DMA 后来源桥、五路统计、unit20 FIR／区域数值及事件96；显式参考参数下原厂 group 13 次／CPU ACK13次 | B/C＋A消费；原生18,528字节、原厂216个已分类字节核对一致；参数不是工厂标定或 PDAF |
| 虚拟时钟供帧及真实等待 r96/r97 | 两个 mailbox、可重构 MAIN 审计；连续源窗口三个原始 AND 等待全部成功 | C供帧／A等待；断点扰动，未修复整机；慢源对照为两成功、一超时 |
| 保留 CW 图像的有限统计 r98 | 原厂33次CW／group，32帧连续统计，122次有限采样／2批／0拒绝；原生93,696字节、原厂两份共1,536字节独立重算一致 | B/C＋A消费；两批同一保留帧，非122个新RAW；16秒终态原厂Error、预览0，默认关闭 |
| r103读出→有限统计输入桥 | 实际完成的C输入生成统计DMA；新native122次／93,696字节、原厂两份1,536字节重算一致；两个原始停止等待kernel0／BOOL1 | C数学＋B传输＋A消费；24秒CW541、grid322、状态[]；绿色背景／preview0，非物理测光／PDAF或完整摄影 |
| r104 CW四帧→受限预览→原厂LCD | 真实DMA后收集四个不同来源，冻结线性视图；24秒CW541／122批预览，LCD颜色匹配；蓝／橙输入变化通过 | B传输＋C数值＋A提交／显示；三种缩略native几何，非全部ISP；菜单恢复未过、超时根因未知，默认关闭 |
| 原厂 JPEG/NEF 编码并存入客体卡 | **未完成** | D；目录卡的软件照片与原厂文件链分开 |
| 完整 Z 镜头通信、原厂 AF 多帧回放/闭环/评测 | **未完成** | D；没有自写 AF 冒充原算法，也未修改 AF 算法 |
| 合焦变绿、自动竖屏、新版 E7 自定义界面、内录 8-bit N-Log | **未作为可用固件功能交付** | 模拟器不能证明这些改动能在 Z6II 实机正常工作 |
| 真机刷写安全认证 | **不具备** | 模拟通过也不能排除实机黑砖、标定或更新路径问题 |

详细清单、失败范围及证据见 [能力覆盖表](docs/CAPABILITY-COVERAGE.md)。

## 当前进展与技术难点

**r104：**已将实际 CW DMA 后的四个不同 slot／publication／地址组成不可变来源集合，保留 bank、epoch 和冻结 transfer；消费者拥有自己的量化 linear12 视图，客体 LUT 编码 RAW 不改。原生累计核对 120,960 字节 NV12、27,427,584 字节私有线性视图及 18,285,056 字节编码 RAW 保持。24.000660666 客体秒窗口无 GDB、两次短 QMP 取数暂停，状态[]、CW541、135 个集合、122 批预览；671 个源包重构通过，LCD 16 点 RGB(210,60,17) 匹配实际来源。生命周期实验另证实 RGB(41,81,161) 与橙色变化，但固定时刻半按早于实际菜单进入，随后通信超时，进程 exit1；不能称两轮菜单或恢复成功。见[r104报告](docs/history/2026-11-04_实施-Z62采集四帧来源与原厂预览r104-report.md)和[来源合同](qemu/z62-capturework/CW-PREVIEW-CONTRACT.md)。下方 r103 及更早段落保留各自当时结果。

**r103：**有限统计unit4按实际输入准备两批数据，缺源不回用CW图像，pending输入／completed cache／owned batch分别保存。两个目标停止等待自然成功，见到原厂真实800h store；24秒无GDB窗口CW541、grid322、状态[]，拍摄OSD恢复。Native122次DMA／93,696字节和原厂两份scalar1,536字节独立重算一致；两窗共1,109包可重构。绿色背景、preview0保持，完整相机仍未通过。见[r103报告](docs/history/2026-11-04_实施-Z62读出统计桥与原厂停止恢复r103-report.md)与[输入统计合同](qemu/z62-capturework/READOUT-STATISTICS-CONTRACT.md)。下方r99–r102是当时云端仍r98的历史检查点。

**本地后续r101／r102（云端仍r98）：**已直接捕获停止等待的kernel结果0／FFCE0000h及布尔1／0；数据完成源计数始终0、初始化完成1。独立默认off的r102新增2020×136 C内联读出，原生数据／取消／reset／mask／W1C及旧CW／有限统计回归通过。原厂16秒完成288次内联读出，319源包和97份消费者摘要核对通过；但unit0资格在失败返回后才开放，3Fh／preview0保持。下一步按有限统计阶段输入合同接入，未修复原厂Error。见[r101／r102报告](docs/history/2026-11-04_实施-Z62原始停止等待与内联读出r101-r102-report.md)与[内联读出合同](qemu/z62-capturework/INPUT-READOUT-CONTRACT.md)。

**本地后续r99／r100（云端仍r98）：**已直接观察原厂有限统计消费者，随后原厂状态从空变为[3Fh]；第二次停止总返回80h，mode及四个清理返回均0，原始分支证明失败来自C18A7634h／mask800h的前置等待。第一次停止返回0。23对原始调用返回及源绑定复核通过，最终Error／preview0保持；尚未修复设备完成源，未补IRQ或修改原厂AF。详见[r99／r100报告](docs/history/2026-11-04_研究-Z62有限统计后的停止错误r99-r100-report.md)。

- **r69/r71：**实际输出来源记录、模式提交确认、带来源的 JPEG/NEF 和短静音 MP4；完整模式往返未通过。
- **r73：**项目临时文件、缓存、工具链和会话迁入工作目录；Q: 仅是经过检查的工作目录 ASCII 别名，不另存数据。
- **r74/r75：**永久故障现场保存、软件照片整链、真实放大裁剪、参数/草稿同步；旧原始栈曾被清理的缺口如实记录。
- **r76–r79：**原厂采集入队在队列 60/60 时返回 0；未按快门的新会话也已满载并反复等待约 201 ms，不能把拥塞仅归因于全按。
- **r80–r82：**连续统计仍产出；捕获线路 101 通知调用。撤回把对象首字 `01000111h` 当作 flags 的错误解释。
- **r83–r85：**从 Z6II 原始 ARM 指令解析真实事件 CB；实际观察内核将 pattern 从 0 写为 `00800000h`、setter 返回 0，但 AND 等待 `05B00000h` 仍返回原始错误码 `FFCE0000h`，上层才转为 0。尚未补齐其它就绪生产者的合法设备合同。
- **r86：**参考 nightglasses 的 CaptureWork 研究，按 Z62 实际读回的 `2020×1342 → 1514×1342 → 1514×1006` 几何实现独立软件像素核心。8 项 native C 测试通过；合成 MAIN 的全部 1,523,084 个输出像素经独立 C 与 NumPy 两级参考核对，零差异，行填充不变。没有注入完成或修改 r69。
- **r87：**新增独立 MAIN／linear16 帧和 C 缓存读占用，模型内背压、取消／停止／复位和旧任务拒绝通过；7 项专项及移动场景两帧共 3,046,168 像素核对通过。当时完整发现 690 项实际为 **2 failures／8 errors／0 skips**，集中于 Q:/D: 别名比较和旧 SD 的 ASCII 路径限制，失败记录保留。[阶段记录](docs/history/2026-11-04_实施-Z62独立MAIN来源与帧生命周期r87-report.md)。
- **r88：**新增不可变 RAW transfer 描述和 C 级量化区间重建，8 项专项通过；两帧 3,046,168 样本与独立参考一致，正向 RAW12 与 r87 字节相同。LUT8 丢失低 8 位，返回区间中点而非原始样本；下游 ISP 尚未接入。旧路径测试按实际工作目录入口适配，旧 guard 保留。
- **r89：**独立 QEMU 采集后端完成真实 DMA／事件锁存接入，默认关闭。合成 ARM 循环下 6 帧、9,138,504 像素读回一致，bank1、冻结 LUT、背压、提交前取消和复位通过；旧 RAW／ISP 及完整 698 项 Python 回归通过。下游新来源 ISP、完整模式恢复和 inflight 取消竞态仍待验证。[阶段报告](docs/history/2026-11-04_实施-Z62原生采集后端与DMA交付r89-report.md)。
- **r90/r91：**原厂写入的共享源字 `0x200040` 暴露 r89 原生夹具遗漏；新增显式 C-MAIN 策略兼容该已观察值，未知值仍拒绝。原始 C1.70 的 8.003 秒窗口记录 13 次 DMA 与 13 组 CPU ACK，保存 6 帧、9,138,504 样本独立核对一致；事件块曾采样到 `0x04300000`，未观察完整就绪条件成立。统计／预览未推进、LCD 全黑；本地完整 Python 701 项通过。[阶段报告](docs/history/2026-11-04_实施-Z62原厂MAIN交付与共享源策略r90-r91-report.md)与[采集后端使用说明](docs/profiles/README-Z62-CAPTUREWORK-DEVICE.md)。

本地 r88 最终完整 Python 发现 **698 项通过，零失败／错误／跳过**；r87 的 690 项失败记录保留。SD 测试使用现有工作目录入口的真实 Path 适配，旧入口和 guard 没有修改。详见[r88记录](docs/history/2026-11-04_实施-Z62冻结RAW域与量化重建r88-report.md)。此结果不覆盖新的原厂运行窗口、LibRaw 或完整相机验收。

**r92：**独立默认关闭的来源桥已把实际 CW DMA 的冻结量化线性视图交给连续统计；原厂8.006秒窗口有13帧统计、2个六槽批次及CPU确认，旧RAW计数始终0。原生六帧五路157,440字节重算一致；原厂保存的6帧9,138,504个RAW样本核对一致，但原厂五路数值未另存。LCD仍全黑、预览未贯通。完整701项回归通过，首轮GCC中文路径失败保留。详见[r92报告](docs/history/2026-11-04_实施-Z62采集来源到连续统计r92-report.md)和[来源合同](qemu/z62-capturework/STATISTICS-CONTRACT.md)。

**r93：**新增默认关闭的unit20采集组C数值／DMA后端，7帧三类记录共18,528字节独立重算一致，原生9进程和完整701项回归通过。原厂窗口的65点曲线与三组系数实际写0，有限参考算子拒绝13次、未发group完成；CW／连续统计各13帧，预览仍0、LCD全黑。此时参数来源尚未恢复，后由r94/r95独立追踪，没有代填ready。详见[r93报告](docs/history/2026-11-04_实施-Z62采集组数值后端与事件96合同r93-report.md)及[采集组合同](qemu/z62-capturework/GROUP-CONTRACT.md)。

**r94/r95：**已更正系数实参为结构+3Eh并核对Z62资源39的实际加载路径。独立诊断标签未产生成功；明确标注为C参考的虚拟group17输入使原厂8.009秒窗口完成13次采集组处理、13次CPU确认，保存4组DMA，其中216个已分类字节重算零差异。710项回归通过。未改固件／AF或代填ready，实际工厂标定仍未知，预览0、LCD全黑；冻结r93内核及默认r75／r69保持。见[r94/r95报告](docs/history/2026-11-04_实施-Z62参数来源与虚拟采集组输入r94-r95-report.md)和[参数输入合同](qemu/z62-capturework/GROUP-PARAMETERS.md)。

**r96–r98：**真实等待对照证明慢源两成功／一超时，按客体时钟供MAIN后三次全部成功；原厂随后进入61槽有限统计。新默认关闭的r98保留真实CW DMA后的量化线性图像，原厂16.000750250秒窗口完成33次CW／group、32帧连续统计、两批122次有限采样，旧RAW计数始终0。原生93,696字节和原厂保存的两份共1,536字节独立重算一致；两批同publication33／frame61，非122个新RAW。最终原厂显示Error、预览0，完整取景／摄影未过。当前完整Python715项通过，RawPy未运行。见[r96–r98报告](docs/history/2026-11-04_实施-Z62连续供帧与保留帧有限采样r96-r98-report.md)和[有限来源合同](qemu/z62-capturework/FINITE-CONTRACT.md)。

主要难点是：r104 菜单／半按恢复的宿主通信超时尚无根因证据；CW 新来源还未支持 paired ingress、旧 output-lineage 标签和视频配方；多输入引擎、bank 及逐单元完成的合同仍不完整；NOR/个体标定、镜头反馈与内部 AF/PDAF 数据格式仍缺。下一次生命周期实验需按实际应用索引推进，并在超时前保留宿主现场。不能靠扩大队列、改原厂返回值、延长等待或补 ready 来宣布完成。公开 T-Kernel 2.0 的服务编号与目标不同，只用于语义参考，不据此宣称已确认整个 RTOS 产品和版本。

r86 的配置读回不等于原厂写入/提交证据。r89 已接入独立 C MAIN、冻结 transfer、worker 和有限控制；r91 另外取得原厂提交及中断 ACK 证据，仍未证明高层工作完成。完整 run/stop 合同、下游 ISP 和整机恢复待验收。LUT 打包输出属于编码域，不能直接冒充旧 ISP 所需的线性 RAW；组曲线/系数读回零也不能据此断言资源被擦除或代填成功。

## 构建与运行

公开仓库是源码快照，**不附带 Nikon 固件、相机/NKN 原件、虚拟卡、工具链或已编译 EXE**。源码检查、原生设备测试、固件运行与实际界面验收是不同层级；首次克隆不会自动得到本地各阶段的 `.build` 缓存。

建议 Windows、Python 3.12 和 ASCII 的 D 盘工作路径。所有新产物留在项目目录：

```powershell
git clone --recurse-submodules https://github.com/new-Beginner/z62-qemu.git
cd z62-qemu
New-Item -ItemType Directory -Force .runtime/tmp | Out-Null
$env:TEMP=(Join-Path $PWD '.runtime/tmp')
$env:TMP=$env:TEMP
$env:PIP_CACHE_DIR=(Join-Path $PWD '.runtime/cache/pip')
$env:PYTHONDONTWRITEBYTECODE='1'
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-raw-verify.txt -r requirements-video.txt
```

固定 QEMU **10.2.4**。当前本机 r69 EXE SHA256 为 `37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9`，VMState 55；这是已验收对象的身份，不要求另一台编译器生成相同字节。现有研究脚本有严格的源/二进制绑定，不应删检查或强改 manifest 来“修复”环境。

准备合法取得的 C1.70 输入、依赖及对应内核后，当前工作目录入口为：

```powershell
./start-z6ii-workspace.cmd --group23-fixture artifacts/fixtures/group23.bin --sd-card artifacts/fixtures/card.raw --software-card artifacts/my-photo-card
```

该入口使用 r75 界面/r69 内核，检查 Q: 是否确实指向当前目录；已被其它位置占用则拒绝。`group23` 是明确合成实验配置，非个体 NOR/标定。旧 `start-z6ii-qemu.cmd` 保留旧机身研究配置，不自动升级内核。

- [当前照片操作与限制](docs/profiles/README-Z62-COMMITTED-PHOTO.md)
- [输出来源、模式确认和 r69 构建边界](docs/profiles/README-Z62-OUTPUT-LINEAGE.md)
- [工作目录存储说明](docs/profiles/README-WORKSPACE-STORAGE.md)
- [异步软件录像路线](docs/profiles/README-Z62-ASYNC-VIDEO.md)
- [候选固件输入边界](docs/profiles/README-FIRMWARE-TEST.md)
- [r86 像素核心、复现方法及设备集成缺口](docs/profiles/README-Z62-CAPTUREWORK.md)
- [r87–r91 MAIN、RAW 域与 QEMU 采集后端](docs/profiles/README-Z62-CAPTUREWORK-DEVICE.md)
- [r94/r95 虚拟参数与实际标定边界](qemu/z62-capturework/GROUP-PARAMETERS.md)
- [r96–r98 连续源、真实等待和有限采样](docs/history/2026-11-04_实施-Z62连续供帧与保留帧有限采样r96-r98-report.md)
- [r104 四帧来源、预览与生命周期失败](docs/history/2026-11-04_实施-Z62采集四帧来源与原厂预览r104-report.md)

未持有完整构建链时，可先运行公开仓库的 `tools/check_public_source.py` 所列无固件子集。它不等于重跑完整历史回归、原生 QEMU、LibRaw 解码或原厂窗口。r91 本地完整测试发现为 701 项、零失败／错误／跳过，174.859 秒；这是已有完整研究环境的记录，不代表公开新克隆能直接运行所有测试。该环境没有 RawPy。

上一 r85 公开副本已执行 **32 个模块、131 项测试，0 失败/错误/跳过**，并检查850个导出文件哈希、567份Python源码的内存编译及Markdown链接；没有加载固件或启动QEMU。该环境没有RawPy，因此该公开检查不冒充重跑LibRaw/RawPy独立解码。r86 数值检查独立记录；本次公开发布的实际复核范围见公开仓库 `docs/VALIDATION.md`，不能把历史计数冒充本轮全量结果。

上一 r86 公开副本实际复核为 **32 模块、131 项无固件测试通过，零失败／错误／跳过**；另以 GCC 16.2.0 严格编译公开核心并执行 **8 个 C case 全部通过**，不依赖私有 relocation manifest。862 个导出文件哈希、573 份 Python 内存编译及 Markdown 链接通过。r91 本次发布的实际复核单独记录在公开仓库 `docs/VALIDATION.md`，不把历史计数当成本次结果。

历史 r91 公开副本实际执行 **33 模块、134 项无固件测试，零失败／错误／跳过**，另以 GCC 16.2.0 严格编译并通过 **16 个 C case**（8 像素、3 MAIN、5 transfer）。902 个导出文件哈希、593 份 Python 内存编译和文档链接检查通过。r98 的公开副本复核另记在公开仓库 `docs/VALIDATION.md`；本地715项、原生DMA及原厂窗口分别计数，不把源码检查称为完整相机或RawPy验证。

本次r98公开副本实际通过**35模块、143项无固件测试，0失败／错误／跳过**，另有**16个严格编译的C case通过**；962个导出哈希、635份Python内存编译、Markdown链接及被排除产物／凭据形态检查通过，819个未转换文件与研究目录字节一致。最终文档回写后再核验静态清单；此次源码检查未加载固件或启动QEMU，未重跑本地715项或RawPy／LibRaw，不改变原厂Error与整机未通过结论。

本次 **r104 公开副本实际通过35模块／143项无固件测试、16个基础C case**，零失败／错误／跳过；1,015个导出哈希、670份Python内存编译、Markdown链接及被排除产物／凭据形态检查通过。860个未转换文件与研究目录字节一致。此检查没有启动QEMU、重跑715项或RawPy／LibRaw；r104数据证据重新核验与生命周期失败分类单独记录。最终文档回写后另做静态核对。

## 开发过程、参考与许可证

历史r103公开副本实际通过**35模块／143项无固件测试、16个基础C case**，0失败／错误／跳过；998个导出哈希、660份Python内存编译和文档链接检查通过，847个未转换文件与研究目录字节一致。它不启动QEMU、不重跑本地715项或LibRaw；当时新增QEMU数据工作及两个原厂窗口的验证另见r103报告和公开`docs/VALIDATION.md`。

开发顺序为：受控启动/菜单 → RAW/统计/近似 ISP → 机身输入 → 软件照片/NEF/视频 → 来源绑定与模式往返 → 当前原厂采集和内核等待定位。历史报告保留失败、未完成窗口和解释更正，不伪造逐日 Git 提交。

- [项目任务与逐阶段记录](docs/GOAL-Z62-QEMU.md)
- [r69–r71 输出来源和交互](docs/history/2026-11-03_实施-Z62输出来源与独立交互r69-r71-report.md)
- [r74/r75 照片闭环](docs/history/2026-11-03_实施-Z62永久诊断与照片闭环r74-r75-report.md)
- [r79–r82 无快门对照与字段更正](docs/history/2026-11-03_研究-Z62无快门拥塞与事件参数边界r79-r82-report.md)
- [r83–r85 真实内核事件与参考边界](docs/history/2026-11-03_研究-Z62真实内核事件与通知交付r83-r85-report.md)
- [r86 采集像素核心与独立验证](docs/history/2026-11-04_实施-Z62采集像素核心与独立验证r86-report.md)
- [r87 MAIN 来源与生命周期](docs/history/2026-11-04_实施-Z62独立MAIN来源与帧生命周期r87-report.md)
- [r88 冻结 RAW 域与量化重建](docs/history/2026-11-04_实施-Z62冻结RAW域与量化重建r88-report.md)
- [r89 原生采集设备与 DMA](docs/history/2026-11-04_实施-Z62原生采集后端与DMA交付r89-report.md)
- [r90/r91 原厂 MAIN 交付及共享源策略](docs/history/2026-11-04_实施-Z62原厂MAIN交付与共享源策略r90-r91-report.md)
- [r92 连续统计来源桥](docs/history/2026-11-04_实施-Z62采集来源到连续统计r92-report.md)
- [r93 采集组数值与事件96](docs/history/2026-11-04_实施-Z62采集组数值后端与事件96合同r93-report.md)
- [r94/r95 资源追踪及虚拟参数](docs/history/2026-11-04_实施-Z62参数来源与虚拟采集组输入r94-r95-report.md)
- [r96–r98 连续供帧、保留帧有限采样及原厂Error](docs/history/2026-11-04_实施-Z62连续供帧与保留帧有限采样r96-r98-report.md)
- [r103 读出统计桥与原厂停止恢复](docs/history/2026-11-04_实施-Z62读出统计桥与原厂停止恢复r103-report.md)
- [r104 实际 CW 四帧来源与原厂 LCD、菜单恢复未过](docs/history/2026-11-04_实施-Z62采集四帧来源与原厂预览r104-report.md)

上游来源包括 QEMU、xiaoqingfeng0526、JKWTCN、WonderLantern、R3tr0ooo、nightglasses 等作者及其贡献者；Nikon 官方资料用于机型/控件校对。Tornado NKN 仅作为 PC 维修软件协议和结构线索，不能当作镜头电气协议或 AF 源码，其原件/恢复包不公开。RawPy/LibRaw 用于独立 RAW 解码，PyAV/FFmpeg 用于 C 视频编码与审计。公开的 T-Kernel 2.0 仅为语义参考，目标代码仍独立核验。

本项目新增代码按仓库 GPL-2.0-or-later 声明及逐文件说明分发，第三方保留各自许可证；Fenestra上游及其派生修改单独遵守CC BY-NC-SA 4.0与其例外，不对Nikon/NKN原件授予权利。公开副本对私人路径和邮箱脱敏，包括少量源码字面量；转换前后哈希明示于清单，只有transformed=false可称字节相同。省略原始大轨迹/反汇编/固件，被省略证据标作本地材料，摘要不替代原始运行。

## 公开仓库导航

- [构建与父依赖](docs/BUILD.md)
- [功能清单](docs/FEATURES.md)与[已知限制](docs/LIMITATIONS.md)
- [开发时间线](docs/DEVELOPMENT.md)
- [参考、作者与许可证](docs/REFERENCES.md)
- [本次源码验证范围](docs/VALIDATION.md)
- [历史内核事件验收摘要](docs/evidence/latest-kernel-events.json)（r83–r85，非完整原始轨迹）
- [r86采集像素核验摘要](docs/evidence/capturework-pixels-r86.json)（独立数值阶段）
- [r91原厂MAIN／DMA验收摘要](docs/evidence/capturework-original-r91.json)（统计／预览未贯通）
- [r98 发布说明](docs/RELEASE-r98.md)
- [r95 参数追踪摘要](docs/evidence/group-parameters-r95.json)
- [r96/r97 实际等待与供帧摘要](docs/evidence/current-stream-r97.json)
- [r98 保留帧有限统计摘要](docs/evidence/retained-finite-r98.json)（最终原厂 Error，预览未通过）
- [r103 发布说明](docs/RELEASE-r103.md)
- [r103 统计输入、原始等待与恢复摘要](docs/evidence/readout-statistics-r103.json)（预览仍未贯通）
- [r104 发布说明](docs/RELEASE-r104.md)
- [r104 四帧来源与原厂预览摘要](docs/evidence/capturework-preview-r104.json)
- [r104 两色变化及生命周期失败摘要](docs/evidence/cw-preview-lifecycle-r104.json)（菜单恢复未通过）

- [最新 r110 + Fenestra r19 发布说明](docs/RELEASE-r110.md)
- [Fenestra ARM32 阶段与真机门槛](docs/profiles/README-FENESTRA-Z62.md)
- [r110 请求资格诊断摘要](docs/evidence/request-qualification-r110.json)
- [Fenestra r19 局部队列摘要](docs/evidence/fenestra-queue-r19.json)
