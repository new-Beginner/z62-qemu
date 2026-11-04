# 2026-11-04 r103 源码更新

在已有r98公开历史上发布r99–r103源码、测试工具、合同、报告与选定摘要。默认仍r75界面／r69内核；新模型默认off，不附带Nikon固件、EXE、卡、工具链、RAW或完整轨迹。

## 新增与结果

- 原厂scalar消费者、状态追加、停止返回组成及原始kernel等待观察；明确r102来源晚于等待的失败。
- 独立r102 C内联读出，严格的完整输入、CRC／序列／所有权、停止／reset与数据完成资格。
- 独立r103 C输入→30×12／61槽有限统计桥：pending输入、completed cache和owned batch分开，缺源不回用CW图像，实际DMA后才完成。
- 新native两批122次DMA／93,696字节、原厂两份scalar1,536字节独立重算一致；旧读出／保留CW统计原生回归通过。
- 两个已定位的原始停止等待均kernel0／BOOL1，见到原厂800h OR/store。24秒无GDB窗口状态[]、CW541／grid322，原厂拍摄OSD恢复。

**真实预览仍未贯通：背景绿色、preview0。** 24秒窗口有两次短QMP取数暂停，不能当无扰动物理时序／长稳；每batch保留一幅C图像，不是61个新RAW采集。完整原厂摄影、镜头／AF、全局快照、NOR／标定和刷机安全仍未完成。本次没有修改AF或连接相机。

初版scalar断点只命中暖启动、快照0的取证缺口保留；另建无GDB窗口完成数据复核。所有来源、失败与边界见[r103报告](history/2026-11-04_实施-Z62读出统计桥与原厂停止恢复r103-report.md)及[合同](../qemu/z62-capturework/READOUT-STATISTICS-CONTRACT.md)。

## 验证与复现

本次公开副本35模块／143项无固件测试、16个基础C case通过；998个导出哈希、660份Python内存编译、文档链接及847个未转换文件字节一致性检查通过。QEMU原生设备和原厂运行属于单独的本地验证，不与143项混计。

[选定摘要](evidence/readout-statistics-r103.json)与[原件哈希索引](evidence-index-20261104.json)只分发事实和身份。1,109个实际接受源包在本地逐字节重构，两个原厂scalar与各自来源核对；没有把摘要当原始数据下载。公开源码子集的本次检查另见[VALIDATION](VALIDATION.md)，不能混计为重跑全部715项、QEMU／原厂窗口或LibRaw。

构建依赖与运行见[BUILD](BUILD.md)，开发过程见[DEVELOPMENT](DEVELOPMENT.md)。QEMU、xiaoqingfeng0526、JKWTCN、WonderLantern、nightglasses及贡献者的固定参考与许可见[REFERENCES](REFERENCES.md)和[NOTICE](../NOTICE.md)。下一步连接CW真实RAW来源cohort与受限预览，保持编码域／线性域和每帧身份。
