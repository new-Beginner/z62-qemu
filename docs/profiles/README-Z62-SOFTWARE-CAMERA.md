# Z6II 软件成像实验 r22

在同一个 r21 QEMU 会话中，保留原厂界面和机身输入，并增加独立的场景、虚拟镜头、JPEG、目录卡、回放和删除窗口。新增成像功能属于 **C：软件替代**，不执行尼康拍照编码算法，不代表修改固件的拍摄功能已经通过验证。NEF、录像和原厂AF闭环未完成。

本页保留r22独立窗口范围。新增[r24入口](README-Z62-NATIVE-SCENE.md)已连接原生RAW帧与部分共享机身事件；不能把本页的旧“尚未连接”描述当作r24状态。

## 启动与拍摄

在项目根目录双击或执行：

```bat
start-z6ii-software-camera.cmd
```

打开 <http://127.0.0.1:8680>。上方仍是原厂固件画面和原来的按键；下方“软件成像实验”使用独立软件后端。默认入口 `start-z6ii-qemu.cmd` 保持原有配置。

1. 等待 QEMU 启动，在下方点击“开机”。
2. 将对焦位置设为 `0.65`，点击“应用镜头设置”，等待实际位置达到目标。默认测试图为单平面场景，深度参数为0.65。
3. 调整焦距、光圈、快门或ISO并应用，观察像素变化。
4. 点击“拍摄 JPEG”，再点击“回放”。可以选择上一张、下一张及1/2/4/8/16倍中央放大。
5. “下载当前照片”读取卡内原文件；“删除当前照片”删除所选软件照片。
6. 下方“关机”关闭软件相机；页面上方“关闭模拟器”结束整个会话并释放卡目录锁。

默认卡位于 `artifacts/z62-software-card-r22`。程序只创建新的专用目录或打开有本项目清单标记的目录，拒绝其他既有目录、符号链接、重解析点、网络／设备路径和并发占用。它与原厂虚拟SD镜像分开，**不是供固件挂载的FAT卡**。

加载候选固件仍使用同一参数：

```bat
start-z6ii-software-camera.cmd --firmware "Z6_2_0170 (1).bin"
```

支持范围仍为C1.70固定布局的三个可执行成员，候选健康保持未知。下方软件照片由软件模型生成，不能用于证明候选中的JPEG、ISP或AF修改正确。新配置的原版及候选加载分支均已完成HTTP软件拍摄流程；本轮候选测试使用原C1.70包走候选分支，不外推为任意修改版已经通过。

## 选择输入和卡

| 参数 | 默认 | 含义 |
|---|---|---|
| `--software-scene` | 内置测试图 | 本地普通图像文件；解码为RGB后作为单平面场景，最多2400万源像素 |
| `--software-card` | `artifacts/z62-software-card-r22` | 新建或重新打开本项目的专用目录卡 |
| `--software-no-card` | 关闭 | 启用无卡配置，拍摄返回 `no_card` |
| `--software-width` | 640 | 输出宽度，64～4096 |
| `--software-height` | 424 | 输出高度，64～4096；总像素不超过800万 |

新目录卡的容量模型默认256MiB，只计算已提交JPEG的载荷字节，不模拟FAT开销、SD总线或实际闪存时序。单卡编号为 `Z62_0001.JPG` 至 `Z62_9999.JPG`，删除后不回退编号。卡清单和JPEG持久保存；异常中断留下的锁或目录不一致会明确报错，不自动覆盖、清除或宣称恢复成功。

## 时间、镜头和图像的范围

- 所有软件事件从QEMU已有客体时钟读取时间，转换为整数纳秒。读时钟失败会终止该操作，不改用宿主时间、不伪造拍摄成功。
- 软件取景和照片使用同一 `frame_id=floor(virtual_time_ns*30/1e9)`；重复相同初态、场景及时间可重现像素。这个编号尚未与QEMU原厂RAW描述符／DMA帧绑定。
- 每个新QEMU运行目录形成独立 `clock_epoch`。重启QEMU后软件相机回到关机状态，镜头与曝光初始化，已经提交的卡文件保留。这不是整机快照恢复。
- 镜头焦距24～120mm、光圈1.8～16、对焦位置0～1；手动命令延迟50ms，移动速度每虚拟秒1单位。以上为**未校准的实验参数**，不是Z镜头协议或实测机械规格。
- 场景按焦距裁切，按对焦误差及光圈施加单平面高斯模糊，按快门、ISO、光圈和曝光补偿计算线性增益。源图的最宽视场定义为24mm。没有真实光学PSF、景深分层、畸变、运动模糊、传感器噪声、测光或尼康颜色校准。
- JPEG由Pillow编码，EXIF描述及卡清单记录C层级、场景身份、帧号、虚拟时间、运行epoch、镜头／曝光状态和编码前像素哈希。不是NEF，也没有通过改扩展名提供RAW。

下方事件不会自动改动上方固件曝光参数，也不会把原厂全按输入当作照片保存成功。两条路径的场景／传感器和统一机身事件桥仍是后续工作。

## 复现验证

依赖Python3.12、项目 `requirements.txt` 中的NumPy与Pillow。独立解码验收另外需要PATH中的FFmpeg。

```bat
python -X utf8 -B -m unittest discover -s tests -p test_z62_software_camera.py -v
python -X utf8 -B -O -m unittest discover -s tests -p test_z62_software_camera.py -v
python -X utf8 -B -m unittest discover -s tests -p test_z62_software_console.py -v
python -X utf8 -B tools/probe_z62_software_console.py --output analysis/z62-camera-r22/software-local-check
```

最后一个输出目录必须不存在。工具实际启动QEMU，通过HTTP完成镜头动作、JPEG拍摄／下载、回放放大、第二张拍摄、删除及关机；用FFmpeg独立解码并与拍摄时场景比对，正常结束后重新打开卡验证持久内容。记录不会被重复运行覆盖。

本轮证据在 software-http-1/software-check.json（本地证据，未分发：`analysis/z62-camera-r22/software-http-1/software-check.json`）：640×424 JPEG独立解码得到814080个RGB字节，像素均方误差1.473334316037736；回放放大不修改卡内原图，第二张删除后首张在正常关机重开时保持一致。已查看实际照片和放大图。浏览器工具无法附着WebView，**实际网页点击及布局验收仍待完成**。

候选分支软件流程（本地证据，未分发：`analysis/z62-camera-r22/software-candidate-http-1/software-check.json`）也正常结束，保持候选健康未知。全量回归352项通过（216.891秒），原始输出见 unittest.log（本地证据，未分发：`analysis/z62-camera-r22/unittest.log`）。JavaScript通过 `node --check tools/assets/z62-software-camera.js` 语法检查；语法检查不替代网页实点。

## HTTP接口

| 接口 | 行为 | 边界 |
|---|---|---|
| `GET /software/status` | 读取软件相机、镜头、曝光、照片目录及客体时间 | 时钟不可用时报错 |
| `GET /software/frame` | 输出当前取景／回放的显示JPEG | 显示编码，不写卡 |
| `GET /software/file/Z62_0001.JPG` | 读取已提交照片并核对大小／哈希 | 不接受任意路径 |
| `POST /software/event` | 统一软件事件入口 | 必须是显式type/payload对象 |

请求示例：

```json
{"type":"lens","payload":{"focus_target":0.65,"focal_length_mm":35,"aperture":4}}
```

支持power、lens、exposure、mode、shutter、playback、zoom、delete。mode可以选择photo/video，但录像功能未实现，record事件会拒绝。所有功能状态来自后端；软件模式不代表固件照片／视频拨杆已接通。

全量覆盖和剩余里程碑见 [能力清单](../CAPABILITY-COVERAGE.md)。
