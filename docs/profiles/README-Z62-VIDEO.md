# Z6II 软件录像配置 r26b

使用同一 QEMU 会话的客体时间、已消费场景帧及实际录像键边沿，生成可解码的 MP4，存入独立虚拟卡并回放／导出。**这是 C 级宿主编码；默认 640×424、可变帧间隔、无音频，不是原厂视频编码、全分辨率传感器或完整相机验收。** 初版RGB录像出现浏览器紫绿偏色，r26b改为通用H.264/yuv420p/CRF18，已重新验证实际流程、独立解码误差与浏览器正确颜色；旧RGB结果仅保留为历史证据。

后续独立 [r27异步入口](README-Z62-ASYNC-VIDEO.md)已实现后台编码／审计、轻量状态、取消和退出确认，端口8684；下文保留r26b同步入口及其原有边界，不把新入口的验收追溯为旧入口已修复。

## 准备与启动

新视频依赖放在独立环境中，不修改全局 Python：

```powershell
python -m venv --system-site-packages .build/tools/video-r26
& .build/tools/video-r26/Scripts/python.exe -m pip install -r requirements-video.txt
```

项目已有 NumPy／Pillow 等依赖需按 `requirements.txt` 准备。还需 PATH 中有独立的 FFmpeg 和 FFprobe。本轮使用 PyAV **19.0.2**（其 libavcodec 为63.1.102）编码，系统 FFmpeg／FFprobe **8.1.1**（libavcodec62.28.101）独立解码；wheel来源、版本及SHA见安装记录（本地证据，未分发：`artifacts/video-codec-r26-install.json`）。生产模块会记录实际库版本。

运行：

```bat
start-z6ii-video.cmd
```

打开 <http://127.0.0.1:8683>。CMD优先选择上述隔离环境；未准备环境时，界面明确显示录像后端不可用。默认目录卡为 `artifacts/z62-video-card-r26`，与r25照片卡和原厂SD镜像分开。原厂LCD初始化仍可能需要数分钟宿主时间。

1. 将手动对焦设为 `0.65` 并应用，或使用自己的场景与镜头设置。
2. 把“软件模式”切到“视频”，点击“开始录像”。上方录像键／键盘V也驱动同一C后端，开始和停止都经过实际GPIO输入边沿。
3. 可以在录制中改变软件曝光和镜头参数，变化会进入后续实际图像。
4. 点击“停止并保存”，等待“视频已保存”回执。当前版本在编码和审计时可能暂时阻塞交互；不要因读取超时重复发送停止命令。
5. 点击回放，使用原生视频控件播放、暂停或定位；“下载当前视频”取得实际MP4。照片功能仍可使用JPEG、NEF与JPEG＋NEF。
6. 删除视频会同时删除其JPEG封面。关闭模拟器保留已提交文件；录制中关闭或取消会丢弃尚未提交的临时录像。

软件模式选择尚未接入原厂照片／视频拨杆。没有原厂AF、镜头通信、视频音频、原厂曝光参数联动或真实刷写安全保证。

## 数据与时间合同

| 内容 | 当前实现 |
|---|---|
| 帧来源 | r24已被四槽DMA消费的同源RGB；不是从原厂视频编码器获取码流 |
| 身份 | 校验C来源、VM epoch、帧号、RGB SHA256及重构packed12 RAW SHA256 |
| 连续采集 | 按观察到的唯一publication录入；重复消费不伪装成新帧，不补造遗漏图像 |
| 时间戳 | PTS来自源帧的客体采样标签；从首个有效源帧开始，以1微秒精度保存可变间隔 |
| 停止边界 | 停止时间是排他边界；正好采样在STOP时刻的帧没有正持续时间，不编码进去 |
| 封装 | MP4、libx264/yuv420p/CRF18、真实样本持续时间、faststart，无音频；属于有损色度采样／压缩 |
| 独立验证 | FFprobe检查格式、尺寸、全部PTS、持续时间和单一视频流；FFmpeg逐帧解码，保留源RGB哈希与解码RGB哈希，另核对逐帧MSE |
| 来源重放 | 默认测试图可逐帧重建，与编码图像及已确认RAW载荷核对；外部场景需提供原图 |
| 资源上限 | 60客体秒、1800个唯一源帧、256MiB PNG临时缓冲、2GiB完整解码数据；超过上限会中止未提交录像 |

记录请求到首个实际源帧之间可能有启动间隔。文件时长为首个源帧至停止边界，按微秒量化；不以宿主编码耗时当作影片时间，也不把可变间隔录像声称为固定30fps。当前不是实时性能或实机编码耗时模型。

## v3媒体卡

新格式 `Z62-QEMU-video-card-C-v3` 复用专用目录、文件名、锁、原子清单和SHA校验，保存照片与视频的混合列表。照片和视频共享递增编号；一段视频的MP4与首帧JPEG封面作为一组提交和删除。卡满、提交失败不会留下可见的半份媒体，也不会消耗未提交编号。

不会自动升级旧v1／v2卡，传入旧卡会拒绝。目录卡不由原厂固件挂载，不代表原厂SD/DCIM、录像编码或播放器互通。容量按媒体载荷计量，临时缓冲上限另行计算。

## 复现与导出

实际原版／候选加载分支的QEMU验证：

```powershell
& .build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/probe_z62_video_console.py --output analysis/my-new-video-flow
& .build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/probe_z62_video_console.py --firmware "Z6_2_0170 (1).bin" --output analysis/my-new-candidate-video-flow
```

两个目录都必须尚不存在。探测器等待原厂LCD预览，设置场景，实际经录像键开始／停止，改变曝光，逐帧解码并重放源图及RAW标签，验证回放、成组删除和关机重开空卡。候选分支本轮使用原包，健康状态始终未知，不能外推任意修改包的原厂录像正确。

正在运行的r26配置也可导出已保存视频，过程中不修改卡：

```powershell
& .build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/export_z62_video.py --url http://127.0.0.1:8683 --output analysis/my-new-video-export
```

外部图像场景可另加 `--scene 原场景图像路径` 进行完整来源重放。没有该图像时仍会审计码流，但不声称完成外部场景重放。

本轮兼容原版流程（本地证据，未分发：`analysis/z62-video-r26/compat-live-1/video-check.json`）、兼容候选分支（本地证据，未分发：`analysis/z62-video-r26/compat-candidate-1/video-check.json`）及网页203帧导出（本地证据，未分发：`analysis/z62-video-r26/compat-ui-export-1/export.json`）保留实际结果。网页样本包含ISO100→200变化，640×424、203帧、7.479354秒；全部源帧重放与时间戳匹配，最大解码RGB MSE约3.26，浏览器实际播放到结尾且颜色正常。逐帧MSE上限1000是C实验的拒绝策略，不能解释为尼康画质指标；有损输出不声称RGB逐字节一致。

修正版隔离环境下415项回归通过／176.038秒（本地证据，未分发：`analysis/z62-video-r26/regression-compat.json`），[正式报告](../history/2026-11-01_实施-Z62软件录像与混合媒体卡r26b-report.md)保留边界、旧失败及未完成项。

全量检查应使用视频环境：

```powershell
$env:PI_SCRATCH_DIR='D:/Z62-QEMU-runtime/sessions'
$env:TEMP=$env:PI_SCRATCH_DIR
$env:TMP=$env:PI_SCRATCH_DIR
& .build/tools/video-r26/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -v
```

临时根目录应事先存在并有足够空间，上述变量只作用于本次进程。普通Python未安装PyAV时，视频专项会明确跳过；那种结果不能算视频测试通过。旧入口、固件、r24设备及其二进制保持原版本，更多边界见[能力表](../CAPABILITY-COVERAGE.md)。

## 当前待完善处

较长片段停止后，编码与审计仍在输入线程持锁执行，可能让界面／监控读取超时；应继续改为可观测的异步完成。当前最终保存结果已有独立验证，但不能因此称交互流畅或长稳通过。关闭期间的HTTP中止、旧原厂就绪提示、音频、全分辨率／原厂视频、完整照片视频拨杆及整机恢复也仍未完成。
