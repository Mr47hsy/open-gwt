# open-gwt

[English](README.md) · **简体中文** · [Русский](README.ru.md)

[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Assets: CC BY 4.0](https://img.shields.io/badge/assets-CC%20BY%204.0-green.svg)](LICENSE-ASSETS)
[![Unity 6.6](https://img.shields.io/badge/Unity-6.6%20(6000.6.2f1)-black.svg)](https://unity.com/)

一个开源、非官方的昆特牌（Gwent）规则重实现——基于与引擎无关的规则内核，支持确定性回放和服务端权威的多人对战。

> 本项目为非官方同人作品，未经 CD PROJEKT RED 批准或认可。

## 为什么做这个

昆特牌的官方内容开发已经结束，但它的核心设计——没有费用曲线、三行战场、三局两胜、以及围绕"何时 pass"
展开的节奏博弈——至今仍是卡牌品类里最有意思的设计之一。open-gwt 把这套设计以开源代码的形式延续下去，
任何人都可以游玩、研究、fork 和扩展。

## 设计原则

- **与引擎无关的规则内核。** 所有规则都在一个纯粹的库里，不依赖任何游戏引擎。Unity 只负责渲染和输入，
  绝不参与规则判定。
- **确定性回放。** 一局对战等于一个随机种子加一串有序的操作记录。重放这份记录能够精确复现整局对战——
  测试、bug 复现和机器人训练都因此变得可行。
- **服务端权威的多人对战。** 客户端只发送操作意图，并渲染服务端返回的状态。隐藏信息（手牌、牌库、
  即将抽到的牌）永远不会离开服务端。

## 计划支持平台

Windows · macOS · iOS · Android，基于 Unity 6.6 (6000.6.2f1)。

## 仓库结构

```
client/   Unity 工程——瘦客户端；用 Unity Hub 打开这个目录
server/   权威游戏服务端，Python——规则内核就在它里面
data/     卡牌、卡组和翻译，以 YAML 编写
docs/     决策记录（adr/）、协议（protocol/）、规则说明
```

## 开始开发

- **先读：** `docs/adr/` 记录架构决策，`docs/protocol/` 是卡牌协议和对局协议。
- **开发服务端：** 代码位于 `server/` 目录，Python 3.12 或更新。规则内核、机器人和模拟器都是它
  内部的包。
- **开发客户端：** 用 Unity Hub 打开 `client/` 目录，Unity 版本 6.6 (6000.6.2f1)。客户端不运行
  任何规则，即使和机器人对战也需要一个运行中的服务端。

## 参与贡献

欢迎各种形式的贡献：规则、卡牌效果、对战机器人、客户端、文档以及原创美术。以下两条规则用于保证项目在
法律上的干净，没有商量余地：

1. **不接受任何 CD PROJEKT RED 的资源。** 包含从昆特牌或《巫师》中提取或仿制的美术、音频、模型、
   卡牌名称、角色名称或风味文本的 PR 将被直接关闭。
2. **仅接受净室实现。** 根据公开的规则说明和实际游戏表现来实现功能，不要提交从官方客户端反编译或
   反汇编得到的代码。

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

代码以 [MIT 许可证](LICENSE) 发布。贡献到本仓库的原创美术和音频，除单个资源另有说明外，
均采用 [CC BY 4.0](LICENSE-ASSETS) 许可。

## 声明

This is an unofficial fan work and is not approved/endorsed by CD PROJEKT RED.
本项目为非官方同人作品，未经 CD PROJEKT RED 批准或认可。Gwent 与 The Witcher 是 CD PROJEKT S.A.
的商标。本项目与 CD PROJEKT RED 没有任何隶属关系，也不包含其游戏中的任何资源。
