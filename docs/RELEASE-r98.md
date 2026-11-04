# 2026-11-04 r98 源码更新

在已有r91公开提交上增加r92–r98源码、测试、合同、阶段报告与选定证据。默认仍是r75界面／r69内核；实验模型默认关闭。本次公开源码，不附带EXE、Nikon固件、卡、RAW、NKN原件或工具链。

## 实现内容

| 增量 | 实际实现 | 验证与边界 |
|---|---|---|
| r92连续统计来源 | CW真实DMA后冻结量化线性域，供五路统计 | 原生157,440字节重算；原厂13帧／2批，不增加旧RAW计数 |
| r93采集组 | LUT65、FIR、ROI／grid三类真实DMA与事件96 | 原生18,528字节重算；未知／零参数拒绝，不补ready |
| r94/r95参数路径 | 系数+3Eh更正、资源39标签追踪、显式参考参数输入 | 原厂13次group／ACK13，216个已分类字节重算；不是工厂标定或可刷文件 |
| r96/r97等待／供帧 | 真实kernel返回与OR/store、虚拟时钟30Hz帧ID、两mailbox审计 | 慢源2成功1超时，连续源3次成功；32个accepted包可重构，断点扰动 |
| r98保留帧有限来源 | CW成功后保留、stop仍有效、batch冻结、下次latest、reset／alias／取消边界 | 原生两输入122次DMA、93,696字节重算；原厂两批同一来源，不是122个新RAW |

## 当前明确失败

原厂16.000750250秒窗口：33次MAIN／CW／group，32帧连续统计，122次有限采样／2批／0拒绝。每批保存一份scalar，共1,536字节独立重算零差异，来源均为publication33／frame61。最终原厂LCD显示 `Error. Turn camera off and then on again.`，预览为0、CW未恢复。进程正常退出不代表摄影通过；具体失败来源仍待定位。

完整相机、原厂编码／客体存卡、模式往返、真实镜头／PDAF／原厂AF、整机快照和刷机安全均未完成。模拟器通过不能保证固件刷入相机不黑砖。本次未修改原厂AF，也未连接实机。

## 验证、复现与来源

本地已有完整715项Python回归，0失败／错误／跳过，187.344秒；无RawPy，没有重跑LibRaw。原生DMA、原厂窗口与公开源码子集分别计数。公开副本本次实际检查结果见[VALIDATION](VALIDATION.md)，不把历史701项或本地715项当成新克隆测试。

公开副本实际通过35模块／143项无固件测试及16个C case，962个导出哈希、635份Python内存编译、Markdown链接检查通过；819个未转换导出文件与原工作区字节一致。最终文档回写后另做静态核对。

选定摘要：[r95参数](evidence/group-parameters-r95.json)、[r97真实等待](evidence/current-stream-r97.json)、[r98数值与失败](evidence/retained-finite-r98.json)；原件哈希见[索引](evidence-index-20261104.json)。原始轨迹和数据留在本地，完整过程与失败见[DEVELOPMENT](DEVELOPMENT.md)及各阶段报告。

构建父依赖与运行见[BUILD](BUILD.md)，新合同见[FINITE-CONTRACT](../qemu/z62-capturework/FINITE-CONTRACT.md)。直接基础、参考作者、固定提交及许可证见[REFERENCES](REFERENCES.md)；特别保留xiaoqingfeng0526、JKWTCN、WonderLantern、nightglasses及其贡献者署名。上游实现与本机交叉核对、C近似、未知硬件分别说明。
