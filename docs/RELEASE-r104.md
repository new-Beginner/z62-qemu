# 2026-11-04 r104 源码更新

在r103公开历史上新增CW实际四帧来源→受限软件预览→原厂LCD通路、原生探针、独立核验器、合同与完整报告。默认仍r75界面／r69内核，新模型默认off。不分发Nikon固件、NKN原件、EXE、卡、工具链或原始大轨迹。

## 本次实现及验证边界

| 项目 | 已验证 | 限制 |
|---|---|---|
| 四帧来源 | 实际CW有效行DMA后，四个不同slot／publication／地址组成集合；消费者独占冻结视图 | 有限RAW12配方，量化中点非无损恢复 |
| 数据与生命周期 | 27,427,584B线性视图SHA、120,960B NV12、18,285,056B客体编码RAW保持；bank／背压／停止／reset／stale通知检查 | 新来源native为三种缩略几何；旧路径回归单独计数 |
| 原厂24秒 | CW541、135来源集合、122批预览、状态[]；671个输入包可重构，scalar1,536B重算一致 | 无GDB但两次QMP取数暂停，非无扰动时序／长稳 |
| LCD与两色变化 | 最终橙色16点、另一个窗口蓝／橙各16点匹配实际来源 | 固定色场不能唯一确定四个来源帧中的显示帧 |
| 菜单／半按恢复 | **未通过**，失败已保留 | 第一半按早于菜单实际进入；最后有效21.224059秒后通信超时、exit1；根因未知 |

不改旧RAW计数、客体LUT编码RAW、原厂AF／ready／返回值，不注入软件事件6。当前CW来源显式拒绝paired ingress、旧output-lineage和video配方；已有软件媒体功能不自动覆盖此来源。完整原厂摄影／存卡、镜头AF、多模式恢复、全局快照及安全刷机仍未完成，完整Goal继续active。

## 开发记录与下一步

父r103缺属性红检查、两次native测试护栏越界失败及修正、24秒成功窗口、菜单恢复失败均保留，见[完整报告](history/2026-11-04_实施-Z62采集四帧来源与原厂预览r104-report.md)和[来源合同](../qemu/z62-capturework/CW-PREVIEW-CONTRACT.md)。后续先接永久host timeout现场捕获，再按实际菜单索引推进两轮恢复；设备语义变化需独立版本，冻结r104保留。

本次重新执行数据证据核验与失败分类，未重新运行QEMU窗口或历史715项／RawPy。公开源码检查的实际执行数和输出见[VALIDATION](VALIDATION.md)；选定事实见[预览摘要](evidence/capturework-preview-r104.json)与[生命周期失败摘要](evidence/cw-preview-lifecycle-r104.json)，原始内容身份见[证据索引](evidence-index-20261104.json)。

QEMU、xiaoqingfeng0526、JKWTCN、WonderLantern、R3tr0ooo、nightglasses及贡献者的署名与许可证继续保留，见[REFERENCES](REFERENCES.md)和[NOTICE](../NOTICE.md)。本轮未重新拉取这些上游；使用已有固定参考与Z6II实际数据交叉核对，未将他人成果称为从零实现。
