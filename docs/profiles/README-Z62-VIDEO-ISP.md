# Z62 显式软件视频 ISP 实验

r59b增加独立默认关闭的C级视频处理路径：实际原生RAW新代数→调用者指定的私有视频视图→MAIN NV12及两份WORK近似平面→三个预览输出。新／旧原生设备检查已通过；原厂55.024秒窗口中视频灰40→210及返回照片灰40实际响应通过，见[阶段报告](../history/2026-11-03_实施-Z62软件视频ISP与原厂LCD响应r59b-report.md)。统计／grid后段停止，严格恢复仍false；原厂录像编码和整机尚未验收。

## 运行验证

工作区根使用现有隔离环境。已有构建无需重建；输出文件／目录必须不存在。

```powershell
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/probe_z62_video_isp_format.py --output analysis/z62-video-isp-r59/native-new.json
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/trace_z62_video_isp_lifecycle.py --output analysis/z62-video-isp-r59/live-new --card <USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/card-r22-4096.raw --group23 <USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/group23.bin --origin-x 0 --origin-y 76 --duration 55
```

第二条命令执行原始C1.70、既有外部selector低／高场景和灰40→灰210→灰40输入；origin(0,76)是显式的软件夹具，未恢复为真实尼康ROI。运行有界，但宿主耗时明显长于客体55秒，不能当作物理FPS。卡为专用snapshot镜像，group23为显式非出厂夹具。

独立可执行文件为 r59b QEMU（本地证据，未分发：`<WORKSPACE>/.build/z62-video-isp-format-2026.11.03-r59b/runtime/qemu-system-arm.exe`），SHA256 `bdc80a5a5a5903d926f70b17b180910aa4025722eae83c68e2bb65257f796cec`。基线QEMU10.2.4未改，r53和r59二进制及其失败记录保留。全新本地复现的构建顺序：

```powershell
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/build_z62_video_isp.py --jobs 8
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/build_z62_video_isp_format.py --jobs 8
```

所有父构建及固定输入应已按项目说明准备，builder会核对父源／身份并拒绝覆盖已有工作目录。r59b是MAIN未启用第二环资格修正，未扩大WORK或未知参数范围。默认交互入口目前保持原样。

## 独立配置合同

新增device属性：

| 属性 | 默认与要求 |
|---|---|
| `nikon-z72-boot-config.z62-video-isp` | false，显式启用软件路径 |
| `nikon-z72-boot-config.z62-video-origin-x` | 未指定哨兵值，开启路径时必须明确提供[-4096,4096]内偶数 |
| `nikon-z72-boot-config.z62-video-origin-y` | 同上；不静默选ROI或改变CFA相位 |

原始命令仍需要既有preview／results和原生RAW来源配置；优先使用上面的受控运行脚本，避免漏掉继承选项。

路径只接受已捕获的1516×854／row2288视频配方、MAIN1508×846／row1520及三路已确认终端参数。源来自真实原生1514×1006／2272 RAW完成通知；在该边界复制四槽9,142,528字节到自有快照。当前要求四槽字节相同，以避免四个phase索引共享输出单元时覆盖不同图像。新输入在等待结果ACK时可替换尚未消费的输入，`video-source-coalesced`记录这种C级latest-frame策略，不能称全部帧都处理完或物理输入FIFO已恢复。

私有视图不会把guest RAW缓冲静默改成新布局。其他原厂消费者读取guest RAW时是否具有真实新布局，仍未验证；本功能不能作为原厂RAW／PDAF正确性的证明。

MAIN为实际写回的有限NV12。WORK两平面分别为线性CFA均值与有符号RB-minus-G，两者由当前图像真实计算，但不是已恢复的时间历史、降噪或PDAF语义。预览由同一MAIN数值图像再采样，未恢复尼康的完整校正、滤波、warp、噪声和色彩方程。

## 生命周期与观测

全部输入、输出RAM和canonical backing alias检查先于DMA，所有MAIN／WORK／十二NV12写完才发布既有bank1结果和命令。银行0、统计新帧、原厂ready／软件队列／超时不由该路径补写。取消撤销拥有者，完整／部分ACK保留背压，复位清理拥有者及完成状态，从引擎隔离。

只读QOM可见`video-batches`、`video-main-bytes`、`video-work-bytes`、`video-rejected`、`video-blocked`、`video-source-captures`、`video-source-coalesced`、`video-source-rejected`、`video-source-cancelled`、`video-source-bytes`、`video-source-seq`和`video-reason`。main／work字节数统计完整提交批次，不把一次中途DMA错误当作完整成功。

自有固定长度源快照与标志／计数进入VMState50/min50；派生数值缓存载入前撤销。不宣称兼容旧49状态、已验证所有迁移路径或完成QEMU＋外部场景／镜头／存储的整机快照。

## 证据与边界

- 新原生检查（本地证据，未分发：`<WORKSPACE>/analysis/z62-video-isp-r59/native-format-1.json`）：MAIN／WORK／十二预览、独立WORK oracle、来源接受后RAM修改隔离、guards、ACK／取消／复位／从引擎、六类拒绝和末尾地址失败的全部输出不变。
- 旧结果回归（本地证据，未分发：`<WORKSPACE>/analysis/z62-video-isp-r59/legacy-format-1.json`）：原photo行为及八类拒绝保持。
- r59的首轮失败、实际诊断及错误MAIN镜像条件保留在同目录。r59b接受MAIN第二环为0，WORK仍镜像；旧格式位FF010200在父模型已有有界支持，夹具统一到真实movie捕获不等于新增设备格式能力。

原厂视频OSD上的新场景响应、严格模式恢复和录像编码是不同的验收；查看当前[能力清单](../CAPABILITY-COVERAGE.md)和本阶段原厂窗口。C级软件图像处理不能保证修改固件刷入真机后不变砖。

方法参考nightglasses/z7ii-qemu固定 [0e53ea5](https://github.com/nightglasses/z7ii-qemu/tree/0e53ea5a6d4f3fc635d63c195a92e943370ac5e9) 的数据拥有者、独立DMA／完成和生命周期思路；实际地址／配方来自本工程Z62原厂观察，未使用Z7II地址平移。新代码GPL-2.0-or-later及原有作者／许可保留，Tornado NKN的PC协议／载荷线索未冒充ISP或AF。
