# r79/r80/r81/r82 无控制输入对照与事件参数边界

- auth：本线程完整目标授权的本地开发、离线固件分析及 QEMU 仿真。
- in_scope：冻结 r69 内核、r76 独立控制台；新 VM 的无快门对照、原厂准备帧／等待、已有统计设备计数、原厂通知调用及原始指令核对。
- network_profile：仅 127.0.0.1 的本任务控制台及经 PID／EXE／命令行确认的 GDB 端点；本轮没有外部网络访问。
- out_of_scope：相机、USB、WPD、物理盘、刷写、GitHub 发布和修改 AF。
- storage：所有新增产物及 TEMP/TMP 在工作目录；Q: 为同一物理目录的 ASCII 别名。
- invariant：无控制输入、无软件标志／返回值／队列写入、无 IRQ 注入、无原厂等待修改。HMP 仅白名单 qom-get；GDB 仅观察断点、单步和读取。
- qualification：有调试器时序扰动，功能资格始终 false；不能把对象首字当成已证实的内核 flags，不能把通知调用点命中当成内核置位成功。
