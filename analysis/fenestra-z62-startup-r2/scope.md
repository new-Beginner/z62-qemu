# Fenestra Z62 原厂集成前置：启动合同 r2

- 目标保持移植 Fenestra，当前只恢复 Z6II C1.70 主/从启动、初始化和地址合同。
- 仅本地原始固件只读分析，以及用户自研固定 r69 Z62-QEMU 的早期执行观察。
- 未改原固件/候选/上游子模块；不加载 Fenestra 到原厂固件，不生成更新包。
- 不连接 USB/PTP/物理卡/相机，不刷机；无远程服务访问。
- 原文件为 raw ARM/Thumb 镜像，无 ELF/PE 导入表。等价接口锚点记录于提取器 imports_equivalent / instruction_windows，不由无导入表推导无文件/网络能力。
- Capstone 5.0.7；已有 Python、QEMU 路径实际检查。已安装逆向 skill 的 tool-index/precedent 相对路径缺失；已读 archived precedent（不作授权来源），本轮选用实际可用的 Capstone+GDB/QMP，不启动或安装 IDA 服务。
- 运行通过模型 boot-image 预装完整原成员，loader 设置各核复位 PC；不是相机早期引导加载器，也不证明真实加载长度、代码空间或更新认证。
- 仅 RSP Z1 执行断点和只读 RAM/寄存器观察；不设置运行中 PC/返回值，不补 ready，不伪造完成；断点扰动时序。
- 不带控制器/参数/卡；仅早期运行时/内核入口，不验收启动完成、正常关机、菜单、拍照或持久化。
- QMP quit 是结束自有 QEMU 进程，不是相机正常关机证据。
- 所有记录 firmware_integrated=false、flash_safety_verified=false。任何空白/清零目标/镜像尾部后的页表映射均不是已确认可用空间。
