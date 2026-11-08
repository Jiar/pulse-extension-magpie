# 可选的 Pulse 卡片滚动修复

Python 扩展通过 Pulse 的公开扩展协议提供数据，无需重新编译 Pulse。卡片布局由原生应用控制；额度很多时，使用扩展的 `configure.py --details` 可直接查看全部详情。

这里附带一个独立的通用原生修复，供希望自行构建 Pulse 的开发者使用：

- 固定账号标题与当前圆环选中的额度，其余明细在列表中滚动。
- 卡片最多占所属屏幕可用高度的 75%；空间不足时进一步缩短。
- 保持箭头尖端对齐圆环，处理侧边 Dock 和屏幕边缘的放置。
- 打开、切换和滚动卡片时不改变面板窗口大小；极窄空间下使用整卡滚动。

## 源码与补丁

- Fork：[Jiar/Pulse 的 fix/detail-card-overflow 分支](https://github.com/Jiar/Pulse/tree/fix/detail-card-overflow)。
- 固定提交：[cae542ec79748e752f9d5eb0b7487556b0413495](https://github.com/Jiar/Pulse/commit/cae542ec79748e752f9d5eb0b7487556b0413495)。
- 基线提交：`32075864aee68d7310672a1544c30df8f96405b9`（Pulse 1.12.7）。
- [detail-card-overflow.patch](detail-card-overflow.patch) 包含 11 个源码、测试和文档文件的通用改动。

补丁没有 Magpie 品牌、专用平均算法或账号信息。平均用量始终由 Python 扩展计算，再通过 Pulse 的 **Ring shows** 选择。

在单独的 Pulse checkout 中，先确认所用基线兼容：

```bash
git apply --check /path/to/pulse-extension-magpie/native-pulse/detail-card-overflow.patch
```

再应用补丁：

```bash
git apply /path/to/pulse-extension-magpie/native-pulse/detail-card-overflow.patch
```

也可以直接检出固定提交。构建与打包按 Pulse 自身的 README 和开发说明执行，需要完整 Xcode；保留所有 SwiftUI 预览并运行原生测试与本地化检查。这里不提供自动替换、退出或重启已安装应用的脚本。

## 验证范围

该固定提交在发布前使用 Xcode 27.2 完成无警告构建、2,156 项测试（262 个测试组）和本地化检查。测试包含视口预算、屏幕边缘与侧边 Dock 的放置、箭头路径和托管 SwiftUI 布局。

托管组件捕获与程序化滚动不能证明真实非 key 面板的滚轮或触控板输入。自行构建后仍应在自己的显示器、Dock 布局和输入设备上检查交互。源码构建的应用也不等同于官方签名和公证发行版；官方更新可能覆盖本地定制。

## 许可

Pulse：Copyright 2026 qunqin24，Apache License 2.0。许可证副本见 [LICENSE-Pulse.txt](LICENSE-Pulse.txt)。本项目对附带补丁的修改为 Copyright 2026 Jiar and contributors，同样采用 Apache-2.0；变更范围在补丁与对应提交中记录。

本目录不分发 Pulse 应用、第三方图标或 Magpie logo。名称用于说明兼容性，不表示上游认可或支持该集成。
