# 已提交来源上的C照片工作流 r74/r75

本入口继续使用r69 QEMU和原始C1.70，照片／NEF／虚拟镜头／回放为明确的软件替代。原厂拍摄编码、全分辨率、AF和完整模式往返仍未通过。

从工作目录运行：

```powershell
start-z6ii-workspace.cmd
```

或指定独立测试卡：

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/run_z62_workspace.py --entry run_z62_committed_photo_console --software-card artifacts/my-new-photo-card --port 8688
```

所有文件物理位于工作目录，Q:只是经检查的ASCII路径别名。新入口仍沿用r71的底层host版本标签；r75是本次控件同步层，不改原厂C1.70版本字段。

## 已验证的操作

| 操作 | 实际证据 |
|---|---|
| 手动镜头0.65、两次JPEG＋NEF拍摄 | 每份保存文件绑定实际C ISP提交标签；JPEG640×424，NEF1514×1006，LibRaw逐样本摘要一致 |
| ISO100→200 | 两份实际解码RAW均值4808.789→8450.968；只是未标定软件模型内结果 |
| 回放／上一张／下一张 | 实际C目录卡与统一输入事件链路通过 |
| 2倍照片放大 | 显示JPEG与独立中心裁剪的MSE0.7858；与未缩放图MSE17938.14 |
| 两组成组删除 | JPEG／NEF同组删除，卡内照片和计入用量均归零，再返回取景 |
| 网页拍摄与状态同步 | 修复已确认输出时照片按钮仍禁用；后台焦点和ISO同步到表单，草稿保留并区别于已应用值 |
| GUI照片关闭后重开 | ISO400的JPEG＋NEF持续存在，独立读取／LibRaw摘要通过 |

以上C操作整链的实际运行无宿主附加，`unperturbed_flow_verified=true`；它不是原厂照片文件或AF验收。完整记录：API流程（本地证据，未分发：`analysis/z62-persistent-diagnostic-r74/photo-flow-1/result.json`）、字节及像素复核（本地证据，未分发：`analysis/z62-persistent-diagnostic-r74/verified-photo-and-faults-1.json`）。

实际C照片回放与已应用参数（本地证据，未分发：`analysis/z62-committed-ui-r75/photo-playback-controls.jpg`）

## 故障现场保存

r72把host-diagnostics放在临时VM目录，正常关闭会删除该目录，原始线程栈因此丢失。旧摘要和SHA不能替代原始栈，缺口见记录（本地证据，未分发：`analysis/z62-persistent-diagnostic-r74/r72-evidence-gap.json`）。

r74将故障保存到`analysis/z62-persistent-diagnostic-r74/.../faults/VM名称/`，不跟随VM scratch清理。仍只尝试一次宿主抓取、请求不重放，任何抓取尝试使功能资格false。

原生机制检查（本地证据，未分发：`analysis/z62-persistent-diagnostic-r74/native-fault-2/result.json`）只在未执行固件的自有实例中显式注入100ms宿主接收延迟，触发一个1us测试请求deadline，验证真实GDB抓栈／detach／QMP恢复及清理后原始栈留存。生产QMP默认5秒未变；这不是自发QMP超时的根因证明。

原厂全按后选择输入已到主缓存但新模式未提交的问题仍需定位。已有r64原始宿主栈仅是瞬时main-loop／GLib与RR时钟线程状态，没有证明死锁。不得通过强写ready、队列、返回值或延长原厂等待宣布解决。
