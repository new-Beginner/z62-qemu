# 工作目录内存储 r73

本项目所有生成物统一放在当前工作目录，不再在C盘或工作区同级目录新建运行数据。

```text
固件Z6II/
  .runtime/
    tmp/                         临时会话、虚拟SD、GDB临时副本
    cache/                       pip、uv等缓存
    tools/                       已迁入MSYS2与旧D盘会话
    migrated/c-runtime/          原C盘运行资料、固件fixture与Ghidra
    migrated/files.jsonl         原路径、新路径、大小、SHA256与迁移状态
  .build/                        QEMU构建与Python环境
  artifacts/                     场景、照片、NEF、录像与目录卡
  analysis/                      诊断与验收记录
```

## 启动

双击 [start-z6ii-workspace.cmd](../../start-z6ii-workspace.cmd) 运行带永久诊断和r75控件同步的C照片入口。已有启动脚本也已设置工作目录内的TEMP/TMP和pip缓存；19个Z62／参考启动命令通过同一个存储入口调用原profile，原内核选择和其余参数保持。

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/run_z62_workspace.py --storage-check
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/run_z62_workspace.py --entry run_z62_paired_diagnostic_console --port 8688
```

目录含中文，旧运行链要求ASCII访问名。启动器验证Q:是否指向本工作目录；未占用时建立SUBST别名，若被其他位置占用则拒绝，不覆盖。**Q:是本目录的访问别名，不是一份另存的数据或另一个物理分区。** 临时文件、原厂固件副本、虚拟卡和调试文件实际都在上述工作目录。

不要再裸运行旧的C盘默认路径命令。旧绝对路径在新的启动上下文中映射到已迁入资料；原始历史回执不重写，避免破坏SHA。当前构建依赖锁为 `.runtime/relocated-toolchain-manifest-r73.json`，对应139个已核对包；原锁也保留在`.runtime/tools`。

## 迁移与验证

| 项目 | 完成情况 |
|---|---|
| C盘项目资料 | 19,446个文件，7,895,797,700字节，逐文件源／目标SHA核对后迁移 |
| 工作区外D盘tools／会话 | 50,519个文件，5,805,994,617字节，同卷移动前后全量SHA清单一致 |
| C盘旧项目根与z62临时目录 | 复核为0；没有迁移系统Python、Codex或其他软件安装 |
| 启动脚本 | 24个均设置工作目录TEMP/TMP；19个Z62／参考入口加存储包装 |
| 新路径访问 | 4项路径／外部写拒绝专项通过；2项迁移复制／目标冲突保留专项通过 |
| 实际r69宿主检查 | 工作目录内9成员副本、GDB附加／分离、QMP恢复和关闭通过 |
| 实际照片文件 | JPEG640×424、NEF1006×1514独立解码通过，文件保存在工作区DCIM目录 |

机器现有其他程序也可能改变磁盘空余量；本次迁移量以上表和文件清单为准，不把C盘的全部空间变化算作本次回收。

存储复核回执（本地证据，未分发：`analysis/z62-workspace-storage-r73/verified-storage.json`）的scope仅为项目存储迁移。它不是新一次完整相机、模式往返、AF或刷机安全验收；既有r72模式失败继续保留。

当前验证覆盖已实际运行的独立交互入口、r69原生宿主和照片存储；19个旧入口未分别重跑完整媒体流程。路径包装只在本项目新启动进程和私有生成源码中生效，没有修改原厂指令或系统级TEMP设置。
