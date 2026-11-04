# Z6II 固件测试 QEMU 工作计划

目标：在现有工作区成果上实现可用于测试用户固件的 Z6II QEMU。完整目标仍在进行，不能用菜单截图或设备单测通过代替整机验收。

## 当前检查点 r104（2026-11-04）

- 独立默认 off 的 `z62-capturework-preview` 已实现并构建；EXE SHA `c4a91a02bc5f2c0d0b6154a7c5eb15ebd9ba644f8950a8e3ce8d97d380b7e3e1`。实际 CW 有效行 DMA 后收集四个不同 slot／publication／地址，保存冻结 transfer 和私有量化 linear12；不改客体编码 RAW、旧 RAW 计数或原厂软件事件6。
- Native 两组分别16／14个CW帧；120,960字节NV12、27,427,584字节完整linear SHA、18,285,056字节客体编码RAW保持经独立复核。背压无credit、bank切换四新槽、错误bank与旧通知拒绝、停止／reset／slave隔离通过；旧预览／r103统计native回归通过。新来源只遍历三种缩略几何，不宣称全部全分辨率配方通过。
- 24.000660666客体秒原厂窗口exit0、状态[]、CW541、135来源集合、123份接受来源、122预览批次；671包重构，原厂scalar1,536字节重算。无GDB但有两次短QMP取数暂停；LCD16点橙色RGB(210,60,17)匹配最近实际源，固定色场不能唯一确定四帧中哪帧显示。
- 生命周期窗口证实蓝RGB(41,81,161)／橙色变化到LCD；但首个半按早于实际菜单进入。最后有效样本21.224059秒、preview102，随后TimeoutError、进程exit1；未完成24秒，不是两轮菜单通过，恢复及超时根因均未验证。
- 本次发布重新执行数据证据复核与失败分类，见 `analysis/z62-capturework-preview-r104/publication-verification-1/result.json` 和 `publication-lifecycle-verification-1/result.json`；不是重跑QEMU窗口、历史715项或RawPy。原始运行、失败、源码归档均保留，新增缓存和产物在工作目录。
- 当前工作为r104源码／README／覆盖表／报告及选定摘要的GitHub发布；完整Goal继续active，默认r75／r69保持。未访问相机／USB／物理盘、未修改AF；完整原厂摄影、镜头AF、视频新来源和全局快照仍缺。
- r104公开副本已实际通过35模块／143项无固件测试、16个基础C case，零失败／错误／跳过；1,015个导出哈希、670份Python内存编译与Markdown链接通过，860个未转换文件与研究目录字节一致。最终文档回写后只复核静态检查；这些结果不冒充新QEMU窗口或完整相机验收。
- 下一开发动作：先接入永久host timeout现场保存，再按index1真实菜单进入→半按→index3及新帧恢复推进两轮；不盲目延长等待、不修改已冻结r104语义。报告：[r104](history/2026-11-04_实施-Z62采集四帧来源与原厂预览r104-report.md)，[合同](../qemu/z62-capturework/CW-PREVIEW-CONTRACT.md)。以下检查点均保留当时历史范围和云端状态。

## 历史检查点 r103（2026-11-04）

- 上轮r102为实质进展。本轮独立默认off的`z62-readout-statistics`已构建，EXE SHA 886e70dda9146be3494413250f4f5ce6b4535615c60bc74178d58197d3c19e72；r102／r98及默认r75／r69保持。
- 显式C输入按实际unit4／30×12／61槽资格供给；完整读出缓存、pending lease和owned batch分开，缺源不回用CW，停止需新输入。linear16>>4的C区域均值产生真实统计DMA，不是Nikon测光／PDAF，也不是61个新RAW。
- 新native两个进程exit0，122次DMA／93696字节逐次读回并独立积分图重算；pending缓存／冻结batch／latest选择／停止取消reset／越界均通过；同r103旧r102读出和r98保留CW原生回归通过。没有重跑历史715项或LibRaw。
- 原厂16.000987666秒：两个800h等待均kernel0／BOOL1，原厂真实OR/store已见；状态[]、CW308、grid169，拍摄OSD恢复。初版102392FCh scalar断点只命中暖启动28次，有限阶段未经过，scalar0的缺口保留。
- 另建24.000898083秒无GDB窗口，用两次短QMP暂停保存两份scalar；来源publication34／frame62及publication97／frame125，1536字节独立重算一致。CW541、grid322、状态[]；两窗共1109输入包可逐字节重构。最终LCD已目视，仍绿背景、preview0，取景／摄影未通过。
- 独立verifier37份源、构建绑定15份、新native6份、红检查6份、两个原厂各7份已归档。完整Goal继续active；没有访问实机／USB／物理盘或改AF。
- 下一步恢复CW真实RAW到预览的来源交付，核对提交与四槽cohort／冻结transfer／数据域，不增加旧RAW计数或复制单帧冒充四帧，也不补事件6跳过原厂依赖。报告：[r103](history/2026-11-04_实施-Z62读出统计桥与原厂停止恢复r103-report.md)，[合同](../qemu/z62-capturework/READOUT-STATISTICS-CONTRACT.md)。本次源码发布信息以README／公开仓库为准；下方本地／云端描述均保留当时历史。

## 当前本地检查点 r101／r102（2026-11-04，云端r98）

- 上轮r99／r100为实质进展。本轮r101直接读取C18A7634h／800h两个等待：kernel0／FFCE0000h，BOOL1／0，第二次100701355ns。真实CB C2C38F28h，pattern180Ch→100Ch；第二次mode2及mask已武装，sensor源计数全0、init完成1。独立复核和14份源归档通过。
- 独立r102默认off的`z62-input-readout`已构建，EXE SHA fe98f30251aaedb6736f1cacea2364df38f765b3f58fe4000f27101d9bc9801e。只在已提交2020×136、correction0和unit0控制资格下消费真实提供的MAIN／linear16；完整有效像素处理后才交付functional sensor完成，旧RAW计数不增加、没有客体RAW DMA／物理CMOS等价声明。
- 旧r98缺属性红检查保留；新native2进程exit0，549440B有效像素sum／FNV独立核对，默认off／缺源／暂停／mailbox替换／坏CRC尺寸epoch旧帧／停止取消重启reset／mask及W1C均通过。同r102旧CW6帧9138504样本及旧retained finite两输入122次DMA原生回归通过，无新715项或LibRaw声明。
- 原厂16.001121500秒正常收尾：31CW、288内联读出、319accepted源包可逐字节重构，内联158238720有效字节；97份实际消费者摘要和两种payload独立重算一致。两次等待仍0／FFCE0000h；第一内联源6404315416ns，晚于失败返回6402969312ns。最终3Fh、preview0、LCD关机重开Error已目视，功能恢复未过。
- 当前直接下一步：恢复有限统计unit4阶段的真实输入／30×12／61槽来源；unit0是在其后开放，不能放宽r102资格或补IRQ去迁就等待。新C统计桥必须同源产生实际DMA并冻结batch身份，缺源拒绝；保留r98静态保留帧和r102后置读出，使用独立新版本。
- r102构建绑定14份、新native3份、红3份、原厂7份、verifier40份源归档通过。所有新产物在工作目录，所有自有窗口terminal；默认r75／r69、原固件／AF、根staged两项及公开r98保持。本轮新内容未推送。报告：[r101／r102](history/2026-11-04_实施-Z62原始停止等待与内联读出r101-r102-report.md)，[合同](../qemu/z62-capturework/INPUT-READOUT-CONTRACT.md)。完整Goal继续active。

## 当前本地检查点 r99／r100（2026-11-04，云端r98）

- 上轮完成r98源码／文档推送，云端main=f9ed1dc9e553135f524aabed74466e35338d07d8，属于实质进展。完整Goal仍active，不因发布而完成。
- r99冻结r98内核上取得3对原始调用返回：有限统计消费者、scalar消费者、3F追加；实际状态[]→[63]。31次CW／122次有限采样，16.001479833秒，detach／进程退出通过。scalar输出首8字节01ffffff08000000，不把R0=0当已确认错误码。
- r100首轮逐帧零结果通知消耗128停点；65入口／63返回，两个停止函数未返回、没捕获3F，范围失败保留。另建r100b去除高频通知入口，未改首轮或重启其进程。
- r100b完整16.002262750秒、23对入口返回，32CW／122采样；第一次停止参数1返回0，第二次参数0返回80h。两次mode及四清理均0；第二次到mode入口101203187ns。原字节102DBBACh／102DBBB2h与literal证明80h来自C18A7634h／mask800h／limit100的前置等待失败。尚未直接捕获该等待原始kernel错误，不声称FFCE超时已证明。
- 第二次停止返回6403615875ns，3F追加6403628645ns；最终原厂Error已目视、preview0。下一步追该事件的原始CALL／RETURN、102D7E26h bit1生产者及136行读出阶段提交／rearm／真实完成；不能补IRQ92、ready或旧RAW计数代替数据工作。
- r99及r100b返回／源复核、停止组成独立复核通过；7个新增Python内存编译。r99 verifier归档14份、r100 composition归档17份，原始两窗口各7份。旧归档因跨目录command保存副本拒绝后，新工具只接受verifier声明且SHA一致的工作区closed-command，不重建旧目录。
- 无新内核、未重跑历史715项或LibRaw；所有三个实例terminal、所有产物在工作目录，未访问相机／USB／物理盘、未修改AF。报告：[r99／r100](history/2026-11-04_研究-Z62有限统计后的停止错误r99-r100-report.md)。原厂摄影／模式往返／全局快照／镜头AF／刷机安全仍缺；本地新阶段未推送。

## 当前检查点 r98（2026-11-04，覆盖下方历史“下一步”）

- 本次公开源码更新到r98，默认r75界面／r69内核保持；r92–r98实验默认关闭。公开发布任务与完整相机Goal分开，后者继续active。
- r96真实硬件执行断点观察：慢源原厂AND等待2次成功／1次FFCE0000h超时；10次实际OR/store形成两组完整05B条件。不是所有就绪生产者均缺失。
- r97按64位客体时钟30Hz帧号供MAIN，busy不积压；两个mailbox／两payload，32个accepted包可逐字节重构，三个原始等待全部kernel0／BOOL1。原厂随后停CW并提交61槽30×12有限统计；旧source gate拒绝，保持RAW计数0。
- 独立r98只在CW全部有效行DMA成功后保留量化linear12和源身份，stop保留、reset清除，owned batch冻结、下一请求选latest，source/output alias拒绝。默认off保留旧gate，没有补ready、扩队列、改原厂返回或AF。
- native4进程exit0，两个输入、122次实际DMA／93,696字节独立重算一致；旧有限统计原生回归通过。当前完整715项／187.344秒／0失败错误跳过，无RawPy。
- 16.000750250客体秒原厂窗口正常退出：33次MAIN／CW／group，32帧连续统计，122有限采样／2批／0拒绝。两批都用publication33／frame61／time2047019729ns，非122个新RAW。两份保存scalar共1,536字节从保留packed12和冻结LUT独立重算零差异；CPU0 bit7 ACK写入7次不能称7批。
- 最终LCD已目视，显示关机重开Error，preview0、CW未恢复；8秒早期黑屏结论不能覆盖16秒终态。没有完整摄影／恢复／刷机安全验收，不提升默认入口。
- r98 verifier归档24份源／生成源／清单，16秒原厂窗口归档7份；r97路径失败、错误QOM属性、旧日志截断、r96归档缺command失败均保留，后者只接受SHA相同保存副本。
- [r96–r98报告](history/2026-11-04_实施-Z62连续供帧与保留帧有限采样r96-r98-report.md)及[有限来源合同](../qemu/z62-capturework/FINITE-CONTRACT.md)为当前结论。下一步沿原厂首次失败CALL／RETURN、帧对象与readout／ISP请求定位Error；不重做已验收数值，不靠补通知推进。完整镜头／AF、原厂编码存卡、模式往返和全局快照仍缺。

## 当前起点（2026-10-28）

- r5 为已构建的独立 QEMU，既有记录显示原厂菜单、受描述符约束的合成 RAW DMA、事务完成桥及虚拟 SD 可分别运行。
- 既有原固件循环证据仍有 0x35；RAW→ISP→LCD、拍照编码及存卡闭环未完成。
- 现有入口仅允许固定 C1.70 原包；因此不能直接满足“测试我的固件”。
- 原固件包、参考仓库、本地未提交改动及旧运行环境保留。

## 实施顺序和验收

1. **候选固件输入与隔离测试入口**：支持明确指定的 Z6II C1.70 布局候选包；严格验证容器、成员边界和 CRC，记录候选/基线哈希与差异；候选在单独会话执行，不冒充原版。损坏包和跨机型拒绝。候选状态地址未证实时标记未知。
2. **可重复基线/候选运行证据**：启动、客体时间、LCD、设备计数、QEMU 正常退出；缺失/异常状态不得当成通过。不能将模拟通过表述为可安全刷机。
3. **稳定启停和菜单循环**：沿 03030004 通知生产链定位 0x35，针对有证据的设备合同实现，不直接改固件返回值/清错误/硬补软件通知。
4. **成像链**：参考其他机型逐模块恢复提交、真实内存输出、完成通知、ISP 消费和 LCD 扫描；每个模块记录已知与假设。
5. **拍照和持久化**：原固件触发、编码、虚拟卡生成文件、重开回放，分别验证；虚拟 SD 扇区读写不等于完成拍照。
6. **发布入口和覆盖表**：统一启动入口、输入说明、复现测试、已知缺陷、未模拟器件和安全边界。真实 NOR/标定缺失仍须明确。

## 约束

仅离线模拟和普通文件镜像，不连接相机、不写物理盘、不生成刷机建议。源代码/文档修改使用 apply_patch。测试、构建和工具运行产生的证据由其正式实现输出；不以临时脚本改文件。

完整目标的验收至少包含：候选固件实际执行；多次冷启动与菜单/取景/拍照循环；原固件生成并回放文件；已实现外设的错误路径；已知硬件缺口清单。硬件模型不能证明真机更新过程安全。

## 本轮进度

- 候选输入、隔离入口和未知健康状态处理已实现，见 [使用说明](profiles/README-FIRMWARE-TEST.md)。
- 原有 207 项回归重新通过；候选专属 10 项测试通过。
- `analysis/z62-candidate1/sentinel-run2/report.json`：真实 QEMU 执行修改后 ARM 指令，r0=0x62、PC=0x10020004，正常退出。第一次运行暴露的早期内存观测错误保留于 sibling `sentinel/`，已修复为明确未知状态。
- 原包经候选 HTTP 入口实测运行，手动 MENU 后 index=1 且显示开启；完整固件健康状态仍明确 unknown。测试实例已正常关闭。
- 已开始追踪 r5 上模式请求的间接回调及其返回，不把候选入口当成完整硬件目标完成。

## r6检查点（2026-10-29）

- 统一入口：`start-z6ii-qemu.cmd`，说明见 [README-Z62-QEMU.md](profiles/README-Z62-QEMU.md)。原版/候选都支持；候选使用明确快照哈希，健康状态仍未知。
- 独立新内核已编译、打包：`.build/z62-capcom-2026.10.28-r6/runtime/qemu-system-arm.exe`，SHA256 `6a14316c4a3f25bdce27f4f649710dcc06b15677e416f7c1e80fb6cb810ec132`。r4/r5不覆盖。
- 已定位并补齐CAPCOM GPIO65请求/54应答，映射04282018 bit8 → 04282014 bit7、IRQ65；显式实验属性 `z62-capcom-sync` 默认off。100微秒为功能性时序假设。
- r6短追踪实际观察到IRQ回调→03030024→03030004→原固件mask8通知，未改guest指令/软件标志/返回值/错误列表。
- 两次独立冷启动各3轮退出/重开/导航通过，共6轮，完整空状态列表；关闭组一次第一轮重开失败，一次第二轮复现0x35。证据及复核脚本：`analysis/z62-capcom-r6/`。
- 同一r6原生GPIO/IRQ65及RAW/IRQ92回归通过；r6实际执行修改ARM sentinel，r0=62、PC=10020004；原版和候选CMD/HTTP入口均进入菜单并正常关闭。
- 最终全量226项通过、零跳过。证据复核脚本通过，归一化后两组对照命令均仅差CAPCOM开关。所有本轮测试实例均已关闭。
- 打包中遇到objdump中文绝对路径失败，改为文件名+cwd并校验恢复；旧失败runtime保留。不需要再次完整构建当前r6。
- [本轮正式报告](history/2026-10-29_实施-Z62候选固件与CAPCOM握手r6-report.md)记录完整边界。目标仍active，不能标记完成。

## 下一个实质工作

优先推进原固件自然RAW→ISP→LCD链：以r6为新可重复启动基线，跟踪实际描述符、命令提交、内存输出及LCD消费；参考Z6/Z7的功能ISP，但先核对Z62布局和消费者。不要把合成RAW槽写入或菜单截图当成取景完成。之后继续拍照编码、虚拟卡文件生成/回放、更多冷启动/长稳和错误路径。

当前设备适配器 `tools/z62_capcom_device.py` 的源身份绑定已构建r6，不可直接改它后仍声称旧EXE验证通过；新增设备层应使用独立版本和新manifest，保留现有基线。

## r7检查点（2026-10-29）

- 前一目标回合属于实质进展：r6实现并验收；本回合继续实现了独立r7原生RAW帧源，非仅状态重述。
- 新EXE：`.build/z62-raw-stream-2026.10.29-r7/runtime/qemu-system-arm.exe`，SHA256 `838e82868251e94d57ee72b6f94ff7bf9d6412df56915cf9d66fc5d7b02062b3`。源身份和五层manifest均已验证，r6不覆盖。
- 从真实指令和动态参数区分了两条事件：103→另一模式的消费者；136→IRQ96→逻辑域200→任务4000→1023831E(200,C26A0AC4,C269FAE4)。正确路径中原固件自行交替bank0/1。
- r7用帧时钟驱动实际四槽RAW DMA，仅成功后产生136对应的完成；有背压、停止、失败、主从隔离和复位处理。独立原生qtest及旧RAW/IRQ92回归通过。
- 无宿主RAW/边界注入的原固件实测245批成功，随后固件通过停止寄存器关闭RAW源；不是持续取景，最后截图仍黑。
- 不启用停止应答时，600、2、20、10命令各等约3秒。启用已有input-command-completion后进入mode1（C1888084=01000203）和flag4（C269FA0C=4），仍黑屏。
- 下一模式的C26A060C通道1描述符：计数3C，目标89C48400，slot bytes12000；对应2006A514=3、2006A518=1、2006A540=1、2006A548=3C、2006A550/560=89C48400、2006A580=12000。通道2统计缓冲88EDF000、slot bytes36000。数据在 `analysis/z62-raw-stream-r7/mode1-descriptors/report.json`。
- r7严格菜单循环第一轮重开失败（状态列表空仍不判通过），因此 `start-z6ii-qemu.cmd` **继续指向r6**。r7独立研究入口 `tools/run_z62_raw_stream.py` 已实测启动、计数/版本读取和正常停止。
- 全量238项通过。摘要复核 `analysis/z62-raw-stream-r7/summarize.py` 通过；正式[报告](history/2026-10-29_实施-Z62原生RAW帧源r7与后续统计缺口-report.md)。本轮所有QEMU测试实例已关闭。
- IDA启动脚本未找到本体；本轮使用Capstone和固定镜像GDB锚点，不把IDA缺失当作目标阻塞。
- 并行复制路径误判已定位为Windows偶发保留扩展路径前缀，已保留范围校验/哈希/防覆盖并加入测试。r7构建已成功，无须重复构建。

## 下一动作（以此项覆盖前一阶段的笼统起点）

从r7+input-drain到达的mode1继续：恢复C26A060C统计输出的真实格式及消费者，核对2006A5xx/6xx等描述符；参考Z6/Z7区域RGB统计实现但不照搬地址、尺寸或算法。核对停止/排空通知是否是菜单重开缺口，避免只改等待时间。随后再实现自然ISP输出及LCD消费。当前依然没有拍照编码/存卡闭环。

需要读的现有证据：`analysis/z62-liveview-r6/channel2-route/trace.json`、`analysis/z62-raw-stream-r7/summary.json`、`native-with-drain/report.json`、`mode1-descriptors/report.json`、`menu-cycles/report.json`。不要重做已通过的RAW源定位，也不要把空状态列表或扫描帧计数当成取景。

## r8实施前研究检查点（2026-10-29）

- 尚未构建r8；r6主入口和r7内核、源码身份保留并重新验证。目标仍active。
- Ghidra11.4.2/Java21已部署；修复了Thumb TBB表和RTOS尾调用造成的坏指令伪代码，输出指令列表及质量审查。含`halt_baddata`的早期导出不能作为设备规格。
- 结果就绪线路3、4、96、101、135合成`C188808C`事件`05B00000`。被动/仅135组各9次配对等待全超时；一次整组诊断使1次等待返回1，后8次又超时。结果通知会被消费，不能永久置位，也不能替代136的RAW缓冲完成。
- 新帧对象证据：原固件自然生成`C2CF2C40`，一次线路6诊断后由`10238A80`消费并通过`1022E15C(041A0002,C2CF2C40)`传到上层。没有软件对象注入；统计数据和ISP消费仍未验证。诊断事件未加入正常入口。
- 停止`2EB`前排空位图为0；本轮没有证据将菜单问题唯一归因于缺失排空IRQ。一次GDB生命周期追踪第一轮重开在5.192客体秒后出现index1，第二轮受墙钟限额中止，没有视觉验收，不覆盖既有r7严格失败记录。
- 追加对象所有权追踪证明：`C2CF2C40+14C` 经原固件从`40001→40000→0`；最后一步由线路6后`1022E474`传入`40000`、`1022DFCC`写回触发。宿主没有清软件标志。同窗口未命中`1023594E`，但它可能是特定模式处理函数，不等于所有ISP路径均未运行。
- 复核：`python -X utf8 -B tools/verify_z62_input_research.py`；最新摘要`analysis/z62-input-ready-r8/research-summary2.json`。全量248项回归通过。完整说明见[研究报告](history/2026-10-29_逆向-Z62输入就绪与帧对象r8研究-report.md)。

下一动作以真实对象生产/消费为锚点：区分当前统计/预览对象和拍照处理对象，追踪真正的预览输出提交点；核对统计缓冲格式及提交节奏后再实现独立r8。对象`+14C`元数据释放已验证，无须重做。不要继续假设原固件没有帧对象，也不要仅重复发整组ready/metadata事件冒充已完成图像处理。

## r8实施与验收检查点（2026-10-29，当前入口以此为准）

- 上一轮属实质进展。本轮已实现、构建和验证独立r8有限统计设备，主入口`start-z6ii-qemu.cmd`已升级到r8、端口仍8675，默认不自动按MENU。r6/r7内核保留。
- r8 EXE：`.build/z62-finite-stats-2026.10.29-r8/runtime/qemu-system-arm.exe`，SHA256 `05fcd74d61700eebf4b8f911308b3c5ecabed29e673f581ba7ad97f51ff7bb91`。设备源码及六层manifest身份已绑定，勿改源码后继续声称旧EXE验证通过。
- 已恢复channel1有限profile：30×12 LE-u16、row64、61槽、pitch12000或第二bank的0。`1023A46E`明确将容量减1；消费者`10218D14`读无符号半字，读取60份样本。数据来自最近一次真实RAW DMA的区域均值，属静止场景功能近似，不等价尼康测光/校准算子。
- 原生qtest和旧RAW源原生回归通过；251项全量测试通过。实际无宿主完成事件的原固件运行完成2批/122帧/93696字节，拒绝0、从引擎0。原厂自行切bank/置pitch0并调用`102301BC→10210B0E`处理数据。
- 原固件约16.994客体秒自然开启拍摄OSD；22秒截图已检查，背景仍绿色，真实取景未完成。三轮MENU退出/重开/导航通过，截图确认选中条移动。候选ARM sentinel在同一内核实际执行；实际CMD/HTTP入口及正常关闭也通过。
- 后端真实提交已捕获：`analysis/z62-finite-r8/backend-payloads/trace.json`，11节点容器`C2377F78`/表`C2BBB478`，另有18节点容器`C2377818`。每节点记录16字节，RAM载荷读取512字节。不要再套用17节点静态模板，也不要停留在有限采集或帧对象存在性的重复验证。
- 复核：`python -X utf8 -B tools/verify_z62_finite_evidence.py`；摘要`analysis/z62-finite-r8/summary.json`；[正式报告](history/2026-10-29_实施-Z62有限统计与自然拍摄主屏r8-report.md)。本轮构建、原生测试、原固件诊断、菜单和入口实例均已结束。

下一阶段：恢复上述11/18节点预览处理图的数值和中断合同，建立独立r9实际RAW→三路输出的设备模型，并验证LCD消费。当前源1514×1006、stride2272；输出1920×1080、1024×682、1024×680。取景、拍照编码、保存回放、更新/NOR和整机完整性仍未完成；目标继续active。

## r9实验预览检查点（2026-10-29，恢复验收未过，主入口仍r8）

- 本轮是实质进展：独立r9已构建，实际RAW→三路NV12→原厂LCD已显示测试图样。EXE `.build/z62-preview-2026.10.29-r9/runtime/qemu-system-arm.exe`，SHA256 `cdd260cba6d28801e00ada2df0ce496b2037bdd6b43beb887118c50246be1961`。源码/适配器/七层manifest冻结；后续语义修正需独立新版本，勿修改后继续声称旧EXE有效。
- 像素运算为明确的packed12 RGGB、裁2像素、CFA单元颜色、固定黑电平/sRGB、缩放和NV12近似。它不执行任意节点算子，不完成统计bank0；当前只报告真实预览bank1数据工作。
- 原生C像素测试、原生QEMU DMA/IRQ/W1C/屏蔽/背压/取消/复位/边界测试、旧RAW与有限统计回归通过。261项全量测试通过。候选ARM sentinel及基线/候选HTTP研究入口均正常退出，候选健康未知。
- `analysis/z62-isp-r9/native/report.json`：22.107客体秒，187批/2244路输出/3891419136字节，拒绝0、从引擎0。`frame-4.png`已目视；16个无OSD覆盖背景点与独立计算完全一致。
- `analysis/z62-isp-r9/menu/report.json`三轮菜单状态及导航通过，但预览停在424批。**不能据此升级默认入口。**
- `analysis/z62-isp-r9/lifecycle/trace.json`：单次MENU/EXIT后停留APPLV，33.735到45.054秒预览一直425批；`20102100=120`、`20102608=0`、RAW几何`14000E`、`203800F0=FC400`，没有重新提交后端配置。实际发生1次排空和1次448字节清空读。
- `lifecycle-menu-toggle/trace.json`使用pin9关闭菜单的对照直到40.048秒仍为菜单，未提供替代恢复路径。不要因该对照修改原EXIT恢复验收条件。
- 新结构解析器`tools/z62_backend_packets.py`已解码捕获的参数包，边界/长度/终止测试通过。Ghidra新加MMIO volatile标注保留W1C自写回，优先参考`analysis/z62-ghidra/isp-volatile-isr/`及真实指令。
- 严格复核`python -X utf8 -B tools/verify_z62_preview_evidence.py --require-resume`当前应失败；摘要`analysis/z62-isp-r9/summary-final.json`明确native_pixel_path_verified=true、preview_resume_verified=false、release_gate_passed=false。所有本轮实例已关闭。[报告](history/2026-10-29_实施-Z62预览像素r9与恢复缺口-report.md)、[研究入口](profiles/README-Z62-PREVIEW.md)。

下一动作：定位停止后未重新提交预览的原因，而不是重做初始像素通路。跟踪`103B73AE/73B2`停止等待、`103B7198/103C02EA`节点忙状态、`1038AF44`的`421930E6`回调及上层停止消费。`102646CC`在RAW原因bit10时写`C1864848=1`，当前模型未产生bit10；这是候选缺口，尚未证明唯一原因，不能盲补或直接写软件标志。`103B7680`应按r1=1配置、0开始、2停止区分，不要沿用早期笼统的stop标签。之后再推进统计bank0、更多节点、拍照保存和更新流程。目标仍active。

## r10输入对照检查点（2026-10-29，独立宿主适配器）

- `analysis/z62-isp-r10/stop-waits/trace.json`：两个unit-idle立即返回1，两次421930E6正常投递到102E47B1，没有目标1000单位等待。不补造RAW bit10或写软件停止标志。
- `no-keys-45`在45.051秒仍输出848批，否定本配置下固定30秒停流的解释。`menu-pin0-matched`同条件45.091秒停在424批、排空1/清空读1；外接半按`menu-g14`45.008秒847批、排空0/清空读0。
- `input-descriptors`只读原控制器证实机身半按PG1、全按PG13；外接半按PG14、全按PG15。`10436600`将它们分别解码为80000000/40000000和08000000/04000000。扩展器0没有这些快门位，旧EXIT命名不能证明实物含义。
- `menu-g1`第一次运行读到C0000200（同时半按、全按），虽然预览持续，不能算纯半按通过。原控制器会在半按未生效时抑制全按状态，掩盖了PG13默认低电平。初版`shutter-cycle`同样保留，不能代替r10b验收。
- `z62_shutter_input_v2.py`在原固件开始运行前显式释放PG1/PG13，沿用r9冻结EXE。网页输入24驱动PG1；短点击与释放走原队列，旧扩展器0保留研究接口。r10b定向6项测试通过；原版/候选`entry-v2`及`candidate-entry-v2`HTTP启动/半按请求/释放/关闭通过。
- `shutter-cycle-v2`两轮测试完成，已读到纯半按80000200，没有40000000全按位。两轮导航通过、正常退出；返回拍摄后33.462–39.032秒514→675批，51.836–57.358秒1043→1203批。截图已目视。最终全量267项通过。
- Ghidra导出工具已支持原控制器0x08000000基址；第一次`base=`参数被Windows批处理拆分，失败保留在`controller-input-r10`。改用`base:`后`controller-input-r10b`导出成功，主模块103C02EA复验与原导出完全相同。

统一`start-z6ii-qemu.cmd`已改用`run_z62_shutter_preview.py`，仍端口8675。QEMU内核仍为冻结r9；输入模块分别为保留的`z62_shutter_input.py`和启动释放补充`z62_shutter_input_v2.py`，当前输入版本2026.10.29-input-r10b。实际CMD复验写入`analysis/z62-isp-r10/main-entry`。

最终`verify_z62_shutter_evidence.py`退出0，摘要`analysis/z62-isp-r10/summary-final.json`：纯半按连续预览通过、main_entry_changed=true、complete_emulator=false。实际CMD启动/半按/释放/关闭已通过，本轮所有研究QEMU实例均正常结束。旧r9 `--require-resume`复核仍退出1，保留原输入0失败。后续Shell调用可用login=false避免本轮遇到的PowerShell配置退出拖延，不要将已打印完成的旧handle误当作需要重启的QEMU。

详细证据见[输入研究报告](history/2026-10-29_修复-Z62快门输入与预览连续性-report.md)。新复核工具`verify_z62_shutter_evidence.py`不会把旧r9输入0恢复失败改为通过，整机目标仍active。下一阶段可从已确认PG1/PG13输入与虚拟SD出发观察真实全按拍照路径，定位统计bank0、编码、保存回放的具体设备缺口；所有候选健康和刷写安全仍未知。不要把旧`menu-g1`或`shutter-cycle`当作纯半按证据。

## r11拍照研究检查点（2026-10-29，未改内核或主入口）

- 已实现`probe_z62_shutter_capture.py`：新建独占4 GiB FAT32常规文件，显式释放PG1/PG13，20秒半按、21秒全按、21.5秒释放全按、22秒释放半按。保留客体写入，不触碰既有卡、物理盘或原固件。`probe_z62_liveview.py`与`probe_z62_preview_firmware.py`仅新增可选sd_card参数，旧调用保持无卡。
- `analysis/z62-capture-r11/full-press`完成50.086秒，但只覆盖全按后29.072秒，主屏曝光30秒，因此不足以否定长曝光完成。原厂主屏实际显示485张，半按/全按解码分别80000200/C0000200。
- 补做`full-press-90`完成90.086秒，覆盖全按后69.077秒；无断点、正常关闭，仍无照片。两张独立新卡最终SHA256均为`b50b07c9effb0c8e7822df696a06570696af3974b2c5f92eebfaebb4c77ffb7d`。已保存两个analysis.json，文件只有NIKON001.DSC(512字节)、DCIM、NIKON/Z_6_2目录。不能把初始化写卡当作拍照成功。
- 卡证据仍在ASCII工作目录：首轮`<USERPROFILE>/AppData/Local/Temp/z62-capture-card-85yb_f28/capture.raw`，90秒轮`<USERPROFILE>/AppData/Local/Temp/z62-capture-card-ps9brm8p/capture.raw`。不要清理；后续路线追踪使用首轮卡的snapshot=on，前后摘要一致。
- 新增`inspect_z62_virtual_card.py`只读FAT32短文件名/簇链/文件头清单，越界与循环有界拒绝；JPEG头不等于照片有效。4项新测试通过，全量271项通过。`analyze_z62_shutter_capture.py`只在正常结束且卡摘要匹配后分析。
- `input-route/trace.json`完成：原控制器全按边沿40000000在21.131秒到达`1038DB5E→10204D77`，释放也到达。`system-targets`与`application-targets`只读捕获系统模式接口和APPLV输入方法，均正常关闭。
- 调用链：10436600→1038DC0C→1038DA94/DB5E→10204D76→1020DF2A→模式对象+8（公共102A7BE4）→1029AB9E→1029A9BA→103FD304→APPLV 10540246。APPLV对象C181D9E4，系统上下文C1818BE0，模式表C1818FC4。模式4对象C1819614。
- `input-action/trace.json`完成30.036秒：全按已到APPLV，21.153秒环队列提交返回1；C181D388实际出现13/14，读写索引推进。旧标签`input-action-conversion-return`(1053EDDA)误称转换，实际1053DE2E只是变化布尔谓词，原证据不覆盖，工具后续标签已修正。
- 真正动作映射器为1053E2A0，ROM表1094A588:80000000→13，1094A590:40000000→14；该原厂函数的静态导出在`analysis/z62-ghidra/shutter-action-map-r11/`。队列取出函数1053E902，主取动作函数1053F25E的唯一直接调用点10544C26，R4在10544C4A为选定动作。
- 最终分发包装104E8F3E→105B1F38，目标在模式对象+14；105B1F44时R0=动作、R2=实际回调。另一个检查入口105448D8，返回点10545080；不要未经实测把它认定为阻塞源。
- `action-dispatch`已完成并正常关闭：21.153秒R4=14，10545080的R0=0，105B1F44时R0=14、R2=104E97AD。即全按已越过外层检查，到达真实模式处理器104E97AC。该处理器及104E94B8、105575DA的反编译分别在`shutter-mode-handler-r11`、`shutter-policy-r11`、`shutter-release-policy-r11`。
- 105B3352仅返回C1821EB8；104E94B8对13/14调用105575DA，后者在特定C202C0E7/C202CA4A及参数C01组合下返回0，否则100。104E94B8还根据106217CC加100；其语义须结合运行返回值，禁止强写这些软件状态。
- 宽断点`shoot-gates`（旧session44134）已达到1000次停止上限，在13.216秒正常detach/关闭，退出码1，没有发快门。104E4258从1.348秒起就以LR=104E9A69反复调用，不是已确认的“曝光请求”；保留其错误标签和`interpretation.md`。第二QMP连接读欢迎超时，未实际发送quit，最终是探针自身有界退出。
- 此前session50503的mode-policy已完成，旧“仍在运行”记录失效。结果及后续就绪时序纠正见下面r12检查点；不要重启旧实例。

下一步读mode-policy中动作14的实际返回值/分支，沿第一个真实条件或后续共享工作的调用者定位。不再怀疑已验证的GPIO、系统输入、队列和外层分发。长时无断点观察已经覆盖显示的30秒曝光，不要再仅延长运行来替代分发定位。不要把104E4258泛称曝光，它也服务启动和后台工作。研究报告见[全按与存卡边界](history/2026-10-29_研究-Z62全按与客体存卡边界-report.md)。完整目标仍active，photo_saved_verified=false。

## r12就绪与监视检查点（2026-10-29）

- 纠正前述早期拍照试验解释：20/21秒动作13/14到达时，C1821EB8仍为1，104E97AC提前返回。原厂约30.2599秒自行完成就绪，C1868AE8=3、C1821EB8=0；不是就绪通知永久丢失。帧消息15.938秒已到达，后续操作回调排在约46项任务之后。
- 等就绪后全按已越过策略（100），并把真实全按状态2写入C202C2C0。`ready-work-validation/trace.json`完成45.114秒、stop_reason=virtual limit、窗口已关闭：104E43C8/104E43F2的validation均返回1，104E43EC返回0，未进入失败重绘点。不能再把无照片归因于上述validation失败，也不能将共享工作直接称为曝光请求。
- `ready-full-press`连续观察至90.938秒后旧QMP失效；独立RSP只读快照计时125.082538秒，随后正常退出。观察仍标失败，卡中仅初始化目录和NIKON001.DSC，无照片。旧失败证据与卡均保留。
- 新`z62_qmp_transport.py`修复socket.makefile读取超时后永久失效：每请求唯一ID，保留分片、过滤迟到回复，不自动重发控制命令。真实QEMU/原固件同进程故障恢复、原版/候选统一入口均验证；全量281项通过。复核`tools/verify_z62_monitor_evidence.py`，摘要`analysis/z62-capture-r12/monitor-summary.json`。
- 主入口仍冻结r9内核和r10b输入，候选健康未知。r12研究实例均已结束；2026-10-29续查发现另有旧r4进程46180，本轮不接管、不停止，不能声称系统中没有QEMU。

下一步沿C202C2C0的实际消费者及1055D4BC工作结果定位真实采集请求。完整ISP、照片编码/保存回放、更新/NOR仍未实现；目标active，完整模拟及刷写安全均不得判通过。详见[就绪与监视报告](history/2026-10-29_修复-Z62就绪时序与QMP监视-report.md)。

## r13独立采集接点检查点（2026-10-29，原厂输入对照通过）

- `ready-callbacks`已完成36.172秒并正常关闭。全按窗口126次对象回调只涉及10653FB1/106F22A7两个目标，另有31次表回调。1055D544返回0的首个原因是C202C0DE=0，而该特定变更谓词要求3；10524626随后仍通过gate并提交106387F5(3,1)。不能把返回0解释成整个拍照被拒。
- 参考Z9的独立采集GPIO架构后，在Z62自己的运行时资源表恢复了新路径。`gpio-bindings`完成2.131秒，无按键、正常关闭、卡不变：C18037DC/3814为资源58/59，输入04282014 bit11/12、EXT4/5、IRQ69/70、回调1022A92B、双边沿mode2。原固件初始化1022BE8C，异步工作分别1022A8FE/1022A8D8；释放1022A8A0/1022A868。旧模型没有驱动这些采集接点。
- 已构建独立r13：`.build/z62-capture-contacts-2026.10.29-r13/runtime/qemu-system-arm.exe`，SHA256 `81406798183345e1aa975aada2c05151aa61c4514cfcee926fc8375cdf95c1fc`。源码/适配器及八层manifest冻结，不改源码后仍声称旧EXE有效。主入口仍r9，r13新功能默认关闭。
- 新设备原生测试通过：IRQ69/70、电平、边沿、屏蔽锁存、分别W1C、CAPCOM共存、主从隔离、只读输入、复位。旧r9缺少属性的负对照保留。r13上的CAPCOM和预览原生回归通过。旧281项回归及新增4项宿主路由测试分别通过。
- 配对对照已正常结束：开启接点`contact-route-on`40.119秒，关闭组`contact-route-off`40.068秒。开启组原厂ISR依次消费(69,1)、(70,1)、(70,0)、(69,0)，四个异步工作各一次；关闭组均无。两个exec session31033/67990均exit0，不重启。`tools/verify_z62_capture_contact_evidence.py`通过，摘要`analysis/z62-capture-r13/contact-summary.json`明确完整模拟/拍照/刷写安全仍false。
- 两组末尾预览705/706批、状态列表空、没有新RAW描述符。开启组半按/全按工作入口时C23E3F70=0，不能再归因为此禁止掩码；全按释放时C23E3F74=10000，结束时C23E3F68和C23E3F78=1，含义待追踪，不改软件字段。snapshot卡没有保存本次写入，不能拿原卡不变否定guest写盘。

报告：[独立采集接点r13](history/2026-10-29_实施-Z62独立采集接点r13-report.md)。下一步追踪1022A8D8→1022CE38(1B)的消费者及C23E3F74掩码来源，定位实际采集提交；不重做已验证的GPIO路由。原ROM表1094A484/48C将0410001A/1B映射为应用事件5D/5E，10541B2C/5C会按payload低半字筛选，只有2/4/8/10再经104E8F6C分发动作7/8；物理接点payload低半字1，不应假定必经这个特殊分支。设备C代码、构建/运行帮助模块和探针均在`tools/*capture_contact*`及`qemu/z62-capture-contacts/`，当前本轮实例均已结束。目标仍active。

## r14采集许可与NOR输入检查点（2026-10-29，未改冻结内核）

- **纠正上轮措辞**：C23E3F74的10000包含字节C23E3F76=1，是采集状态，不是已确认错误掩码。`full-state-targeted`完成40.015秒：103F3A6E→1022C28A→1022B620(0)→1022B594返回1；释放后事件1返回0。没有进入状态3。
- `permission`完成36.092秒，32.038秒实际决策时C1869788=0，活动位图C23E3F24与选择位图C23E3F34交集为25、2C。容量124位，描述符C18697A8/B0。不要只看上层空状态列表。
- 宽断点首轮`full-state`在25.036秒达到600次停止上限，没有按键，正常关闭但保留未完成；不需要重启。它捕获了频繁B0/B1条件通知，不能算拍照验收。
- `requirements-boot`完成2.033秒，2C来自1026E866；25/26的设置来自10430787/10430851，清除来自1020F8DD。条件2C由1026E794等待组件47/50的04400046后清除，对应C1868538/3C。基线50已就绪、47未就绪。
- `components`和`component-types`恢复原厂目录：47使用类型索引17(hex，即十进制23)，NOR13420000/E0000，工作区C8068000/D8000；50使用类型20(hex)，NOR13E80000/180000。当前主启动参数只有17、18、32组，未提供第23组。
- 新`probe_z62_group23_fixture.py`仅在独立实验中生成零体+ENDM的E0000字节镜像，以QEMU loader加载NOR地址13420000；没有改软件就绪字段。`group23-header`原厂产生47/50就绪并自行清2C；`group23-capture`完成40.111秒，32.024秒实际全按只剩25阻止，仍状态1、未进3。两镜像SHA256为`c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700`，真实标定未知，未加入默认入口。
- `verify_z62_capture_permission.py`通过，摘要`analysis/z62-capture-r14/summary.json`。本轮六个Python诊断/复核文件通过语法检查，所有QEMU/Ghidra实例均结束；只有旧r4进程46180仍在，未接管。r13内核及主入口r9保持冻结。

下一步以剩余25/26镜头控制为锚点：1043077C/10430822（SysC_Len）→10247ED2/EE2/EF2→103F34D4/34FE/353E→异步103F0262/0298/02F6→103EAA44→103C720C/71CE/724E→102F0E1C。需要定位真实请求、回复、状态和重试；不要直接清条件位或假定AF/无镜头A档限制。`lens-control-loop-r14/104304e4.c`有坏指令/PIC警告，不能当完整规格。详见[许可与NOR第23组报告](history/2026-10-29_研究-Z62采集许可与NOR组23-report.md)。完整目标仍active。

## r15镜头重连与CPU写入观察（2026-10-29，未改内核）

- 已完成9组有界原固件观察并正常关闭。`lens-control`显示回复4100006/7/9首字为0，但这不代表镜头没有底层异常；`lens-policy`显示2F停止请求后立即2E启动请求，状态3→4完成后仍处理pending stop，进入6→7→1→2→3。
- `lens-error-reconnect`证实102F0CA8读槽7=1后调用10314C96(0)/(1)，产生042F0101，经103EE5CC→4100004/3→10430422→1043075C→2F/2E反复重启。`lens-presence-code`核对相关指令与原模块一致。不要再简单归因为上层命令不返回或短按。
- `hold5`完成42.054秒；名义5秒，实际全按31.988–36.922共4.934秒，未出现许可恢复工作1022B702或状态3。普通调度仍为名义绝对时间，不能声称精确5秒。
- 新增`write_watchpoints`到`trace_z62_upper_waits.py`及route接口：对齐、限RAM、拒绝与call-frame窗口混用，原生GDB Z2/z2、单步原指令、记录前后值、正常清理。`slot7-watch`实际观察7次PC10345330、LR1030A8A9、R0=7/R1=1/R2=C293D28C的0→1写入；字节42f82010匹配原固件。清除由原函数10346BA6/10346BB8完成。
- 真正置位链为1030A842：检测为存在且C2941E85重试耗尽→1034532A(7)。运行时R6=0B，配置1030A74C映射类型6。600C候选1034ABD4**没有命中**，不能把它当本次根因。先前工具payload_32偏移错误已更正为描述符+14(hex)，旧记录附纠正说明，不用于协议结论。
- `lens-detect`：0.363秒102F38F4收到C18A7CBF数据起始9101000000000101，byte2=0、byte7=1，沿102F3982→10347DD6(1)置C188A212为存在；103C3114(294)返回0，未强制覆盖。输入来自103867E4回调。控制器候选080311C4构造91帧、08042400注册91命令，尚未确认byte7与物理引脚映射，不盲改。
- 全量292项通过；`verify_z62_lens_evidence.py`通过，摘要`analysis/z62-capture-r15/summary.json`；r14复核重新通过。所有本轮实例都已结束，旧r4进程46180未接管。冻结r13内核、主入口r9不变，整机/拍照/刷写安全仍false。

下一步从检测为存在的原厂数据来源及1030A842重试类型0B入手，恢复MCU/镜头接口真实外部合同。不要写C18A7CC6/C188A212、清槽7或清25/26。详见[镜头重连与写入观察报告](history/2026-10-29_研究-Z62镜头重连与原生写入观察-report.md)。目标active。

## r16无镜头配置与双段输入（2026-10-29）

- MCU原函数080308C0反相读取PG0；描述符2000E33C给出GPIO G=40021800、mask1。未连接且无上拉时读低，误报镜头存在。仅在启动前设置外部PG0高后，原厂91帧byte12=0，经10386848→102F38F4→10347DD6使C188A212=0；槽7与25/26重连消失。未写软件字段。
- `no-lens-capture`完整60.006秒，原厂30.044秒就绪、31.669秒全按自然进入状态3，46.790秒经事件4退出。没有新照片RAW描述符，frame-completions=0；结束预览1288批。snapshot卡不变不等于guest未写盘。
- 新宿主`run_z62_capture_console.py`使用冻结r13内核、实验group23、PG0高和`z62_capture_input.py`双段输入。X半按、S全按，自动半按包含/正确释放；主/MCU两路接点同时驱动。没有r16新内核，r13源码/八层manifest仍冻结。
- `console-entry3`与`candidate-console-entry`均通过全按HTTP、4个边沿/IRQ、释放和正常关闭，候选健康未知。前两次aux数量和版本判断失败保留。NOR23以独立loader加载，不能放入第四boot-aux。
- `no-lens-menu`两轮菜单/纯半按恢复完成并关闭：33.420–38.945秒522→681批；51.796–57.306秒1051→1210批，状态空。目视确认菜单选中项移动与两轮预览恢复；first-menu截图过早仍为拍摄画面，不作菜单视觉证据。`visual-review.json`绑定已审图片哈希。
- 新`verify_z62_no_lens_evidence.py`已通过，最新`analysis/z62-capture-r16/summary-cmd.json`明确photo/complete/flash=false。默认CMD已切换r16宿主+r13内核，端口8675；旧r9Python入口可回退。实际CMD原版及候选测试均通过，已正常关闭；复核同时要求四组入口证据。
- 新`trace_z62_capture_flow.py`追踪实际请求及C23E2948阶段/回调。首轮capture-flow误在MCU断点读master内存失败已保留；capture-flow2已完整60.095秒并关闭，analysis.json复核通过。本轮宿主修改后297项全量回归通过，耗时230.809秒。
- `capture-flow2`：31.561秒请求首字节0，选103ED297；阶段80/4000分别登记未完成位80/4000，8000回调103EC626返回4等待，deadline2774=10100。36.634秒80自然清除；46.685秒计数达到10100、4000清除后继续，1022C5AC实际R0=1/R1=0、caller103EC2EF，不是R0=0取消。无新照片RAW；结束仍stage2000000、callback103E7CD1、pending800000。不能把上层计数完成当照片完成。
- 4000提交链103EC498→10325186→1031624C→排队10320018；`capture-submit`已完整50.043秒并关闭、analysis.json复核通过。31.520秒命中包装但未命中排队worker/下层setup；因此不能归因于worker内部事件C0缺失。提交时C23D9F14=[C23D9F2C,5C,3C,3C,30]，原代码确认capacity=count=60已满。1031624C不处理10225714返回值，待实测该次入队是否返回0。
- 新`trace_z62_capture_queue.py`只在10325186→103EC564调用帧内启用1031627E；`capture-queue`完整36.114秒并关闭，31.471秒实际R0=0/R4=10320019/R7=103EAE81，证明采集工作入队被拒。60项里59个10322449、1个1031FD2B；10325186仍返回0，上层等待未提交工作。`verify_z62_capture_queue.py`通过，queue-summary.json记录哈希。没有修改队列容量或清队列。
- 所有本轮Ghidra均结束。旧r11 ready-queue部分记录显示10322449每次约0.304秒（124/144次worker入口），当前满队列工作类型已匹配。`operation-waits`公共同步函数窗口失败：Unexpected PC 1035D1D8，已关闭保留，不将诊断异常视为固件崩溃。改为具体调用/返回断点后的`operation-waits2`与3秒`prepare-waits`均完成并关闭，所有本轮exec/Ghidra/QEMU测试均已poll终止。
- `verify_z62_worker_waits.py`通过，worker-waits-summary.json：43次103215BC完整配对0.005–0.305秒，分配≤0.001秒、参数收集≤0.003秒、模式切换≤0.007秒、99次状态机在毫秒精度下0秒。准备帧占用队列的耗时已验证。
- 短窗口102333C8内部：查询设置立即返回，C1887CDC掩码8等待8次返回1无延时；1023382C以(C1887CDC,5,0,100)多次等待0.100–0.101秒返回0。整个提交最长0.303秒，另约200毫秒尚需定位。静态1022F17A的041A000F消费者设置bit4；尚未恢复该消息的硬件生产链，不得注入消息/写事件位，也不得直接认定是统计bank0。
- `capture-lower-build-r16/101046d0.c`坏指令是误按Thumb解码；原字节按ARM是SVC #6系统调用包装。103E5C8E读取其两输出字，不是已确认的采集调度函数。不要据坏伪代码报客体崩溃。

当前优先恢复103215BC→102333C8中的帧完成/缓冲消费合同，使10322449工作自然及时返回、队列消退；再验证真实采集工作10320018被接受和执行。不要重做已确认的快门/请求/入队拒绝链。下一锚点：1023382C mask5超时的生产者041A000F→1022F17A，以及提交剩余约200毫秒（10235AD4/10231FAC等实际分支需继续动态区分）。报告见[无镜头与双段快门r16](history/2026-10-29_实施-Z62无镜头配置与双段快门r16-report.md)。完整目标active。

## r17输入边界工作中（2026-10-29）

- 上一轮是实质进展，r16默认入口和队列拒绝/准备帧耗时证据已完成。重新执行verify_z62_capture_queue.py仍通过。
- 新`trace_z62_frame_delivery.py`基线3.002秒、单次input-event0对照3.054秒均已正常关闭。1.463秒在16次成功RAW批次和内存前缀核对后只发一个硬件事件0；1.469秒10238FF2读41072800 payload bit0→10238B8A任务1→1022F17A收到041A000F。1.546秒下一次mask5等待立即返回1，随后恢复100ms超时。`verify_z62_frame_delivery.py`通过，route-summary.json绑定哈希。
- 同时定位剩余约200ms：10233836→10235AD4几乎立即返回；10233B1C→10231FAC每次约0.202秒。后者1023AE42先102387B6等待，再更新输入参数；本配置C1887D0C=2EB对应ready集合05B00000。这是另一条未完成数据/就绪合同，不随事件0一起伪造。
- 已实现独立r17原生RAW输入边界：qemu/z62-raw-boundary/、z62_raw_boundary_device.py、run_z62_raw_boundary.py、build_z62_raw_boundary.py、probe_z62_raw_boundary.py。仅成功原生RAW事务增加计数后设置bank0 bit0/IRQ94，失败、停止、重复高电平、背压、无关DMA和从引擎均不报告；默认off，W1C/屏蔽沿用原器件。时序为同帧功能假设，不声称精确帧开始/结束。
- `parent-negative.json`已实测失败于旧r13缺少raw-boundary-events属性，正常清理。r17构建68831已exit0，1315项完成；二进制SHA256 `88d902d75dfebf92c633b65c8fc71d19921ac3684653bb513d64d9ca87d63b69`，位于`.build/z62-raw-boundary-2026.10.29-r17/runtime/qemu-system-arm.exe`。设备/头文件/构建器及九层manifest身份冻结，不改源码后冒称旧EXE有效。默认CMD仍r13+r16。
- `native.json`新原生DMA/IRQ94+96/独立W1C/屏蔽/背压/合并/失败/从引擎/复位通过；`raw-stream-regression.json`旧原生源回归通过。297项全量测试通过，151.024秒。上述实例及构建均结束。
- `frame-delivery-native`完整3.026秒，无宿主脉冲，61次原厂041A000F、12次mask5等待全部立即返回1，已关闭。`verify_z62_frame_delivery.py --native`通过，native-route-summary.json记录哈希。另200ms依旧存在，不把该100ms修复当队列/照片完成。
- `frame-ready-contract`完整3.019秒并关闭：mask2EB→实际(C188808C,05B00000,stack,200)等待返回0，随后提交20068100=9E。8个RAM参数描述符已保存。静态`input-parameter-contract-r17`五函数导出完成。该ready集合仍需实际数据合同，不能仅按commit造应答。
- `capture-queue-native`已完整36.025秒并关闭（94108已exit0）：18.604秒入队仍返回0，队列59个10322449+1个10323C2B满60项，10320018未执行；verify_z62_capture_queue.py --native通过，queue-native-summary.json。r17没有解决完整队列/拍照，不升级默认入口。
- `frame-ready-resources`已完整3.017秒并关闭（93323已exit0）：第2项描述符+34头有三条32字节记录，输出88F15000/88F27000/88F39000，半字序列80、26、18、18、18、3C、28、0，后部标识1/2/3。与Z6参考的60×40/row128三平面相似，但颜色/位宽/所有权/中断合同未验证，不能照搬Z6。
- 本轮构建、全部exec/QEMU/Ghidra均已poll确认终止；旧r4进程未接管。下一步以实际二级头和10239EA2→1020C894/89E配置函数、结果消费者为锚点恢复05B00000的真实数据合同；r17边界已验证，不再重复仅补通知的实验。报告见[原生RAW边界r17](history/2026-10-29_实施-Z62原生RAW边界r17-report.md)。完整目标active。

## r18连续统计（2026-10-29）

- 上一轮r17为实质进展。本轮原厂统计寄存器/缓冲合同已恢复；initial-contract首轮读MMIO洞失败保留，initial-contract2完整3.066秒并关闭。五路format3/1、六槽、地址88E37000/88E73000/88EDF000/88EF1000/88F03000，步长A000/12000/36000/36000/36000。
- 增加有界原生读观察点（Z3），与写观察Z2分离，物理统计池与缓存别名可读，拒绝MMIO、非对齐、超范围和混合call-frame窗口。原厂reader-watch 18.011秒捕获72次读，primary-reader-watch 11.068秒捕获26次读。10240362证明通道0为三个u32和/计数、通道1为u16、2–4三平面u16；原CPU指令和字节匹配。verify_z62_statistics_contract.py通过，contract-summary.json。
- 已实现并构建独立r18：`.build/z62-continuous-stats-2026.10.29-r18/runtime/qemu-system-arm.exe`，SHA256 `6cf9523bc6fca13c3b2fcaf687ca5c9d515fcc2dc9535cc9cc8c6ceb223f6a77`。统计器件、两个头文件、适配器、构建器及十层manifest冻结，勿改源码后冒称旧EXE有效。默认CMD仍r13+r16。
- 数值模型从实际成功RAW按网格生成和/计数、标量及三平面区域均值，明确不等价尼康裁剪/阈值/校准算法。六槽只写当前槽，101在五路DMA全部成功后发出，103在六槽完成后发出；有背压、W1C、mask、源去重、复位、未提交变更拒绝等。不会给其他单元代造ready。
- pixels-before缺头文件负对照、pixels及pixels-diagnostic初版移位错误均保留；独立C测试发现新代码奇数像素应左移4位，pixels-fixed通过。旧冻结内核解包本来正确，未改。parent-negative确认r17缺continuous属性。native.json全数据/30槽/guard/失败路径/旧有限共存通过，finite-regression.json通过。
- firmware-initial 3.019秒仍显示05B00000/200等待返回0；native-contract 3.109秒63帧/10批/1653120字节、拒绝0，从引擎0，C269FA04=8。native-reader 11.041秒原厂三平面36次读全部与独立场景计算匹配。
- native-primary-reader在14.219秒原生读观察单步超时，detach失败，进程最终已关闭，保留失败。读单步改为暂时撤下全部读观察点，恢复后native-primary-reader2完整18.109秒正常关闭：48次sum/count和标量读全部匹配；371帧/61批/9735040字节，拒绝0、背压0、从引擎0。不能把调试超时直接归因于固件。verify_z62_continuous_stats.py --long-observation通过，summary.json明确剩余等待/整机/照片/刷写安全false。
- 302项全量通过（183.896秒）；最后单步调整后21项相关测试通过，最终302项全量复验通过（275.644秒，43524已exit0）。本轮全部构建、测试、QEMU/Ghidra均已poll终止；旧r4会话未接管。报告见[连续统计r18](history/2026-10-29_实施-Z62连续统计数据r18-report.md)。

当前下一动作：统计逻辑位8已由实际数据满足，继续剩余逻辑位1/2/40/200及其硬件来源。原RAW回调10239128的bank4 bit7(135)→ready4000000与bit8(136)→RAW消费不同；公共10238FF2的bank0 bit3/4还包含条件任务分支；engine20由1023926E bank3 bit0(96)→ready1000000，配置10239BEC/1020C17A读取BB70/74/78、BC78、BD78、BB7C/BC7C/BD7C。必须恢复真实处理合同，不能仅把剩余IRQ绑到统计成功。完整目标active。

## r19 机身普通输入增量（2026-10-30）

- 用户目标扩展为完整机身控件、触屏、肩屏和镜头。原拍照/更新目标及全部硬件缺口仍保留，不能以按键页面代替完成。
- 已从原厂 C1.70 `10938C04` 的96项名称表、控制器扫描/汇总/报文和master解码恢复15条普通输入。新增入口 `start-z6ii-body-controls.cmd`，端口8676，沿用r13+r16；默认CMD未变。
- 新增播放8、删除23、释放模式1、i2、ISO19、曝光补偿18、DISP10、放大22、缩小21。原版/候选实际CMD分别通过9组按下/释放的QEMU电平回读，全部释放清空held/queued。候选健康未知。不要套用Z72的ISO20/放大23等旧标签。
- `analysis/z62-body-controls-r19/pin8`完整47.152秒正常退出：PLAY位2、APPPLAY、原厂无卡提示；半按返回后超过5客体秒预览749→918。没有照片回放验收。旧探针缺心跳，名义1秒间隔不是实际物理长按时长；新HTTP探针有心跳/直接电平回读。
- Chrome实际页面验证新增9键可见，ISO点击及释放全部正常；约21.8秒点击i，27.6秒仍为拍摄画面，i功能未验收。页面测试旧stage早于电平诊断字段，最终字段由body-http及body-http-candidate覆盖。页面QEMU已正常关闭。
- 30项相关回归通过，`verify_z62_body_controls.py`通过；摘要 `analysis/z62-body-controls-r19/summary.json`明确全按键功能/照片/整机/刷写安全仍false。
- 控制器双编码器静态采样：0803E360读取PF11/PF14，计数200186D1→C25D6FD0；0803E3B8读取PE7/PE13，计数200186D2→C25D6FD4。主副对应和旋转方向未动态验证。Ghidra导出位于controller-body-r19、controller-expander-r19，原件未改。
- 下一步：追踪i/DISP/释放模式的解码和应用动作，恢复编码器电平序列及组合键；继续AF-ON/Fn/录像/模式盘/拨杆/摇杆/触屏/肩屏/镜头。成像链剩余ready条件仍按r18线索推进。

- 最终补齐汇总真实入口0803D8C4（旧0803D8C8是函数内部位置），确认state[5]写200114F2；补充Ghidra目录controller-summary-entry-r19。最终复核摘要使用summary-final.json，旧summary.json保留。

详见[机身按键r19报告](history/2026-10-30_实施-Z62机身按键映射与控制台r19-report.md)及[实验入口说明](profiles/README-Z62-BODY-CONTROLS.md)。本轮属实质进展，完整目标仍active。

## r20 双拨轮物理输入与ISO组合（2026-10-30）

- 上一轮r19为实质进展。本轮新增双编码器物理层、客体时钟队列、取消回零、主副拨轮网页控件。新入口`start-z6ii-encoder-controls.cmd`端口8677，包含r19所有普通键；仍用冻结r13内核，默认入口及旧适配器保留。
- GPIO端口由QOM memory-region.addr/size解析完整八端口，不硬编码device编号。首次无controller-firmware的原生端口探针未实例化MCU，ports.json保留；ports-with-controller.json验证成功，CPU保持暂停。
- `messages`10.027秒、`queued-messages2`10.037秒：原厂10436600收到的非零计数均严格为[1,0]、[-1,0]、[0,1]、[0,-1]。PF11/PF14为接口0，PE7/PE13为接口1；原厂10938B70名称表提供ROTSW0 MAIN、ROTSW1 SUB。
- `iso-combo`49.132秒：30.09秒原厂就绪后按住ISO，接口0−1、接口1+1；报文0x16明确ISO仍按住。最终原厂AUTO消失并显示Lo0.3。前两张松键图都是AUTO51200，不能单独声称主拨轮ISO数值变化已隔离验收。没有自动快门、软件写入或相机访问。
- 队列最低每相位20ms客体时间，128相位上限，禁止宿主延时后突发补相位。取消用不增加计数的回零路径。7项新模型测试含所有取消前缀；实际`cancel-messages`10.135秒验证四种首相位取消，仅保留既有[-1,0]/[0,1]，不增加反向步数。
- 首次queued-messages探针因重复获取非重入Machine.io锁在约2秒卡住；确认父408808及子412360/暂存9okvzji4身份后仅结束这两进程，失败记录保留。调用rotate移出外层锁，单测使用真实Lock，queued-messages2通过。不能把该宿主死锁当固件异常。
- 最终原版/候选HTTP入口四方向和无效输入拒绝、双段快门、正常退出通过；候选健康unknown。Chrome四按钮实点，browser-status记录16相位、0排队、两轴00，页面释放/关闭后进程退出0。
- 37项相关回归通过（5.538秒）；r19旧证据复核仍通过。r20最终复核`tools/verify_z62_encoders.py`，摘要`analysis/z62-encoders-r20/summary-final.json`。所有本轮QEMU/探针均已结束；没有新QEMU内核或原固件修改。
- 下一步：恢复模式盘和照片/视频、电源拨杆；定位i/DISP/释放模式的原厂功能条件，并在合适模式下隔离验证主拨轮快门、副拨轮光圈及ISO数值。AF-ON/Fn/录像、独立摇杆、触屏、肩屏和镜头仍须实现；r18成像/拍照/更新缺口保持。

详见[r20报告](history/2026-10-30_实施-Z62双拨轮输入与ISO组合r20-report.md)、[拨轮入口说明](profiles/README-Z62-ENCODERS.md)。完整目标仍active，不标记完成。

## r21 工作中：额外机身输入、运行时ADC与模式盘（2026-10-30）

- 已实现AF-ON=PG2、Fn1=PB15、Fn2=PA10、录像=PB1（UI IDs26–29），独立摇杆公共触点11及右14/左15/上13/下12，含四斜向与中央按压。extra-inputs原厂13秒追踪得到四个独立GPIO及九个摇杆报文，释放归零，不是对焦或录像功能验收。
- 新宿主z62_extra_console.py基于r20队列，摇杆保留150ms客体时间、心跳/看门狗及释放全部；新入口start-z6ii-extra-controls.cmd端口8678仍用r13内核。extra-http2及extra-http-candidate分别通过4GPIO+9摇杆、旧拨轮与双段快门、正常退出；候选健康unknown。浏览器检查Fn2/斜向/中央/释放及关闭，进程78946已exit0。
- 新硬件r21继承r18，增加19路12-bit运行时ADC外部输入，转换中的sample保持锁存、下次转换使用新值，不改原固件。EXE `.build/z62-analog-input-2026.10.30-r21/runtime/qemu-system-arm.exe`，SHA256 `0a772865868c4f666024533512d5ede2751255744caf56b594a41da6fc0ef90b`。构建57607已exit0；源码/头文件/适配器/构建器与11层manifest冻结，禁止改后冒称旧EXE有效。
- adc-native.json通过24组bank/resolution/alignment及范围、在途锁存、复位/取消；旧ADC/GPIO原生回归亦通过。旧r18缺input-channel0负对照保留。模式盘资源2000D42C中base40012000、channel2已原厂读取确认；20018447的18是IRQ选择子，首次字段mode_adc_channel_selector误名已记录纠正。
- 原厂八个ADC区间对应code0/1/2/3/6/5/4/10。当前不猜名称。第一次mode-selector在10.244秒读QMP超时、未发模式动作，已关闭且失败保留。extra-http首次HTTP状态超时，forced cleanup已完成，不算通过。
- 系统Temp中Ghidra、旧group23及4GiB卡随后发现消失，原因未知，不断言与超时因果相关。已从校验存档恢复到 `<USERPROFILE>/Documents/Z62-QEMU-runtime`，Java仍D:/java；Ghidra locator更新。新512MiB空白卡sha `a8a6ccc0129b962713931dc8ca130589ee2b0f12b551fb76cca69c7533a2a57f`；新group23保持原合成hash。后续PI_SCRATCH_DIR/TEMP/TMP使用该目录sessions，旧证据不替换。
- 全量318项888.455秒，317通过，唯一旧NativeBoot slave调试端口超时；同项单独复测通过（9.680秒），不改原失败结果。新增hardware_revision三项通过，宿主能分别验证并报告r13/r18/r21，不再对新内核硬标r13。
- mode-selector2/session58299已exit1：21.963客体秒后QMP query-status request14161超时；尚未模式动作，detach=OK、cleanup_error=None、process_closed=True。稳定目录与精简采样未消除监视超时，不能称问题已解决。
- 新增可选observation_timeout_recovery：周期状态读取超时后记录GDB可读性和QMP诊断，回到原RSP事件循环再读；连续三次仍失败，不重放任何控制命令，默认旧行为不变。3项单测通过。注意旧QMP类没有diagnostics，使用延迟hasattr兼容。
- **历史检查点（该观察现已结束）**：`trace_z62_mode_selector.py`输出`analysis/z62-body-r21/mode-selector3`，当时exec session **7467**，目标89客体秒，3000秒wall限额。使用新稳定目录的512MiB卡和group23，r21内核，不自动发快门，启用上述观察超时记录。保留原厂输入/就绪/状态/LCD，省去无关逐帧捕获诊断；八挡每挡5.5秒截图，code3额外主拨轮+1及截图。最终状态见下方2026-11-01复核，不再把7467当作活跃进程。
- 下一线索：扩展器pin0并不是普通按键，state25→summary53→wire57→C25D6FE6是selector值。它很可能与照片/视频拨杆有关，但尚未验证，不能先标注为已实现。另需继续触屏/肩屏/镜头及r18成像缺口。完整目标active。
- 当时检查点（已过时）：mode-selector3/session7467曾轮询到客体5.063秒。观察恢复/输入/旧监视相关36项通过（2.437秒）。按键及ADC证据复核`verify_z62_extra_inputs.py`通过，`base-summary.json`当时明确模式盘/拨杆/对焦录像/整机/刷写安全仍false。[r21报告](history/2026-10-30_实施-Z62额外按键摇杆与ADC-r21-report.md)与[额外按键说明](profiles/README-Z62-EXTRA-INPUTS.md)保留历史状态。

## r22 软件成像与盘点（2026-11-01）

- 重新完整读取goal-objective，优先任务一的场景／镜头、JPEG与存卡回放；完整任务一和任务二仍active，不以读取目标文件作为完成。
- 已在同级`AI/tornado-nkn/recovered`定位并阅读相关报告、脚本、反汇编和验证记录；master/slave/controller去CRC载荷与本工程逐字节一致。复用及适用边界见[能力清单](CAPABILITY-COVERAGE.md)。没有设备I/O。
- mode-selector3终态已核对：89.069客体秒、detach=OK、process_closed=true、无failure或cleanup_error。M主拨轮1/8000→1/6400等原厂证据由新模式盘复核器重新核对。
- 修复测试生命周期：普通路径显式before_stop回调替代三层Request拦截；失败清理直接stop，不再发起未执行的外层输入检查。报告保存last_state和探测器traceback。2项回归先失败后通过。旧`mode-console-http-final`的KeyError记录保留；偶发工作线程失败根因未宣称修好。
- 新原版`analysis/z62-camera-r22/mode-diagnostics-1`与候选`mode-candidate-diagnostics-1`均正常完成，包含旧拨轮、4GPIO、9摇杆、8挡模式盘。`mode-summary.json`明确引用这两份新报告；无参旧复核仍引用原失败，不篡改历史。
- 新增C级软件相机：确定性场景、按QEMU时间推进的手动虚拟镜头、实际像素曝光／裁切／模糊、JPEG、专用目录卡、回放、中央缩放、删除。14项核心测试（含Python -O校验）和4项客体时钟／生命周期测试通过。
- 新入口`start-z6ii-software-camera.cmd`，端口8680，仍使用冻结r21 QEMU，不宣称有新r22内核。原厂GPIO输入和软件成像面板分开；新接口/software/event与/software/status来自同一后端。
- 实际原版QEMU软件流程`software-http-1`正常完成：两张JPEG、独立FFmpeg解码（640×424，RGB814080字节，MSE1.473334316037736）、回放4倍不改原图、删除第二张、关机后卡重开首张一致。已查看照片和放大图；浏览器WebView无法附着，网页交互／布局仍未验收。
- 候选加载分支`software-candidate-http-1`也完成同一软件流程、独立解码及关闭重开，始终保持候选健康未知；本轮使用原包走候选分支，不外推任意修改版。两个实际会话中的三个C核心模块均与当前源码逐字节相同。
- 全量352项通过（216.891秒），原始输出及摘要已保存；新JS语法检查通过。未重编译或修改QEMU设备源码，仍为r21二进制。不存在本轮未收尾的QEMU测试会话；浏览器预览host已正常关闭。
- [操作说明](profiles/README-Z62-SOFTWARE-CAMERA.md)和[覆盖表](CAPABILITY-COVERAGE.md)已建立。原厂场景／RAW帧／机身事件桥、网页实点／布局、NEF、视频、拨杆／触控／肩屏完整行为、原厂AF实验和整机更新／恢复／长稳仍须继续完成。

## r23a／r24：原生场景帧与共享机身事件（2026-11-01）

- 新增88字节头的C级场景包与RGGB packed12输入：epoch、publication-id、frame-id、客体纳秒、固定1514×1006／stride2272、SHA256和零填充。它不是尼康传感器或PDAF协议。
- r23首次构建因Windows GLib的stat ABI类型失败，失败目录及记录保留。修正为GStatBuf后在新目录构建r23a，EXE SHA256 `cd2085ecdc5d77151c07958ae6a111d5055199affac3d751db3568bb019f29dc`，原生完整测试通过。中文命令行数据路径失败由同一ASCII暂存合同对照确认，不改DMA逻辑。
- 实测暂停CPU时经QMP发送约3MB base64帧耗时13.765秒，造成5秒预算超时；没有重放控制命令。新增独立r24文件邮箱层，复用完整包验证，QMP只传短路径。EXE SHA256 `dbe36d222dbfa633086f906f626968635c61d9825eaee8174480bef22a39abf2`；旧r21/r23a及失败r23均保留。
- r24原生测试覆盖四槽逐字节回读、10种坏包不改变活动帧、发布不等于DMA、失败描述符不确认、替换／重复、只读回执、复位保留外部帧、默认关闭兼容旧图样和预加载。文件接口测得0～15ms（约15ms计时分辨率）。旧RAW全套与24组ADC在新内核通过。
- `start-z6ii-native-scene.cmd`端口8681，统一/camera/event；机身全按、半按、播放、删除和缩放的实际电气边沿连接C相机。物理结果未知时不拍C照片，C保存错误不伪装成功或杀死输入工作线程；AF／录像／Fn未实现的C效果不编造。
- 场景现在经过原生RAW DMA及已有近似ISP出现在原厂LCD。C照片选择已被四槽DMA消费的同源RGB帧，核对设置版本、未来时间及1虚拟秒新鲜度；EXIF记录实际采样帧／捕获时间和RAW载荷SHA，未执行原厂JPEG编码。
- 原版live-flow-1、最终原版release-flow-final、候选分支candidate-flow-1均通过共享全按→JPEG→回放4倍→删除→返回取景，FFmpeg独立解码及RAW载荷重建通过。原版及候选MSE分别约1.486／1.476；候选仍为原包走分支、健康unknown。
- IAB隐藏页本轮成功附着。网页实点镜头0.65、拍摄、回放、4倍、删除已验证；显示已保存文件及照片自身帧495／ISO100等信息。异步排队不再误报完成。删除后缩放框未同步的问题已由组件回归修正，未重跑整个浏览器流程；关闭期间有HTTP中止及QMP截屏超时告警，主进程exit0、卡重开为空且无QEMU残留，不能称长稳通过。
- 首轮372项回归通过（189.261秒）；后续JS保存回执／照片信息／缩放同步测试先红后绿，最终全量结果另存。源码、构建、运行和UI证据见[新说明](profiles/README-Z62-NATIVE-SCENE.md)、[设备合同](../qemu/z62-scene-file/CONTRACT.md)及覆盖表。
- 最终373项全量通过（187.220秒），含JS回执／回放信息／删除后缩放状态回归；日志为`analysis/z62-camera-r24/unittest-final.log`。实际原版最终流程与当前六个运行核心文件逐字节一致。浏览器保存／回放／放大／删除已实点，关闭主进程exit0、卡重开为空；HTTP中止／QMP截屏告警保留为长稳待办。详见[r24阶段报告](history/2026-11-01_实施-Z62原生场景与共享事件r24-report.md)。
- 下一步仍优先任务一：完成NEF所需RAW／格式证据与实现，推进视频采集编码保存，补齐原厂镜头／曝光／存储互通及其他控件、关闭和长稳。任务二原厂AF执行／评测尚未完成。总目标保持active，绝不因读完目标文件或C级JPEG成功标记完整模拟完成。

## r25：软件NEF与成组媒体卡（2026-11-01）

- 前一检查回合产出当前388项回归及NEF格式复核证据，并确认全流程探测器缺少events初始化。本回合补齐调用合同，保留旧失败，以全新目录完成实际QEMU验证。
- 新C级NEF是真正Nikon F0 lossless14差分／Huffman编码与TIFF／MakerNote封装，不复制样片。1514×1006已消费预览RAW的12位有效样本左移2位存入14位，明确不增加传感器精度，不声称原厂全分辨率／codec等价。
- `MediaCard` v2支持JPEG、NEF及同编号双文件组，单清单提交、双成员容量、成组删除回滚、关闭重开和外部改动校验；不自动升级旧v1卡，不由原厂固件挂载。
- 原版`analysis/z62-raw-r25/live-media-flow-2`和原包走候选分支`candidate-media-flow-1`均通过JPEG＋NEF、JPEG独立解码和来源重放、4倍回放、成组删除、仅NEF拍摄回放删除，以及进程正常关闭后重开空卡。四份NEF各1,523,084样本逐个一致，内嵌预览逐字节一致；候选健康仍unknown。
- `start-z6ii-media.cmd`端口8682，沿用冻结r24二进制，未修改C设备／13层manifest。网页格式选择、实际NEF拍摄与下载校验、回放4倍、删除后缩放归1及关闭已实点，最终媒体三核心与实际会话副本相同。主进程exit0，专用卡重开为空。
- 增加成组删除中途／提交失败回滚、黑白电平／精度、像素与帧标签失配边界。全量391项首次在夹具truncate遇到NoSpace，未进入该项功能断言；保留失败摘要，D盘临时目录下最终391项通过（282.656秒），没有改动断言或清理原数据。QMP读取／截屏超时、HTTP中止和关闭后Failed to fetch提示仍保留为未修复问题。
- [新使用说明](profiles/README-Z62-MEDIA.md)、[r25报告](history/2026-11-01_实施-Z62软件NEF与成组存卡r25-report.md)和覆盖表已同步；正式证据在`analysis/z62-raw-r25`。独立审计依赖另列`requirements-raw-verify.txt`，生产相机入口不需要RawPy。
- 按用户新要求检查两个参考仓库。Z72最新`d91718fd5c7de88bb48abdc6469669170d6f20d6`较固定HEAD新增203提交，较此前选择性参考4a7bed3新增195提交；获取对象但未切换HEAD或合并。Z62原地址多种路由仍404／重置，公开同源副本new-Beginner的R3完整SHA与本地一致。结果及新RAW／排空／计算邮箱／SFLT／SDHC参考点见[上游报告](history/2026-11-01_分析-Z62与Z72上游更新检查-report.md)，不外推上游已有原厂照片或AF。

下一步仍保持完整目标：沿同一客体时间、场景源和机身事件推进M4视频采集／编码／封装／存卡与独立回放验证；并按Z62原始代码核对新Z72研究与本地原厂采集等待的对应关系。原厂照片、剩余控件、整机恢复／长稳及任务二原厂AF均未完成，不修改或优化AF算法。总目标保持active。

## r26／r26b：同源软件录像与混合媒体卡（2026-11-01）

- 前一回合完成r25的真实NEF与上游检查，属实质进展。本回合完整重读goal-objective后推进M4，不缩减到离线编码器。
- 新增VideoRecorder、VideoCard v3、VideoSceneCamera及录像GPIO29边沿扩展。只录唯一已消费publication，校验epoch／RGB／RAW SHA，以客体采样标签和排他停止边界生成MP4；无音频，60客体秒／1800帧／256MiB缓冲／2GiB解码上限。虚拟卡一组提交MP4与JPEG封面，照片和视频共享编号，旧卡不自动升级。
- `start-z6ii-video.cmd`端口8683，PyAV19.0.2安装于独立环境，CMD版本输出已验证；硬件继续冻结r24，不改C源码后沿用旧EXE。原版和原包走候选分支实际执行了开始／改变曝光／停止／编码／存卡／回放／删除和退出重开空卡。
- 初版libx264rgb数据独立解码逐像素一致，239帧网页样本能播到结尾却出现紫绿偏色。保留旧数据和回归，修正为版本r26b、libx264/yuv420p/CRF18；有损输出分别保存源哈希、解码帧哈希及逐帧MSE，不能继续宣称RGB字节相等。
- r26b `compat-live-1`为10帧／0.462441秒／最大MSE3.952304，`compat-candidate-1`为11帧／0.395768秒／最大MSE3.935702，全部源／RAW标签重放和时间戳检查通过，进程exit0、重开空卡。候选仍是原包经分支、健康unknown。
- 浏览器r26b实际录得203帧／7.479354秒／192499字节，含ISO100→200；导出全部源重放、正确video/mp4、yuv420p Constrained Baseline、最大MSE3.262087，通过灰度颜色视觉复核并播放到结尾。删除后正常关闭、重开空卡；五个媒体核心与实际运行副本相同。
- 补测排他STOP、重复按压／释放、未知GPIO不补造结果、无卡／卡满／提交失败／取消／坏源。新24项专项通过，最终全量415项通过（176.038秒），零跳过。旧RGB全量415项保留历史范围；普通Python无PyAV时跳过视频专项不算视频验收。
- [视频说明](profiles/README-Z62-VIDEO.md)、[r26b报告](history/2026-11-01_实施-Z62软件录像与混合媒体卡r26b-report.md)、[能力表](CAPABILITY-COVERAGE.md)及`analysis/z62-video-r26`证据同步。没有相机／物理盘操作，不以软件视频通过判断真机安全。

下一步优先解决视频编码／审计持输入锁导致交互与监控超时的问题，形成可观测的异步完成与安全关闭，再补齐M5其余控件、状态／曝光联动、原厂存储互通及恢复／长稳。同时继续利用已获取Z72新合同核对Z62原厂采集链；任务二原厂AF仍须按真实接口推进，当前不优化算法。完整目标保持active。

## r27：异步软件录像与后台退出确认（2026-11-01）

- 新增独立AsyncVideoSceneCamera／VideoJob／worker／AsyncVideoCard，编码与FFmpeg审计移出固件输入锁，卡审计移出清单锁。轮询返回紧凑条目，完整逐帧元数据由/software/item显式读取；旧r24／r26b源码与EXE未改。
- 只有受控worker确认退出0、身份／SHA／来源／时间／审计合同复核与卡提交都成功才saved。Windows Job Object按句柄管理子孙进程，取消先cancelling、确认退出后cancelled；提交已开始不假报撤销。结果文件存在、validated:true或worker自己报错均不能代替实际进程终态。
- 原版早期快照live-encode-1有121帧，STOP返回0.407宿主秒，75次实际worker存活观测期间客体和预览推进；live-cancel-1与live-close-1分别验证活进程取消／关闭、无成片与退出重开空卡。原版早期快照范围不冒充最终文件竞争修正版。
- 网页首轮261帧任务在prepared7遇Windows progress.json原子替换共享冲突，真实退出1、卡中0视频，失败现场保留。新增自有文件有界1秒退避和2项先红后绿回归，不重放任何GPIO／QMP控制。
- 最终修正版candidate-encode-final为124帧／4.808994秒，STOP返回1.5宿主秒，78次存活观测中预览173→244、客体21.295→23.765秒，全部源重放、回放／删除／关闭重开通过。使用原包走候选分支，健康unknown，不外推修改包原厂录像。
- 最终网页样本267帧／11.031006秒，最大源RGB MSE2.439623；浏览器640×424播放到结尾、无媒体错误。录制中ISO100／200各205／62帧，停止后后台可应用ISO400且未混入影片。全部267个RGB／RAW来源重放通过；点击回放的工具曾超时，重新读取确认操作已生效，没有重复控制。
- 网页删除后MP4及封面载荷归0，关闭主进程exit0，专用卡重开为空，指定stage无QEMU／worker残留。8个执行核心及新增JS后缀与当前源码一致；25个r24和12个r26b固定文件SHA全部一致。
- 最终全量438项通过（257.102秒，零失败／错误／跳过），21项异步专项和2项JSON共享冲突测试也分别通过。全量摘要由当次工具输出转录，未存完整日志，不伪造日志文件；见analysis/z62-video-r27/regression.json。
- 新入口start-z6ii-async-video.cmd端口8684，版本2026.11.01-async-video-console-r27已由实际CMD验证。使用说明、正式报告、能力表及analysis/z62-video-r27证据已同步。
- 应用户要求再次以Git HTTP/1.1及GitHub API重试：Z62原地址仍not found／404，公开同源副本R3仍4f438994；Z72仍d91718fd，较固定本地多203提交。不能据此推断原地址已删除；参考工作树／origin和固定内核未切换。

下一步优先M5：核对并接入照片视频／电源拨杆、其余控件的应用行为与模式相关曝光绑定，改善统一入口及就绪／关闭反馈，推进恢复与长稳。原厂采集等待沿已确认准备帧队列、真实完成与Z72新合同继续研究。原厂全分辨率照片／视频、镜头协议、AF执行／闭环及更新安全仍未完成；完整目标保持active。

## r28研究：持续选择输入与模式恢复（2026-11-01）

- 前一回合r27补齐267帧来源重放、网页播放到结尾、删除／关闭／重开空卡、固定源身份及正式文档，属实质进展。本回合完整重读目标后推进M5，没有重复构建冻结内核。
- 原厂观察`analysis/z62-selector-r28/pin0-initial-1`已完成55.039客体秒／903.657宿主秒，exec97881已exit0，detach=OK、process_closed=true、该stage无残留QEMU。没有自动快门或guest软件写入。
- 30.772秒持续拉低扩展器pin0，30.799秒原厂报文57从0变1；39.509秒恢复高，39.529秒报文回0。主输入C25D6FE6也0→1→0，其他扩展器位不变。
- 30.133秒原厂OSD存在／ready_join3；38.879秒OSD消失／ready_join1；恢复高电平后47.604秒截图仍相同，至55.039秒仍display_enabled=false。脚本completed是观察完成，不代表模式恢复；不认定照片视频拨杆身份或将其直接绑定C软件模式。
- 2次QMP读取超时后原会话恢复，控制不重发；4GiB专用卡snapshot前后SHA相同。原厂输入链路与显示／就绪切换缺口分开报告。
- 原指令和新有界Ghidra导出恢复C1F7A746／77A→103C9276→C1F7A628（当前／前次／变化）合同；getter103C93B4读当前值，103C93BA／1035CA6E读变化标志。没有调用guest函数或改状态。
- 初版merge导出混入RTOS／混合模式代码，质量检查exit1。仅修Ghidra复制veneer分析边界并先分析原比较器，新四函数导出issues为空、exit0；旧坏导出保留，不作为硬件规格。
- 新`inspect_z62_call_refs.py`与4项先红后绿测试提供有界Thumb BL／B.W候选检索；10200000..10600000中得到1035CA6E的102A5838分支候选，未动态确认后续策略。新工具保留“数据可能解码成分支／非完整xref／未证实运行消费者”边界。
- 最终全量442项通过、199.991秒、零失败／错误／跳过，完整捕获stdout／stderr与摘要保存在analysis/z62-selector-r28。r24 EXE及r27固定源身份未改；默认入口不变。详见[r28报告](history/2026-11-01_研究-Z62持续选择输入与模式恢复r28-report.md)。

下一动作：从C1F7A628的值／变化和原厂应用输入回调追踪持续选择输入的真正策略，区分实体身份、输入接收与模式初始化／恢复。可在1038D886、1035CA6E返回、10540246及实际模式请求处进行有界配对观察；不重做已证实的MCU报文映射，不补写ready_join或display_enabled。之后继续M5其余控件／曝光、原厂采集和后续AF平台；完整目标保持active。

## r29研究：原厂应用交付与就绪路径（2026-11-01）

- 前一r28回合为实质进展，本回合完整重读目标后新增`z62_selector_observation.py`和`trace_z62_selector_route.py`，在原r28虚拟电平计划上增加MCU解码前、比较前、变化检查返回和APPLV入口只读快照。5项测试先红后绿，包含正确R0参数及无效指针／短读保护。
- `analysis/z62-selector-r29/application-route-1`已完成55.126客体秒／813.922观察宿主秒，exec53350 exit0，detach=OK、process_closed=true、指定stage无QEMU残留。共有16份相关快照，原卡snapshot前后SHA相同，控制不重发。
- 拉低30.667秒→MCU30.695秒→比较返回1→APPLV30.701秒，应用实际参数为当前1／前次0／变化1。恢复高39.366秒→MCU39.383秒→比较返回1→APPLV39.386秒，参数为0／1／1。其后原厂分别自然更新为1／1／0与0／0／0，没有宿主写入就绪或变化位。
- 两次APPLV的R0都为C1F7A5AC，输入值与global标量一致；已排除本次MCU／主输入／应用交付丢失。恢复后图片仍无OSD，结束ready_join1，不能据此标记模式恢复或实体拨杆身份通过。
- 新静态导出恢复1029FDEA将输入+7C/+80构造为ID3的0／1批量请求，1035CE6A跳板到103F7D9A；检索到102A0126调用候选。此请求路径尚未动态配对，ID3不直接命名为照片视频。
- 已有原厂10321E20含参数+18变化时清ready_join bit2的条件，10322B50回调置bit2并继续上层就绪。下一步应观察实际清除PC、回调注册／触发及对应设备完成；不能因静态代码存在就宣称这是本次唯一根因。
- Ghidra三个目录均正常导出且原字节未变；system-change两函数结构检查通过，policy中的103FD304间接跳转与request中的10623930 PIC告警保留，不作为完整规格。
- 最终447项全量通过、192.264秒、零失败／错误／跳过，完整捕获stdout／stderr与摘要保存于analysis/z62-selector-r29。r24硬件SHA及r27的13个固定源未变，没有新相机内核或入口切换。详见[r29报告](history/2026-11-01_研究-Z62选择输入应用交付与就绪路径r29-report.md)。

下一动作：对C1868AE8设置有界原厂写观察，配对10321E20的bit2清除、10322B50回调与帧处理／配置请求，验证恢复后卡在哪个真实完成条件；同时复用1029FDEA／103F7D9A请求参数锚点。输入已交付的结论不需重做，不通过软件写状态或仅补完成通知绕过。任务一其余控件、原厂拍照／视频及任务二AF仍保留，完整目标active。

## r30原生就绪字写观察（2026-11-01）

- 前一r29回合新增工具、真实应用交付与447项回归，属实质进展。本回合完整重读目标后实现`trace_z62_selector_ready.py`，对C1868AE8设置4字节原生写观察，并观察10322B50回调，不写guest字段或调用回调。
- `analysis/z62-selector-r30/ready-watch-1`运行55.080客体秒／783.125观察宿主秒，exec97216 exit0、detach=OK、process_closed=true、指定stage无残留。实际4次写入：0.619秒1031ED90的0→0；0.622秒1031A248的0→1；29.924秒10322B5A的1→3；31.145秒10322054的3→1。第二位指掩码0x2。
- 回调入口仅初始化29.924秒一次，切换后至55秒没有再置位，显示仍未恢复。旧r29 trace无写前／写后记录的检查先失败，新原生记录检查通过；没有以静态位置代替运行证据。
- 回调10322B51从10324622加载，分发器恢复栈后由10323FE6尾跳1031624C。此时只确认提交路径，不能直接断言再次入队被拒。
- 此阶段447项回归通过、177.986秒，完整输出保存；两份旧观察库文本已归档analysis/z62-selector-r30/source-snapshot，后续r31改动不追溯为旧库已验证。见[r30报告](history/2026-11-01_研究-Z62就绪字原厂写入与回调r30-report.md)。

## r31回调入队与尾调用观察范围（2026-11-01）

- 原指令确认分发器栈96字节、队列助手栈112字节。新增可选return_sp_delta=-16及gate_return，默认仍0／false；通用队列返回点只在指定窗口内启用，关闭后不重复删除／重装。4项新测试先失败后通过，9项窗口专项全部通过。
- 新`trace_z62_selector_ready_queue.py`只在10324622登记至10316288助手栈回收前观察1031627E的接受返回，核对R4=10322B51并读取原队列；未修改容量或工作内容。
- `analysis/z62-selector-r31/ready-enqueue-1`55.025客体秒／802.969观察宿主秒完成，exec77281 exit0、detach=OK、process_closed=true、指定stage无残留。窗口只开／闭各一次，skipped0、总停顿26。SP实测C5418308→C54182F8，同一GDB CPU线程02，偏移-16，正常关闭。
- 15.627秒原入队返回1，容量60／计数48，含47项10322449准备工作及1项ready回调；29.930秒回调实际执行。本次模型内排队约14.303秒，不当作实机性能。
- 30.637秒拉低、39.395秒恢复高均交付APPLV；到55.025秒该已确认登记点未再次执行，只有初始一次入队记录，不能声称回调再次入队被拒，也不能排除其他队列／配置处理问题。结束ready_join仍1、显示未恢复。
- 10326934／10306820静态小包装调用1034C27C后固定返回1，不能当设备接受确认。1034C27C坏指令导出保留；原指令只确认区域选择和指针前4字节读取，暂不认定为配置传输接口。
- 最终451项回归通过、181.747秒、零失败／错误／跳过，完整捕获输出保存于analysis/z62-selector-r31。r24 EXE、r27固定源和默认入口未变。见[r31报告](history/2026-11-01_研究-Z62就绪回调入队与尾调用窗口r31-report.md)。

下一动作：追踪10321E20的返回控制、活动操作C1868AFC及10323DC6真实分发条件，核对选择切换后为何没有再次到达已确认的ready登记点；不要重做输入接线或将固定返回1当作硬件完成。保留其他可能生产路径的未知性，按原始指令及请求／返回配对推进。继续M5、原厂采集和后续AF，完整目标active。

## r32处理配置对照与r33调用配对检查点（2026-11-02）

- 按用户要求再次复核上游：原Z62地址的网页／API和连接器仍404、Git引用未取得；同一轮可访问Z62副本仍为4f4389944fc339d107f22f5f7ca3f90cc34b78de，Z72 main仍d91718fd5c7de88bb48abdc6469669170d6f20d6、较本地固定HEAD多203提交。历史搜索索引不作当前版本证据，原地址失败原因未知。原始记录analysis/upstream-retry-20261102/evidence.json；不更换origin或合并工作树。
- 发现r28—r31实际argv未启用已有r17 RAW边界／r18连续统计。新增trace_z62_selector_processing.py显式组合已有配置函数，保留--legacy-processing。两组同冻结r21、同固件／实验参数／snapshot卡；临时路径和端点端口归一化后，仅差两个精确-global对，comparison.json已保存。
- r32 ON／OFF分别55.028／55.038客体秒完成、宿主exit0，队列登记10.575／15.629秒、原回调16.669／29.945秒；模型内排队6.094／14.316秒。最末计数样本ON RAW1406／边界1406／连续统计744帧19,522,560字节，OFF RAW1408／边界0／统计0。两组最终ready1／显示false，未解决恢复，不升级默认入口。计数非原子、每条件一次，不作实机性能结论。
- 新trace_z62_selector_configuration.py在103226AE／B2／BA只读配置调用／共享控制位置，增加3项先红后绿测试。原始configuration-1在1200停顿预算中止，最后断点48.871秒、最后周期观察48.825秒、宿主exit1；completed=false保留，detach=OK、process_closed=true。
- 新analyze_z62_configuration_flow.py按原生sequence、CPU线程和精确caller SP配对CALL→RETURN→UPDATED；3项新测试先红后绿。1174位置快照仅有3次完整配置调用、incomplete0／outside_scope1165，重新计算与保存flow相同。调用4.981、9.253、30.682秒，请求kind3／0／1，控制码15／17／17，状态3→4、5→6、9→6，第三次ready3→1；调用边界活动指针均0。高恢复39.241秒后至截断无新配对调用。
- 状态表10225994索引ROM1190A57C[event+state*20]与三个动态样本一致。状态8直接到9的列14／16，另4→10、6→11、19→17，18自环。560个同CPU／SP相邻worker RETURN→UPDATED观察中，初始化9.329秒有16使8→9；高恢复后只见18／状态8。worker观察不能算额外配置调用。
- 原始Thumb确认103244CE的code16前依次检查R8、10327896(R4)返回、103D3464(R4)返回及上下文状态8；后者前缀读取操作+0D与C1864CD2／CD1。另1032286E构造16，其前调用103226D0分配／初始化操作对象。动态生产者和根因尚未确认，不注入控制码或写状态9。
- 最终457项／167.608秒、exit0、零失败／错误／跳过，完整捕获输出与摘要已保存analysis/z62-selector-r33/regression-final.log/json；454项观察器旧阶段保留。r24 EXE、r27固定13个源及r21 EXE复核未变。4GiB卡前／后／当前SHA相同，指定三stage无残留QEMU。两阶段verified-artifacts.json、scope和正式报告已完成。
- [r32报告](history/2026-11-02_研究-Z62处理配置与选择输入对照r32-report.md)、[r33报告](history/2026-11-02_研究-Z62配置配对与控制状态r33-report.md)。没有新相机内核、默认入口切换、原厂照片／视频或AF完成声明。

下一动作以此项为准：对10324498／103244BE前后返回及R4操作对象、C1864CD1／CD2做有界只读观察，区分未进入分支、10327896拒绝与103D3464拒绝，确认真实完成条件；缩小共享位置断点范围后再补完整55秒。不要重做已验证输入接线、重复登记入队或初始像素通路，不将固定返回／状态表列当设备ACK。保留r33预算中止，继续任务一其余控件／原厂媒体、镜头与恢复／长稳；任务二AF尚未完成，完整目标active。

## r34处理拒绝与r35b原厂状态写入（2026-11-02）

- 前一回合完成上游重试、r32严格参数比较和r33调用配对／证据归档，并用原字节确定code16候选门控，属实质进展。本回合继续在同一冻结r21上实现两份独立只读观察工具；不改原厂软件字段、设备完成条件或默认入口。
- 新trace_z62_selector_completion.py六点门控观察，4项必要测试先失败后通过。r34/completion-1完整55.051客体秒／1048.453观察宿主秒、634停顿、host exit0、detach=OK、process_closed=true、指定stage无残留。608次均为103D34B4前缀拒绝，其中456次在高恢复39.253秒之后；共同值为上层8、C1864CD1=4、C1864CD2／操作+0D=29／29、载荷+2CCE=31、计数0。其余五个选定候选位置未命中，不扩展为所有code16来源未执行。
- r34最终ready1／displayfalse，前后图像已目视，OSD未恢复。461项／242.381秒回归通过、完整回归输出保存；运行stdout有一块工具流截断，明确不声称完整stdout，完整trace和completion保留。所有源与证据SHA见analysis/z62-selector-r34/verified-artifacts.json。
- 新Ghidra导出103D3464／10327896结构无问题；103226D0仍有PIC／BADSPACEBASE，不用完整伪代码作规格。重读已有103215BC与原指令确认另一code16来源：10321CD4的R10非零，或10321CE6处理返回非零，可到状态8的10321CF4／CF6写返回槽16；此前只看两个直接构造入口不足。
- 新trace_z62_processor_state.py原生观察C1864CD0四字节，2项提取测试先失败后通过。首版r35/state-watch-1在启动前因内存观察与调用帧窗口冲突失败，随后又读缺失trace产生次生错误；失败和首版源码文本保留。修订为r35b直接沿r29输入计划、独立write watch、显式开启相同RAW／统计配置，不启用入队窗口。
- r35/state-watch-2完整55.159客体秒／769.766观察宿主秒、37停顿、15次原生word写；host exit0、detach=OK、process_closed=true、指定stage无残留。7次byte01变化：0.623秒103D2920的0→1；4.983秒103D313C的1→4；5.000秒103CE574的4→1；9.253秒103D313C的1→4；9.255秒103CE574的4→1；10.374秒103CE868的1→2；30.888秒103D313C的2→4。
- 同30.888秒103D3048先把byte02从2写成29；30.972秒103CF4BE／103CF42C仅改变byte00的1→4→1。到55秒未再记录此word的CPU写，最后native after=01041d00；未另做结束RAM直接读，不冒称覆盖其他写入来源。高恢复39.437秒后无CPU写，ready1／displayfalse，恢复仍缺。
- 新9个静态函数全部结构检查无列出问题、原字节未变。103D2C52的停止辅助涉及C1864CD4／CD5、C237A874／A894／A8B4列表和C237A754软件工作0x8000；三个列表count(+8)全0且CD4为0时才请求0x2000工作。103CE43E的状态4分支可由103CE574写1。软件工作通知不是可以宿主补发的硬件IRQ，具体未满足项尚未动态确认。
- 归一化stage／run路径与端点端口后，r34／r35b底层QEMU argv逐项相同；GDB策略不同，不比较宿主性能。卡前／后SHA均27386955eeb28270fd04bf6e2ea9f6baa09f1235e11f5041dbb0a83dd8e61da7。r21、r24冻结EXE及r27固定13份源保留。
- r35修订前463项／189.220秒中间结果保留；修订后最终463项／180.711秒、exit0、零失败／错误／跳过，完整stdout／stderr保存。r35b运行完整捕获输出也已保存。两阶段清单、scope、正式报告齐全：[r34报告](history/2026-11-02_研究-Z62处理前缀拒绝与状态4门控r34-report.md)、[r35报告](history/2026-11-02_研究-Z62处理状态原厂写入与恢复门控r35-report.md)。

下一动作以此项为准：以30.888秒原厂写4为锚点，对C1864CD4及C237A874／C237A894／C237A8B4三个列表+8计数做有界只读观察，配对C237A754的0x8000／0x2000原厂生产与消费，确认103CE43E在切换后是否再次进入及具体停点；结合新9函数和Z72停止／排空资料，按Z62原字节与运行证据补设备真实合同。不要重做输入接线、初始RAW／预览、回调入队或已确认的状态写入；不写状态1／9，不清队列，不注入软件工作或成功事件。继续任务一其余控件、原厂媒体、镜头及整机恢复／长稳；任务二原厂AF尚未完成，完整目标active。

## r36停止列表与原时钟长观察（2026-11-02）

- 上一r34／r35b回合新增真实门控／原生状态写观察，55秒实测和463项回归、完整证据归档，属实质进展。本回合新增trace_z62_processor_drain.py，读取C1864CD0控制区与五列表头／+8计数，九个原厂点记录通知及恢复路径，不注入事件。
- 3项新测试先失败后通过，55秒观察器全量466项／169.914秒通过。drain-1完整55.020客体秒／923.328观察宿主秒，33停顿、11新增点命中、13周期样本全已知，exec44449 exit0、detach=OK、process_closed=true。已完成stage z62-reference-j6o3li2w无残留QEMU，原卡snapshot前后SHA相同。
- 30.647秒103D2ED4实际准备C237A754／0x8000通知；当时状态2／模式2、CD4=2／CD5=2，C237A8B4=81、其他四列表0。103D2EE2和30.752秒字节00相关工作点均确认同样积压；后者不是0x8000消费者已配对的证据。
- 周期数据纠正“CD4始终未清”猜测：30.960秒CD4=2，36.079秒已为0；列表81→76→71→66→61→58→57，到55.020秒仍57，状态4／模式29。此前状态2期间该表2→22→42→62增长。约每客体秒回收一项是模型内观察，具体超时／退休原因未定，不能把短窗口未恢复称为永久卡死。
- 初始化4.993／9.218秒实际进入103CE43E／状态4分支和谓词返回0，4.997／9.220秒到达写1之前；选择切换后55秒内没有再次命中恢复入口。选定停止辅助的0x2000调用点未命中，不代表覆盖所有生产者。最终ready1／displayfalse，OSD未恢复。
- 新四函数导出／原字节确定正确分发器103CF080：0x8000→103CE2F4，0x10000→103CE69C，0x2000→103CE43E。前者按CD4=2／1给10266076传1／0，后者可清CD4并再查三表。103CF504是字节00相关另一分发器，不能当作0x8000消费者。四函数结构检查无列出问题；原厂通知消费还未按请求动态配对。
- 读取固定Z72 d91718fd的两份研究：其四路排空改善过该机型工作准入，但未证明原厂照片和完整显示；早期未到达命令的停止确认曾撤回。本地r9已含0x14a0000四请求排空及临时输入，不重复添加；本地448／参考640字节差异仍需Z62几何／消费者证据，未因此改冻结C模型。
- 新trace_z62_processor_drain_dwell.py为原时钟150秒长观察，末尾另读RAM并截图，时长限60..180，1项新测试先红后绿。首轮wall_limit6000被已有60..3600合同在启动前拒绝；失败／首版源码保留。修订版2026.11.02-processor-drain-dwell-r36b2改3600，未放宽原启动器。
- 修订后全量467项／224.581秒、exit0、零失败／错误／跳过，完整输出保存；466项旧阶段和55秒runtime日志分别保留。r21／r24 EXE及r27固定13源重新核对未变，默认入口／设备模型未改。[r36报告](history/2026-11-02_研究-Z62停止队列缓慢回收与长观察r36-report.md)、analysis/z62-selector-r36/verified-artifacts.json和scope已归档。

**历史长观察启动检查点（已于后续回合结束）：** 原exec session4268、PID56192、stage svjhjet5、dwell-150-2已完成150.117秒并exit0，见下方r37／长观察终态检查点。pending-dwell.json保留为当时启动记录，不是当前live状态；不要重启或继续等待这个已终止实例。

下一动作以此项为准：先继续150秒运行，确认队列清空后状态1、ready3、原厂预览及OSD是否自然恢复，检查末尾dwell-final.png／RAM快照和退出；尚未完成不能提前标成功。并沿单项回收的实际等待调用／返回和请求身份确定近1秒一项的原因，尤其原指令103CF04C附近等待及正确103CF080分发；不能只缩短原厂超时、清队列或补通知。原厂媒体、其他控件、镜头、整机恢复／长稳及任务二AF仍保留，完整目标active。

## r37实际计数写与r36b2长观察终态（2026-11-02）

- 前一r36回合新增停止条件工具、55秒原厂取证和467项回归，发现CD4清零／列表缓慢回收并启动原时钟长观察，属实质进展。本回合先poll同一handle4268，没有重启，完成了原150秒运行。
- r36b2/dwell-150-2：150.117客体秒／2382.390观察宿主秒、37停顿、31周期样本全部已知，exec4268明确exit0、detach=OK、process_closed=true，stage svjhjet5无残留。期间6次单次连续只读QMP超时后继续进展，控制未重发，完整日志保存。handle4268已终止，不再当作live。
- 长观察的重要分支变化：70.263秒仍状态4／列表43，71.461秒实际进入103CE43E时已为状态3／五表0／CD4=0；75.331秒及149.005末尾直接RAM为状态5／模式29／五表0。74.572秒界面index变0，原因未知，不能直接命名为待机／关机／崩溃。150秒结束ready1／displayfalse，末尾PNG已目视无OSD。
- 所以不能线性推断“81项每项1秒后原路径自然恢复”；实际发生额外状态3处理。原状态4切换恢复仍未验收，但本次队列并非永久不动。初始pending记录保留为历史，终态见analysis/z62-selector-r36/dwell-final.json与dwell-150-2/verified-artifacts.json。新增[长观察最终报告](history/2026-11-02_研究-Z62长观察结束与停止分支变化r36b2-report.md)。
- 新trace_z62_retire_count.py观察C237A8BC原生u32写及96字节RAM栈，3项必要测试先红后绿，全量470项／213.095秒通过。r37/count-watch-1完整55.125客体秒／874.625观察宿主秒、220停顿、198次word写；exec96279 exit0，detach=OK、process_closed=true，stage cmlh9rxd无残留。127次+1均CPU01／1034BF9C，70次-1均CPU02／1034C05C，另1次幂等初始化写。
- 低输入后24次减一，31.703秒81→80到54.671秒58→57；后段间隔大多1.006—1.007客体秒，首个0.830秒。原厂实际在改计数，不是宿主清队列；尚未证明是哪个超时或回调轮询导致间隔。
- 原指令确认移除助手1034C026帧16字节，写点SP+0C保存LR；回调103D32EE帧24字节，其保存LR在写点SP+24(hex)。全部70次分别为103D335B和10295579，对应BL103D3356和BLX10295576。因此本次限定调用链为10295558完成FIFO线程→103D32EE回调→1034C026→1034C05C计数减一。不是仅凭栈中代码地址猜调用链，不是通用unwinder。
- 回调先清工作+3E30一个标志，并在剩余标志非零时以参数5调用让出辅助，退出点103D3334；之后才移除队列，并在状态3／4／6、三表全空且CD4=0时可由103D3424通知0x2000。回调入口至轮询出口／返回的时长、上游完成FIFO供给时机尚未量到。
- 两批6函数导出中103CEE30／103D32EE／1034C026有坏尾部／PIC／栈告警，完整伪代码不作规格；所述局部帧和指令由原始Thumb字节与运行保存字核对。10295558线程循环导出无列出问题。既有定界检索102955A2入队入口保留11候选，仍不是完整运行调用图。
- r37完整runtime／470项回归日志、scope、stack-contract及源／证据SHA已归档；r21／r24冻结EXE及r27固定源／默认入口未改。两个本轮实例均已终止，未关闭无关实例。[r37报告](history/2026-11-02_研究-Z62回收计数写入与回调调用链r37-report.md)。

**当前没有待续的本轮QEMU运行。** 旧4268／96279均终态，使用现有证据后再启动新的、命名独立的实验，不重复跑原150秒。

下一动作以此项为准：对已确认103D32EE回调入口、103D3334轮询出口、103D3356移除前后、10295578实际返回按同CPU／精确SP／请求身份配对，读取仍存活的包和工作+3E30标志，区分上游FIFO供给慢、回调轮询和真实设备等待；返回后不追读已释放包。可用已有调用窗口（entry SP、函数内SP-24、return恢复原SP），不要与native write watch组合。同样需对约70—75秒状态3请求与界面index0的原厂写／参数来源取证，再决定物理保持活动／唤醒对照，不按猜测命名输入或改模型。继续原厂媒体、其余控件、镜头、整机恢复／长稳及任务二AF，完整目标active。

## r38b回调窗口终态与r39／r40工作阶段等待（2026-11-02）

- r38b/callback-2已结束55.083客体秒／865.047观察宿主秒，exec75673 exit0、detach=OK、process_closed=true；70对完整回调、窗口70开／70闭、无incomplete／outside。PID30608／stage ro9s_4eq已关闭，不再poll或重启。初版错误入参筛选／主动终止exit1与源码／测试快照仍保留callback-1。
- 70次entry R0均43080001、busy_3E30均0；entry到poll出口最长1ms。整个回调61次0、8次1ms、1次174ms，例外发生在poll后31.529→31.703秒，不能把全部回调都写成≤1ms。70次返回R0均0，返回extra只有retire_callback，无generic input_r0及已释放包读取；结束显示仍false。
- caller+24实际派发器1029A7D5；1029A7D4先通过1029A714执行阶段，随后改写参数再派发。因此旧“完成FIFO”术语修正为含阶段执行的工作FIFO，保存调用者R4不是实际回调R0。回收包+4的C2BB44F0不是新读到的20阶段表，其具体映射身份未完全还原。
- r39/table-1目标18秒，但10.375秒达到250停顿，exec90135 exit1、completed_observation=false、已关闭。26份完整表均C2BB3E60／SHA80e6020e2732302e5b349d4fbdcab51139209939cedaacd7630c9dac4dbdc78f，三个poll为1026B8F3／102675D9／1026B8EF；消息回调10245379，stage对象与callback userdata分开，不能跳过中间层声称已完整直达103D32EE。
- r40/waits-1完成18.048秒／271.328观察宿主秒，exec42017 exit0、325停顿、159对／1个结束时未返回，outside0；已关闭。A资源事件4次，1.006／1.006／1.004／0.802秒，R0零／非零各2；失败时输出仍初值A0000000。B多事件条件155次，141次R0=0，14次1，主要51—52ms；资源标志0仅3次、28共152次，不能把稳态延迟笼统归因于A。
- B的旧机器标签output-queue不代表FIFO语义：102B5B7E按work+1C构造选择mask，调用102E9144逐个等待work+24的12字节描述符，再原厂清理。实读三项通常指向C1F59AD0，mask随工作变化；不能将某个80000／100000／200000组合当所有工作的常量，更不能把它当硬件IRQ直接补发。
- 477／479／483项既有全量结果、完整捕获运行／测试输出已保存；r38及r39／r40正式报告与scope、源／证据清单归档。r21／r24 EXE、原master和r27固定13源本回合重新核对未变；普通snapshot卡前后相同。默认入口和设备合同没有改动。
- 用户要求再重试上游：原Z62仍未取得引用，网页／API／无代理API／连接器404；可访问同源副本仍R3，Z72 main仍d91718fd／领先本地203提交。第二轮记录analysis/upstream-retry-20261102-r2/evidence.json。继续参考其三路实际写回和结果通知研究，不直接套地址或成功事件。
- [r38报告](history/2026-11-02_研究-Z62回收回调窗口与真实入参r38-report.md)、[r39／r40报告](history/2026-11-02_研究-Z62工作阶段表与两类等待r39-r40-report.md)。上述本轮QEMU均终态；完整相机、原厂媒体、其他控件与镜头、快照长稳、任务二AF仍未完成。

下一动作：已用固定Ghidra导出102E901E／102E9144／102E9092／102E917A／10245378，原字节未变；核对逐描述符CALL／RETURN，定位实际失败项及原厂生产者。没有硬件合同之前只读取证，不缩短超时或写ready。完整目标active。

## r41b逐描述符观察终态（2026-11-02）

- 新工具trace_z62_work_event_waits.py、初版5项先红后绿；首轮events-1因共享回调寄存器字典只有r0-r7、无r8而KeyError退出。exec86422 exit1，trace已detach=OK／process_closed=true，PID14356／stage h5y9bwl2无残留；没有生成有效event-waits.json。首版源码／测试、失败runtime及488项旧阶段回归保留，旧全绿不证明实际适配正确。
- 修订r41b使用已核GDB read_register('r8')显式读当前停住CPU，extended frame字段单独保存在snapshot；不改共享寄存器适配器。新增真实缺r8字典的先红后绿测试，最终6项专项通过。
- events-2在附着前发生本地QEMU debugger connection timed out，exec90513 exit1；trace无hit／observation、process_closed=true，stage osk4vsl7无残留，console空。归一化QEMU argv与r40相同，未确定启动超时原因，不冒充r8修订又失败。完整失败与现场保留events-2。
- 修订后全量exec44788已结束：489项／277.120秒、exit0、零失败／错误／跳过，完整日志regression-final.log/json已保存。结束并发回归后，相同代码／参数的events-3已完成18.001客体秒／290.203观察宿主秒，exec5913 exit0、419停顿、detach=OK／process_closed=true，stage yve0p8x7／PID33372无残留。三次自有实例均终态，不再poll或重启旧handle；没有证明第二次启动超时由并发造成。
- 原Thumb验证102E901E只是按描述符取对象／mask并调1035D3BE；102E9144选中描述逐个等待、遇0即早退。10245378导出含间接跳转告警，不作完整规格。对信号助手102E900E的4MiB有界检索得到四个候选调用点，保存descriptor-signal-callers.json；候选不等于已运行生产者。

- events-3总206对／1未返回／outside0；目标CPU02／SP C541C798为181对：索引0返回0共139次，主要51—52ms，后两项未被尝试；另14组三项均返回1。另一SP C52FAF98为25个count1／参数14、15、23的调用，单独分列，不能混算成目标三项等待。
- 原Thumb确认1026B9F8在work+4非零时可通过102B5B0C／102E9118依次发描述信号并减work+20；取消清理可以让等待通过，但尚未动态证明14组都来自取消。R3原始结果不当已收到事件；末尾17.952秒开始的索引0／mask800000尚未返回，保留incomplete1。
- 三批12函数原字节未变；10245378间接跳转、102B5BE0扩展坏尾部告警保留，限定Thumb局部使用。有界候选清单不当完整调用图。正式[r41报告](history/2026-11-02_研究-Z62逐描述符等待与取消信号边界r41-report.md)、69项证据SHA清单、scope及完整运行／测试输出均已保存。r21／r24 EXE、原master、r27固定13源和普通snapshot卡重新核对一致，默认入口／设备响应未改。

完整目标active。当前无待续的本轮QEMU或测试handle。下一步将139次失败的第一描述与原厂取消／正常结果生产者按活work关联，核实三路数据写回与硬件通知合同后再实现；不将返回成功、取消清理或软件标志等同图像单元输出完成。任务一整体、原厂媒体、其余控件／镜头、快照长稳与任务二AF仍未完成。

## r42取消及其他收尾路径终态（2026-11-02）

- 新trace_z62_work_signal_route.py观察工作等待、取消调用／返回、原厂计数写指令及描述信号入口／OS转发，复用r41逐项等待；返回点只读寄存器，不追读可能已释放work。局部栈核对为取消助手16字节＋描述派发24字节，不当通用栈展开器。
- 新6项专项已通过，最初5项先红后绿；覆盖错CPU／SP／描述／计数、短读、未知指令、缺返回及不同word0身份。word0含义未确认，不把它命名为真实分配代数；allocation_epoch_verified与exclusive_producer_verified均false。
- 全量回归handle62736已结束，495项／180.595秒，exit0、零失败／错误／跳过，完整输出regression.log/json保存。随后才启动同代码18秒动态实验，终态见下一条；输出analysis/z62-selector-r42/routes-1，不覆盖r41证据。未改变原厂时间，观察墙钟上限1200用于更多断点。
- r42/routes-1已完成18.005客体秒／518.328观察宿主秒，exec70043 exit0、1462停顿、detach=OK／process_closed=true，PID45888／stage mzpmahke无残留。没有QMP观察超时；旧handle已终态，不再poll或重启。
- 完整16个取消局部帧全部核对；270个描述入口／OS转发，155个工作等待返回（141次0、14次1）＋1未返回，208对逐描述等待／无未完。末尾停在新工作CALL后，不能把两层incomplete强凑相同。
- 220条限定16字节帧及原BL复核确认：共享102B5B30的141次计数写位置来自102675FC，16次来自1026BA20；单项包装63次均来自102675D0。旧机器标签work-cancel-counter-store不是所有调用都来自取消的证据。新102675F2导出原字节／局部结构通过，但上游成功／失败语义仍未知。
- 9条同活等待区间的描述信号／计数关联：6个成功等待由102675FC发索引0并到达写0位置；另1个成功区间混合102675FC索引1和取消分支索引0；1个失败区间只收到索引1。141个失败CALL计数均仍1或2。其他7个成功CALL计数已0，不作区间外因果归属。
- 全部三项取消链与完整work身份关联仍0，不能按地址放宽。例如C2D1A9C0取消点word0=4、等待点=6且operation不同；C2D2B000另有变化。这是字段变化，不先命名分配代数／复用bug；allocation_epoch与exclusive_producer仍false。ROM表片段5处匹配，运行时地址等价仍未证。
- [r42正式报告](history/2026-11-02_研究-Z62取消及收尾信号与等待关联r42-report.md)、scope、完整runtime／495项回归、3相关源及23证据SHA已归档；r21／r24 EXE、原master、r27固定13源和普通snapshot卡重新核对一致。

完整目标active；未改设备C代码、冻结EXE、默认入口、原厂字段或超时，不补事件。当前无待续本轮QEMU／测试／Ghidra handle。下一步追102675F2实际阶段执行与活work字段写入，核对子工作收尾及数据来源，再决定数据写回／硬件通知合同；原厂成像、完整相机及AF仍未完成。

## r43b多地址写观察修复与阶段／字段来源终态（2026-11-02）

- 新trace_z62_work_stage_origin.py及4项先红后绿专项，读取102675F2实际入口的work、R4阶段对象、R7工作线程、当前索引及20阶段表，并核对LR1029A77F／work指针／部件与当前poll。不会凭相同ROM字节选择表地址。
- 在r42已经观察到字段变化的C2D1A9C0／C2D1A9CC上启用原生4字节写观察；这是局部地址假设，不能当作全局分配身份。保存写前后、原指令与96字节栈，不写guest字段。
- 四项专项通过；修订前全量handle36843已结束，499项／219.042秒、exit0，完整输出regression.log/json保存。origin-1实测暴露双写观察点与STM指令的工具缺陷：只撤下一个写观察点，另一点再次触发，却被旧代码误当单步完成。1035D2EC的STM覆盖C2D1A9C0..CF；1000余停顿后客体仍0.991秒。已核实PID55484／stage5_m6c8jv后主动终止，exec31079 exit1、process_closed=true，失败／旧源码保留，ConnectionResetError来自主动停止，不是新网络故障。
- 新3项单步回归先红后绿，重现另一写点会阻止原STM及写回推进；修订通用观察器为单条原指令暂撤所有活动内存观察，并拒绝把嵌套watch停顿当作指令执行完成。r43b不写原厂内存／寄存器，不改原厂时间或冻结设备。
- 修订后全量handle20584已结束：502项／157.381秒，exit0、零失败／错误／跳过，完整输出regression-final.log/json保存。随后同参数origin-2完成18.007客体秒／306.125观察宿主秒，exec60677 exit0、582停顿、detach=OK／process_closed=true、零只读超时；PID52536／stage c7dkfz4w无残留。原1035D2EC从负面1000次停顿降为本次88次，全部暂撤两写点，实际越过0.991秒；不以停顿次数作性能比较。旧handle已终态，不再poll或重启，负面原样保留。
- 142个入口核对通过、三表完整SHA各自恒定：C2BB43D8／worker C18649E8为62次（A300→675F2），C2BB41A8／C1864B38为32次（69CF8→69446→675F2），C2BB4090／C1864980为48次（6B3D2→6B5EA→675F2）。setup／flag全0。20次入口work+4仍1，进入末段不代表像素成功。
- 278条写观察、99次值变化，原构造写点与寄存器证明：103D359A把操作R4写work+C，359C加载operation[0]后359E写work首字；观察到首字4→6。同时103D3584可把同址用作外层包首字段，R7为该地址、R5为另一work指针。不能把word0当全局分配代数，启动池数据也不能一律作work解释。
- 两批五个实际上游函数导出；A300／69446含C18647D8的80800000／81000000、1000参数等待，6B3D2含200条件，6B5EA含类型传播告警并有条件请求构造／回调。仅核局部原指令，不把伪代码或表存在当成完整执行／设备规格。
- 正式[r43报告](history/2026-11-02_修复-Z62多地址写观察与工作阶段来源r43-report.md)、scope、7相关源／47证据SHA、完整运行／502项回归、负面现场及旧源码均归档。r21／r24 EXE、原master、r27固定13源与普通snapshot卡重新核对相同；改动仅宿主工具与说明，未改默认入口或设备响应。

完整目标active，当前本轮QEMU、测试、Ghidra均终态。下一步核对三条实际前置工作链的等待返回、数据写回与通知生产条件，按已确认合同推进设备；原厂媒体、模式恢复、其他控件／镜头、快照长稳与AF仍未完成。

## r44b前置等待与银行1源路径终态（2026-11-02）

- 新trace_z62_stage_resource_waits.py及6项专项先红后绿，核对A300／69446的80800000／81000000输出等待及6B3D2的200查询；CALL严格核对对象、mask、1000参数及输出栈槽，RETURN不使用已覆盖R2。无效CALL不作有效返回配对。
- 后续102675F2按实际派发LR、同CPU、40／32字节原栈差和活work快照关联。候选通知仅记录四个已核原始调用点的标量参数，不补事件。
- 实际r43快照已有byte74为0／1及word64递增多种状态，不能把所有工作都说成执行了同一等待。静态通知引用只作候选；102646CC导出有间接分发告警，完整伪代码不作规格。
- 全量回归handle61799已结束，508项／233.137秒、exit0，完整输出regression.log/json保存。其后waits-1已完成18.086秒／326.937观察宿主秒，exec84619 exit0、已关闭；旧handle不再poll，初始源码与结果按版本归档。
- 静态回调初选65222只从PUSH开始，漏65220的LDR R1常量；原Thumb和四处65221函数指针引用确认入口65220。旧导出保留，修订导出独立目录；不把旧伪代码推断出的第二参数当成已确认ABI。

- 初始waits-1已完整18.086秒／326.937观察宿主秒，exec84619 exit0、process_closed=true。完整后段捕获12对／1未返回：A300的80800000共5次成功且很快；69446的81000000共7次约1.006秒返回0，输出仍初始81000000，同work在F2时标志由0变1。12次均按原CPU／SP／身份关联。不能把前7.8秒未命中外推成全程没有等待；后续入口扩展计划已按完整证据转为追实际缺失通知。
- 原10263D08在通知42193081且payload bit0为1时检查C1864884跳过计数；非正时增C1864868并由10263D34设置C18647D8／01000000。输入译码102E47B0和固定Z72银行1转发记录可交叉核对；sampling-output-complete是输出比较计时器，不直接当此银行1数据完成合同。
- r44b新增实际源回调入口／跳过计数／01000000发布点，只读标量，新增第7项专项先红后绿。修订后全量handle43876已结束，509项／164.106秒、exit0、零失败／错误／跳过，完整输出保存。其后waits-2已完成18.096秒／321.641观察宿主秒，exec73883 exit0、398停顿、detach=OK／process_closed=true，PID53356／stage6kgxjixh无残留；初始PID49416／stage mfmdlusw也已关闭。旧handle均终态，不再poll或重启。
- 两次都确认12对／1未返回、outside0、12个收尾关联：A300的80800000共5次快成功；69446的81000000共7次约1.006秒返回0，输出仍初始81000000，同work到F2时标志0→1。操作类型／通道0204。200条件查询本窗口未命中；不把未执行说成成功或失败，不将此初始化场景直接外推为原选择切换场景的唯一原因。
- waits-2目标10263D08入口、跳过检查、01000000发布点均0次；跳过计数值未知，不能写0。223个实际候选通知均为00400000。零命中只限定本次观察点与18秒窗口，仍需确认注册／实际路由／DMA，不全局断言没有42193081。
- 本机原1036BAB0／1036EBB6确认银行1状态读口203C0024、模式字节C1801ECD、回调槽C1801ED8，原读后写回与分类mask27EF2080已核；运行时注册／IRQ映射及数据合同仍未验。1036BB24有PIC尾部告警，不从不完整伪代码推断IRQ100绑定。软件payload bit0也不是已确认的硬件状态bit0。
- 正式[r44报告](history/2026-11-02_研究-Z62前置等待超时与银行1通知路径r44-report.md)、两次完整runtime／509项回归、初始源码、7源／71证据SHA及固定Z72契约限制已归档。r21／r24 EXE、原master、r27固定13源和普通snapshot卡前后重新核对一致；未改设备、固件等待或默认入口。

完整目标active，当前本轮QEMU、测试、Ghidra均终态。下一步先核对C1801ECD模式／C1801ED8注册、银行1原处理函数与实际配置，再恢复状态到42193081及有效DMA数据完成的合同；不因payload bit0而盲发硬件bit0，不用输出比较计时器替代银行1完成。原厂媒体、模式恢复、其他控件／镜头、快照长稳与AF仍未完成。

## r45传输注册与消息来源进行中（2026-11-02）

- 复用r9合同与实际22秒快照，确认有多个不同“银行”接口：20100000/IRQ102传输与20380000／203C0000处理器IRQ银行不同。已有预览只在真实4 RAW读／12 NV12写成功后发20100020 bit3及20380024=1002，不完成统计bank0 bit2。不能按名称把42193081直接绑定203C，先追实际注册和消息流。
- r9实际C1801D60区域记录命令回调103B754D和控制回调1038B021；原103BF564读取三状态后570/572/574写回。原103B754C按逻辑位分命令bank0/1。新观察点IRQ102采样只用原CPU R5/R6/R4的18/1C/20值，不额外读IRQ口。
- 102E47B1消息译码钩子由102E47E8经1038B1D8安装到C1809500；另两钩子9504／9508。42193081定义在102BD860，原102BD5E0入队前已构造code／callback／payload字段，新的只读观察器同时跟踪入队、译码、控制／数据／命令分发及等待前实际绑定。
- 新trace_z62_transfer_bindings.py及4项专项先红后绿，严格区分消息R0／R1指针和标量注册值，短读不补零。初版全量handle49936已结束，513项／157.480秒通过，旧源码／日志保留。补入C1801D78三张8项表及C1CF0F40八回调槽只读快照后，r45b全量handle46511已结束，513项／152.308秒、exit0、零失败／错误／跳过，完整输出regression-final.log/json保存。
- bindings-1已完成18.045客体秒／481.422观察宿主秒，1086停顿；handle99290已终态exit0，detach=OK、process_closed=true。PID53116／stage a3fqzuqv已关闭，不再poll或重启。传输寄存器读取使用冻结模型已核无副作用的transfer_read，IRQ样本用原CPU寄存器。

完整目标active，未改设备、原厂数据或默认入口；实际目标42193081来源及有效数据完成合同仍待继续核实。

## r45b传输绑定终态（2026-11-02）

- 701条实际绑定／分发记录逐条与完整trace对应，原指令锚点全部匹配。8份等待前配置一致，mask为1／71／03FF7FFC；228次IRQ102中6次状态1／0／0、222次0／0／8，status1C始终0。不能把持续到达的预览命令bank1完成当单元结果或统计bank0完成。
- 结果槽0／5／6绑定103B7541，槽4为103B7547；原指令确认分别转入103B742A的银行参数1／0。共同路由仍受查询配置、C180955C转发掩码及C1809558回调影响，后两个值本轮未读取，完整结果路由尚缺。
- 两次入队81分别绑定10265221／102646CD，四次译码为81两次、83两次；未观察到10263D09目标消息。消息+18按回调解释，本次81是RAM指针，不能用其bit0作硬件状态。12对资源等待／12次收尾关联及末尾1个未返回保留，目标源跳过计数值仍未知。
- 五新函数导出及9条原字节锚点已核对，两个间接尾跳告警保留；不将整批伪代码判为设备规格。r45最终513项全量记录保持，结构化运行证据完整；某次终端poll截断，因此只称捕获stdout，不称完整stdout。正式[r45报告](history/2026-11-02_研究-Z62传输绑定与结果中断边界r45-report.md)、摘要及证据清单归档。
- 上游第三轮重试确认默认Git对三个仓库均连接失败；单命令指定可访问GitHub地址后Z72成功，仍d91718fd／领先固定HEAD203提交。Z62副本API仍R3；原Z62网页／API／无代理API／连接器404、Git未获引用，原因未知，不认定删除。未改系统网络、凭据、origin或参考HEAD，记录analysis/upstream-retry-20261102-r3/evidence.json。

下一步从真实转发配置与订阅出发：读取C180954C至C180955F、实际结果登记及单元配置，沿103B742A到订阅者确定目标通知生产条件。只有确认硬件节点、有效配置及实际数据写回后才实现独立结果模型；不因同源Z72使用61就直接照搬，不根据软件callback／事件mask决定硬件成功，不缩短等待、不清队列或补软件通知。任务一其余控件、原厂媒体、镜头和整机恢复／长稳仍须继续；原厂AF未完成，完整目标active。

## r46两银行订阅及结果路由终态（2026-11-02）

- 前一r45回合完成701条实际绑定记录、源路由复核及上游重试，改变后续调查点，属实质进展。本轮新增trace_z62_result_subscriptions.py，读取软件转发／硬件屏蔽、两银行实际回调、物理单元表和图配置，不注入完成事件。
- 新5项专项先红后绿，最终全量handle75044已终态，518项／169.759秒、exit0、零失败／错误／跳过，完整输出regression.log/json保存；随后才启动实际原厂观察。
- subscriptions-1已完成18.055客体秒／288.390观察宿主秒、251停顿、245条新记录，handle62189已终态exit0、detach=OK、process_closed=true。PID55468／stage k8puzvhh已关闭，不再poll或重启；正式工具内部记录完整stdout并验证1至251的HIT序号连续。通用capture标志false不改为完整拍照通过。
- 8份等待前配置完全一致：硬件mask1／71／03FF7FFC、软件结果转发mask71、结果回调1038AD1B。原生结果回调存储1次、mask入口／存储各4次；存储后读取均与原CPU值相符。223次库交接实际为mode0、参数1、上下文C23777A0、预测81／10263D4D，未另观察该回调入口，不混写执行已验证。
- 银行0上下文C2377F00的+14表C2377F38，两回调均10263D09，关联11节点图C2377F78；银行1上下文C23777A0的表C23777D8，两回调均10263D4D，关联18节点图C2377818。原始102E6A14的零模式生成81、非零模式生成82；结果路径走非零模式，不能把预览结果82当银行0所需命令81。
- 当前结果表映射物理49／54／55到槽0／5／6、低位01／20／40、事件2／1／4；物理53在槽4、低位10、事件10。结合r45独立槽快照和原包装，三路预览61路由已有Z62依据，但物理配置与真实DMA完成条件、实际IRQ结果交付尚需设备验证。未执行的银行0图仍不能发命令完成。
- 实际图参数已捕获：11节点1份、18节点3份且相同，有限解码与原描述符保存；14个新静态局部导出保留两个间接尾跳告警，102BF71C的错切入口未用于完整函数语义。目标63D09静态登记到C1864CBC已定位，不当作本轮直接观察了全局槽每次写入。正式[r46报告](history/2026-11-02_研究-Z62两银行订阅与预览结果路由r46-report.md)、scope、摘要、图参数、完整运行／测试输出及SHA清单归档；设备、原厂时间与默认入口未改。

**当前没有待续的本轮QEMU运行。** 下一实质动作：在已存在的真实4 RAW读／12 NV12写回之后，以Z62当前物理49／54／55配置、提交和几何为条件，开发独立且默认关闭的新预览结果层，验收低位结果、IRQ／W1C／屏蔽／背压／取消／复位，不能读取软件回调或事件mask来决定成功；另行恢复银行0的11节点真实数据处理以解除81000000命令等待。先复用r46实际参数和Z72固定对象，不再重复怀疑已验证的银行订阅；不得发银行0假完成、清队列或改超时。完整目标active，原厂媒体／镜头／AF与整机验收保持未完成。

## r47/r47b预览结果设备进行中（2026-11-02）

- 上一r46回合取得两银行实际订阅及物理结果映射，属实质进展。本轮已实现并构建独立默认关闭的结果层，未修改冻结r21／r24或默认入口。
- config-1已完成18.027秒／250停顿，exec33558终态exit0，PID41260已关闭；8份物理提交／160字节RAM参数快照证明内部行数1108／700／698，54／55的格式字段随后由ff010000改ff010200，49保持ff010000。不能照抄Z72的内部行数，两个实际配方均保留。
- 初版r47构建exec2045已先完成exit0，SHA55aae5f735a962e47d5531f0b2f506413f46ff47c2429cb369022fae796cd069；仍只接受初始格式，保留为阶段负面基线。格式C回归及native-initial.json已重现其拒绝后续格式；未改旧设备源后声称旧二进制包含修复。
- 独立r47b构建exec43073已终态exit0；新format目录／适配器／构建／校验代码只扩展已观察的54／55 bit9变化，旧r47仍可按旧身份核验。C格式测试通过，native-final1.json全部通过：4 RAW／12 NV12实际像素与边界、逐位结果W1C、共享IRQ102、屏蔽待定、背压、取消／停止、复位、从引擎隔离及8类拒绝无写回／无完成；软件回调／事件字段被种为无关值仍保留，未被用作硬件成功条件。
- 新原厂观察工具trace_z62_preview_result_delivery.py的2项专项先红后绿；delivery-1已完成12.013客体秒／244.453观察宿主秒、608停顿，exec54744终态exit0，detach=OK／process_closed=true。PID54292／stage ym6gh32_已关闭，不再poll或重启。602条记录，49次IRQ原状态0／61／8，146次82回调，145对同CPU／SP／参数发布点；48组完整2／1／4，最后1个回调未配对、第三路尚未观察，保留窗口边界。
- 原生父预览回归exec19029在同一r47b且新功能关闭时通过。最终全量exec14377已终态，524项／186.987秒、exit0、零失败／错误／跳过，完整日志保存；C原生检查另计。不能以这些检查宣布完整相机通过，scope见analysis/z62-results-r47/scope.md。

## r47b预览结果终态（2026-11-02）

- 本回合实现了真实数据处理后才产生的结果设备，而非只增加观察工具。r47b SHA145520bd35f763957f6be0e0cce33cb84312f34a6501991f49a93af91f9e46e8；物理路由B层、像素C层，默认关闭，旧r21／r24／r47、原厂二进制、13项固定交互源和默认入口保留。
- 8份原厂物理配置快照来自当前非出厂标定实验输入，明确不是实机测量。r47初版及格式C失败／QEMU拒绝保留；独立r47b接受54／55观察到的bit9变化，49维持LCD配方。软件回调／事件字段不参与成功判断。
- 原厂145对回调到发布点的计数各增1，但观察间有8次计数回落，范围1至123，扣减来源未另跟踪，不能称最终累计145。银行0命令计数在本次回调采样中为0、跳过计数为1；不能清该计数或靠发送预览82代替银行0命令81。完整trace、HIT1至608连续stdout、未配对末项、scope、源／证据SHA及正式[r47b报告](history/2026-11-02_实施-Z62预览逐单元结果r47b-report.md)归档。[使用说明](profiles/README-Z62-PREVIEW-RESULTS.md)。

**当前没有待续的本轮QEMU运行。** 下一实质动作以本项为准：恢复银行0的11节点输入／输出和有效配置，先完整读取固定Z72的image_generate_grids及本机r46两图参数，核对60×40等实际几何、端口、缓冲、消费者和真实RAW／统计来源后开发独立新设备；只有实际数值处理并写回成功，才产生银行0命令完成。不得直接置20100020 bit2、81、01000000、清软件队列／跳过计数或缩短超时。r47/r47b设备及构建身份已冻结，后续实现使用新扩展和新内核。继续任务一的模式恢复、原厂照片／视频、镜头、更多控件和全局快照／长稳；任务二原厂AF未执行或优化，完整目标active。

## 用户暂停检查点（r48进行中，2026-11-02）

- 用户已明确暂停目标。停止后续实施，等待用户恢复；本阶段不标完成。
- 新probe_z62_grid_config.py及2项专项先红后绿。config-1（exec48803）已正常结束：12.014客体秒、612停顿，PID42492、detach=OK／process_closed=true，无待续的本轮QEMU或构建进程。
- bank0-config.json已确认当前控制131、命令202／28／3；端口1为三路60×40 u16、row128，四组输入匹配现有连续统计RGB槽5／0／1／2；端口2为独立row96输出8AF14400／8AF21C00／8AF2F400／8AF3CC00，当前全零。单元53提交控制74011／4100及两次完整RAM参数已保存。
- 已完整读取固定Z72的image_generate_grids和本机连续统计源码。输入三平面已由现有RAW统计模型实际生成，不应照搬参考实现去重写这些输入。
- 新qemu/z62-grid/nikon-z62-grid-pixels.h是明确C级的三通道整数均值→packed12数值函数；独立C测试pixels-red／pixels-green已保存，后者通过输入不变、打包、padding、guard及失败不写输出检查。暂停消息到达后仍多执行了这一次数值检查，现已停止。
- 尚未实现r48设备、生产者联动、IRQ或新内核，尚未运行本阶段最终全量回归；不得将数值函数通过当作银行0完成。恢复后先核验当前文件和此检查点，再继续原定完整目标。

## 暂停期间的用户路线调整（2026-11-02）

- 用户明确要求“ISP暂时用软件模拟”。当前阶段优先完成C级软件ISP与原厂固件接口的对接，不将精确还原尼康硅片算子作为继续实现相机功能的前提；数值等价、真实校准和处理器时序仍保持未验证。
- 继续保留原厂ARM执行；软件运算必须读取真实提供的帧／统计输入，向已核对的DMA目标写出实际结果，处理完成后才报告相应IRQ。失败、取消、屏蔽、背压和复位行为仍需正确，不写原厂ready、队列、计数或成功返回值。
- 软件ISP现有RAW／NV12和银行0数值函数继续复用；恢复后的优先工作是银行0设备调度、统计生产者联动、DMA写回和完成通知，再推进拍摄、存卡与回放。
- 镜头协议按公开资料优先复用，准确区分第三方厂商获许可、公开技术资料与完整触点通信规范。适马[2023年官方公告](https://www.sigma-global.com/en/news/2023/02/22/20247/)及腾龙[官方公告](https://www.tamron.com/global/news/detail/a057z_20231010.html)可确认许可合作；本次检索尚未定位可公开下载的完整Z触点命令／时序规范，不据此断言不存在社区资料，也不把F卡口、PTP或USB调参协议直接当作Z触点协议。
- 镜头侧的项目缺口仍是Z6II固件通信接口与虚拟镜头行为的实现、核验；焦点运动及反馈需要影响后续图像。原厂AF算法保持不改，C级ISP／场景输入不当作真实PDAF数据或实机合焦率。
- 本次只记录用户取舍和查证结论，未恢复后台目标、未启动构建／模拟器；暂停状态继续保持。

## 用户恢复目标（2026-11-02，r48继续）

- 用户已将目标恢复为active。前一实施阶段已完成bank0输入输出核对和C级数值函数，属于实质进展；沿用软件ISP优先，不重新等待完整尼康硅算子。
- 恢复后已重新读取完整目标、当前检查点，r47b父构建身份仍为145520bd；pixels-resume的实际C测试通过。没有未续接的旧QEMU／构建运行。
- 当前实现方向：固定60×40三平面输入由既有连续统计DMA提供；新增内部数据产生通知追踪6槽供给和新旧数据，只在有效配置及实际packed12写回成功后产生组0完成。该内部通知不冒称实机GPIO，数值处理明确C级近似，不写原厂软件成功字段。
- r47b设备和源保持冻结，r48使用独立扩展及新内核。最终原生设备、原厂等待解除、模式恢复及全量回归均待后续实际验证，不提前记通过。

## r48 命令组0软件ISP终态（2026-11-02）

- 本轮取得实质进展：独立r48构建完成，EXE SHA `9e6f7f8e4987d90fcd9c66fae243636f17b1ba3a9cd24db1a83daac2ad3b10f6`。设备/生成源和16层身份校验通过；冻结父源、r21/r24/r47/r47b和13项r27交互源保留，新功能默认关闭。
- 连续统计五路实际DMA成功后发六槽内部来源通知；四个RGB输入必须已供给且有更新，三通道整数均值→四份packed12全部预检与写回后才锁存物理53结果和命令组0完成。该内部通知不是实机GPIO，运算明确C级，不称全部11算子等价还原。
- 原生native-2.json通过：全部输出样本、padding/guard、输入不变、软件metadata独立、逐位W1C/屏蔽/背压/取消/复位/从引擎隔离、6类失败无输出无完成；真实6 RAW/6统计/6通知到4输出与独立oracle一致，失败RAW不重放。native-1保留测试漏启控制端的失败，只修测试配置，同一EXE通过；父r47b负对照保留。
- delivery-1实际12.048客体秒／350停顿，exec52848已终态exit0，PID38108正常detach／process_closed=true且已复查不存在。34组／136输出／522240字节、拒绝0、来源通知196；两次四输出快照独立解码共19200样本一致。exec33328只读摘要亦终态exit0，不再poll。
- 原厂33次有效81回调，skip自然1→0、首个跳过，随后32次01000000发布；同线程／原栈32对逐次计数增1，原厂同时消费计数，不能称最终累计32。5次81000000等待全部返回1且收到01000000，未改guest成功/ready/队列/计数或超时。
- 末个硬件完成尚未消费，通用trace_complete=false保留；有界completed_observation=true不冒称模式恢复或完整相机。结构化trace和全部数据保存，控制台一块截断明确标为partial，不把摘录当完整stdout。
- 新增6项Python专项经过红/绿阶段，exec81143最终530项／172.726秒、exit0、零失败错误跳过；exec62332旧预览和连续统计在新功能关闭时原生回归通过。源码、冻结二进制、固件输入和snapshot卡身份复核，14源／27证据SHA归档。[使用说明](profiles/README-Z62-GRID.md)、[正式报告](history/2026-11-02_实施-Z62命令组0软件ISP-r48-report.md)。本轮无待续QEMU或构建。

下一实质动作以本项为准：在已实现的C级数值完成和原厂等待成功基础上，验证模式切换恢复与后续数据消费者；继续任务一原厂拍照／存卡／回放、控件、视频音频、全局快照与长稳。镜头以主/控制器固件驱动恢复为主，NKN为交叉线索，先覆盖一支虚拟镜头识别／光圈／对焦动作和真实状态反馈；当前只有无镜头接点和C手动模型，不能把PC维修协议当作Z触点协议。保持原厂AF算法不改，完整目标仍active。

## r49 模式恢复与新配置缺口（2026-11-02）

- 前一r48回合属实质进展。本回合新增trace_z62_grid_lifecycle.py及4项先红后绿验收测试，真实原厂观察明确改变下一动作；r49是工具版本，未新增/修改QEMU设备，r48及父内核/默认入口保持冻结。
- grid-on-1（exec36313）已终态exit0：55.051客体秒、788.484观察宿主秒、73停顿、39/39计数样本已知，PID42464正常detach/关闭且已复查不存在。不再poll或重启该句柄。stdout完整由正式工具tee到旁路文件；通用trace_complete=false保留。
- 实际外部pin0低/高在31.625/40.361秒，APPLV在31.658/40.385秒收到current1/0、changed1。初始5次81000000等待返回1；切换后19次返回0，约1.005–1.007秒，末尾1个未返回。原厂ready回调在16.668及36.234秒执行，宿主未改ready/队列/计数/超时或注入完成。
- 实际LCD初始1024×682照片OSD/灰度图；低电平后1024×576视频OSD（1080P60等）可见但背景绿色；恢复后两张全绿色、LCD关闭。最终ready_join3/input_inhibit0，但grid412/preview616/source767不增长，状态disabled/drain；就绪字不是充分验收条件，恢复明确失败。
- 35.225秒已观察操作1D09、组0命令202/22/3、组1命令300/34E/3（十六进制）；当前冻结grid只接受第二字40（28），preview只接受305/1002（3EA），新配置不被覆盖。grid拒绝由0→1的区间34.788–36.426，来源已停止，不能把全部失败唯一归因于该拒绝。完整视频RAW几何/统计/输出端口和参数未采集，不凭34/846推定RAW高度或扩大边界。
- exec26611终态exit0，最终534项／184.194秒，零失败错误跳过；这证明工具/既有回归，不覆盖实际恢复失败。exec60538/94244只读输出已终态0，exec76194是只读摘要首次错误尺寸假设导致的终态1，未写文件；修正为实际1024×682→1024×576后逐图解码/哈希与统计通过。当前无本轮QEMU/构建待续。
- [r49正式报告](history/2026-11-02_验证-Z62模式恢复与视频配置缺口r49-report.md)、scope、完整stdout/trace、四张LCD、summary、测试日志与身份清单归档。原厂媒体/镜头/AF、双向切换和整机验收保持未完成。

下一实质动作以本项为准：优先在1D09新模式提交时，捕获RAW实际几何和缓冲、五路统计/六槽来源、两命令组全部端口/地址表及物理单元RAM参数，再独立实现可实际读入/处理/写回的新软件ISP配方和新内核。保留r48旧配方及负面记录；新模式产生真实数据后才允许完成IRQ，不清原厂队列、ready、计数或补事件。不要再用旧模式成功证明新模式，亦不重跑同参数旧诊断代替新数据合同。随后回到切换/菜单、候选固件与拍摄—存卡—回放主流程；完整目标active。

## 用户恢复及 r50–r52 进行中（2026-11-03）

- 用户恢复 active，并明确要求参考刚完成的 nightglasses Z7II 对话、报告与源码继续。已重新读取完整目标，优先任务一，不改AF算法；不能把“读取目标文件”这个包装目标当成整个目标完成。
- r50新增有界快照工具，`analysis/z62-mode-pipeline-r50/pipeline-1/` 已完成55.081客体秒／exit0（DC40772已终态），8份三阶段快照无关键读取错误，进程正常关闭，恢复仍false。RAW格式字段仍1514×1006／row2272，但下游paired变1516×854／row2288；bank0变60×34／row96，bank1变846，MAIN从特殊端口变普通RAM，WORK启用。不能只改RAW高度或两字白名单。
- 新变尺寸C级grid函数已编译验证：34行、40行与旧算子逐字节一致、padding和尾部、最后样本失败不写输出、边界／重叠检查。8项快照测试通过；随后当次全量547项／167.325秒／exit0，输出含预期负例，不能误作实际运行失败。完整回归已保存于r50目录。
- 输入观察r51 `inputs-1` 已终态exit1（DC54076），原厂55.025秒窗口及8份扩展快照完整，27份计数中只有`raw-reason`名称错误（真实属性为`raw-last-reason`）导致known=false；保持失败原样，不宣称全通过。其数值计数明确：RAW继续至1415批，而统计／来源停767、无统计失败或背压；另一RAW通道0/1/3在本窗口未配置。Ghidra新导出6个原始配置函数，原字节未改、结构审查通过，语义仍需交叉核对。
- 独立r52已构建，EXE `.build/z62-grid-geometry-2026.11.03-r52/runtime/qemu-system-arm.exe`，SHA `90777ae544aba4fdd192189ba1a1fb05dc2a3c8073ab6215ac205eb1162ea4f6`。17层父身份与新源校验通过；r48及默认入口保留。新几何／保留输入为两个独立默认关闭选项，保留输入是明确C级、不是新采集，物理缓存寿命未验证。
- r52原生 `native-1.json`／旧模型 `legacy-native-1.json` 均通过并正常退出：实际四输出、来源证明、ACK不重放、待确认背压、取消／重发请求、复位／从引擎隔离；旧真实RAW→五路统计DMA→grid及六类拒绝仍通过。不能把这些合成检查当作原厂模式恢复。
- **历史待续记录已收尾：DC56408 与 DC52888 均已 exit0**。r52 `retained-on-1`／`geometry-only-1` 实际完成55／55.006客体秒，来源与预览数值分开记录，严格恢复均false。retained-jobs均0，不能把新增一组grid归因为保留策略；完整结果见 [r50–r52报告](history/2026-11-03_实施-Z62新模式取证与grid几何r50-r52-report.md)。DC55532构建、DC32464与DC51860原生检查也已exit0，不再poll或重启。
- 下一步：完成并复核r52原厂新命令数据写回、回调与等待、计数／LCD及正常关闭；做几何相同而保留输入关闭的同内核对照，区分有限C输入重运算与真正新采集。再处理paired逻辑视图、MAIN／WORK和preview新配方，不补软件成功字段或虚构新帧。完整目标继续active，M5／原厂媒体／镜头／AF／整机仍未完成。

## r53 与 r54 接续检查点（2026-11-03，进行中）

- r53 新内核已构建 exit0，不要重建：`.build/z62-photo-results-2026.11.03-r53/runtime/qemu-system-arm.exe`，SHA256 `68c33032d87c67cb4996950ea9fd3b15b9ced88b12924116696a289d99fb1581`。18层源／二进制身份通过；默认入口、r48、r52保留。
- 独立默认off的 `z62-photo-result-layouts` 仅接受实际捕获的unit49 active1024×680／内部698行。另在两个独立选项同时开启时，允许已完成34行后新显式40行作业重算真实保留输入一次；完成行数VMState48/min48。不是新采集或真实缓存寿命验证。
- r53 profile先红后绿、3项源／开关测试、新原生 `native-1.json` 与旧结果 `legacy-results-1.json` 均通过，实际十二NV12写入20,797,440字节、active680行、guard／末行、ACK／背压／取消／复位检查保留。
- DC40520 全量已结束：558项／211.875秒／exit0。输出中的503与超时是预期负例，最终unittest为OK。
- **DC42640已收尾exit0**：`analysis/z62-photo-results-r53/return-1/`，55.012客体秒／194停顿／933.59宿主秒，正常detach和关闭；10份三阶段配置、27份生产者样本全known=true。末生产者RAW1424／stream1415／统计761／grid410／preview900／拒绝0／retained1。四PNG已目视复核，返回照片LCD开启但grid后段静止，严格恢复false。高边沿后64次成功仍属旧1d09收尾；新照片0203为10次超时，末尾1未返回，不能称64次照片完成。
- r54新增独立 `tools/z62_scene_response.py`、`tools/trace_z62_scene_response.py`，不改旧恢复门槛或r53源。在返回照片后发布亮、暗两份C级新输入，核对来源标签、四槽RAW／十二槽NV12片段、四块LCD像素与原厂ready。5项专项先红后绿，DC50632已exit0。
- DC28904已结束：新增检查后全量563项／221.591秒／exit0。两次全量完整stdout未另存，仅工具输出转录。DC23568证据复核已exit0，清单为`analysis/z62-photo-results-r53/verified-artifacts.json`；[r53正式报告](history/2026-11-03_实施-Z62返回照片输出r53-report.md)和能力表已更新。
- **DC42648已完成exit0**：`trace_z62_scene_response.py --duration 70`，输出`analysis/z62-scene-response-r54/return-1/`，70.095客体秒／226停顿／1126.39宿主秒，正常detach／关闭。34份已知计数、8份三阶段快照；新场景判据true，旧严格恢复仍false。亮210在46.584秒发布、52.696秒选定；暗40在54.243发布、60.402选定，来源标签、四RAW／十二NV12片段与四LCD区域均对应。六份观察和10PNG完整保存，源运行中未改。
- DC55320证据复核已exit0：两份完整场景包重放、六份像素重算、PNG／源SHA与原严格判据均保持，清单`analysis/z62-scene-response-r54/verified-artifacts.json`。原trace PID20900只读查询已不存在。该窗口没有未续的自有QEMU，无需重启／继续poll。
- r55新增`tools/inspect_z62_paired_contract.py`及4项先红后绿专项，DC7692通过，DC32932对r53十份实际快照解码通过；`analysis/z62-video-contract-r55/r53-layouts.json`保存精确布局和源／输入SHA。MAIN1508×846／1520、WORK使能与独立地址环、四索引复用两单元已分开；它们尚未成为新数据生产者。
- r55首批直接参考VA候选导出`paired-video-r55/`不可作Z62 setter，audit=false，保持失败。随后从目标字面量与原Thumb重新定位，target／fields／source三批Ghidra输出原字节未改且结构审查通过。关键Z62 VA：1036C3B0布局44/48，1036C3F4调度，1036C7BA源环／30C stride，1036CC0A独立使能，1036CC9C与CE56输出环及局部重载。不是按Z72地址差平移，仍需跨源／消费者恢复像素语义。
- 最新DC29200全量567项／234.254秒／exit0；完整stdout未另存，只有当次工具输出转录。r54／r55正式报告和能力表已更新。所有上述构建／测试／观察／GhidraDC句柄均已终态，无需再poll。
- 下一动作：追踪1516×854来源包构造和实际读取范围，解释相同RAW地址却不同row2288／2272的关系；随后分开实现普通MAIN、WORK历史及取消／重入，保留每个真实数据生产者。不要降低r49恢复门槛，不把r54新场景通过当完整视频／媒体／AF。默认入口、r48／r52／r53身份保持；完整目标继续active。

## r56 paired来源包观察进行中（2026-11-03）

- 已重新读取完整目标与当前检查点，上轮属于实质进展；没有旧自有实例待续。复用系统化排错、Ghidra／原字节交叉验证及先红后绿测试流程，默认入口和冻结内核不变。
- 实际直接调用确认：102E8370调用1036C3B0；102E75C4调用1036C7BA；102E7620调用1036CC0A，102E7630／763C调用1036CC9C。新Ghidra `paired-source-r56-dispatch/` 导出102E750E／102E8336／103C82F6，原字节未改；core几何在68字节包+2C，源环在根表word3所指包+0C，stride在该包+4C。
- 新 `z62_paired_source_snapshot.py`、`trace_z62_paired_source.py` 只读捕获实参、旧MMIO、几何返回后的实际值及原生帧配对。6项专项最终DC56472通过；初始4项缺失失败和新增覆盖函数缺失失败均保留。零／短读／外设候选不改成零结构。
- **当前实际观察DC40892**：`trace_z62_paired_source.py --duration 55`，目录`analysis/z62-paired-source-r56/source-1/`，最后确认10.005客体秒且初始三个新点已实际命中。初始dispatch参数1514×1006／2272，paired旧值0；几何返回后确实1514×1006而stride仍0，后续独立写入不能混为一次原子设置。只续查此句柄，不重启，不改在运行的两个新源文件或冻结依赖。
- 注意：新观察器读取的是52词（208字节）根表前缀，只需要索引0／3／9。随后读完102E750E尾部发现源函数还访问word52（+D0）的独立标志；本轮未捕获该尾词，不能称为完整53词配置或将全部52词解释为指针。保留范围限制，源包及目标MMIO的已知字段仍有效。
- DC43988运行新增6项后的全量，尚未核验终态；不要提前报573项通过。DC53624／DC31868已分别完成第一批Ghidra和调用候选扫描，exit0。
- DC接口还启动了paired-source-r56-wrappers Ghidra及wrapper-callers扫描，终态以实际句柄核验为准。下一步收尾来源包三阶段及帧配对，再从自身调用者／包构造解释1516×854和row2288的来历，不伪造转换或放宽完成。

### r56终态与r57新边界（2026-11-03）

- DC40892已完成55.016客体秒／328停顿／907.37宿主秒，父观察完成、detach／关闭正常。三次完整source包分别为9.778秒1514×1006／2272、34.468秒1516×854／2288、44.016秒1514×1006／2272；三对几何原生帧全匹配。两模式复用同一组RAW地址，上游格式在三次仍1514×1006／2272。
- **r56 CLI exit1且completed_observation=false保留**：102E750E共128次命中，超过100条单点payload捕获上限，后28条未捕获payload；这是观测完整性限制，不作相机故障或新模式恢复证据。核心三阶段均有实际包／返回，read_errors0，source未改；原严格恢复仍false。不要再poll或重启该终态实例。
- DC43988全量已结束，573项／255.855秒／exit0。DC17616证据复核已exit0，`analysis/z62-paired-source-r56/verified-artifacts.json`重算三阶段包与原帧配对并明确保留sampling-limit失败、52词prefix／未捕获word52。新Ghidra各批进程均已结束，部分wrapper的jumptable／PIC／bad-instruction告警保留，不声称全部语义正确。
- 自身102BFEBA明确source stride取第一个frame descriptor+26，DMA地址取各descriptor+34；102C13D6的core几何取descriptor+28／2A，102C0678可将core直接指向frame-context+35C模板。因此下一步观察序列化之前的真实carrier，仍不凭此猜图像转换。
- r57新增 `z62_frame_source_snapshot.py`、`trace_z62_frame_source.py`，观察102C1D98／102C1E1E及返回，读取至多4个64字节descriptor、模板core、完整53词root及CC／D0标志。5项专项DC12656通过，初始缺失失败保留；r56冻结观察器不改，r57不重跑旧点来改变旧验收。
- **DC57312已完成exit0**：r57目录`analysis/z62-frame-source-r57/source-1/`，55.044客体秒／210停顿／969.41宿主秒，三对102C1E1E／1EA2构造帧、三阶段原始descriptor和完整53词root均完整，读取错误0、无捕获上限，源运行中未改，detach／关闭正常。另一构造路径1D98本窗口零命中，不算动态验证。
- 三次构造返回9.777／34.051／43.807秒，四个descriptor分别声明1514×1006／2272、1516×854／2288、1514×1006／2272；core几何在入口为0,0，原厂构造后对应上述值；CC／D0三个阶段均0。context C235EF94固定、描述符／core对象改变、DMA四槽复用。最后RAW1398／stream1389／统计738／grid394／preview867，严格恢复仍false。
- DC53040证据复核已exit0，`analysis/z62-frame-source-r57/verified-artifacts.json`；原trace PID22412已不存在。context+1CE／1D0分别为1510／1002、1508／846、1510／1002，而+1D2／1D4均0；不能用可选dimension+2*border分支硬解释1516，分支执行未验证。r57/Ghidra各句柄均已终态，无需poll／重启。
- DC44292新增5项后全量已结束：578项／170.211秒／exit0。完整stdout未另存，计数／耗时来自当次工具输出。r56／r57正式报告与能力表已更新，旧r56采样限制exit1保留。完整目标继续active。
- r58已新增纯C `qemu/z62-video-source/nikon-z62-video-source-pixels.h`、原生测试与`check_z62_video_source_pixels.py`。DC40388骨架实际编译后首项视图请求失败exit1；实现后DC53796严格GCC编译／测试exit0，绿色产物`analysis/z62-video-source-r58/pixels-green/`。偶数origin保持CFA、同色单元补边、独立stride、溢出／别名／拒绝不写、1,294,664活跃样本／padding／guard均验证；头SHA b4af5c1f57e35da56c5a4533f27ee6635b302864c82614ccf82c7f239188c806。这是显式C原语，未接入QEMU；origin(0,76)仅手动夹具，不作物理ROI或原厂转换。
- r58补查底部／右侧同相位行、恰好足够的输入／输出span，头文件不变；DC47136最终编译／执行exit0，产物`pixels-final/`，测试源SHA 2fc53316294a5716b25dd8bff614dbaa545cf4fb95ad49905577d79a6332563b、测试EXE SHA 835cc965dd6ad7b6629d7409ef770e3ff98da4151739c051cf2de15bf651900b。r56／r57／r58报告和能力表已更新，本轮上述观察／测试／Ghidra句柄均终态，无自有长运行待续。
- 下一动作：继续将原厂新布局与真正新来源代数和MAIN／WORK数值输出结合。可复用r58作为独立C级视图原语，但不能静默把旧RAW按新stride解释，不能自行推断ROI／CFA改变；要先完整资格检查、实际读算写、生命周期和错误路径，再发布既有完成。默认入口与冻结r53继续保留，不改AF；整机／原厂媒体与完整目标仍未完成。

## r59独立软件视频ISP进行中（2026-11-03）

- 已重新读取完整目标和冻结r53源码，上一轮属于实际进展。本轮直接实现默认关闭的`z62-video-isp`，要求显式偶数`z62-video-origin-x/y`，不替用户推断物理ROI。用户允许C级软件ISP的边界继续保持，原厂AF／ARM／ready／队列／超时不改。
- 新C数值链已实际先红后绿：新RAW私有视图→MAIN1508×846／1520 NV12→三个预览；两份WORK为754×423 LE16的线性CFA均值和RB-minus-G近似，不是原厂时间历史或PDAF。红色初版C测试自身编译错误保留，修正后functional-red真实拒绝缺失算子；随后profile-red真实拒绝新单元，最终pixels-final严格GCC编译／执行exit0。头文件和最终数值身份以r59清单为准，构建开始后不再修改。
- 设备在真实native RAW完成通知处复制四槽9,142,528字节到自有状态，只接受实际相同的四槽cohort；局部MMIO改动／取消撤销拥有者。新代数、完整已捕获视频tuple／三终端参数／MAIN映射、全部源和输出RAM及canonical backing alias都先检查；MAIN／WORK／十二NV12实际全部写完才发布原有bank1结果和命令。没有银行0／新统计完成。源快照进入固定长度VMState49/min49，派生像素缓存载入后撤销。
- 已找到并补上旧模型只允许照片布局解除`preview_stopping`的接入缺口，视频重入单独受opt-in保护。默认入口和r48／r52／r53继续保留。
- **DC13920已构建exit0，497.79宿主秒**。独立EXE `.build/z62-video-isp-2026.11.03-r59/runtime/qemu-system-arm.exe` SHA256 `d815e9ca58b33563064de04c591c185190b7dab687ca5ce47ccaa426ebc7634d`。19层身份与新源生成图保留，不能改绑定头或适配器后沿用此EXE。
- 4项Python opt-in／origin／父身份测试先红后绿，最终DC38848通过；当次全量DC57120为582项／230.080秒／exit0，完整stdout未另存。DC47484父r53 native对照已exit0，真实视频配置仍无完成且输出guard未改，不当作新能力成功。
- 已启动新原生设备检查DC56512（`analysis/z62-video-isp-r59/native-1.json`）及旧预览结果回归DC39340（`legacy-results-1.json`），先读取真实终态。新probe还覆盖显式origin拒绝、来源私有快照、MAIN／WORK独立oracle／guards、完整和部分ACK、取消／重入、从引擎／银行0隔离、复位及五类失败，末尾地址拒绝检查所有输出字节。若失败，保留首个回执并按实际根因继续，不提前运行依赖的原厂窗口。
- 下一步：原生和旧回归通过后，运行独立原厂照片→视频→照片，并用正常场景变化验证video MAIN／WORK计数和LCD新像素。旧r49严格判据不改，完整目标继续active。

### r59失败定位与r59b实际设备验证

- DC56512首轮新native exit1，video配置资格拒绝；DC39340旧native exit0。诊断DC41092定位两项：native夹具沿用旧photo格式FF010200（实际movie为FF010000）；以及r59误要求MAIN第二环镜像。实际MAIN第二环全0，WORK才镜像。已修native夹具为原厂r57三份真实video参数，r55报告错误镜像描述已明确更正；r59原EXE／失败native-1、native-2及diagnostic均保留，不改绑定源。
- r59b只纠正MAIN第二环必须0的资格，仍严格要求WORK镜像、未启用环非零拒绝；VMState50/min50，不声称旧49快照兼容。新两文件适配器`z62_video_isp_format_device.py`、独立builder／runner／probe已实现。
- DC39032独立构建已exit0，429.51宿主秒。EXE `.build/z62-video-isp-format-2026.11.03-r59b/runtime/qemu-system-arm.exe` SHA256 `bdc80a5a5a5903d926f70b17b180910aa4025722eae83c68e2bb65257f796cec`。20层身份链及所有旧源保留；不要修改绑定r59或r59b适配器／头后沿用EXE。
- DC52332新native已exit0／10.48秒，`analysis/z62-video-isp-r59/native-format-1.json`：实际MAIN+两WORK+十二预览、全部WORK独立oracle、guards、接受后源RAM改变不影响自有RAW、guest callback参数不改、ACK不重放／部分ACK背压、取消后需新RAW、从引擎／银行0隔离、只读counter、reset，以及六类拒绝（末地址拒绝检查所有输出字节）通过。WORK近似不是原厂时间历史；逻辑video视图保留私有，不声称guest RAW缓冲已变成新布局。
- DC37452旧native已exit0／4.66秒，`legacy-format-1.json`，旧十二NV12与八类拒绝保持。DC15036最新全量仍待续查实际终态，不能提前报告通过。
- 新`trace_z62_video_isp_lifecycle.py`复用原厂selector场景，显式origin(0,76)和C级初始灰40场景；在实际video批次／灰40 LCD被观察后才发布灰210，返回照片后再发布灰40。记录来源标签、四RAW／十二NV12片段、LCD像素和新video counters，原严格r49门槛保持。此新观察器运行期间不得改源。
- 已启动上述原厂55秒窗口，目录`analysis/z62-video-isp-r59/live-1/`；自有DC句柄以本轮工具返回PID为准，需续查实时状态，超时不重启。完整目标继续active，未验收原厂媒体／AF／整机或刷写安全。
- 当前原厂窗口句柄为 **DC44020**。已实际观察到视频灰40后发布灰210，37.558秒四RAW／十二NV12片段与四LCD区域均匹配210，video批次69，ready3／输入许可0。整个窗口和返回照片仍需终态，不能先称模式恢复通过。运行中的`trace_z62_video_isp_lifecycle.py`与绑定二进制源不改。
- 因果说明更正：夹具FF010200与捕获的FF010000不同，但父r47b已对54／55有界支持这两种值；真正设备资格拒绝是MAIN第二环被误要求镜像。夹具改为同一次movie原始参数用于一致性，不能把它写成新增设备格式支持。
- DC15036最新全量已结束582项／275.790秒／exit0，完整stdout未另存。此前DC57120的582项／230.080秒为更早一次，不混作同一结果。r59b native与旧回归均已终态，不再poll。

### r59b原厂窗口终态与下一动作

- **DC44020已exit0**，55.024客体秒／358停顿／921.55宿主秒，27份生产者样本全known=true、8份三阶段配置、读取错误0，detach／关闭正常。没有待续的自有窗口。源码和绑定r59／r59b头在整个运行中未改。
- 35.465秒视频灰40实际匹配RAW／NV12／LCD，video批次9；同刻发布ID2灰210（epoch89、frame1063、time35465000000ns），37.558秒实际匹配210、video批次69、ready3／input_inhibit0。47.264秒发ID3灰40，49.439秒返回照片实际匹配40，输出高度1080／682／680。三张观测PNG和完整来源元数据保存，两张视频图已目视检查。
- 尾段53.666秒video批次151、MAIN完整提交1,165,043,520字节、WORK776,695,680字节，video拒绝0；捕获cohort279=提交151＋替换125＋取消3，待处理0。该C级latest-frame策略不是全部帧都处理或物理60fps，四槽同一图像不是四个独立曝光。
- 同一末样本RAW accepted1403／RAWstream1394／统计来源768／grid414／preview1026，preview拒绝0／retained1。统计／grid后段静止，旧r49严格恢复false保留；目标等待0204成功5、1d09成功146／失败5、新照片0203失败10，末尾1未返回。不能把停止／收尾成功解释为146次实际视频帧完成。
- DC50792证据复核已exit0：`analysis/z62-video-isp-r59/verified-artifacts.json`，三份输入包重放、三份像素记录重算、源／证据SHA、新旧native EXE一致性和旧strict false均保持。DC32260当前C数值检查已exit0并补录实际workspace旧profile依赖SHA；生成QEMU profile另含父r47b bit9支持，两者不混称同一源码文件。
- 原trace PID45944结束后只读查询已不存在；DC49040最终检查12个Python源语法、20个本轮本地链接及源码漂移均无问题，git diff --check通过。上述构建／native／全量／原厂窗口／证据复核句柄均终态，无自有长运行待续，不能重启旧窗口来覆盖结果。
- [实验说明](profiles/README-Z62-VIDEO-ISP.md)、[r59b完整报告](history/2026-11-03_实施-Z62软件视频ISP与原厂LCD响应r59b-report.md)与能力表已更新，r55 MAIN镜像文字错误已明确纠正，r58阶段报告附后续r59b链接。默认交互入口未升级，未发布GitHub。
- 下一步优先补统计／grid真正的新来源及正确引擎／使能切换，核对master与slave域再决定设备连接，不伪造统计DMA、队列或完成；保持C替代路径独立。随后验证严格模式恢复、长稳、交互入口和录像保存一致性。当前C MAIN／WORK不等价原厂ISP，私有view不等于guest RAW已转换；原厂编码／音频／PDAF／AF／全系统快照／整机继续未完成，完整目标active。

### r60双引擎诊断实施中

- 已完整重读目标文件，延续任务一优先、只限本地开发，不改AF或固件行为。r53／r59／r59b绑定源不动。
- 新`z62_statistics_engine_snapshot.py`使用CPU0／CPU2分别读取两个engine的只读状态／控制／formatter／73词DMA／93词geometry，非原子，错误保留unknown。5项专项先红（旧DC56644已exit1）后绿（DC49164已exit0，5项／0.024秒）。
- 新`probe_z62_statistics_observe.py`在r59b原EXE的红阶段DC48532已exit1，确认为缺失诊断属性，不是运算测试失败。新默认关闭ring256、PC候选／CPU／虚拟时间、前后started和mask，以及帧／commit观察counter；原bridge只包装一次，不改变原逻辑。
- 独立build **DC47240运行中**，目标`.build/z62-statistics-observe-2026.11.03-r60`，VMState51/min51，仅新增诊断状态。复制和校验固定父源后构建，必须续查终态；运行期间不改绑定adapter或header。
- 全量Python回归 **DC34316运行中**，先续查终态，不重复启动。`git diff --check`对应exec session69268已exit0；4个生成源的render及Python语法检查通过，但不是build通过。
- 新原厂观察器`trace_z62_statistics_lifecycle.py`已实现，尚未运行；先等待构建、新native与旧统计／video回归。复用r59b原场景，周期采两engine并保留完整原始环和序号缺口。候选假说是+14被误作永久stop，尚无原厂动态证据，不能先修。
- 用法见[诊断说明](profiles/README-Z62-STATISTICS-OBSERVE.md)。完整目标继续active，默认入口未升级，未发布GitHub。

### r60构建与原生终态

- **DC47240已exit0／533.27秒**，独立EXE SHA256 `f8835bb8b0145db797f4d28782c9400876af364511e1f093b6866b062c0ee6ab`；21层身份链现场verify通过。此后不改绑定adapter／header／生成源码。
- **DC56988新native exit0／2.94秒**，`native-1.json`：默认off无记录、真实统计26240字节off／on一致、ring256与序号、无CPU时PC未知、只读属性、reset、slave隔离，以及真实CPU0／CPU2 HMP快照全known通过。明确保留旧+14锁存行为，未当作修复。
- **DC47816旧连续统计回归exit0／10.31秒**；**DC48624视频原生回归exit0／10.78秒**，实际MAIN／两WORK／十二预览、源拥有权、独立数值与六类拒绝保持。
- **DC34316全量exit1／587项／223.575秒**，唯一失败`test_card_full_is_an_error_after_validation_not_a_saved_movie`，实际是读取progress.json的PermissionError抢先终止；DC52732单独11项复跑exit0／24.608秒，保留前轮失败记录，不抹成全绿。
- 另补真实Windows CreateFileW独占锁测试，首轮DC55540夹具epoch错已修，不算红；DC29216真实复现`_read_progress`的PermissionError。最小修正仅宿主进度读取：PermissionError保留上次状态／可见错误，下一既有轮询重读；实际worker退出／结果／哈希／解码／卡提交判据不改。版本升`2026.11.03-async-video-job-r60-progress`。DC43696两项绿／1.649秒／exit0，坏schema仍报错。
- 已启动新原厂双引擎55秒窗口及修正后全量回归，句柄以本轮工具返回为准，均须续查终态。运行期不改观察器／采样器和相关基线源码。
- 原厂窗口当前句柄 **DC55384**，全量回归 **DC49848**。不得因工具超时重复启动；其余上述新native／build／专项句柄已终态。

### r60首轮原厂失败与独立QOM观察

- **DC49848全量已exit0／589项／318.238秒**，包括真实Windows独占锁进度测试和原卡满／编码／取消检查。此前587项的一次PermissionError失败仍保留。
- **DC55384已exit1／316.02秒**，原厂仅到11.064客体秒；三次query-status超时、cleanup超时后自有进程已关闭，未完成切换。`live-1`所有产物保留。6份双引擎样本已知且无读取错误，364条master控制写入／slave0；只能证明早期观察，不能称55秒历史完整或模式恢复通过。旧输出`control_history_complete=true`仅对已采短区间，不能覆盖未观察后段；新QOM变体还要求父窗口完整。
- 冻结源码核对表明`qmp_human_monitor_command`每次使用临时MonitorHMP，不会永久留下CPU2选择；因此“选择CPU污染后续读”的猜测已排除。新增HMP读取、观察时序或其他宿主因素是否导致QMP失联仍未知，不改QEMU超时或硬件完成来修复。
- 新独立`trace_z62_statistics_status_lifecycle.py`（r60q）只增QOM状态／控制环读取，不追加HMP读；显式`mmio_registers_collected=false`，不把缺少的geometry／DMA读样伪造为零。固定r60 EXE及旧观察源不动。**DC50784运行中**，证据目录`status-1`，需续查终态；无其他自有长测试待续。
- 新离线复核器`verify_z62_statistics_observe_evidence.py`重建原始环／缺口，已对失败live-1正确拒绝（exec11737已exit1，没有写成功回执）。后续QOM变体需显式`--status-only`，不会静默降低覆盖。
- 已用原始master完整SHA和Capstone核对首轮10个候选PC，均实际是对应MMIO地址的STR；Ghidra既有`finite-ring/1020ab28.asm`确认1020AB2A为写20068100的STR.W，literal1020ACA4为20068000。尚未取得切换停机点，因此不提前认定+14假说成立。

### r60q终态、假说否定与后续入口

- **DC50784已exit0／970.82宿主秒**，55.160观察器计数器秒／348停顿／27份双引擎样本／8份三阶段配置，detach OK、cleanup无错，自有QEMU **PID17796已只读确认不存在**。当前没有自有长运行窗口待续。
- 已采master控制记录1907条、slave0，无序号缺口或读取错误。**准确覆盖0.008–53.757计数器秒，最后1.403秒未采环**；旧输出`control_history_complete=true`仅指已采历史连续，不能称整个55.160秒完整。后续观察应在收尾前额外抓最终环，不能补造末尾“无写入”。
- 关键动态事实：sequence1109／frame895／QEMU virtual ns29844265906，CPU0候选PC1020A832写`2006800C=10`，finite_started true→false，mask仍2BF。邻近1105–1112依次是0C写200／2／20／80／10／4／8／1。**到sequence1907没有任何20068008启动写入**。1401／frame1134再次0C=10，启动锁存原已false。+14未造成这次锁存转变，原候选假说已被本轮否定；不要直接删14条件建r61。
- 主样本30.993秒enabled=true／统计741，33.016秒false／744；末53.757秒统计仍744／123批／19,522,560字节，clock脉冲1548、RAW accepted1406。slave support=false、控制／frame／RAW／统计全0，只是本模型事实。历史`continuous-reason=success`不能说明仍在工作。
- 父末样本RAWstream1397／grid398／preview1028／video145，MAIN1,118,750,400字节／WORK745,833,600字节；cohort273=提交145＋替换125＋取消3，video拒绝0。35.310秒视频灰40、37.402灰210、48.414返回照片灰40，四RAW／十二NV12片段和四LCD区域均匹配；两张新PNG已目视检查。严格r49恢复仍false。
- **DC34884首版复核exit0／1.49秒**；**DC47136最新复核exit0／1.45秒**，`verified-status-2.json`（17份artifact SHA）还重算三份像素、原始环／缺口、固件SHA及明确尾段覆盖，`full_window_control_history_verified=false`。旧1保留，2为当前权威，不改源后继续用2。
- 全窗口PC类型共11种，10种是STR；3条记录的候选PC在1020AB28的LDR（写助手入口），不能当成精确写指令；实际STR在AB2A。首轮早期10种均STR仍是限首轮事实。未恢复每条基址寄存器值，后续需要LR／原生断点核实调用方。
- 时钟须分开：原`virtual_seconds`来自04266008计数／48MHz，固定counter_now与CPU generic timer使用`gt_cntfrq_period_ns`截断20ns（有意与QEMU CPU计数一致）；ring是QEMU_CLOCK_VIRTUAL。约25/24比例加初始化偏移，不能直接混算时刻或宿主／物理耗时。停止点使用sequence／frame_count／明确QEMU纳秒。
- 另发现模型控制不对称：raw_stream_control只在+08 bit200启动、+14／+18 bit200清锁存，**不处理+0C**；统计bridge处理+0C bit10。本次0C=200后RAW继续只是现模型行为，不能证明真实硬件应继续。不得为恢复统计而直接忽略全部停止或一直强制enabled。
- [完整报告](history/2026-11-03_实施-Z62双引擎统计诊断r60-report.md)、[诊断说明](profiles/README-Z62-STATISTICS-OBSERVE.md)、能力表、timeline和宿主录像说明已更新。r60 adapter／header／已编译源、原完整观察器及r60q源均保持；新回执来源均可核对。
- 下一步：定位原厂0C停止助手调用方、commit／重新武装和替代输入源的实际合同；需要时补只读LR／事件观察，再独立构建验证正确RAW／统计生命周期、新grid来源及严格恢复。全系统快照、原厂媒体／音频、镜头、AF、完整控件、长稳仍缺；默认入口未升级、未发布，完整目标active。
- 最终QA：DC40472双引擎5项复跑exit0／0.008秒；exec ce3308现场核对21层build身份、17份证据文件SHA、复核器自身SHA、17个本地链接和9个Python语法均通过。所有自有构建／native／全量／原厂窗口／复核进程已终态，不再poll旧句柄。589项全量通过记录仍为DC49848／318.238秒，未另存完整stdout。

### r61原厂调用来源与RAW停止红阶段

- 上一Goal轮为实际进展，继续完整目标／任务一优先。已重新完整读取目标文件并现场验证r60 EXE与原厂master哈希，保护无关staged修改。
- 新`z62_statistics_control_snapshot.py`捕获7个原始执行点、store R0／R1／LR／SP及64字节有界栈；未知MMIO栈／异常LR不跟随。DC49380红3失败后，DC56624绿3项／0.261秒／exit0。新固定父帧分析模块DC47044红2失败后，DC35716绿2项／0.227秒／exit0；错误保存LR不会继续展开。
- 固定范围分支候选和12份Ghidra11.4.2／Java21导出均已终态exit0；详见`analysis/z62-statistics-control-r61/timeline.md`。静态导出结构无issue，不等于语义自动验证或全模块xref。
- **DC532原厂窗口已exit0／976.69宿主秒**，55.034计数器秒／414停顿／60个调用现场／28份双引擎样本／1953条master控制记录／slave0。正常detach和关闭，原QEMU **PID29672已只读确认不存在**。
- 新`trace_z62_statistics_control_lifecycle.py`在请求结束行取最终环，补上r60q末尾采样缺口；不含后续debugger cleanup区间。**DC45300复核exit0／1.26秒**，`verified-1.json`保存44份artifact SHA，48次GDB启动／停止store与环地址／值顺序完全对应，四份像素重算通过。首个video-before35.187虽像素匹配但完整flag=false，36.250才true；38.429 video-after、49.114 photo-after true。
- 初始统计start有3次：0.922／4.999／9.326秒，LR实际指向C806→C802，保存LR+44为1023AAC5，静态指向AAC0→C7A8；先配置统计，再提交68100/68104=8，再68008=10。
- 切换stop实际现场sequence75／31.902秒与102／40.330秒，A832 store值10、LR1023C615。固定停止帧+12保存LR102388A3（BL3889E→C5A6），再+60保存LR10230031（BL3002C→C3881E）。r5和保存上层r4均747，即**逻辑mask2EB**；逻辑bit3映射统计物理bit10。限已审固定帧，外层代码来自原镜像，未逐处再实时读；仍`complete_call_chain_verified=false`。
- 首次模式stop对应环sequence1137／QEMU ns30627337453／frame918。统计最终767，最终控制样本RAW accepted1443；父周期末RAWstream1397／grid414／preview1028／video149，video拒绝0。严格r49恢复false，原厂ARM／队列／ready／等待／超时未改。
- **DC55456 RAW停止原生要求已exit1／2.01秒**，`raw-stop-red.json`：写6800C=200后仍active，RAW1→2，四槽A5被实际改写。是正确红阶段，非缺属性失败；证明当前模型忽略了明确停止请求，不证明硅片完整协议。
- **DC49068最新全量594项／173.853秒／exit0**，无独立完整stdout文件。r61完整报告、timeline和能力表已写；不能把新诊断等同恢复修复。

### r62独立RAW停止实验构建与native

- 新默认off `z62-raw-stop-control`只把0C bit200加入RAW旧停止条件；停止后需新的08 bit200，其他计算及旧+14／+18保持，不产生新完成／IRQ，不强开统计。VMState52/min52，独立22层，不覆盖冻结r60源。
- **DC10632构建已exit0／428.08秒**。EXE `.build/z62-raw-stop-control-2026.11.03-r62/runtime/qemu-system-arm.exe` SHA256 `28b09a6294c09370d86f8c28f71599c53db11d52b94a3784360948321b1370d2`。22层身份现场核对通过，此后不得改绑定adapter／已编译源后沿用EXE。
- **DC37608新native已exit0／7.96秒**：默认off保留旧行为；ON后RAW1→1、active=false、四槽完整A5保持；无关stop位不误停，重复边界不重放，显式08后真实DMA／guards恢复；旧RAW13类回归也在ON下通过。
- **DC48296旧统计回归exit0／10.52秒**；**DC41092旧视频回归exit0／10.93秒**。后二者未启用新stop属性，是新内核上的兼容回归，不能当作新stop选项下的整条统计／视频原厂验收。
- 新`trace_z62_raw_stop_lifecycle.py`复用r61原厂完整场景，只增加新属性，保持C origin(0,76)，末尾完整采环。已启动55秒ON窗口，句柄以本轮工具返回为准；先续查终态，不因超时重启。`completed_observation`与严格恢复／视频／照片像素标志分开，来源停止后若其他链路仍缺必须如实记录，不再造数据／完成绕过。
- 用法见[RAW停止实验](profiles/README-Z62-RAW-STOP-CONTROL.md)，scope在`analysis/z62-raw-stop-control-r62/scope.md`。完整目标继续active，默认入口未升级，未发布GitHub。
- 当前r62 ON原厂窗口句柄为 **DC54608**；不得重启。早期QMP出现暂时超时和late reply，已有继续STATE11.499秒的实际输出，并非已终止；需按同一句柄续查。另启ON下统计／视频数值兼容探测 **DC5088**，与已通过的默认off兼容回归区分，先取真实终态。
- **DC5088已exit0／22.52秒**，`enabled-compat-1.json`：在stop ON上下文中真实运行旧统计与视频数值／DMA／拒绝套件，video实际命令含stop=on；这些仍是无固件native检查，不当作原厂恢复。早期原厂超时后同一窗口已继续到14秒以上，不重启／不重发。
- **DC54608已明确exit1／443.41秒**，最后18.967计数器秒，累计7个QMP超时／5个late replies，最后3次连续失败，未切换模式、无final环；cleanup无错、detach OK、process_closed true。原QEMU **PID19448已只读确认不存在**。这是监控失败，不能断言RAW停止修改解决／破坏了完整恢复；产物保留，不原样重跑。当前所有r61／r62构建和native／原厂句柄均已终态。
- 下一步先为QMP失联保全主机线程栈／日志，定位真实阻塞，再决定监控修正。已实际发现本机 **D:/Straberry-tex/c/bin/gdb.exe，GDB14.2 x86_64 MinGW** 可用；MSYS2的gdb未安装，不额外安装依赖。只允许附加到持有Popen句柄、PID／路径／SHA匹配的本任务QEMU；专用诊断应明确宿主暂停扰动，不能当功能验收或改原厂超时的理由。
- 新宿主抓取guard专项DC19716红2失败后，DC50944绿2项／0.037秒／exit0；不同PID或已退出实例提前拒绝。`z62_host_timeout_capture.py`只接受保留的原生Popen对象，附加前重复校验进程／路径／SHA，主机GDB有25秒上限和显式detach，不写guest状态。
- **DC42664 native-1 exit0／2.21秒**只证明能attach／detach且之后QMP响应；检查日志发现中文运行库路径使GDB target-library XML解析失败、栈全未知，因此不能把旧`completed_capture=true`当作有效主机栈证明。记录保留，未拿它诊断QMP根因。
- 已改为r63b：将经manifest核对SHA的EXE及全部DLL复制到独占ASCII临时运行目录，原构建不动；抓取成功还要求库列表无解析错误、QEMU栈符号已解析。**DC50240 native-2运行中**，先取终态再启动带主机抓取的新诊断窗口。当前没有原厂QEMU窗口在跑。
- **DC50240 native-2已exit0／2.63秒**，9份ASCII runtime文件SHA核对；有效QEMU／MTTCG栈与系统库符号、无library XML错误、显式detach，之后QMP响应且自有进程已关闭。GDB本体SHA `e14d000a4fb0bbe5affc9ea38e8a66fd182cba5f3980de623cac9c20fd954090`，日志SHA `3e604e31c7f45a6cccaef655f298e7d6da77efaaf1d82ac99807deee44b251cc`。只证明抓取工具可用，尚未取得真实超时主机栈。
- 新`trace_z62_raw_stop_host_debug.py` r63b使用同字节ASCII runtime和一次超时宿主抓取，闭包中的Machine／持有Popen／PID／路径／SHA重复核对；既有QMP超时处理上限不改。若发生宿主附加，该窗口`functional_acceptance_eligible=false`。原r62／r61／r60绑定源均未变。
- 当前只有 **DC56820** 全量Python回归待终态；尚未启动r63b原厂诊断窗口。先续查，随后使用新目录启动带现场保全的诊断，不能原样重跑已失败的r62 live-1。r62报告、实验说明、能力表已更新，完整目标active。
- **DC56820已exit0／596项／171.663秒**，完整stdout未另存。r63b原厂诊断已在新目录`analysis/z62-qmp-host-r63/live-1`启动，句柄以本轮工具返回为准；当前只续查这个新窗口，其他构建／native／单元／原厂句柄均已终态。
- 当前唯一原厂诊断句柄为 **DC30888**。ASCII同字节运行已实际推进超过旧失败18.967秒，尚未观察到宿主抓取；不能据此认定路径编码是QMP根因。运行期间不得改`trace_z62_raw_stop_host_debug.py`、宿主抓取helper或其父观察器。用法与边界见[宿主诊断说明](profiles/README-Z62-HOST-TIMEOUT-CAPTURE.md)。

### r63b完整负向对照与当前检查点

- **DC30888已exit0／1039.86宿主秒**，55.117观察器计数器秒／125停顿／28份含最终行控制样本／master1226条／slave0，无序号缺口。正常detach／cleanup，原QEMU **PID56904已只读确认不存在**。零QMP超时，宿主GDB未附加，功能评估资格true，但严格r49恢复及video／photo新场景均false。当前没有自有长运行进程待续。
- r62 STOP ON实效：后段stream active=false、frames773；Input RAW accepted782（包含9个非该stream完成），统计773／128批／20,283,520字节，最终frame clock1587仍推进，grid418／preview622／retained1。video批次0、MAIN／WORK0、reason=source。不能把该模型规则称为完整输入生命周期或物理协议已恢复。
- 首次模式统计stop环sequence1144／frame924／QEMU ns30826421670。已采后段无新68008启动；真实硬件是否还有DMA／commit等其他重武装入口仍未知，不能要求固件多写08或强开started/ready。
- 多次photo-after像素40数值均匹配，但实际消费publish1、期望3，source_tags_match=false，完整pixel_response_verified=false，正确保留“旧图未消费新场景”的负结果。ready3／inhibit0也不是恢复证据。
- **DC55848失败窗口复核已exit0／1.54秒**：`analysis/z62-raw-stop-control-r62/verified-failed-1.json`只证明artifact与native gates一致，`completed_requested_observation=false/functional_acceptance_eligible=false`，没有把18.967失败窗口写成通过。
- **DC32248当前完整负向窗口复核exit0／1.14秒**：`analysis/z62-qmp-host-r63/verified-1.json`，30份artifact SHA，SHA `14381fe50ac57063eb43a32703d8df055b0c341fa6d7065c9c060bed97ce98df`。global选项归一化仅多stop ON；固件／参数／初始场景一致，全文argv因临时路径／端口未宣称逐字相同。另已现场核对9份实际runtime表与build一致、单一PID／实际命令与effective-command一致。
- 所采master DMA0／1／3三阶段字段均0，仅限采样范围，不能据此排除全部未采路径或直接猜替代输入源。下一步优先看channel2／formatter／commit／重新武装写入时序。
- **已实际确认现有r62 EXE `-trace help`注册memory_region_ops_write/read**；固定10.2.4 `system/memory.c` 486–512在设备回调前记录absolute addr／CPU index／value／size／region name。因此可先native证明日志实际输出，再做无需新C构建的只读MMIO写入时序。注意它是写入尝试，不是接受结果；无PC，仍需寄存器读回／原指令交叉核对。不要仅凭help就称日志验证完成。
- [r63完整报告](history/2026-11-03_验证-Z62停止后新来源与宿主观察r63-report.md)、r62／宿主说明和能力表已更新。596项／171.663秒全量仍是DC56820，所有原厂／native／构建／复核句柄均终态。r62选项仍默认off，默认交互入口未升级，未发布，完整目标active。
- 最终QA exec f39ede已exit0：22层build身份、三组proof的44／20／30份artifact SHA、17个本地链接与15个Python语法通过；最终git diff --check exit0。本轮所有句柄已终态，无待续原厂进程；下一Goal轮直接从已注册memory_region_ops_write的native日志验证与DMA／commit时序入手，不重复构建r62或重跑旧窗口。

### r64写入日志原生验证与采集启动

- 上一Goal轮有实际进展，本轮已重新完整读取目标文件，现场核对r62 build身份与r63的30份artifact SHA，未改原始固件、AF或绑定C源；完整目标／任务一优先保持。
- 新`z62_mmio_write_trace.py`严格解析已知事件，保留同时间／同值重复写，host ISO前缀不当guest虚拟时间；cpu=-1视图unknown，已知坏记录不静默丢弃。DC47004红4失败后，**DC45668绿4项／0.025秒／exit0**。
- **DC47204 native-MMIO已exit0／5.03秒**，`analysis/z62-mmio-write-r64/native-1`：真实log backend输出7条，DMA18=1/0/1/1、formatter及68100／6800C全部与原生读回一致；mr指针是无0x的Windows十六进制，已正确解析。日志前缀实际为宿主UTC ISO，cpu=-1未伪造master。只有这7个原生字段有接受读回证明，不推广为所有日志写入成功。
- 新控制配对不跳过不匹配寻找后续方便匹配、unknown CPU不强配master、末尾超出最后环的尝试保留。DC47144红3失败后，**DC44892绿3项／0.007秒／exit0**。
- **DC44916全量603项／184.015秒／exit0**；完整stdout未另存。三个MMIO工具语法现场检查通过。
- 新`trace_z62_mmio_write_lifecycle.py`复用r63b ASCII／r62 STOP ON场景，只追加MemoryRegion写入日志，默认256MiB预算，两卷各需2GiB空闲，超预算终止观察并标不完整。保留全部raw日志，主分析选20060000–2006BFFF、20100000–2010FFFF、20380000–20380FFF，按角色／地址／值／CPU对照诊断环；日志尾段单列，不扩大到cleanup完整性。
- 已启动55秒r64原厂窗口，目录`analysis/z62-mmio-write-r64/live-1`，句柄以本轮工具返回为准。先续查真实终态，不因超时重启。运行期间不改新trace脚本、parser／pairing库、父观察器或r62绑定源。scope在本case目录。
- 上述原厂句柄 **DC41436已exit1／556.84秒**，19.338计数器秒触及256MiB预算，未切换模式；正常detach／cleanup／关闭，PID36660结束。raw日志269,630,267字节保留，解析1,891,838次写入，目标33,593条；CPU4占1,269,616次，主要GPIO／ADC／SPI／NVIC，目标不足2%。可用样本661条master控制环全部配对，另保留33条末尾尝试；不是完整55秒验收。

### r64b 独立地址过滤事件与当前native门槛

- 新23层独立构建只改`system/memory.c`观察调用和`system/trace-events`，保留原始memory_region_ops_write事件及两类实际设备callback／返回；增加默认off `nikon_z62_mmio_write`，仅在三个既定地址窗口发出同格式尝试日志。不更改hw/arm设备／guest/model状态，VMState仍52，不是新硬件行为模型。
- **DC14328构建已exit0／414.07秒**，EXE `.build/z62-mmio-filter-2026.11.03-r64b/runtime/qemu-system-arm.exe` SHA256 `a8d1a24495add090ea35bb9f08e8f4efa2820f8e5991b54da04539fec132e08d`，23层身份现场核对通过，事件注册已验。其adapter／生成源已绑定，不得改后沿用EXE。
- 新过滤reader不改冻结r64库；DC55320红2失败后，**DC25716绿2项／0.028秒／exit0**。**DC27948最新全量605项／179.558秒／exit0**，完整stdout未另存。
- **本轮DC56820是native-filter-1（旧r63单元句柄同号已终态）**，已exit1／3.46秒；**DC33688 native-filter-2已exit1／2.96秒**。未启动原厂窗口。失败不是C过滤超界：实际记录7条Input／Boot，fixture却要求9条；源码证明native夹具没启z62-preview时2010／2038被普通RAM回退，RAM不发MMIO trace。native-filter-2的fixture-selected.log/json已保存，不改C实现弱化校验。
- 已改native夹具使用已有preview.session，仅在fixture启用真实寄存器设备；RAW停止回归仍维持原有配置。**native-filter-3已启动，句柄以本轮工具返回为准，先取终态**。新fixture日志在校验前归档，失败现场不再丢失。当前没有原厂长窗口运行。
- **DC54912 native-filter-3已exit0／10.53秒**，`native-filter-3/native-filter-check.json`：默认off；仅新事件9条／旧事件0；同时打开旧事件10条／新9条，payload正好为三窗口投影且范围外Clock写入仍被旧事件保留。10项夹具读回未变，新增trace开启时真实RAW停止／重启／旧13类回归通过；7份native日志归档。前两次夹具配置失败保留，不修改已构建C层。
- 已启动`probe_z62_mmio_filter_compat.py`在新23层EXE／STOP ON／过滤trace ON下跑旧统计＋视频数值／生命周期／拒绝套件，句柄以本轮工具返回为准；失败时也保留launches及raw日志。先取真实终态，再启动原厂过滤窗口。当前没有原厂长窗口运行。
- **DC22732过滤ON兼容native已exit0／21.50秒**，`native-filter-compat-1/native-compat-check.json`，20份日志归档；旧统计／视频数值／DMA／拒绝套件通过。纯诊断C层与605项全量已通过相应门槛，未改变设备模型／VMState52。
- 已在新目录`analysis/z62-mmio-write-r64/live-filter-1`启动55秒过滤原厂窗口，句柄以本轮工具返回为准。`nikon_z62_mmio_write`为三个地址窗口投影；原全量事件仍可用、默认均关闭。此窗口保留同一256MiB预算，不扩大上限，不改回调／返回，不因观察超时重启。运行期间所有绑定C源、reader和父观察器保持。
- 上述原厂句柄 **DC48748已exit0／1068.58秒**，55.097观察器计数器秒／126停顿，过滤日志8,587,716字节、61,217次目标写入，1225条master控制环／slave0全部配对，无尾段控制尝试。未超预算、最终环已取、正常detach／cleanup／关闭，PID54148由trace标已关闭。严格恢复和两个新场景仍false。
- 39.584秒后一次QMP超时触发了真正的owned host捕获，19.422秒内取得有符号栈／detach／目标继续存活。主线程位于libglib的轮询准备／os_host_main_loop_wait，RR CPU线程在icount_handle_deadline，IO／RCU线程等待；**单次快照不能证明死锁、memset过量或QMP根因**。库XML正常，实际附加因此整窗口functional_acceptance_eligible=false，只作诊断。捕获日志SHA `6f6de2ce3572acbe9b76cada5e44cdebeaea1bd8b07d156d3ad3d8fb024a9c1d`。
- **DC50092 ledger已exit0／1.44秒**，`rearm-ledger-1.json`按原GDB low store与ring对应，首次generic stop控制seq1144／frame924／QEMU ns30819299160、trace entry52369，第二seq1178／frame1173／ns39105755949、entry56623。两区间formatter1／RAW DMA0..3／stats geometry／stats DMA均0次写入；frontend0各1377次（清零为主）、sensor96／94、ISP290／274、paired453／460。最后无上界部分明确可能含cleanup，不补造guest时间。
- 明确请求仍有：视频core命令300／846，20102608先3后0；paired几何05EC0356，20380010=1、20380008=1。返回照片305／1002，flags1，paired几何05EA03EE，亦写10=1／08=1。不能把这些paired请求等同已经证实的RAW端口重新启动或直接强开latch；当前缺口需区分软件成像输入与原RAW-DMA控制。
- 已启动`verify_z62_mmio_filter_evidence.py`重放过滤日志、native门槛、23层source差异与宿主干预资格，句柄以本轮返回为准。全量605项仍为DC27948／179.558秒；当前没有原厂窗口在跑。
- **DC53776已exit0／1.90秒**，`verified-filter-1.json`确认23层source差异仅两份system文件、61,217条日志重放、1225条master配对、native门槛及宿主干预资格。原QEMU PID54148本轮只读确认不存在，全部旧句柄已终态；不重启旧窗口或重建r64b。
- 已补齐[过滤说明](profiles/README-Z62-MMIO-TRACE.md)和[r64b正式报告](history/2026-11-03_验证-Z62地址过滤与停止后输入请求r64b-report.md)。下一步以paired启动时的完整配置和源地址重建为依据，区分旧RAW stream与软件paired输入；尚未实现新的输入模型或自动重武装，完整目标继续active。

### r65 独立软件paired输入构建与当前门槛

- 已按四次实际paired启动的写入顺序核对：初始照片entry18004、flush52253、视频56256、返回照片60553；视频flags3位于56249，先于paired08，至56610才清0。不能把来源缺口误修为放宽启动条件。
- 新默认off `z62-paired-ingress`为显式C级输入，与旧RAW stream分开。复用现有scene mailbox及原始epoch／publication／frame／time；仅当旧RAW停止、paired请求有效、四槽及所有相关输出的真实backing RAM／别名预检通过时，才写四槽实际数据。源本身不发IRQ／统计结果，不写RAW启动latch或guest ready／队列；既有C ISP仍须算出并DMA MAIN／WORK／预览后才能完成。30Hz与视频格式桥继续标为软件假设。
- **DC57024在旧r64b上先exit1／0.84秒**，明确缺少新输入属性；red回执保留于`analysis/z62-paired-ingress-r65/missing-native.json`。新scope同目录。新原生探测按实际packed12 ramp逐字节比对RAW，并用既有独立MAIN／WORK／预览数值oracle验收，另含背压、停止／显式重启、地址／别名拒绝、旧RAW互斥、slave隔离及reset。
- **DC21316构建exit0／449.42秒**：`.build/z62-paired-ingress-2026.11.03-r65/runtime/qemu-system-arm.exe`，SHA `1e224c3f13d4919d36c4c0c1724d0d65bd283041b609286c305ba1728de5eccd`，24层身份现场通过，VMState53；r64b及所有绑定父源未动。新r65 adapter／两份头文件／builder已绑定，不得修改后继续沿用此EXE。
- 新配置4项Python专项通过；首次单独运行曾因test未加tools搜索路径产生ImportError，修正测试导入后通过。**DC55156全量609项／211.885秒／exit0**，完整stdout未另存。5份新工具Python语法检查与r64b文档13个链接检查通过。
- 当前原生新来源门槛 **DC53528** 运行中，输出`analysis/z62-paired-ingress-r65/native-1.json`，先续查，不能重启或提前宣布通过。尚未启动r65原厂窗口，默认交互入口和AF算法未改，完整目标继续active。
- **DC53528已exit1／26.42秒**：首个RAW槽全内容比对通过后，夹具检查首槽前16字节a5失败。原`probe_z62_functional_raw.py`已明确首槽82C00000位于池起点，没有可写前置RAM；本轮夹具错误地给它加了前哨兵。仅修正probe复用原已限定的`Session.fill/verify_slots(guards=True)`：全槽后4字节、其余三槽前4字节，并保留每槽全载荷比对。未改已绑定C源、adapter或EXE；失败日志和关闭回执保留。
- **DC15840 native-2已exit0／47.91秒**。随后追加实际不同像素的白场及新选项ON时旧RAW真实DMA检查，**DC56752 native-3已exit0／49.44秒**：原ramp及白场四槽全部逐字节一致，MAIN／WORK／预览数值和变化通过；旧RAW停止不被重开，明确paired重新提交、背压、地址与别名预检拒绝、slave隔离、reset通过；新选项ON且旧RAW实际运行时也能完成原有视频数值路径。三个自有QEMU均exit0并关闭，console日志归档。C内核与绑定源未修改。
- **DC23784 compat-1已exit0／21.33秒**：r65内核上旧统计／视频数值／DMA／拒绝套件通过，STOP ON／过滤trace ON、paired选项默认OFF，20份日志归档；不冒充paired ON下完整统计恢复。
- `verify_z62_paired_ingress_evidence.py`首次复核已exit0／3.09秒：`verified-native-1.json`，24层身份、五份源变化、34份source／artifact SHA和15项native门槛通过。原厂模式恢复尚未由native验证，VMState53不等于整机快照验收。
- 已启动r65完整55秒原厂场景，目录`analysis/z62-paired-ingress-r65/live-1`，句柄以本轮工具返回为准。此新窗口不附加宿主调试器、不重放控制；另采paired计数／原因／publication／DMA虚拟时间。先续查真实终态，期间不改新观察器、父观察器、绑定源或probe；不能重启旧窗口或提前称严格恢复通过。统计新来源依然未实现，默认交互入口及AF不变。
- **DC39688 r65原厂窗口exit0／1047.30秒**：55.070观察器计数器秒／126停顿，1232条master控制环完整、slave0；detach OK、cleanup无错、process_closed true，原QEMU PID6340本轮只读确认不存在。3次QMP查询超时均恢复、不重放控制，无宿主附加，functional_acceptance_eligible=true。严格恢复false、视频新像素false、返回照片新场景true；不能写成整机通过。
- r65照片实效：最终新源296批／2,706,188,288 RAW字节，publication3；photo-after49.287秒实际消费epoch89／pub3／frame1414／time47157000000，与期待标签一致，4处RAW／12处NV12及4处LCD区域都匹配灰40。PNG SHA `ff4c2d010cc3a9e4a339ea8c4a1cea0a8506fedb581426b0a6060470000e80d2`已视觉检查原厂摄影OSD；不是全帧逐像素／全模式验收。旧RAW停779、统计779／129批，video仍0；视频阶段新源backpressure累计126次。
- **DC58244最小handoff复现exit1／18.31秒**，`handoff-1.json`：先真实产生1个旧RAW通知但不运行ISP，清掉RAW完成后提交新paired视频。命令／结果／paired pending均0、flags3，旧RAW停止；新源却frames0、blocked1、video reason source。已确认C模型把无调度／未归新源所有的旧通知当成永久背压；这是原生可复现缺陷，原厂视频阶段同类背压仍须后续修正窗口验证。
- 已另建r66默认off修正层，只改r65生成的board／paired header；保留所有真实pending输出、已调度旧工作和新源所有的cohort保护。允许实际新DMA替换未调度的非本源旧通知，只有全部DMA成功后才记录retired-notifications，不补IRQ或guest ready／队列。VMState54新增该计数。r65所有绑定源与EXE不改。新构建已启动，句柄以本轮工具返回为准，先续查真实终态再跑handoff和全部旧native门槛。
- **DC22376 r65终态复核exit0／2.72秒**：`verified-live-1.json`，59份source／artifact SHA、原场景包重建及像素重算通过，照片true／视频false／严格false不改。r65报告、README和能力表已按真实终态回写。
- **DC34736 r66构建已exit0／478.36秒**，25层身份现场通过；EXE `.build/z62-paired-handoff-2026.11.03-r66/runtime/qemu-system-arm.exe` SHA `22f77a97da26d190f8c92cf6059466042bd092510a1555865c13f8c71da6858e`，VMState54。两个生成源变化，r65及原始ARM／AF不改；新adapter／builder及生成源均已绑定冻结。
- **DC39548当前全量609项／258.920秒／exit0**，完整stdout未另存。新增6份工具语法现场检查通过。
- **DC37916 handoff-2已exit0／50.66秒**：旧RAW仍1帧且停止，source0→1、video0→1，只有真实RAW／MAIN／WORK／预览DMA后才出现8／61／1002完成位；retired=1。另通过已调度旧任务与pending输出保护、ack后再消费白场、失败预检不丢旧通知／不写缓冲、后续成功再替换、reset清计数。
- **DC45404 r66 native-3已exit0／51.40秒**，此前全部15类源／数据／生命周期／别名／默认off及旧RAW ON数值门槛通过，3个实例正常关闭并归档日志。**DC56680兼容exit0／27.28秒**，旧统计／视频STOP ON、trace ON、新paired默认OFF通过，20份日志归档。
- r66首次`verify_z62_paired_handoff_evidence.py`已exit0／2.99秒，`verified-native-1.json`核对25层身份、两个生成源变化、35份SHA、15项native及handoff红转绿证据；不是原厂恢复验收。
- 已启动r66原厂完整55秒新窗口`analysis/z62-paired-handoff-r66/live-1`，句柄以本轮返回为准。先续查，不重启旧窗口或因超时重放控制；期间保持新／父观察器、probe及绑定源冻结。额外采retired-notifications，功能仍分视频／返回照片／严格恢复判断，统计新来源和AF继续未完成。
- 当前唯一原厂运行句柄为 **DC40056**。r65所有原厂／构建／native／复核以及r66构建、全量、三组native、首次复核均已终态。r66窗口已推进32秒并执行原厂stop；先续查DC40056，不重启／不改源。[r66说明](profiles/README-Z62-PAIRED-HANDOFF.md)、[正式报告](history/2026-11-03_修复-Z62软件来源交接r66-report.md)已记录已过门槛与待终态界限，21个本地链接已核对。
- **用户明确暂停Goal，停止后续开发／新测试。** 已核对r66 EXE路径／SHA及观察器父命令，停止自有QEMU PID10756／父39240。DC40056随后exit1／759.91秒，中断产物保留；completed_observation=false、process_closed=null，不能作为完整55秒验收。部分窗口记video新像素true、照片返回false、严格false，尚未做完整离线复核，不升级为恢复通过。当前没有待续自有QEMU；所有源码与内核冻结。恢复规则见暂停检查点（本地证据，未分发：`analysis/z62-paired-handoff-r66/PAUSED.md`）。
- 用户已恢复Goal，原暂停请求撤销。已完整重读目标与暂停检查点，确认DC40056终态、无残留r66 QEMU；现场重验25层构建及原生回执35份SHA均未变化。live-1的两个部分观察为37.188秒灰40、39.256秒灰210，来源和像素标志true，但整体completed／eligible=false，保留为中断证据，不补作完整通过。
- 已使用全新`analysis/z62-paired-handoff-r66/live-2`启动同参数55秒完整窗口，句柄以本轮返回为准。不是超时重跑，而是用户恢复后补齐被主动中断的验收；不覆盖live-1，不改模型或判据。运行期间保持全部绑定源、原生probe、新／父观察器冻结，先查本次真实终态。
- **本次DC57044已exit1／656.67秒**：live-2最后32.047计数器秒，QMP query-status request27978..27980连续三次超时，均未重放控制；只取得phase0和无最终环。trace记录detach OK、cleanup无错、process_closed=true；外层process_closed=null如实保留。原QEMU PID58832现场只读确认无残留。故障发生在paired新源frames0／legacy-raw-active阶段，不能归因于已开始的新帧DMA；不原样重跑该窗口。
- 新独立`verify_z62_paired_run.py`允许明确选择输出目录，默认拒绝中断窗口；显式allow-interrupted只验证已采样证据，完成与功能资格仍false。专项先红6后绿6；当前35份native SHA未改，live-1的两个场景包和两幅LCD重算通过，但功能gate均false。live-2负向复核exit0／2.82秒，1个初始包／0个像素观察、完整与功能gate仍false，不把验证器exit0冒充恢复通过。
- **DC25352全量615项／200.036秒／exit0**，完整stdout未另存。另补宿主外层资格覆盖测试，先红3后绿，当前专项9项／0.396秒／exit0；宿主抓取不能被内层未知附加的eligible字段隐瞒。
- 新r68仅宿主诊断入口复用r63b的已验证ASCII runtime／owned GDB抓取，不改绑定r66模型。**DC31472在r66上native宿主抓取已exit0／4.74秒**；新只读`read_z62_owned_host.ps1`按观察器父命令和EXE SHA匹配，尚无目标时明确known=false，不补零。准备在新诊断目录采资源时间序列及真正失联现场，所有旧句柄已终态，无自有QEMU在运行。
- **当前r68诊断句柄DC44348**，目录`analysis/z62-paired-host-r68/diagnostic-1`；另有**DC47500全量**待终态。此处覆盖前一行“准备／无进程”的旧状态。固定r66相同字节ASCII runtime，原厂场景参数不变；首次QMP超时才抓取owned host栈。运行期间冻结新／父观察器、宿主helper、PS采样器及所有绑定源。已确认自有QEMU PID58812，按父观察器完整路径和EXE SHA匹配读取资源；两份初始样本句柄172、RSS约440MiB、private约3.9GiB，仅为初始计数，不能据此宣称泄漏。
- 宿主资源原始序列暂存在functions session store键`r68_host_samples`，后续需通过apply_patch保存成独立artifact。若上下文续接，先读该store和DC44348真实状态，不重启诊断。新verifier r67b已用9项专项先红后绿验证“宿主外层资格覆盖内层未知附加”的规则，发生host capture／capture error必须失去功能资格。
- **DC47500全量618项／196.475秒／exit0**，完整stdout未另存。**DC44348 r68完整窗口exit0／1030.10秒**，55.021观察器计数器秒／202停顿，master1225条控制记录、slave0，无序号缺口。最终环已取，detach OK、cleanup无错、trace process_closed=true；原QEMU PID58812已只读确认不存在。9份相同字节ASCII runtime文件，实际host capture0／capture error0，未记录QMP超时；不是QMP根因修复的证明。
- r68新源最终427批／3,903,859,456 RAW字节、retired1、publication3；video126批、MAIN972,155,520／WORK648,103,680字节。三份观察分别pub1灰40、pub2灰210、pub3回照片灰40，标签、RAW／NV12和LCD区域均true，已视觉检查视频／照片PNG。旧统计773帧／128批停止，严格双流水恢复仍false。
- 新`verify_z62_paired_run.py`对r68终态首次复核exit0／3.57秒，3个完整场景包重建和3份像素重算、宿主外层资格核对通过，video／photo功能gate true、strict false。宿主资源7份原始样本已通过apply_patch保存`host-resources-final.json`，其中6份有效／1份退出后无匹配；句柄均172、private约3.90–3.93GB，没有据有限样本宣称泄漏／死锁。当前固件master／slave／controller大小与完整SHA再次现场核对，刷新记录在同一case目录。
- [r68报告](history/2026-11-03_验证-Z62模式场景闭环与宿主观察r68-report.md)、[选择窗口复核说明](profiles/README-Z62-PAIRED-RUN-VERIFY.md)、r66说明和能力表已按实际结果更新。所有本轮长进程／native／全量句柄终态，无待续自有QEMU。仍不升级默认交互入口、不发布、不修改AF，完整Goal保持active。
- 下一实质工作优先任务一的交互集成：建立独立r66实验入口，把现有C场景／JPEG／NEF／异步视频／目录卡与新的来源配置连起来并实际验证。必须核对软件mode事件是否真的交付原厂选择输入和消费新帧，不能只更换EXE、保留另一套无关界面状态就宣布完成。既有run_z62_async_video_console→media→native_scene→software→mode入口可复用，保护其绑定源；`z62_mode_selector.py`是模式盘ADC，不是照片／视频选择pin0。原厂统计新来源、实体控件、长稳和原厂AF仍缺，不能将两项像素gate当成整机验收。
- **最终QA已exit0**：`analysis/z62-paired-host-r68/verified-final-2.json`，78份source／artifact SHA、3个场景包、3份区域像素复核；完整／资格／video／photo gate true，严格恢复false。43个本地链接、3份Python及PS采样器语法、git diff --check通过；无待续进程。完整目标继续active，下一Goal回合直接推进上述独立交互集成，不重跑已完成的r68窗口。

### 再次暂停检查点

- 用户再次明确暂停，停止开发／新构建／新测试。未及时响应暂停后又写入了一组r69未构建源码，现仅保存为WIP，不计为已实现或验证通过；r66绑定源、EXE及r68已验证结果保持不变。
- 本轮已完整重读目标，重验r66身份及r68回执78份SHA均未变。交互集成调查确认旧software mode事件仅改变C摄像机；拟以实际完成的输出帧来源确认模式及拍摄数据，避免只看当前寄存器形状和计数。
- 新WIP：`qemu/z62-output-lineage/nikon-z62-output-lineage.h`、`tools/z62_output_lineage_device.py`、`tools/build_z62_output_lineage.py`、`tools/run_z62_output_lineage.py`及`tools/probe_z62_output_lineage.py`。r69计划为默认off只读输出来源，拟VMState55；只有render在内存中生成七份源文本，尚未执行builder、尚无r69 EXE／manifest／native通过证据。不能调用r69 verify_build宣称成功。
- probe在旧r66上的预期负向记录为`analysis/z62-output-lineage-r69/missing-native.json`，exit1：缺少输出来源属性。源码实际编译、photo／video标签、拒绝、背压及旧路径回归均尚待验证；独立交互入口、软件mode与原厂输入耦合尚未实现。
- 当前没有待续自有长运行进程。恢复后先重读本检查点并核对用户已恢复Goal，再审查未构建r69源码、补齐必要测试与构建；不要把WIP误当已验证内核，也不要重跑已完成r68窗口。

### r69恢复与交互准备

- 用户已恢复Goal；本轮完整重读目标，核对r69 WIP及r68回执78份SHA无变化。已审查只读输出来源代码，原r66所有绑定源与EXE保持。
- 首次构建**DC21908 exit1／148.50秒**：已完成源复制／七份渲染，尚未配置编译；历史MSYS2根目录已不存在，不是C错误。新builder增加仅限本版本、未打包workspace的显式resume，并在续建前逐文件校验全部准备源，不放宽完成内核保护。
- 恢复私有工具链到ASCII固定目录`<PROJECTS>/z62-qemu-tools/msys64`。缓存base20260927 SHA ea2f31a0b6ade63914ce441ffb022f0f6aa96982bfefa2326460a26d5fb01322与官方HTTPS完整字节一致；公钥probe4进一步验证官方主指纹0EBF782C5D53F7E5FB02A66746BD761F7A49B0EC、签名子指纹E0AA0F031DBD80FFBA57B06D5A62D0CAB6264964及RSA签名通过。早期URL／装甲格式／错误信任域失败均保留。
- 原私钥代理初始化停在gpg -K、agent耗CPU，owned辅助进程采栈后仍无进展；前台对照也失败。只停止本私有根内辅助进程，**DC33740终态exit1／1345.09秒**，未删除旧keyring。公开发行方密钥验证不需要私钥代理；使用发行方认证的5个master指纹及4个revoked指纹，保持pacman SigLevel Required，未启用TrustAll、Never或弱签名选项。
- **DC3456私有工具链恢复exit0／625.40秒**，128包版本及缓存归档SHA锁定。随后**DC20780配置exit1／79.86秒**，明确缺FDT库。**DC40704依赖扩展exit0／12.76秒**，新增dtc1.8.1与libyaml，130包另存不可变锁`z62-toolchain-manifest-r69-2.json`；原锁保留。新GLib2.90.1、Python3.14.10及DLL变化必须在回归及报告中明确，不能仅称字节相同r66。
- 当前已用新锁启动r69续建，句柄以本轮工具返回为准；保持header／adapter／builder及全部准备源冻结，不因观察超时重启。尚无r69完成manifest或已验证EXE，先取真实终态再运行native来源、照片／视频数值及旧回归。
- 新`z62_paired_camera.py`及其9项专项已先红后绿（最后0.008秒）：只从实际提交ISP来源取帧，不读取较新的RAW consumed代替；标签／参数／陈旧帧拒绝，模式请求不立即改确认状态，需实际输出后再消费当前模式帧，未知交付不重发，超时不算确认。界面mixin／新入口与实际I/O集成仍未完成，不能以这些单测称整机通过。

### r69构建完成与r71交互验收进行中

- 已完整重读目标后继续。本轮查明旧DC40400缺diff；DC1464 base-devel失败为mirror.msys2.org返回403及repo签名下载低速超时。官方repo签名HEAD200后，仅将私有根mirrorlist.msys的repo顺序提前，签名Required保留。**DC31636 exit0／18.84秒**：139包锁`z62-toolchain-manifest-r69-3.json`，旧锁不改。
- **DC25076 r69续建exit0／309.26秒**，EXE SHA256 `37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9`；VMState55、26层、七份生成源、工具链锁SHA已记录。r66及既有绑定源未改。
- **DC36356输出来源native exit0／79.48秒**，`analysis/z62-output-lineage-r69/native-1.json`：默认off、照片／视频实际输出、发布不等于完成、背压、旧RAW、拒绝、只读及reset通过；不是原厂窗口／AF／整机验收。
- 新独立`run_z62_paired_console.py`及生成器、JS状态、`probe_z62_paired_console.py`已写入。仅生成全新ASCII临时staging，使用显式r68 group23实验fixture，不改旧默认入口；照片／视频模式需实际提交来源确认。实际页面发现新mixin重复获取非递归io锁，已用专项测试先红后绿修正；另核对具体类覆盖mixin方法，新增实际类的键门控／状态注入，待新staging验证。
- 第一次server **DC43836已exit1／159.31秒**，因上述宿主死锁，核对路径／父进程后只停止自有QEMU39668及host24008；临时目录z62-reference-u4cfcxxb保留，不能算正常关闭。
- 第二次server **DC44924**，staging `<USERPROFILE>/AppData/Local/Temp/z62-reference-0fujlaie`，测试卡`artifacts/z62-paired-qa-card-r71-2`、端口8685。`http-1`在10.403秒实际照片输出确认，JPEG／NEF存卡；独立JPEG解码通过，但video环境缺rawpy使probe exit1／26.23秒，不能算完整通过。
- `http-2`用既有raw-verify-r25环境接续同一照片，核对原下载SHA，未重放快门；NEF LibRaw解码及RAW14摘要通过。17.121秒发送视频输入，readback=0xfffffe，未释放或改写；后续实际输出仍photo，32.12秒虚拟截止已超时，模式切换未通过。尚未确定是完整快门触发后的原厂流程缺口还是其他交付条件，不能强改ready、补完成或称录像通过。
- 当前自有句柄以本轮真实工具结果为准：DC44924 server、DC26192 http-2待终态；r69 paired回归已新启动。完整Goal保持active，下一步先保存失败终态及验证新staging，再做不按全快门的模式对照。不要重跑r68已完成55秒基线。

### r69/r71本轮终态与下一步

- 上一段“待终态”已结束：**DC26192 http-2 exit1／362.69秒**；实际JPEG／NEF字节及独立解码通过，拍照后切video未确认。**DC44924 server正常exit0／781.20秒**。首次失败server的DC43836句柄后来被系统复用于归档进程，勿按旧句柄／PID识别当前任务。
- **DC35544 paired回归exit0／66.81秒**：15类数据／控制门槛通过、3个实例正常关闭及日志SHA归档；**DC43072 handoff回归exit0／65.39秒**：retired1、真实待处理输出背压、旧调度工作及失败不写／不退休通知保持。没有重跑r68已验证窗口。
- **DC44936全量635项exit0／216.139测试秒、219.02进程秒**。随后LCD文字／顶部确认提示及机身按键禁用的8项生成专项先出现未归一化测试JS锚点错误；改为两个已审查版本的唯一锚点后，**DC19396最终8项exit0／1.980测试秒**、生成JS经Node语法检查。全量后只调整提示／生成兼容，未重复全量；摘要`analysis/z62-output-lineage-r69/suite-result.json`明确完整stdout未另存。
- 第三次server **DC556**，staging `z62-reference-e1c2x9tx`、端口8686、卡`artifacts/z62-paired-qa-card-r71-3`。**DC43064未按全快门的selector对照exit0／266.57秒**，10.348秒确认photo，21.017秒确认video及当前模式帧；`selector-before-shutter-1/result.json`。不能从操作历史／生成源并非完全相同的两次对照确定全快门就是阻塞原因。
- **DC44700录像probe exit1／10.61秒**，部分事实通过：错模式快门明确400拒绝、开始／重复开始／停止／重复停止，实际保存`Z62_0001.MP4`，SHA `36dac23f60745d31413b769c4fe03861f042752215cb0d713b4c286b91da7f02`；9帧640×424 H.264/yuv420p静音视频，0.296543秒，FFmpeg／FFprobe解码、每帧提交来源及视频回放通过。返回请求在退出回放半按未释放时被camera_operation_busy明确拒绝，不是交付未知。
- **DC45432释放后接续exit1／280.58秒**：核对相同视频SHA、不重放录像，确认按键释放再发photo；读回高成功，但观察遇HTTP503，完整返回仍未通过。之后只读status仍running，QMP timed_out=2、late_replies=2、replayed=0，状态码为空，不能称QEMU退出或永久失联；也不能以稍后可读覆盖原验收失败。`session-3-return-failure`含HTTP及110份会话快照。
- 旧启动器最终写回缓存record会丢失runtime参数说明；新r71入口增加只核对自有staging及实际fixture字节的收尾同步。第四次无目录卡server **DC42812正常exit0／148.94秒**，staging `z62-reference-3s6q9io0`；现场读回clean_exit=true、group23 SHA一致、zero_body=false、paired_profile=r71通过，归档`session-4-final`。
- 第三次server已通过本地`/stop`正常关闭，**DC556 exit0／1281.39秒**。本轮临时IAB页已关闭，未操作用户原8682页。无新默认入口升级、无GitHub发布、无相机访问。r66及全部已绑定模型源／EXE保持。
- **DC37132一致性复核exit0／9.77秒**，`analysis/z62-output-lineage-r69/verified-final-1.json`核对26层r69身份、native／paired／handoff回执、照片／视频字节及会话副本；保留interactive_full_flow／photo_to_video／video_return_photo／AF／flash_safety全部false。它是证据一致性复核，不是另一次完整相机运行。
- [使用说明](profiles/README-Z62-OUTPUT-LINEAGE.md)、[正式阶段报告](history/2026-11-03_实施-Z62输出来源与独立交互r69-r71-report.md)和能力清单已更新。完整Goal继续active。**下一步先对交互入口做原厂选择交付／停止条件与QMP超时现场诊断，定位拍照后和录像后切换缺口；再推进照片回放／缩放／删除及异常路径的新来源验收。** 不提前进入修改AF，不改ready、原厂队列、等待／超时，也不把短C录像说成原厂录像或完整刷机验证。

### r72只读交互诊断进行中

- 新Goal回合完整重读目标，判定前回合为有效进展。继续保护r69内核、r71根模块和已绑定回执，不重跑r68。复用r28／r29原厂输入字段与之前的ready观察条件，尚未修改原厂输入门控或算法。
- 新`z62_paired_diagnostic_console.py`、`run_z62_paired_diagnostic_console.py`及5项专项：有界半字字段读取、缺失读取拒绝、不重放控制、取证错误不覆盖原TimeoutError、每控制台只尝试一次宿主抓取。已先红后绿，**DC39540 exit0／0.209测试秒**。
- **DC27824 r69宿主GDB原生检查exit0／3.57秒**，实际9成员ASCII副本与r69字节一致，GDB附加／线程栈／detach／QMP恢复、正常关闭通过；无原厂执行，不是模式切换验收。证据`analysis/z62-paired-diagnostic-r72/native-host-1/native-host-check.json`。
- 当前诊断server **DC24048**，端口8688，staging `<USERPROFILE>/AppData/Local/Temp/z62-reference-fei9l1_k`，测试卡`artifacts/z62-diagnostic-card-r72-1`。仅默认on诊断配置和相同字节ASCII运行时；`/paired/diagnostics`读C1.70选择scalar／cached／decoded、input_inhibit、ready_join、processor状态及提交来源。首次QMP超时才对持有Popen的自有EXE抓栈，任何尝试都取消功能资格；不改变timeout或重放请求。
- 初次现场读2.034秒原厂inhibit1／join1，15.200秒C photo输出ready但原厂仍inhibit1／join1、processor2、配置[773,1002,1,0]。**这是C输出ready不等于原厂操作可用的现场证据，尚未证明为前次切换失败的唯一原因。** 两项视频诊断counter误用了video-isp前缀，实际属性前缀为video；当前现场保留unavailable而不补0，核心selector／来源读取正常。保持该运行生成源冻结，后续新变体再改counter名字。
- 当前原厂观察 **DC37688**，`analysis/z62-paired-diagnostic-r72/photo-then-mode-1`，正式新probe `probe_z62_paired_selector_diagnostic.py`。先等实际C photo输出与原厂inhibit0／join3，再发一组全快门／释放、确认存卡及松开，随后只发一次video选择；持续采原厂选择传播。read timeout／503保存为缺口并继续同一VM，不能因观察过期重启。先续查这两个真实句柄，完整Goal保持active。

- **DC37688已exit0／217.18秒**：只表示观察完成，video_mode_confirmed=false；functional资格true、源码未变、无宿主抓取。16.820秒原厂条件变为inhibit0／join3，随后实际全按／释放及C照片存卡；18.680秒主引擎decoded/cached/scalar已为1，changed1，但到31.864秒处理配置仍[773,1002,1,0]、实际输出photo，最终模式超时。说明等待原厂初始条件不能单独解决此路径，选择输入已到主缓存，后续处理仍需定位。
- 该会话112份快照已归档`analysis/z62-paired-diagnostic-r72/photo-case-session`，**DC24048 server正常exit0／577.63秒**。未改该运行实际生成源码，两个视频counter的unavailable保留。
- 新无全按control计划保持相同r72设备／reader及初始gate，工具`probe_z62_paired_selector_control.py`。首次新server **DC44012 exit1／32.54秒**，尚未启动固件：复制4GiB SD时C盘空间耗尽，最终session.json也因ENOSPC变零字节。失败目录`<USERPROFILE>/AppData/Local/Temp/z62-reference-ruflz7ez`及报告保留。
- 已只删除该失败目录中**2,889,875,456字节不完整virtual-sd.raw**：删除前核对绝对目标、普通文件／非链接、大小、零字节session及三成员完整SHA与本项目一致，源卡与其余证据保留。C盘恢复2,884,386,816字节可用；未做其他清理。记录`failed-control-copy.json`。
- 新`run_z62_paired_managed_console.py`（r72a）将后续scratch限制在D盘任务私有owner目录，复制前检查SD大小＋2GiB空间；仅进程内保持gettempdir／TEMP／TMP／PI_SCRATCH_DIR一致，退出恢复。3项容量／owner／异常恢复专项通过（DC42300），不改r71/r72已冻结模板或系统环境。新control server已启动，句柄以本轮工具结果为准，先查真实终态／Session路径再启动唯一control probe。

### 用户最新强制存储边界：全部项目产物位于工作目录（2026-11-03）

- 用户明确要求“所有的东西不要放到c盘…放到工作目录中”。**此后所有本项目生成文件、TEMP/TMP、虚拟卡、会话、工具链、下载和缓存必须物理位于本工作区；不能再用C盘，也不能放在工作区同级D:/.../z62-qemu-tools。只读外部输入／已有系统程序不移动。** 后续运行使用`tools/run_z62_workspace.py`或`start-z6ii-workspace.cmd`；普通工具命令也必须在子进程设置`TEMP=TMP=<WORKSPACE>/.runtime/tmp`并使用Python -B。Q:仅为本工作目录的ASCII访问别名，不另存数据，启动器会验证／重建该映射，绝不覆盖其他盘符。
- 迁移前本轮诊断终态：DC552无全按control **exit0／213.33秒**，video_confirmed=true；16.691秒原厂gate满足、21.314秒视频新帧确认。与全按组相比scalar changed清零、配置[768,846,3,0]，原厂gate不是永久ready定义。
- DC44868分段半按／全按probe **exit0／516.20秒**：观察完成但video_confirmed=false；半按200ms→全按200ms→先松全按再松半按仍未切换。发生宿主抓取尝试／output-unavailable，functional资格false，源码未变；此组只能诊断，不能作为功能对照。用户存储调整时已归档`analysis/z62-paired-diagnostic-r72/before-workspace-migration`，保留host-diagnostics实际文件。DC32268原server正常exit0／1143.34秒。没有因观察超时重启；这次停止是为执行用户明确迁移要求。
- `migrate_z62_storage.py`逐文件SHA核对再move提交：**DC27380 exit0／370.40秒**，19,446个C盘实际存在文件、7,895,797,700字节迁至`.runtime/migrated/c-runtime`；旧C temp的z62目录当时已为空，逐空目录移除，未猜测其此前清理者。原C项目运行根与z62-* temp目录再次盘点均为0，`c-storage-after.json`。不把C盘其他空间变化归为本次回收。
- `move_z62_tools_into_workspace.py`：**DC24320 exit0／288.34秒**，同卷迁移旧D盘同级tools目录至`.runtime/tools`；迁移前后50,519文件、5,805,994,617字节SHA清单一致，旧D目录不存在。完整清单`.runtime/tools-relocation*.json`；旧锁原字节保留，后续构建应使用新的物理root／迁移锁。
- 新`z62_workspace_paths.py`只在独立启动上下文和新私有host副本中映射文件路径，原厂指令与设备模型不改；旧C项目路径映射到已迁入数据，输出越出工作区则拒绝。4项路径／拒绝C输出专项 **DC32512 exit0／0.005秒**；迁移复制／冲突保留2项 **DC42804 exit0／0.082秒**。`.runtime`已加入Git忽略。
- `run_z62_workspace.py`配置本进程TEMP/TMP、缓存、Java home和子进程AppData到工作区；将新生成host的Path导入改为已验证物理归属的ASCII别名访问，不修改原绑定模板。19个Z62／参考启动命令已接此入口，原entry和参数保留；24个所有start-*.cmd都加入工作区TEMP／TMP／pip缓存及禁pyc。历史报告与回执不改字节，旧绝对路径依`.runtime/migrated/files.jsonl`追溯。
- r73原生宿主测试首次因Q别名和普通D Path比较导致owner未匹配，**DC39064 exit1／3.73秒**，未启动抓取，保留`native-host-1/adapter-failure.json`。改为一致使用已验证WorkspacePath，不放宽owner guard；**DC572 native-host-2 exit0／5.03秒**，自有QEMU附加／detach／QMP／正常关闭通过，全部临时数据实际在工作区。
- r73实际照片存储检查server **DC3564正常exit0／655.90秒**，session `<WORKSPACE>/.runtime/tmp/z62-reference-cvtoc8rk`。真实C photo提交与场景源无错，JPEG＋NEF存入`artifacts/z62-workspace-storage-check-r73/DCIM/100Z62EM`，独立JPEG640×424／LibRaw1006×1514通过；DC46412 exit0／1.57秒。JPEG SHA ed3b252e7775df2a16349d526aee08ab4ecda0d76179614a3f0ab9e4b38c5f68；NEF SHA c4bf8dfb6c3be7189f0139c8ecb4359788421ed110729cc48f61b0d3af6db6c6。第一次离线检查误把payload当卡根目录，已按实际DCIM路径纠正，未重拍。
- 当前待续：DC49388存储最终复核（逐C迁移文件SHA、工具清单、139包锁、r69身份、原生宿主及媒体字节）；另已启动旧默认capture profile的工作区存储启动检查，句柄以本轮返回为准。**禁止再执行旧裸入口去C盘创建临时目录；也不要把新的存储包装当作模式恢复或AF通过。** 完整Goal保持active。

- **DC49388已exit0／104.63秒**，`analysis/z62-workspace-storage-r73/verified-storage.json`：重新核对19,446份C迁入文件SHA、D工具迁移前后清单、139包版本、r69身份、工作区宿主原生及照片字节；C旧项目根／z62临时目录为0，24启动器均有工作区TEMP。`.runtime/relocated-toolchain-manifest-r73.json`已生成，原锁不改字节。
- 最后旧默认capture profile存储启动检查为**DC48228**，session `<WORKSPACE>/.runtime/tmp/z62-reference-td5q41pe`；实际API读回phase/execution=running、error=null、原r16 host／r13内核，证明未借迁移升级旧默认内核。已通过本地/stop请求结束，先查该句柄最终关闭后再续后续工作。它只是启动／存储检查，没有重验完整旧媒体流程。
- **DC48228已正常exit0／249.28秒**；最后进程检查无本任务QEMU，C项目运行根不存在、C temp下z62项目目录0、旧D盘同级tools根不存在。当前无待续本任务长进程，存储调整子任务已验证完成；完整相机Goal仍active。

### r74永久故障保存与r75 C照片工作流进行中

- 新回合完整重读目标；前回合为有效进展。检查实际文件及shared.Machine._cleanup源码，发现上段建议读取的r72原始host-diagnostics已随self.work正常清理，摘要／log SHA还在但原始栈不在迁移清单。不能从摘要推断阻塞位置，缺口`analysis/z62-persistent-diagnostic-r74/r72-evidence-gap.json`。
- 新`z62_persistent_diagnostic_console.py`／`run_z62_persistent_diagnostic_console.py`独立r74层，把首次超时文件保存到工作区analysis永久目录，保留原self.work作为console来源；仍只尝试一次GDB、控制不重放、不改生产timeout，任何尝试功能资格false。2项先红后绿，**DC42184 exit0／0.379测试秒**，真实模拟VM目录清理后文件保留及越界输出拒绝。
- 新原生故障probe第一次1us接收deadline没有触发超时，**DC2276 exit1／4.39秒**，失败保留。后改为显式测试专用100ms接收延迟＋1us该请求deadline；未改生产QMP默认5秒。**DC46784 native-fault-2 exit0／4.88秒**：无固件执行，实际自有QEMU／GDB抓栈、detach、QMP恢复、timedout1／late1／replayed0、正常关闭；删除VM scratch后真实host-gdb.txt与SHA仍在`analysis/z62-persistent-diagnostic-r74/native-fault-2/permanent`。这是故障机制测试，不是自发QMP超时根因修复，functional资格false。
- r74实际server **DC25420正常exit0／1120.84秒**，session `<WORKSPACE>/.runtime/tmp/z62-reference-1fx7uekn`，卡`artifacts/z62-persistent-card-r74-1`。**DC47432 C照片整链exit0／30.36秒**，`analysis/z62-persistent-diagnostic-r74/photo-flow-1`：已提交photo来源→C镜头手动0.65稳定→JPEG＋NEF两组存卡／独立解码→ISO100/200实际RAW均值4808.789/8450.968→回放/前后切换→2x显示独立裁剪MSE0.7858（对未缩放17938）→两组成组删除／用量0→返回live，通过；unperturbed_flow_verified=true。原厂拍摄／AF仍false，C镜头未标定。
- 浏览器检查暴露r71层的两个UI缺陷：初始disabled通过 ||= 永远不释放，已确认photo时拍照按钮仍禁用；后台API改变焦点／ISO后表单仍0/100。新独立r75前端`z62_committed_controls_console.py`、`assets/z62-committed-controls.js`、`run_z62_committed_photo_console.py`，明确赋值拍摄门控、同步已应用表单并保留未提交draft；Node状态转移1专项 **DC16208 exit0／0.145秒**。原r71/r72及r69绑定源不改。
- 当前server **DC40860**，entry必须经`run_z62_workspace.py --entry run_z62_committed_photo_console`；session `<WORKSPACE>/.runtime/tmp/z62-reference-lw_srajl`、卡`artifacts/z62-committed-ui-r75-1`、故障永久根`analysis/z62-persistent-diagnostic-r74/live-ui-1/faults`。浏览器实际确认API设置.65/200后表单一致且拍摄按钮启用；UI将ISO400保留为draft（当前仍200），点击应用后显示已应用400；UI拍照生成Z62_0001.JPG＋NEF并回放2x。独立API DC47648确认view=playback、zoom2、ISO400、photos1、全部按键释放。新截图均存工作区`analysis/z62-committed-ui-r75`，最终使用photo-playback-controls.jpg；旧8682用户页不动。
- 当前IAB工具变量photoFlowTab，tab3／browser2，仅本轮测试页。尚未关闭DC40860或最终归档该会话；卡中1组GUI照片需要保存验证和关闭重开检查。接下来先继续相应真实句柄，不重放已完成照片输入，不用C流程成功覆盖原厂模式切换／AF未完成；完整Goal保持active。

- **DC40860已正常exit0／1709.08秒**，DC21864 /stop exit0／2.92秒；本轮tab3已关闭，未操作用户旧8682页。**DC47580复核exit0／2.33秒**，`analysis/z62-persistent-diagnostic-r74/verified-photo-and-faults-1.json`：真实永久栈SHA／VM scratch已删、两份LibRaw RAW均值与摘要、2x裁剪像素、GUI ISO400卡关闭重开、r69身份均通过；factory_capture／AF／flash_safety仍false。当前无待续本任务server／probe。
- `start-z6ii-workspace.cmd`现在走独立r75控件入口，旧`start-z6ii-qemu.cmd`的r13内核不升级。新[照片操作说明](profiles/README-Z62-COMMITTED-PHOTO.md)、[r74/r75阶段报告](history/2026-11-03_实施-Z62永久诊断与照片闭环r74-r75-report.md)和能力清单已更新；工作区存储约束继续强制。
- 已实际读取另一份仍存在的r64原始栈`analysis/z62-mmio-write-r64/live-filter-1/host-timeout-1/host-gdb.txt`（63行），其SHA见capture.json；main thread位于GLib／os_host_main_loop_wait，RR线程位于qemu_clock_deadline_ns_all／icount_handle_deadline，单次快照不能证明死锁。r72原始栈确已丢失，不再反复查旧路径或将摘要当原始证据。
- 下一Goal回合优先跟踪全按后APPLV动作消费与选择变化标志未清除的具体条件，必要时利用r74永久目录重采真实现场；同时完善任务一剩余异常／视频往返／其余控件。不修改AF算法、不强写ready或伪造完成，完整Goal保持active。
- [工作目录存储说明](profiles/README-WORKSPACE-STORAGE.md)已写明当前布局、启动方式、迁移量与验证范围；r69和r72使用说明已改为workspace入口。后续优先读取已迁入`.runtime/tools/interactive-sessions/z62-reference-gdpjth72/runs/z62-ynyswh0t/host-diagnostics`的真实超时现场，继续原厂全按后的APPLV处理定位。所有新的分析结果和临时文件仍必须在本工作目录内，完整Goal保持active。

### r76 原厂采集队列与上下文观察（2026-11-03）

- 本轮完整读取目标，前回合为有效进展。DC17012句柄已不存在、8688无服务且无本任务QEMU，才新建server DC26216；session `<WORKSPACE>/.runtime/tmp/z62-reference-lu7o2ake`，全产物在工作目录，r69内核及绑定源不改。
- 新 `z62_action_queue_console.py`、独立入口及读取测试：严格六字队列头／92字节stride／环顺序、40字采集上下文和APPLV只读快照；无效布局不补空，明确非原子。workspace启动器已加入该entry的工作区fixture默认参数。
- **DC11772 exit0／448.20秒仅为观察完成**，`analysis/z62-action-queue-r76/photo-then-mode-2/result.json`：213份样本、无read error／QMP超时／late reply／请求重放／宿主附加，video确认false。16.752秒初始gate满足时队列已60/60（59准备帧工作＋1其他）；16.934秒全按释放后stage8000／callback103EC627／pending4080／result word4、APPLV动作14h；31.987秒stage2000000／callback103E7CD1／pending800000仍active，选择changed1、输出photo，模式超时。采样队列59–60、head持续推进，不能称完全死锁。
- `record_z62_action_evidence.py`／3项新增专项；首次误把UI生成器当运行模块、默认晚绑定拒绝及r73 Path导入差异均已查明。**源仅后段绑定，r76_reader_bound_before_shutter=false**，不可宣称新模块全窗口绑定；实际生成网页及唯一Path替换逐字核对。**DC9532 exit0／1.25秒**复核`verified-action-2.json`。
- `analyze_z62_capture_pending.py`对原master全SHA及两个Thumb区间重新核对；**DC26484 exit0／1.36秒**，`pending-instructions-2.json`：103EC626调用的掩码排除60h，当前4080h／4000h并不豁免；不是等待60h出现。尚未逐调用观察返回，亦未识别缺失硬件完成合同。
- **DC36776最终6项专项exit0／0.008测试秒**。未重复旧r68窗口或全量套件。**DC30232归档115文件exit0／2.18秒**，`session-before-close-2`；本地/stop后**DC26216正常exit0／632.21秒**。
- [r76报告](history/2026-11-03_研究-Z62全按后队列与采集上下文r76-report.md)及能力表已更新。下一步用既有限定调用帧／断点重入处理，直接观察当前r69上 `10325186→1031627E→103EC564` 的采集提交是否拒绝，再沿pending生产／清除路径定位。不要把旧r16/r17拒绝返回当本轮结论，不扩大队列、不补完成、不改ready和原厂等待。完整Goal保持active，默认交互入口仍r75。
- 收尾已新增 `probe_z62_action_queue.py`，在原probe首个网络读取前同步绑定实际生成源，保留原输入／等待／失败标准。仅新包装顺序专项已验证，不能回溯提升本轮已结束窗口的绑定范围。**DC33088最终7项exit0／0.041测试秒**；**DC5740 exit0／2.56秒**复核115归档／8绑定源、clean_exit=true及r69身份。当前无本任务QEMU，下一轮使用新包装并继续限定采集提交观察。

### r77/r78 采集拒绝与输入就绪等待（2026-11-03）

- 本轮完整读取目标，前轮为有效进展；真实进程检查无旧QEMU后启动DC21980，session `<WORKSPACE>/.runtime/tmp/z62-reference-mli80mdo`，r76配置／r69内核不变。所有新数据在工作目录。
- `probe_z62_capture_submit.py`复用既有BreakpointWindow和CPU限定单步，仅观察采集调用帧。首次DC8104 trace-1在TCP State枚举查询失败，未附加、未发快门；核对该枚举为空但端点／PID有效后改为精确回环端点＋RemotePort0／正PID＋EXE同文件＋完整命令行校验，不重启VM。
- **DC34532 trace-2 exit0／5.93秒**：同CPU02、外层SP闭合的`10325186→1031627E→103EC564`。目标work10320019、callback103EAE81，队列60/60时下层入队R0=0；上层包装随后也R0=0，但原指令证明它没有传播入队布尔结果。全按／释放各一次、detachOK、无QMP超时／重放。新生成源在输入前绑定通过，guest断点使功能资格false。
- 后续四组均在**同一VM、该次采集拒绝之后**观察，无额外控制：r78 DC23400 exit0／13.46秒、r78b DC7048 exit0／17.06秒、r78c DC34740 exit0／15.89秒、r78d DC27236 exit0／15.26秒；各3包完整闭合、源码不变、detachOK。
- 当前准备包约202ms；事件15实际约3–14微秒返回1，不套用旧r16事件15超时。长耗时经10231FAC→1023AE42定位到`1023AE4E→102387B6→10238804/1035D43A`。**三次C188808C／mask05B00000h／参数200等待耗时201.256–201.402ms，R0=0、输出字0；事件字01000111h，仅满足掩码一部分。** 包装后来返回1不等于前置等待成功；2EB是位图线索，非已确认硬件命令号。事件8未配对return-site保留，不伪造返回0的等待。
- `verify_z62_capture_submit_evidence.py`已验证四组源／调用帧／虚拟时钟／显式驱动配置及原始指令，`analysis/z62-capture-submit-r77/verified-traces-2.json`；**DC22464 exit0／2.41秒**含5项专项。另2项准备帧时钟／窗口专项已过；最终合并7项句柄DC30824待确认。没有重跑旧r68或全量。
- 两份session归档各115文件，`session-after-submit-2`及`session-final-1`。已发送本地/stop（DC37172 HTTP200）；先核对DC21980正常终态和归档SHA再续下一轮，不能按旧PID误认其他进程。
- [阶段报告](history/2026-11-03_研究-Z62采集拒绝与准备帧就绪等待r77-r78-report.md)及能力表已更新。下一步从当前05B00000h就绪掩码的实际生产者、描述符及通道启停状态查缺失设备合同；不补ready、不扩队列、不改原厂等待。完整Goal仍active；本轮没有新增仿真设备或修复模式往返，不修改AF。
- 收尾：**DC30824 合并7项新专项exit0／1.63秒**；**DC21980正常exit0／1191.09秒**，session clean_exit=true，最终进程检查无本任务QEMU。DC11020复核最终115文件归档及verified-traces-2引用的12份证据文件、verifier自身SHA和r69构建身份。未重跑固件窗口，无关staged修改保留。
- 因果边界：r78等待时长来自采集拒绝后的现场，不能单独证明全按前队列饱和的唯一原因。下一步优先在相同r69配置的**无全按**初态做短限定准备帧／05B00000h等待对照，再结合真实生产者与通道启停状态决定设备实现；不要直接照搬旧r16或给未工作的通道发送成功。

### r79–r82 无快门对照、通知调用及对象首字更正（2026-11-03）

- 前回合为有效进展；本轮完整重读目标，确认无旧QEMU后启动DC9992，session `<WORKSPACE>/.runtime/tmp/z62-reference-l6okq1kb`，仍为r69内核／r76控制台。所有产物在工作目录，未改绑定设备源。
- **DC22084无全按对照exit0／160.71秒**：`analysis/z62-prepare-control-r79/no-shutter-1/result.json`，只GET、无控制、取证前后／每个命中capture active0、空卡、按键释放。约17.07秒队列已60/60；3次原厂等待mask05B00000h耗时201.423／201.876／201.021ms，R0=0、输出字0；三个包闭合、源未变、detachOK。证明此拥塞在全按之前已存在，仍不等于已找全设备原因。
- r80通过同一自有GDB端点的白名单HMP qom-get读16项已有属性，处理完整RSP O包再解析：**DC19444 exit0／4.92秒**、**DC23644 exit0／4.39秒**。同PID连续统计成功帧642→2744、bytes16846080→72002560，两次reject0／blocked0／reason success；不应再假设所有统计都没产出。有限统计仍2批／122帧。
- **DC20852 r81通知调用窗口exit0／13.88秒**：2包闭合、source unchanged、detachOK；指定五个post点中16次命中102392FC，R0=C188808C／R1=00800000h；两次等待期间分别5／6次请求仍超时。其它四点只在该窗口未命中，不称全局缺失；没有捕获setter返回或真实kernel flags。五个对应输入mask位均启用。
- **重要更正（覆盖r77/r78旧叙述）**：C188808C首字01000111h不能直接解释为就绪位图，之前“只满足01000000h／缺04B00000h”的比较已撤回。原始Thumb封装1035D446解引用首字，再BLX到ARM10104A14／SVC#6，stub选择字80300500h；它是传入内核的opaque参数，真实flags尚未读取。r77入队0／队列满及r78/r79超时证据不受影响，原JSON/SHA不重写。**DC18784边界复核exit0／1.27秒**，`event-object-boundary-1.json`，并已更正旧报告及当前能力表。
- `verify_z62_prepare_control_evidence.py`检查同VM／源绑定／原字节／无控制无照片无采集／CPU-SP调用配对／显式producer配置及两次计数：**DC18804 verified-control-3 exit0／1.61秒**。**DC41080新6项专项全部通过／exit0／2.30秒**（含证据复核运行），没有重跑旧r68或全量。新探针和分析工具的SHA已绑定，后续语义变化应另建版本，不改后仍引用旧回执。
- **DC36688归档115文件exit0／1.80秒**；本地/stop HTTP200后，**DC9992正常exit0／1535.66秒**。最终session clean_exit=true，进程检查无本任务QEMU；DC4044复核归档／回执／源SHA（已清理的命令文件从同SHA归档核对）及r69构建身份。无关staged `.gitmodules`、`third_party/z62-qemu`保留。
- [本轮报告](history/2026-11-03_研究-Z62无快门拥塞与事件参数边界r79-r82-report.md)及能力清单已更新。下一步核对原厂通知的setter返回和真正内核事件对象，可结合80300500h的公开ABI线索作候选但不预设RTOS；或沿其它输入通道实际配置与生产条件找模型合同。不得把opaque首字补成flags，不因连续统计有数据就替所有引擎发成功。默认仍r75；完整Goal active，模式往返／原厂存卡／AF未完成。

### r83–r85 真实事件控制块和内核返回（2026-11-03）

- 完整重读目标；前回合为有效进展。本轮利用工作区nightglasses/z7ii-qemu内核研究线索，但以Z6II完整masterSHA和ARM实际操作数独立核对。公开T-Kernel2下载至工作目录references/rtos/tkernel_2，固定5778f619…；其WAI服务80360500与目标80300500不相同，仅作语义参考，不据此确认目标RTOS产品/版本。
- 原始代码解析事件全局C18AEC38、32字节CB、ID+8／attr+10h／pattern+14h；现场ID01000111、tableC2C37808、CBC2C39A08、pattern地址C2C39A1C、attr8。新z62_kernel_event_layout.py拒绝坏ID／越界表／不匹配CB。
- 首次DC10536 r83 events-1为不完整：共享内核返回点过热，96停顿在目标返回前耗尽；之后运行态RSP读取超时、cleanup失败，未篡改原结果。VM仍为同PID33960、QMP正常paused。首个恢复因z1不存在返回E22拒绝；DC7464 recovery-2逐已知地址验证insert/remove OK、detachOK、query running，未重启VM、未发控制。
- **DC17272 r84 events-2 exit0／9.68秒**：目标任务栈的1035D450处得到原始FFCE0000（signed -3276800，主错误部分-50），源未变、detachOK。**DC30436 r85 events-3 exit0／8.18秒**：在原厂AND等待期间，实际ARM OR/store将同CB pattern从0写为00800000，setter返回0；随后真实pattern00800000、所需05B00000缺05300000，内核FFCE0000／上层0／输出0。此结论来自实际pattern字段，r82撤回的首字比较不再使用。
- **DC38808 verified-kernel-1 exit0／1.24秒**复核三版窗口／失败与同VM恢复／源SHA／CB身份／调用帧／原始store前后值／错误；3项新专项通过。全程仅GET和原始执行断点/单步，未调用inferior函数或写guest状态，功能资格false；没有修改或重建r69。
- **DC33448归档115文件exit0／1.62秒**；本地stop后**DC21924正常exit0／2005.18秒**。本轮[阶段报告](history/2026-11-03_研究-Z62真实内核事件与通知交付r83-r85-report.md)记录证据与限制。
- 用户随后明确要求“这次完成推送github云端，更新readme等文件”，本轮新增GitHub发布授权覆盖先前仅本地限制的发布部分。已确认既有公开new-Beginner/z62-qemu main=39540055…为r49快照，在工作区.runtime/publication/z62-qemu-20261103独立克隆并建codex/publish-r85；原工作区无关staged修改不动。新README和公开快照正整理，不能在真正推送和远端验证前声称完成。
- 完整相机Goal仍active，下一设备工作聚焦其它就绪生产者的合法配置和数据合同；原厂存卡／模式完整往返／AF仍未实现，不以已有统计101和内核置位成功冒充其它通道完成。

### 用户授权的GitHub更新已完成（2026-11-03）

- 已在独立公共克隆codex/publish-r85提交并正常fast-forward推送到既有公开仓库[main](https://github.com/new-Beginner/z62-qemu)，commit **5ad2a6a0246d93099a16ab2ee5eee72531d231f4**；保留39540055…等公开历史，没有force push。原工作区`.gitmodules`与`third_party/z62-qemu`暂存保持。
- README更新至r85研究快照，明确r69内核/r75界面；同步功能／限制、技术难点、开发时间线、构建依赖、参考署名、NOTICE和文档索引。发布源码、测试、历史报告、scope和选定脱敏摘要；不发布固件/卡/工具链/NKN原件/完整内存或反汇编。
- 公开克隆的32模块**131项无固件子集全部通过，零失败/错误/跳过**，850导出文件哈希、567份Python内存编译及本地Markdown链接通过。首轮仅因尚未生成的结果链接停止，失败记录保留；最后文档修改后再做源/链接复核，没有重跑历史635项/固件/LibRaw。
- GitHub main ref、git ls-remote均与提交一致；远端tree **ac74a3d3dca32bc150f34adc7203efb97e1f2906**与本地1037项完整树一致。匿名raw README HTTP200、SHA256 **11ba764913b300270ef38845f4bb8af41d5be20a715d858a987a2a1830a5aa6e**与提交副本一致；仓库仍public，发布克隆clean。
- 发布回执：`analysis/publication-20261103/publish-receipt.json`。发布子任务完成；完整仿真Goal仍active，不能把推送或131项源码测试称为原厂采集／模式恢复／AF或刷写安全完成。后续继续其它真实就绪生产条件的模型合同。

### r86 两级采集像素核心与独立验证（2026-11-04）

- 新增C11独立核心：非整数两级nearest缩小、CFA 2×2相位、256项LUT及RAW12/14/16 LE打包；尺寸／stride／跨度／LUT／重叠先预检，错误不写，padding保留。不含MMIO／DMA／timer／IRQ，没有修改r69绑定源码或EXE。
- DC29816只读快照完成／detachOK：2020×1342→1514×1342→1514×1006，RAW12／pitch2272／packing6。读回不等于原厂写入／commit来源；MAIN仍是合成梯度，组曲线／系数零不能推断擦除或代填。
- DC5340的8项native C通过；DC39944 native-observed-2全1,523,084像素与独立C两次实化参考一致，输出SHA f8a5e164cb63b9040e9aa425b3b92f5c6d2fbfc3edd78ece9ca75e1746c6a1e1；DC40892归档8份源码；DC28288 NumPy独立全样本／padding／原件SHA复核exit0。native-observed-1不作为当前源码权威。
- 恢复后重验首次在编译／stderr解码阶段失败，无源码修改，在ASCII位置与C locale下8项通过。115文件会话归档后，本地8688 stop返回ok；DC34460正常exit0，session clean_exit=true。旧8682页面未操作。
- [r86说明](profiles/README-Z62-CAPTUREWORK.md)、[本轮报告](history/2026-11-04_实施-Z62采集像素核心与独立验证r86-report.md)和能力表已补齐。继续用户授权的GitHub发布，不能在远端实际核验前宣布本次推送完成。
- 下一步：独立MAIN生产者、原厂有效提交和run／stop／reset／cancel／generation／背压、ring-bank真实合同、不可变RAW transfer／LUT描述及下游逆变换；最后才接实际QEMU DMA和对应IRQ。不补unit1/2/200完成，不改AF。模式完整往返／原厂存卡／AF仍缺，完整Goal active。

### r86 GitHub发布完成（2026-11-04，本地发布回执）

- 已在独立公开克隆codex/publish-r86提交31文件更新，正常fast-forward推送main到 **8c4591d77bb8c39936f08c064f0da4ae0326396b**，保留既有5ad2a6a等历史，无force。README／能力／限制／难点／构建／开发记录／署名、r86源码测试和选定摘要已公开；不含固件、卡、工具链、NKN原件或完整RAM轨迹。
- 公开副本实际32模块／131项无固件测试，零失败／错误／跳过；独立GCC编译8个C case全部通过，无私有relocation依赖。862导出文件哈希、573份Python内存编译和Markdown链接通过；最终文档之后另做源／语法／链接复核，没有重跑635项、QEMU或RawPy。
- 初次Git直连fetch超时，在任何push前终止。后用已存在的系统代理作单条Git参数，正常fetch／push成功，不持久修改Git或网络配置。
- GitHub main ref、ls-remote、tree **9f466d0b03ed074329a13f21e337d0f8311e6d72**、含目录的1249项递归树均与本地一致；匿名main README HTTP200／SHA **993352901e4b7b12b625ea588269e681d8e286f79025a468e977f965d8309d12**一致，仓库public，发布克隆clean。回执`analysis/publication-20261104/publish-receipt.json`。
- 发布子任务已完成，完整相机目标仍active；r86仍为独立C核心，没有新QEMU设备、模式恢复、原厂存卡或AF验收。原研究索引的两项无关staged保持。

### r87 独立MAIN生产与帧生命周期（2026-11-04，本地后续）

- 前回合为有效进展，完成r86 GitHub发布。本轮完整重读目标，从已确认2020×1342 MAIN需求继续实现独立C来源，保留旧1514×1006辅助帧和r69绑定源／EXE，不重跑旧原厂窗口。
- 新增Z62M v1／96字节帧，明确MAIN角色／linear16 LE／RGGB、stride／epoch／publication／30Hz帧号／虚拟时间／黑白电平及CRC；C11单缓存与读占用在占用时背压，取消／停止／复位使旧serial失效，release仅所有权而非DMA确认。没有MMIO／timer／DMA／IRQ。
- 首轮6项因缺模块失败，实现后6项通过；render用例先失败，接入后7项实际GCC／Python专项全部通过。两个完整色彩场景各1,523,084像素由独立NumPy两级采样／RAW12解码比对，padding和输出变化通过。
- `scene-1`首试Q:/D:相对路径比较失败保留，修正probe路径归一化后`scene-2/result.json`完成：复用现有Scene移动图块和r86实际读回几何／LUT，两帧共3,046,168像素零差异；8份源码原件归档。输出仍为LUT编码域，不当作旧线性ISP输入。
- `check_z62_regression.py`完整发现690项，169.578秒，exit1／2 failures／8 errors／0 skips；完整日志和名称已保留。两构建mock为Q:/D:同位置比较失败，ReferenceSD两项和VirtualSD六项因旧接口resolve后拒绝中文路径；没有改guard或掩盖失败。新专项通过不代表全量绿。
- [r87报告](history/2026-11-04_实施-Z62独立MAIN来源与帧生命周期r87-report.md)和MAIN合同／当前能力已更新。本轮r87仍本地，云端最新r86／8c4591d。下一步继续不可变transfer／LUT描述、逆变换及QEMU有效配置提交／bank-ring／DMA-IRQ；同时处理旧路径兼容并重验。完整Goal active，原厂AF和刷机安全未完成。

### r88 冻结RAW域与量化重建（2026-11-04，本地后续）

- 前回合为有效进展。本轮完整重读目标，复现ReferenceSD两项错误，核对现有r73入口本来就适配reference／virtual_sd的Path。未改这些旧宿主或guard；测试按实际入口选Path、规范化构建mock路径。5＋9＋13项相关测试通过，原r87失败记录保留，不当作新的硬件修复。
- 新增Z62T v1／532字节不可变transfer描述，Python复制tuple、C按值LUT；12／14／16 shift和LUT8。解码先整帧验证后输出线性16，未知末像素码也零写入，padding保留。LUT8低8位已丢，返回输入区间中点而非精确原样本。
- 8项专项先红后绿；四配方各穷举65,536输入，含无损shift16、量化区间、外部LUT修改隔离、坏描述／缓冲／重叠拒绝。新scene用例先失败后接通C核心／主源／decoder；没有QEMU DMA／IRQ。
- `analysis/z62-raw-transfer-r88/scene-1/result.json`完成，两帧3,046,168样本独立NumPy核对零差异，实际最大误差50、通用界128；正向packed与r87字节一致。冻结描述SHA0556c437…，结果SHA f8e7b181…；数值链10份和fixture-binding8份源码分别归档，当前SHA已核对。r69 EXE SHA37603d1f…保持。
- 全量`regression-1.json`698项／171.906秒／exit0；最后测试夹具兼容物理ASCII checkout后重跑`regression-2.json`，**698项／178.953秒／零失败／错误／跳过／exit0**，完整日志保留。无RawPy，不称为LibRaw或新原厂窗口验收。
- [r88报告](history/2026-11-04_实施-Z62冻结RAW域与量化重建r88-report.md)、RAW域合同和能力表更新。本地r87/r88尚未发布，云端仍r86／8c4591d。下一步必须推进实际Z62有效commit／run、bank/ring、逐任务描述与代次绑定、取消／数据所有权和QEMU DMA／对应IRQ，并把重建线性域接入下游ISP；不能继续用standalone成功代替设备完成。默认r75／r69、AF及原厂状态保持，完整Goal active。

### r89 独立QEMU采集设备与实际DMA／输入事件（2026-11-04，本地后续）

- 前回合为有效进展。本轮完整重读目标，将r86–r88原语接入独立QEMU，保留r69／r75默认入口和绑定源／EXE。固定master原字节和旧61,217次MMIO尝试核对bank bit0；一次临时查看的错误基址输出已舍弃，正式分析固定10020000h并核对旧几何锚点。control-contract-1已归档4份源。
- 新增默认关闭的CaptureWork：实际写入资格／选择提交、按值配置／LUT、独立MAIN、最多一个私有worker、代次取消、虚拟时钟DMA、整选中ring规范RAM／别名预检、实际行写回后3/4/135事件、W1C／部分ACK背压。没有写原厂软件标志／ready／队列／返回；启用时阻止不完整迁移。
- 新构建`.build/z62-capturework-2026.11.04-r89/runtime/qemu-system-arm.exe` SHA **65c3eccad787d7ddef4bc8bfef603df115a88d29c61b64cb8a165a66d26b2777**。保留部分复制／TMP中文／链接器诊断解码／QEMU头路径差异的失败；只改新构建器，以ASCII TMP、GCC_EXEC_PREFIX和sysroot完成。旧准备源9文件及清单归档在prepared-attempts/1，最终Configure/Ninja日志保留。
- native-red-1在r69缺属性失败，旧探针源归档；native-1首过，native-2补存6组MAIN／实际DMA和两会话命令／日志。新QEMU合成ARM循环下6帧／**9,138,504像素**一致，bank1、冻结LUT、背压、提交前取消、停止重启、新publication门槛、复位、ring重叠拒绝和只读状态通过；两进程exit0。本轮没有加载原厂固件新窗口，inflight worker取消竞态未穷尽。
- 同一新EXE的旧RAW全槽／错误拒绝／主从及原照片视频软件ISP／来源原生检查通过。完整Python发现698项／179.813秒／零失败、错误、跳过，仍无RawPy，不称为LibRaw或整机验收。
- verification-2对保存的全部DMA再次独立RAW12解码，9,138,504样本零差异、padding、EXE／DLL／旧回归／完整日志／来源均绑定；新native依赖9份、构建／源21份分别归档。原r69 EXE37603d1f…与无关staged两项保持。
- [r89报告](history/2026-11-04_实施-Z62原生采集后端与DMA交付r89-report.md)、设备合同和能力表更新。下一步在原厂C1.70验证实际消费，恢复缺失统计／group20合同，将CaptureWork输出transfer交给下游ISP并绑定共享场景时钟；继续模式完整往返、原厂媒体、快照和后续AF。本地r87–r89未发布，云端仍r86／8c4591d。完整Goal active。

### r90／r91 原厂MAIN窗口与共享源策略（2026-11-04，本地后续）

- 前回合为有效进展，本轮完整重读目标。新增只读／C源供给驱动，从客体完整64位计数和频率取时间，按实际几何生成MAIN，不等旧预览ready，不发控件或完成事件。3项资格／时间测试先红后绿，未知几何不回退常量。
- `original-1`在r89上21次输入缓存接受但0 DMA，wall180秒未达到目标16秒，进程exit0。追踪发现实际`20069530=0x200040`（旧r86也已有），r89guard只允许0；旧原生夹具用了0，未覆盖该字段，是测试覆盖遗漏。失败与4份原驱动／宿主源绑定保留，不改成成功。
- 独立r91新策略仅显式`z62-capturework-policy0=on`才接受0x200040，0保留、未知0x200041拒绝；仍不模拟物理源对、不改像素数学或ready。新EXE SHA **5270d7cfb7db60bbb2ef2f8102ce6c37de4b6c3dbf34a35ea84aed6d67675aa2**，r89/65c3…保持。构建后pacman与r73锁一致，8份新构建源／清单归档。
- 原生policy测试先在r89缺属性失败，r91默认策略拒绝／显式策略接受／未知值拒绝均通过，原有6帧9,138,504样本矩阵复用并保留非零字段来源，4进程exit0。新字段是显式C输入策略，不把未知物理路由当已恢复。
- `original-2`正常到8,003,360,666客体ns／进程exit0：14个缓存接受输入、13次实际DMA，CPU0有13次front18h和13次packed80h W1C；保存publication2…7共6帧9,138,504像素，独立RAW12解码零差异。时间来自真实客体计数，原始3成员与snapshot卡源SHA保持，只有C MAIN发布。
- 603次状态采样中真实CB pattern为0共424次、08000000h共17次、04300000h共159次；末尾0不能当全程0。未采样到完整05B条件，但未断点跟踪setter／返回，不证明采样间从未满足。最后ready_join1／inhibit1、队列60，持续统计0/source、预览0/reset；grid是disabled配置状态，不当硬件完成缺失。1024×682 LCD已看且逐像素确认全黑。
- 原厂复核verification-1绑定窗口／源／原始成员／非零策略／CPU trace几何和ACK，源76份归档；原厂窗口源7份、native源3份也保留。完整当前Python701项／174.859秒／零失败、错误、跳过，仍无RawPy，不冒充LibRaw或整机验收。
- [r90/r91报告](history/2026-11-04_实施-Z62原厂MAIN交付与共享源策略r90-r91-report.md)与能力更新。下一步将CW的冻结transfer解码为有来源线性视图，连接统计/readout/ISP的真实输入资格和交付，检查已有启用条件；不能仅补136/0等事件或改raw计数。原厂摄影存卡、模式完整往返、快照、AF与刷机安全未验收；默认r75/r69及两项无关staged保持。本地r87–r91未发布，云端r86／8c4591d，完整Goal active。

### r91 公开源码整理与发布验证（2026-11-04）

- 用户明确要求本轮完成 GitHub 推送。独立公开克隆使用 `codex/publish-r91`，延续 r86／8c4591d 历史，研究根仓库的两项无关 staged 不参与发布。
- 导入 r87–r91 新增源码、测试、合同和阶段报告，更新 README、覆盖表、构建、限制、开发过程、原作者署名及选定 r91 摘要。默认 r75／r69 与冻结 r89／r91 EXE 保持；公开不含固件、卡、工具链、完整 RAM／trace 或 NKN 原件。
- 独立发布目录实际完成 33 模块、134 项无固件测试，零失败／错误／跳过；GCC16.2.0 严格编译 16 个 C case 全部通过。902 个导出文件哈希、593 份 Python 内存编译与文档链接通过；最终文档回写后另外静态核对，不声称再跑原厂窗口或本地 701 项。
- GitHub API 已核对 `new-Beginner/z62-qemu` 为公开、默认分支 main。云端最终提交另以推送后回执为准；完整 Goal 仍 active，后续统计／ISP 来源桥、原厂摄影、模式恢复和 AF 尚未完成。

### r91 GitHub 发布完成（2026-11-04，本地发布回执）

- 独立公开克隆 `codex/publish-r91` 提交 62 个文件，commit **a9088bf571c4f66d8629b1f60cee128203166110**，正常 fast-forward 推送 `main`，保留 r86／8c4591d 历史，未 force。
- 推送后 Git `ls-remote` 与匿名 GitHub API 均确认 main 指向该提交、仓库公开；远端 README、`docs/RELEASE-r91.md`、`docs/VALIDATION.md` 解码后 SHA256 与本地逐一相同，发布克隆 clean。
- 134 项无固件测试、16 个 C case、902 个导出哈希、593 份 Python 内存编译及链接检查通过；文档回写后另做静态复核。本轮没有新建 QEMU 内核、启动原厂窗口、重跑本地 701 项或进行 RawPy/LibRaw 解码。
- 本地云端回执：`analysis/publication/cloud-r91-20261104.json`。研究仓库 `.gitmodules`、`third_party/z62-qemu` 两项既有 staged 保持，未混入公开历史。默认 r75／r69、冻结 r89／r91 EXE 均保持。
- 本次发布子任务完成；完整相机目标仍 active。下游来源／统计／ISP、原厂摄影、模式完整往返、快照、镜头和 AF 均继续未验收，不能保证真机更新安全。

### r92 CW真实来源到连续统计（2026-11-04，本地后续）

- 前回合完成r91公开推送，为有效进展。本轮完整重读目标，检查实际r91生成源码及有效命令：旧连续统计只认raw_accepted，而CW关闭旧RAW；原厂驱动还漏了card-detect，影响统计时钟和预览资格。grid reason不是直接supported属性，不能仅凭disabled解释硬件缺失。
- 独立r92适配层和默认关闭`z62-capturework-statistics`：worker以冻结transfer量化重建linear16，再打包私有linear12；只有真实CW DMA成功才取得来源资格。单缓存背压、五路写回后消费、代次取消／停止／reset、旧计数0、编码客体RAW保持。EXE SHA **7ec44439301467bd9ef7d170e77425830be0bf6d823e7121815eef9b4e24a644**，父r91／r89和默认入口保持。
- 旧r91缺属性红检查保留。首轮native夹具拒绝上传后遗留frame-3重名，修夹具后native-2通过；native-3只加强MAIN／五路输出保存，六帧157,440输出字节独立重算零差异，背压／冻结LUT／几何拒绝／停止／reset通过，四进程exit0。
- 独立wrapper复用冻结r90b驱动，明确补card-detect并启用桥；原厂8,005,927,333客体ns有14次输入接受、13次CW DMA、13帧统计和2批，CPU有11次20h和2次A0h W1C。旧RAW accepted／stream计数始终0；从CPU trace恢复提交几何，保存6帧9,138,504样本独立核对一致。原厂五路统计数值未另存，不冒充独立数值验收。
- 内核pattern采样0共414、08000000共23、04300000共17、04B00000共158，另2未解析。非原子采样，不能证明05B条件间隙从未满足；ready_join／inhibit1、队列60、预览0，最终LCD已看且全黑。仅组合原厂实验，没有单独card-detect对照，不量化两改动各自贡献。
- 完整回归首轮693项／1个setUpClass错误，根因GCC从中文物理路径找crt2／库失败，stderr又被严格UTF-8遮蔽；不改冻结helper，显式ASCII GCC_EXEC_PREFIX／LIBRARY_PATH后8项专项及701项全量通过，0失败／错误／跳过，180.844秒。旧连续／有限统计及旧CW／policy原生回归通过；仍无RawPy，不称重跑LibRaw。
- 生成源／构建、原厂窗口、native-3、独立复核分别归档12、7、4、13份源／清单；旧失败保留。[r92报告](history/2026-11-04_实施-Z62采集来源到连续统计r92-report.md)、来源合同和能力表同步。下一步完成四槽cohort／readout／ISP真实来源与其它就绪生产者，不能把单帧伪装四帧或补ready；摄影、模式恢复、快照、镜头和AF仍未验收。
- 本地r92未发布，云端仍r91／a9088bf；所有新产物位于工作目录，未访问相机／物理盘、未刷机／改AF；完整Goal继续active。

### r93 unit20数值／DMA及事件96边界（2026-11-04，本地后续）

- 前回合r92为有效进展。本轮完整重读目标，检查实际生成源、r92完整CPU写轨迹及固定nightglasses参考；发现尚未写预览输入和主要配方。重新核对Z62回调literal／注册mask／原始字节，缺少的01000000h生产者是unit20的输入事件96，不是metadata-only事件6或猜测的136。
- 独立r93默认关闭`z62-capture-group`：冻结MAIN／配置和代次，65点插值、signed8/7水平FIR及ROI／9×9网格三类记录；143必需配置字、可选B984冷零且非零拒绝；完整RAM／alias、只读8字cursor包，所有活动族实际DMA后才发96。旧RAW计数不增加，没有原厂ready／队列／返回值写入。EXE SHA **bad3bc345bb152ddb3587beefbbf0a7dbd9a1ae30dc2f67ae872435752294dac**；r92及更早对象保持。
- 初版误将未写的可选B984列为必需，在未验收构建阶段停止唯一自有构建树，归档prepared／生成源后刷新增量构建，日志保留。原生红检查旧r92缺属性；native-1正向通过后因把可写启动RAM误作unmapped负例而中止，源归档。改用真实越界跨度后native-2完整通过，9进程exit0。
- 原生7个MAIN、19份三族输出共18,528字节独立NumPy重算零差异；三族、5槽、bank1 grid-only且忽略未选ROI、masked pending／独立ACK、未分类字节、只读结果、取消／重启／reset、零曲线／零系数／坏曲线／越界／RAW alias拒绝均通过。共享CW worker／按成功工作推进cursor是C有限实现，inflight交错、独立TG和物理时序未穷尽。
- 原厂8,006,316,916客体ns：实际65曲线字及24系数字明确写0；group有效提交但以reason3数值profile拒绝13次、完成0、pending0；CW和连续统计仍各13帧，旧RAW accepted始终0。内核pattern样本0×454、08000000×17、04300000×20、04B00000×165，另2次未解析；非原子，不能证明AND条件间隙从未满足。预览0，LCD像素核验全黑，卡源和原始3成员保持、进程exit0。
- 独立复核verification-1通过，绑定原生／原厂／源／构建、数值载荷和实际零参数；原厂group数值验收保持false。contract/native/original/verification分别归档3／3／7／28份源清单，后者含group wrapper及6个生成源。一次同目录重复归档保护拒绝，已有归档未覆盖。
- 默认group关闭的旧CW→连续统计原生回归通过；完整701项／192.641秒／0失败错误跳过，仍无RawPy，不冒充LibRaw或整机。当前C参考算子不做Bayer解混，不是原厂AF／PDAF；未补曲线或系数。
- parameter-source-1另按Z62原字节确认C26A0884参数结构、C26A08DC packed系数实参与C26A0904曲线指针槽，setter调用10239C14／10239C6A。Z72同地址函数及resource39/descriptor17偏移未在Z62验证，未照搬加载。下一步观测真实指针／provider与资源来源，再推进合法96消费、四槽取景／模式恢复；不能直接用零值推断NOR擦除或用ready掩盖输入缺口。
- [r93报告](history/2026-11-04_实施-Z62采集组数值后端与事件96合同r93-report.md)、采集组合同及能力表同步；本地r92/r93未发布，云端仍r91／a9088bf，默认r75／r69保持。未访问相机／USB／物理盘、未刷机／改AF，完整Goal继续active。

### r94/r95 参数来源更正与显式虚拟输入（2026-11-04，本地后续）

- 上轮r93为有效进展。本轮完整重读目标，沿实际参数结构追provider，使用冻结r93内核，无新QEMU构建。r94是被动观察版本，r95是独立虚拟输入／验证宿主，默认r75／r69与云端r91保持。
- 原字节明确撤回旧+58系数标签：packed系数在C26A0884+3Eh／C26A08C2，走1020C132→10208CB0；+58／C26A08DC走1020C13E→10208CF4为另一配置。曲线+80指针仍正确。旧脚本和回执冻结，当前文档附更正，r93寄存器数值模型未受影响。
- 新静态合同核对资源表118D74C0={0,11500,2C00,00270300}、ID39；1021F3E2→103DFC14→102ABBC0→102AB28A从上下文+18读资源，系数186C/18CC/192C/198C/26B0各24u32，曲线1A1C/130B。并非直接套用Z72PC／偏移。
- 被动读到C21835D4经C1861EF0发布，资源C8159500，曲线C25DAF18。候选整块缓存C8148000与staged group17有10字节差异，完整镜像假设保持false。没有把全零相等当来源证明。
- 独立marker参数文件只改资源曲线第17点的2字节为0123h，四次一致读取验证文件→资源源页→原厂缓冲→实际寄存器；系数仍0、group完成0。由此确立本实验加载路径。基线资源体来自既有合成group17零填充，不证明真实NOR擦除或恢复了标定。
- 独立reference输入改140字节，声明65点线性曲线和五套三组差分FIR；其它资源／ENDM保持。由既有132C0000参数窗口preboot加载，原固件／AF不变，运行中不写软件对象／寄存器／ready或发完成。marker SHA6c904efc…，reference SHA8deb1d24…，完整SHA见生成manifest。
- 原厂reference-1先验证13次group成功；reference-dma-1正常至8,008,828,354客体ns、group13次／832B、CPU事件96 ACK13次。保存4组DMA256B，其中216个已分类字节按实际MAIN与唯一稳定提交配方独立重算零差异；未分类字节原厂前后保持未另证。旧RAW accepted始终0，原始3成员与snapshot卡保持，进程exit0。
- 当前pattern样本0×566、08000000×15、05300000×15，另2未解析；没有跟踪AND等待返回，ready_join／inhibit仍1，预览0、LCD全黑，不把group／ACK计数当整机就绪。下一步跟踪真实等待CALL／RETURN和帧对象链，再推进四槽／readout／ISP。
- 早期origin-1在读取前QMP超时、无源发布／无参数捕获，终态exit1；image-1初始硬件频率0、终态exit0。新增clock guard只等待真实非零频率，不替代频率／时间；四项时钟及五项参数完整性专项并入710项／171.813秒／0失败错误跳过，仍无RawPy。旧QMP自发故障未被宣称修复。
- marker/reference/DMA输入窗口各归档6份源，独立复核归档22份；verification SHA9e2e7e86…，原EXE仍bad3bc34…。复查NKN ROM配置／EX读口材料，未取得真实标定／主ROM，不把PC全局或EX窗口当本资源。
- [r94/r95报告](history/2026-11-04_实施-Z62参数来源与虚拟采集组输入r94-r95-report.md)、参数合同、README和能力表同步。所有新产物在工作目录，无相机／USB／物理盘／刷写／AF修改；完整Goal继续active。本地r92–r95尚未发布，云端仍r91／a9088bf。





