# Z6II 原生场景输入与共享快门 r24

这个实验入口把C级场景输入送入QEMU的原生RAW DMA设备，再经已有近似ISP显示到原厂LCD。机身快门、回放、缩放和删除也连接到同一个C级照片后端。**JPEG仍是软件替代编码；原厂照片编码、NEF、录像、原厂AF和完整固件更新尚未完成。**

## 使用

在项目根目录双击或执行：

```bat
start-z6ii-native-scene.cmd
```

打开 <http://127.0.0.1:8681>。原厂主屏初始化通常需要约17秒客体时间，宿主等待可能是数分钟。场景和RAW输入可能早于原厂LCD就绪；初始化切换阶段若没有新鲜的已消费帧，软件拍摄会明确拒绝保存，不使用旧帧冒充新照片。

1. 场景随此配置自动启用。下方将手动对焦位置设为`0.65`并应用，可把默认测试图从模糊变清晰。焦距、光圈、快门和ISO会实际改变输入像素。
2. 使用上方机身全按／键盘S，或下方“拍摄JPEG”。两者走相同的物理输入队列；只有实际发出的按键边沿才驱动软件拍摄。HTTP排队成功不等于照片保存成功，请看后台保存回执和卡内照片数。
3. 上方播放P／下方“回放”打开C级照片；放大／缩小以及下方1/2/4/8/16倍选择使用同一按键路径。回放显示照片自身的帧号、ISO、快门、光圈和焦距。
4. 删除仅影响本配置的专用目录卡。使用“关闭模拟器”结束整个会话。下方开／关机目前只控制C级场景相机，**不代表机身电源拨杆或原厂断电流程**。

默认目录卡为`artifacts/z62-native-scene-card-r24`，与原厂SD镜像和旧r22入口分开。自己的C1.70固定布局包仍用：

```bat
start-z6ii-native-scene.cmd --firmware "Z6_2_0170 (1).bin"
```

候选健康始终未知。本轮候选验收是原C1.70包走候选加载分支，不能外推任意修改版通过；C级JPEG成功也不证明修改后的原厂编码／AF代码正确。只执行master/slave/controller，另外两个外设成员仍不执行。

## 数据路径和真实性

原有C级镜头／曝光模型 → RGB源帧 → 实验RGGB packed12 → 专用ASCII文件邮箱 → QMP短路径命令 → 原生设备完整校验 → 四槽RAM DMA → 原有完成信号 → 原固件消费及近似ISP／原厂LCD。

软件照片从**已经被原生DMA消费的同源RGB帧**编码，并记录epoch、publish-id、frame-id、采样时间、捕获请求时间及packed12载荷SHA256。它没有从原厂JPEG编码器或拍照RAW描述符取得输出，也没有宣称执行真实尼康ISP数学。JPEG源图与RAW载荷同源；它不是从RAW重新去马赛克后编码。

| 项目 | 当前含义 |
|---|---|
| RAW几何 | 固定1514×1006、stride2272，来自已有预览DMA合同；不是全分辨率照片传感器模型 |
| CFA／黑白电平 | RGGB、black64、white4095，沿用近似预览假设，未获工厂标定 |
| 时间 | 输入队列已有QEMU客体时钟，帧号按30Hz虚拟时间计算；不使用宿主耗时充当相机处理器时间 |
| 发布／消费 | 发布只更新外部输入；消费标签只在四槽DMA全部成功后更新，重复帧另计数 |
| 新鲜度 | 照片需要当前设置版本、非未来且不超过1虚拟秒的已消费帧；这是实验保护阈值，不是尼康快门时延 |
| 镜头 | C级归一化位置、50ms延迟、每虚拟秒1单位；影响像素，但没有Z镜头协议或原厂AF闭环 |
| 曝光 | 下方C级参数会影响像素；尚未跟随原厂曝光参数存储和所有机身拨轮组合。原厂OSD仍可能显示F--、不同ISO／快门值 |
| 回放 | C级目录卡播放器；原厂SD/DCIM照片生成与原厂播放器互通仍未贯通 |

AF-ON、录像、Fn等仍只具有已验证的原厂输入路径，不虚构AF／录像完成。RGB或本输入RAW不是内部PDAF统计。

## 接口与配置

继承[软件相机配置](README-Z62-SOFTWARE-CAMERA.md)中的`--software-scene`、尺寸和目录卡参数。新统一接口为：

| 接口 | 用途 |
|---|---|
| `POST /camera/event` | `{type,payload}`；key、rotate、joystick、body-mode、mode-lock、release、heartbeat，以及C级镜头／曝光／拍摄操作 |
| `GET /camera/status` | 原厂、软件相机及输入回执；不是跨设备原子快照 |
| `GET /software/status` | C级相机和已消费RAW帧标签 |
| `GET /software/frame` | 当前已消费源帧或C级回放；初始化／失步时可能返回等待错误 |
| `GET /software/file/Z62_0001.JPG` | 读卡内原JPEG并校验大小和SHA |

上下两个快门区都使用已有双段快门队列。C级保存失败会显式记录，不能杀死原厂输入工作线程；硬件操作结果未知时不会补造C照片，也不会重放控制命令。

## 验证和已知限制

- r24二进制SHA256：`dbe36d222dbfa633086f906f626968635c61d9825eaee8174480bef22a39abf2`。旧r21、失败r23、成功r23a均保留；新C设备源码和13层构建清单绑定。
- [原生文件输入测试](../../analysis/z62-camera-r24/native-file-final/report.json)覆盖四槽逐字节回读、10种坏包、失败DMA不确认、只读标签、重复、复位、预加载和默认关闭兼容性。测试未执行固件。
- 旧RAW（本地证据，未分发：`analysis/z62-camera-r24/legacy-raw.json`）和24组ADC（本地证据，未分发：`analysis/z62-camera-r24/legacy-adc.json`）在新二进制上通过。
- [原版流程](../../analysis/z62-camera-r24/live-flow-1/native-console-check.json)、[最终原版复测](../../analysis/z62-camera-r24/release-flow-final/native-console-check.json)和[候选分支](../../analysis/z62-camera-r24/candidate-flow-1/native-console-check.json)实际执行固件，经共享快门完成JPEG、回放4倍、删除及返回取景。FFmpeg独立解码，并重放校验采样RGB与原生RAW载荷SHA。
- 浏览器实点已完成手动镜头设置、拍摄、回放、4倍放大、删除；回放截图（本地证据，未分发：`analysis/z62-camera-r24/ui-qa-zoom.jpg`）和删除截图（本地证据，未分发：`analysis/z62-camera-r24/ui-qa-delete.jpg`）保留。删除后目录卡重新打开仍为空。
- 实点时发现退出回放的缩放选择值未同步，已补组件回归修正；该小修正未再次运行整套浏览器操作。关闭阶段曾出现HTTP连接中止／QMP截屏超时告警，主进程exit0且无残留QEMU；长稳和关闭提示仍需完善。
- 部分界面沿用旧宿主版本文字；构建身份以`hardware_version`、`native_scene.version`和构建清单为准。原厂电源／照片视频拨杆、触屏、肩屏完整状态、NEF、视频和AF平台仍待完成。

全量功能及里程碑见[能力清单](../CAPABILITY-COVERAGE.md)。不能从这些局部通过得出真机更新安全结论。
