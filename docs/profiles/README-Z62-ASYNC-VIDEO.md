# Z6II 异步软件录像 r27

在冻结 r24 QEMU 上使用独立后台进程完成 r26b 软件录像的编码、审计和存卡，停止录像后继续处理取景、镜头、曝光及状态读取。**这是 C 级替代链路：640×424、H.264/yuv420p/CRF18、可变帧间隔、无音频。原厂视频编码、完整相机和真机更新安全仍未完成。**

## 启动与操作

沿用 [r26b 的隔离视频环境与依赖](README-Z62-VIDEO.md)，运行：

```bat
start-z6ii-async-video.cmd
```

打开 <http://127.0.0.1:8684>。默认专用目录卡为 `artifacts/z62-async-video-card-r27`。旧入口、旧卡和硬件基线保持独立；不自动升级 v1／v2 卡。

1. 等待原厂 LCD 预览，按需设置软件镜头和曝光；测试图的清晰对焦位置为 `0.65`。
2. 将“软件模式”设为“视频”，点击开始。录像键或键盘 V 也经过 GPIO29 边沿驱动同一后端。
3. 点击“停止并保存”一次。后台显示准备帧数、实际阶段和**宿主等待时间**；该时间不是影片时长或相机处理耗时。
4. 后台工作时可继续查看取景、改变软件曝光和镜头。重复录像、拍照和切换模式会拒绝；这些后续设置不会改写已冻结的录像来源。
5. 等待“视频已保存”后回放或下载。后台完成前可取消；提交清单已经开始时需等待实际结果，不能声称取消了已开始的提交。
6. “关闭模拟器”会先处理后台退出，再清理 VM；删除一段视频会成组删除 MP4 和封面。成功保存的文件在关闭后保留。

结果未知的输入操作不自动重发。若读取超时，先读取实际状态，避免再次发送开始／停止。

## 保存与退出合同

| 环节 | r27 行为 |
|---|---|
| 源与时间 | 沿用已被原生四槽 DMA 消费的同源 RGB、RAW SHA、epoch 和客体采样时间；STOP 为排他边界 |
| 后台进程 | 专用 worker 和监督线程；Windows Job Object 管理其子孙进程，按持有的句柄取消 |
| 真正完成 | 必须观察进程退出码 0，再核对代码／任务身份、媒体 SHA、来源与时间及审计合同，最后成功提交卡清单 |
| 假结果拒绝 | `result.json`、进度或 `validated:true` 本身都不能证明成功；worker 仍存活时不发布终态 |
| 虚拟卡 | v3 格式兼容；媒体审计移到卡锁之外，仅原子提交使用短锁；MP4 与封面共同发布 |
| 轻量轮询 | `/software/status` 返回帧数和紧凑条目；`/software/item/<name>` 显式读取完整逐帧元数据 |
| 失败与取消 | 卡满、非零退出、超时、错来源和损坏媒体不落卡；确认实际退出后才显示取消完成 |
| 诊断 | 每个任务保存独立 `runs/video-jobs/video-job-*` 日志；失败保留现场，成功清理重媒体副本 |
| 文件竞争 | 自有 JSON 的原子替换遇到 Windows 临时共享冲突时最多退避 1 秒；持续失败仍报错，不重放相机控制 |

2026-11-03补充：监督进程读取`progress.json`也可能遇到Windows共享冲突。宿主job版本`2026.11.03-async-video-job-r60-progress`在此时保留最后一次有效进度，将错误保存在状态的`progress_read_error`中，下一次既有轮询再读；成功读取后清除该错误。它不改worker超时，不把进度当保存凭据；坏schema仍拒绝，实际退出／结果／哈希／来源和卡提交检查保持。真实CreateFileW独占锁的红绿复现和修正后589项全量通过记录见执行记录（本地证据，未分发：`analysis/z62-statistics-observe-r60/timeline.md`）。此补充没有重做整套浏览器／实机验收。

后台 worker 默认 180 宿主秒超时。录像仍受 60 客体秒／1800 帧／256 MiB 源缓冲等 r26b 上限约束；本轮没有验收完整 60 秒录像或长稳性能。

## 复现与导出

以下探测器会启动真实 QEMU。输出目录必须尚不存在：

```powershell
& .build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/probe_z62_async_video_console.py --scenario encode --output analysis/my-new-async-encode
& .build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/probe_z62_async_video_console.py --scenario cancel --output analysis/my-new-async-cancel
& .build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/probe_z62_async_video_console.py --scenario close --output analysis/my-new-async-close
```

候选加载测试在同一命令添加 `--firmware "Z6_2_0170 (1).bin"`，将路径换成候选包。当前验收使用原包走候选分支，候选健康状态仍为 unknown。

对正在运行的 r27 只读导出并重放来源：

```powershell
& .build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/export_z62_async_video.py --url http://127.0.0.1:8684 --output analysis/my-new-async-export
```

外部图像场景需另加 `--scene 原图路径` 才能完成来源重放。单独运行测试使用隔离视频 Python，命令和临时目录要求见 [r26b 说明](README-Z62-VIDEO.md)。普通 Python 缺少 PyAV 时的跳过不算视频验收。

## 已验收范围

最终源码的候选分支流程为 124 帧；网页样本为 **267 帧／11.031006 秒**，全部源重放通过，浏览器能播放到结尾且无解码错误。录制时 ISO100／200 分别为 205／62 帧，停止后设置的 ISO400 没有混入成片。后台阶段曝光设置仍可响应；删除、关闭后重新打开专用卡为空，指定会话无残留进程。

本阶段全量回归记录为 438 项通过、零失败／错误／跳过；摘要由当次工具输出转录，未保存完整全量日志，见 回归摘要（本地证据，未分发：`analysis/z62-video-r27/regression.json`）。实际结果及版本边界见 [阶段报告](../history/2026-11-01_实施-Z62异步录像与可观测后台r27-report.md)与 验收清单（本地证据，未分发：`analysis/z62-video-r27/verified-artifacts.json`）。

原厂照片／录像、音频、全分辨率输入、照片视频拨杆、镜头协议、AF、完整曝光绑定和整机恢复仍缺。旧页面就绪提示、媒体删除用词、QMP／HTTP 超时及长期稳定性也没有因本轮异步录像验收而全部解决。完整覆盖见 [能力表](../CAPABILITY-COVERAGE.md)。
