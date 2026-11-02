# Z6II QEMU v0.2.0 构建范围

- auth：用户明确要求实际构建 Nikon Z6II QEMU 模拟器，并允许下载网络参考内容。
- in_scope：公开上游源码核对、固定摘要下载、隔离构建依赖部署、新建 Z6II 板型、编译 Windows 原生程序、运行用户提供的原固件副本、GDB/QMP 本机测试和便携打包。
- out_of_scope：连接/刷写相机、修改原始固件、将未知外设假回复伪装成硬件正确行为、宣称 MENU 或真实双芯片通信已实现。
- network_profile：访问 QEMU 官方下载站、GitHub/MSYS2 官方发布及软件仓库，用于源码和工具链；未向网络上传固件。
- 文件边界：项目目录保存源码、构建缓存和交付物；独立 MSYS2 工具链部署在会话 scratch，未替换系统编译器。临时盘符已清理。运行便携包不依赖 scratch 工具链。
- 机器状态边界：尝试启动已有 Docker Desktop 但其引擎未能启动；最终未依赖 Docker/WSL，没有安装 Linux 发行版。
- 固件保护：原始包及两份 payload 按 SHA-256 核对；板型只读载入 ROM，不写回输入文件。
