# Z62 软件视频ISP、MAIN／WORK DMA与原厂LCD响应：r59／r59b

日期：2026-11-03，`flavor=null`。范围见 [scope](../../analysis/z62-video-isp-r59/scope.md)，使用方法见 [实验说明](../profiles/README-Z62-VIDEO-ISP.md)。仅本地开发和离线仿真，没有设备、刷写或发布。

## 结论

已构建独立r59b QEMU并接入默认关闭的C级视频ISP路径。实际新RAW源被复制为自有快照，经显式私有视频视图生成MAIN NV12和两份WORK近似平面，再从MAIN生成三路预览；完整DMA之后才发布既有bank1结果／命令完成。新旧原生检查通过，原厂C1.70完成55.024客体秒窗口，视频模式的灰40→灰210和返回照片后的灰40均到达原厂LCD。

严格模式恢复仍为false：统计／grid后段没有持续，原厂新照片操作仍有目标等待超时。本阶段没有制造银行0完成、补写ready／软件队列或改超时。原厂录像编码存卡、PDAF／AF、全系统快照和整机没有因此验收。

这是明确的软件近似。私有视图不把guest RAW缓冲改成真实新布局；WORK是当前图像的均值与色差代理，不是原厂时间历史。实际ROI、噪声、warp、色彩方程和物理ISP等价仍未知。

## 1. 本轮实现

| 组件 | 实际行为 | 层级／边界 |
|---|---|---|
| 原生RAW拥有者 | 在实际RAW完成通知处复制四槽9,142,528字节，保留native新代数 | C级虚拟设备拥有者；当前要求四槽字节相同，避免共享phase输出覆盖不同图像 |
| 私有视频视图 | 1514×1006／2272→1516×854／2288，显式偶数origin | C；本窗口选择(0,76)，不是已恢复的尼康ROI，也不重写guest RAW |
| MAIN | 实际生成1508×846、stride1520的NV12并写到已编程普通RAM地址 | C级像素／B级有限DMA路由 |
| WORK | 两份754×423 LE16，分别是线性CFA均值与signed RB-minus-G | C；不是PDAF、原厂降噪或跨帧历史 |
| 预览 | 从同一MAIN数值图像采样到1920×1080和两路1024×576，实际十二槽写回 | C；不是完整原厂滤波／校正数学模型 |
| 完成 | 全部MAIN／WORK／预览写回后发布原有bank1结果61、命令bit8和paired1002 | B有限路由；不完成银行0或新增统计帧 |
| 重入 | 显式video opt-in下补上视频布局的preview停止解除 | 不放开未知几何或原始固件状态 |
| 状态 | 固定源快照／地址／标志／计数进入VMState50/min50，派生数值缓存载入前撤销 | 未验证整机迁移或兼容旧49 |

新属性`z62-video-isp`默认false。启用时还必须提供[-4096,4096]内的偶数`z62-video-origin-x/y`，缺失、奇数或越界拒绝启动；不会静默选光学中心或改变CFA相位。来源、配方、RAM后备、canonical backing alias和全部输出范围在首次DMA之前检查。取消撤销拥有者，完整／部分ACK保留背压，新输入等待期间的替换显式计入`video-source-coalesced`。

源代码：[数值链](../../qemu/z62-video-isp/nikon-z62-video-pixels.h)、[事务设备](../../qemu/z62-video-isp/nikon-z62-video-isp.h)、[配方资格](../../qemu/z62-video-isp/nikon-z62-video-profile.h)及[独立MAIN环修正](../../tools/z62_video_isp_format_device.py)。

事务设备源保留r59身份，修正通过独立适配层应用；当前EXE实际编译的r59b事务设备文件（本地证据，未分发：`<WORKSPACE>/.build/z62-video-isp-format-2026.11.03-r59b/source/qemu-10.2.4/hw/arm/nikon-z62-video-isp.h`）已要求MAIN第二环为零。

## 2. 首轮失败及修正

r59首次原生检查在配置资格处拒绝，未产生完成。实际诊断显示：CORE／paired数值／ports均与捕获一致，WORK第二环镜像，MAIN第二环为零。此前r55文字和r59条件误将MAIN第二环也当作镜像，这是实际设备拒绝的根因。

另有夹具差异：旧photo variant的单元54／55参数1C是FF010200，当前movie捕获为FF010000。父r47b早已对这两种值有界支持，所以不能将其当作本次设备拒绝根因或新增格式能力。native夹具现统一为同一次r57 movie的完整三份参数。

r59 EXE和native-1／native-2失败、native-diagnostic-1原始读回全部保留。r59b只将MAIN未启用第二环限定为零，WORK仍必须镜像；非零MAIN第二环有独立拒绝测试。没有把未知值一并放开。旧r55镜像描述已明确纠正。

## 3. 构建与身份

| 项目 | 已核验 |
|---|---|
| QEMU基线 | 10.2.4，Windows x64，既有MSYS2／UCRT64工具链 |
| 冻结r53 | SHA256 `68c33032d87c67cb4996950ea9fd3b15b9ced88b12924116696a289d99fb1581`，保留 |
| r59构建 | DC13920 exit0，497.79宿主秒；EXE SHA `d815e9ca58b33563064de04c591c185190b7dab687ca5ce47ccaa426ebc7634d`，含首轮错误资格，保留 |
| r59b构建 | DC39032 exit0，429.51宿主秒，20层源／生成树／EXE／DLL身份链通过 |
| 当前r59b EXE | qemu-system-arm.exe（本地证据，未分发：`<WORKSPACE>/.build/z62-video-isp-format-2026.11.03-r59b/runtime/qemu-system-arm.exe`） |
| EXE SHA256 | `bdc80a5a5a5903d926f70b17b180910aa4025722eae83c68e2bb65257f796cec` |
| 原master含CRC | `bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4`，未改 |

默认交互入口和r48／r52／r53不变；r59与r59b是单独工作目录。父manifest记录的是继承阶段，当前配方和VMState以顶层r59b清单为准。没有修改未理解的原厂版本字段。

## 4. 实际执行的检查

| 检查 | 结果与覆盖 |
|---|---|
| C数值先红后绿 | 初版测试自身编译错误保留；修正后functional-red真实拒绝缺失算子，profile-red真实拒绝新单元；当前严格GCC编译／执行exit0 |
| C像素／数据 | 字面量红／绿／蓝／白，完整MAIN和WORK数值、预览源自MAIN、输入自有快照、非法origin／短输入不破坏旧数据、缓存随输入变化及参数不改 |
| Python专项 | 4项先红后绿，origin必须显式／偶数／有界、默认不启用、重复属性拒绝、父源身份改变拒绝 |
| 最新全量 | DC15036，582项／275.790秒，exit0。完整stdout未单独保存，计数／耗时来自当次工具输出 |
| 原r53 native对照 | video请求无完成、guard保持，证明默认旧路径没有该新能力 |
| 新r59b native | DC52332，10.48秒、exit0：native-format-1.json（本地证据，未分发：`<WORKSPACE>/analysis/z62-video-isp-r59/native-format-1.json`）；实际MAIN／WORK／十二预览、所有WORK字节独立oracle、来源接受后RAM变动隔离、无guest callback改写、ACK／部分ACK、取消需新RAW、从引擎／银行0隔离、只读计数、reset |
| 六类拒绝 | opaque改变、末尾未映射输出、输出别名、WORK环不匹配、未启用MAIN环非零、错误结果参数；末尾地址拒绝核对全部输出字节未改 |
| 旧结果回归 | DC37452，4.66秒、exit0：legacy-format-1.json（本地证据，未分发：`<WORKSPACE>/analysis/z62-video-isp-r59/legacy-format-1.json`）；旧十二NV12、W1C／mask／背压／取消／复位及八类拒绝保持 |

C当前数值记录为 pixels-current/report.json（本地证据，未分发：`<WORKSPACE>/analysis/z62-video-isp-r59/pixels-current/report.json`），包含实际使用的旧profile依赖SHA。独立C测试使用workspace profile，QEMU生成树还包含父r47b的bit9有限格式支持；两者不混称同一文件，实际设备行为由相同r59b EXE的native和原厂窗口另证。

## 5. 原厂55秒和新场景响应

DC44020实际完成55.024客体秒／358次停顿，921.55宿主秒、exit0、正常detach和关闭。27份生产者样本均known=true，8份三阶段配置，读取错误0，运行源未变。

| 观察 | 客体时刻 | 来源／计数 | 实际像素与原厂状态 |
|---|---:|---|---|
| 视频初始灰40 | 35.465 | source ID1／epoch89，video批次9 | 四RAW、十二NV12和四LCD区域匹配40，端口高度1080／576／576，ready3／输入许可0 |
| 视频改灰210 | 35.465发布，37.558观察 | source ID2、frame1063、time35465000000ns，video批次69 | RAW／NV12／LCD匹配210，四LCD中位数均210，ready3／输入许可0 |
| 返回照片改灰40 | 47.264发布，49.439观察 | source ID3、frame1417、time47264000000ns | RAW／NV12／LCD匹配40，端口高度1080／682／680，ready3／输入许可0 |

两张视频图已目视复核；原厂OSD由固件绘制，背景来自新C路径实际NV12：

视频灰40（本地证据，未分发：`<WORKSPACE>/analysis/z62-video-isp-r59/live-1/video-before-0.png`）

视频更新灰210（本地证据，未分发：`<WORKSPACE>/analysis/z62-video-isp-r59/live-1/video-after-1.png`）

OSD的1080／60只是原厂当前设置和显示，不证明物理60fps、原厂编码或录制文件成功。红色时钟图标仍存在，未作为已修复项。像素核对是四个RAW片段、十二个Y／UV片段和四块LCD区域，并非对全部帧所有像素逐字节比较或真实色彩校准。

最后样本53.666秒：video批次151，完整提交MAIN 1,165,043,520字节、WORK 776,695,680字节，video拒绝0；来源cohort捕获279、替换125、取消3、待处理0。该稳定尾段满足279=151+125+3，不把coalesced／cancelled输入写成全部帧成功处理，也不把四槽同一图像写成四个独立曝光。

同一末样本RAW accepted1403、RAW stream1394、统计来源768、grid414、preview1026、preview拒绝0、retained-jobs1。统计／grid后段静止，所以r49要求双流水持续增长的恢复仍false。原目标等待按操作区分为初始0204成功5次、1d09成功146／失败5、新照片0203失败10，末尾1个未返回；成功返回含停止／收尾路径，不能写成146次新视频完成。

## 6. 证据重放、复现及未完成项

DC50792证据复核exit0，三份完整输入包可重放，三份像素记录从保存RAW／NV12／PNG重算一致，构建／源码／证据SHA及原严格恢复false保持。核心结果：video-isp-lifecycle.json（本地证据，未分发：`<WORKSPACE>/analysis/z62-video-isp-r59/live-1/video-isp-lifecycle.json`）、完整stdout（本地证据，未分发：`<WORKSPACE>/analysis/z62-video-isp-r59/live-1-stdout.txt`）、verified-artifacts.json（本地证据，未分发：`<WORKSPACE>/analysis/z62-video-isp-r59/verified-artifacts.json`）。

复现命令见实验说明；证据复核可单独运行，输出须不存在：

```powershell
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/verify_z62_video_isp_evidence.py --case analysis/z62-video-isp-r59/live-1 --output analysis/z62-video-isp-r59/verified-artifacts-new.json
```

后续优先补齐统计／grid真正的新来源和正确引擎／使能切换，再做严格模式恢复、长稳及交互入口接入。当前没有原厂JPEG／NEF／录像保存闭环、音频、PDAF／AF多帧闭环或全系统快照验收。既有C级JPEG／NEF／静音MP4另有自己的范围，不由这次视频预览成功外推。模拟器不能保证真机修改固件更新不变砖。

## 7. Evidence → Finding → Path 与来源

| E-id | source_ref | repro_command | content_hash |
|---|---|---|---|
| E-imports | 裸ARM C1.70 master，无PE／ELF动态导入表 | 项目载荷身份与原厂运行脚本 | 原master SHA如上；基址10020000、原字节未改 |
| E1 | 两份build manifest、C红／绿／当前和native／legacy／失败诊断 | README中的build／native命令 | 顶层manifest与verified-artifacts的逐文件SHA |
| E2 | live-1完整trace／pipeline／inputs／lifecycle、来源发布／PNG | README中原厂55秒命令 | verified-artifacts的evidence_sha256 |
| E3 | 新源、绑定适配器／头与证据复核代码 | 本文复核命令 | verified-artifacts的source_sha256和EXE SHA |

F1，`severity=n/a_re`，`evidence_ids=E1/E3`，高置信度，C数值与实际DMA／生命周期已验证。F2，`evidence_ids=E2/E3`，高置信度，原厂视频LCD新灰度响应与返回照片响应通过。F3，同一证据，严格恢复false、真实guest RAW转换／WORK物理语义／完整视频编码未知或未完成，限制保留。

P1，`path_type=callflow`：实际native RAW完成→自有四槽快照→显式C视图→MAIN／WORK数值→预览源自MAIN→实际所有DMA→既有bank1完成→原厂LCD。P2：取消／布局改变撤销拥有者，ACK只解除背压，不创造source代数或银行0结果。

开发时间线：C缺失算子与新单元先红后绿→独立r59构建→新native资格拒绝／旧回归通过→实际配置诊断与MAIN环根因→保留r59、构建r59b→新旧native通过→582项全量终态→原厂场景窗口→输入／像素重放复核。

主要参考：[nightglasses/z7ii-qemu固定0e53ea5](https://github.com/nightglasses/z7ii-qemu/tree/0e53ea5a6d4f3fc635d63c195a92e943370ac5e9) 的实际数据生产、拥有者和完成分离／生命周期方法；实际地址与配方来自本工程Z62观察，不是Z7II VA平移。QEMU CPU／TCG是官方实现，本阶段没有自研或识别真实E6硅内核。新C源GPL-2.0-or-later及原有作者／许可保留，Tornado NKN仅作既有PC协议／载荷线索，没有用它代替AF或扩展到维修操作。
