# r68 r66宿主失联诊断范围

auth：延续完整Goal的本地开发、仿真和故障观测授权。in_scope：固定r66 EXE及全部DLL的逐文件相同ASCII运行副本、原厂同一55秒三阶段场景、首次QMP超时的自有Popen宿主GDB栈，以及本观察器自有子进程的只读CPU／内存／句柄／线程采样。network_profile：仅localhost实验通信，无真实相机、USB、WPD、物理盘或GitHub发布。

不更改QEMU设备、原始ARM／AF、ready、队列、完成、原厂等待、超时或重试上限，不重放控制。GDB抓取使用既有guard_owner，须匹配保留的Popen／PID／EXE路径和SHA；最多一次，25秒有界并detach。若发生抓取或抓取失败，外层诊断资格覆盖未感知该附加的内层记录，不能据内层eligible=true作功能验收。

PowerShell采样器只匹配本观察器完整路径的QEMU子进程，并再次核对EXE SHA；不接受任意PID，不写进程状态。时间为宿主UTC、CPU为宿主线程CPU耗时，不能当作guest虚拟时间或实机处理性能。多时点资源计数和单次栈用于定位线索，不凭一次快照宣布泄漏、死锁或QMP根因。

r66原始live-1是用户中断，live-2因连续三次QMP查询超时在约32秒终止，二者均保留为不完整。此诊断使用新目录与新增观测，不能替代缺失的完整相机、统计来源、原厂媒体或AF验收。
