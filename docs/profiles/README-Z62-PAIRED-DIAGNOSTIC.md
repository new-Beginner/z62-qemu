# Z62 交互输入诊断 r72

该入口沿用已构建的r69核心和r71媒体／场景接口，增加有界只读原厂状态采样及首次QMP超时的自有进程抓栈。它不代表完整相机验收，也不修改原厂ready、队列、等待或超时。

## 运行

用户最新要求所有文件位于工作目录；后续使用工作目录存储入口，复制虚拟SD前检查可用空间：

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/run_z62_workspace.py --entry run_z62_paired_diagnostic_console --port 8688 --software-card artifacts/my-r72-test-card
```

默认scratch为工作区内`.runtime/tmp`，通过验证过的Q:别名访问；源卡位于`.runtime/migrated/c-runtime/fixtures`。此前项目同级的tools和会话已迁入`.runtime/tools`。详见[存储迁移说明](README-WORKSPACE-STORAGE.md)。TEMP、TMP和缓存定位仅在该进程内切换，退出恢复。

不更换旧默认CMD入口。普通r71入口仍使用系统临时目录；4GiB虚拟SD会完整复制一份，因此不能在空间不足的C盘直接启动新会话。本轮一次启动前ENOSPC已保留记录，并只清理了那份无法运行的不完整副本，原卡和其他证据保持。

## 读取什么

本地 `GET /paired/diagnostics` 返回逐项采样，明确 `atomic_cross_device_snapshot=false`。

| 字段 | C1.70地址／来源 | 解释范围 |
|---|---|---|
| selector.scalar | C1F7A628，两个word | 当前16位值、前16位值和变化标志 |
| selector.cached | C1F7A746／C1F7A77A | 原输入缓存，不能当作APPLV调用证明 |
| selector.decoded_master | C25D6FE6 | 主引擎已有解码字段 |
| input_inhibit／ready_join | C1821EB8／C1868AE8 | 沿用r28选择实验的观察条件；不是完整相机ready定义 |
| processor_state_byte | C1864CD1 | 原厂处理状态的字节值，保留数字，不推定完整状态机 |
| command_group_0 | 20102600起四个word | 原配置快照 |
| output | r69只读paired-output-lineage | 实际C ISP提交模式、来源及标签 |

这些地址沿用既有C1.70原指令和运行证据，其他固件版本不适用。该版本有两个视频统计属性名误用了video-isp前缀，返回明确unavailable；没有补0。当前对照保持读取代码相同，不在运行中修订模板。

## QMP超时处理

请求仍由原QMP传输发送一次，不重放。首次TimeoutError触发原有宿主抓取工具，必须持有对应Popen、匹配实际EXE路径、PID和SHA；ASCII运行时的9个成员逐个校验。任何抓取尝试都将该诊断实例的功能资格设为false，原TimeoutError保留，取证自身失败也不能覆盖它。

该机制在无固件原生检查（本地证据，未分发：`analysis/z62-paired-diagnostic-r72/native-host-1/native-host-check.json`）中实际验证了附加、线程栈、detach、QMP恢复和关闭。它不能证明真实QMP超时的原因已经找到。

## 本轮观察

| 同样等初始inhibit=0、join=3 | 主缓存选择值 | 变化标志／配置 | 结果 |
|---|---|---|---|
| 实际全按、释放、C照片存卡后切视频 | 到达1 | changed持续1，配置[773,1002,1,0] | 输出仍photo，模式确认超时 |
| 不按全快门，直接切视频 | 到达1 | changed清零，配置转[768,846,3,0] | 21.314秒确认video输出及当前设置帧 |

两次观察没有宿主附加、没有QMP读取失败，生成源保持。对照支持继续调查全按后的应用处理；它没有证明某个具体原厂函数阻塞，也没有证明唯一根因。

第三组已按半按、等待客体时间、全按、先松全按再松半按执行，仍未确认视频；同时触发宿主取证，功能资格false。该组作为诊断现场保留，不能把前两组推断或观察完成标志直接当作修复。

完整记录见[阶段报告](../history/2026-11-03_诊断-Z62全按后模式交付r72-report.md)。
