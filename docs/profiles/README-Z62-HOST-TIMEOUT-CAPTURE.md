# QMP超时的宿主线程诊断 r63b

此入口用于保全真实QMP超时时的QEMU主机线程栈。它复用r62内核和RAW停止选项，不改原厂算法／ready／队列／完成／等待或超时。宿主调试器会暂停并扰动QEMU；发生附加的窗口不作为功能恢复验收。

## 已验证的工具边界

| 检查 | 结果 |
|---|---|
| 所属检查 | 不同PID或已退出对象会在附加前拒绝；只接受保留的Popen实例及匹配的PID／路径／EXE SHA |
| native-1 | attach／detach及之后QMP机械检查通过，但中文运行库路径导致GDB库XML解析失败、栈缺符号；不能用于归因 |
| native-2 | 逐文件校验的ASCII EXE＋8份DLL副本，库XML正常、QEMU／MTTCG线程符号可解析；detach后QMP响应，原生进程已关闭 |
| 全量Python | 596项／171.663秒／exit0（工具输出摘要，无独立完整stdout） |

工具为本机`D:/Straberry-tex/c/bin/gdb.exe`，GDB14.2 x86_64 MinGW。SHA256为`e14d000a4fb0bbe5affc9ea38e8a66fd182cba5f3980de623cac9c20fd954090`。没有安装新依赖。native-2日志为`analysis/z62-qmp-host-r63/native-2/host/host-gdb.txt`，SHA256 `3e604e31c7f45a6cccaef655f298e7d6da77efaaf1d82ac99807deee44b251cc`。

## 运行

在工程根目录PowerShell执行，输出目录必须不存在：

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/probe_z62_host_timeout_capture.py --output 'analysis/my-new-native-host-capture'
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/trace_z62_raw_stop_host_debug.py --output 'analysis/my-new-host-timeout-window' --card '<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/card-r22-4096.raw' --group23 '<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/group23.bin' --duration 55
```

原构建EXE及DLL不修改；仅把manifest中逐项核对SHA的成员复制到本任务独占ASCII临时目录，保留逻辑构建路径、实际执行命令、复制成员SHA。符号副本与实际运行EXE字节相同。专用虚拟卡继续snapshot，不访问相机。

## 超时抓取与结果

沿用既有观察超时策略及连续失败上限，不重放任何控制。第一次真实QMP观察超时后，核对snapshot闭包中的本任务Machine／Popen，再调用本机GDB，最多一次。GDB使用`-nx -nh`、关闭自动加载及debuginfod网络，`thread apply all bt 24`限栈深，25秒有界并显式detach。若自身工具失败，记录失败；不把缺失栈或未知帧补成有效结果。

若自有console文件存在，额外保存最多末尾2MiB；不可用会明确记录。`host-timeout-1/capture.json`保存实际附加、解析质量、detach、目标是否存活以及日志SHA。无超时时不会产生该目录。`host-timeout-lifecycle.json`另保存完整观察是否完成、是否满足功能验收资格及原有严格恢复／场景响应标志。

`completed_capture=true`仅表示取得有QEMU符号的有界栈并成功分离；不能据此判定QMP根因。`functional_acceptance_eligible=false`时，即使后续画面或严格恢复标志变化，也不能当作正式功能验收。新ASCII路径本身也不证明路径编码造成了原QMP故障，需要真实超时现场和进一步对照。

当前目标仍是完整相机模拟与后续原厂AF实验平台。此工具只改善失效现场保存，不验收物理时序、原厂媒体、镜头／AF、整机快照或实机更新安全。

本次[r63b窗口终态](../history/2026-11-03_验证-Z62停止后新来源与宿主观察r63-report.md)：55.117计数器秒正常结束，零QMP超时，所以宿主抓取未触发。该配置的数据可作功能结果判断，但严格恢复／新视频／返回照片新场景均false。没有取得真实超时栈，不能以此宣布QMP根因已修复。
