---
name: 投镜 · 玻璃中的投资时间
description: 深海军蓝中的个人投资 AI，以蓝橙玻璃球和克制的液态玻璃承载长期投资记忆。
colors:
  primary: "#9fddff"
  secondary: "#ffb17e"
  neutral-bg: "#07121d"
  neutral-surface: "#0b1723"
  neutral-foreground: "#edf3f8"
  neutral-secondary: "#acbecd"
  neutral-muted: "#839cad"
  neutral-line: "rgba(211,230,245,.12)"
typography:
  body:
    fontFamily: "Geist, -apple-system, BlinkMacSystemFont, PingFang SC, Segoe UI, sans-serif"
    fontSize: "14px"
  display:
    fontFamily: "Geist, -apple-system, BlinkMacSystemFont, PingFang SC, Segoe UI, sans-serif"
    fontSize: "clamp(36px, 3.5vw, 56px)"
    fontWeight: 400
    lineHeight: 1.35
    letterSpacing: "-.035em"
  title:
    fontFamily: "Geist, -apple-system, BlinkMacSystemFont, PingFang SC, Segoe UI, sans-serif"
    fontSize: "30px"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "Geist, -apple-system, BlinkMacSystemFont, PingFang SC, Segoe UI, sans-serif"
    fontSize: "11px"
rounded:
  control: "9px"
  pill: "30px"
spacing:
  control: "8px 12px"
  page-horizontal: "32px"
components:
  button-primary:
    backgroundColor: "#cee8f7"
    textColor: "#122c3f"
    rounded: "{rounded.control}"
    padding: "12px 17px"
  button-secondary:
    backgroundColor: "#c4dff30a"
    textColor: "#cddce9"
    rounded: "{rounded.control}"
    padding: "11px 15px"
  input:
    backgroundColor: "#0b1726"
    textColor: "{colors.neutral-foreground}"
    rounded: "{rounded.control}"
    padding: "9px 12px"
  chip:
    backgroundColor: "#a5cce80a"
    textColor: "#b3c8d9"
    rounded: "6px"
---

# Design System: 投镜 · 玻璃中的投资时间

## Overview

**Creative North Star: “玻璃中的投资时间”**

投镜把个人投资记忆表现为一团可亲近的蓝橙玻璃光体。全屏背景使用用户指定的 CloudFront 循环视频，保持原画颜色与亮度，不以其他视频、图片或深色渐变替代。Geist 与系统中文字体保持信息清楚、当代而克制；蓝色承担可读的交互提示，暖橙只为重要的情绪与路径差异添温。

液态玻璃以极淡的透光底、细微高光和轻模糊建立材质，而不是把每块内容都做成浮起的卡片。图表、正文与数字需要稳定的不透明阅读底；玻璃用于品牌球、导航、工具和浮层。原生玻璃球资产是身份锚点，不能被泛化的发光圆球替代。

**Key Characteristics:**
- 深海军蓝底色与低对比冷色分层
- 蓝色交互光与克制的暖橙强调
- 原生蓝橙玻璃球作为持续的身份意象
- 轻薄液态玻璃与稳固的数据阅读面并存

## Colors

这组颜色由近黑的蓝调底色、冷白文字和一对低饱和冰蓝/暖橙强调构成。

### Primary
- **冰川蓝** (#9fddff): 用于链接、焦点轮廓、播放与选择状态，给暗背景上的可操作元素提供清晰识别。

### Secondary
- **暖琥珀橙** (#ffb17e): 与蓝色共同标识玻璃球与路径差异，用于少量暖色节点和强调。

### Neutral
- **深海军蓝** (#07121d): 页面与应用的基础底色。
- **墨蓝阅读面** (#0b1723): 稳定的信息表面和内容底色。
- **冷白正文** (#edf3f8): 主要文字和高优先级信息。
- **雾蓝次级文字** (#acbecd): 描述、辅助标签与次级导航。
- **灰蓝弱化文字** (#839cad): 面包屑、弱提示等低层级内容。
- **冰雾细线** (rgba(211,230,245,.12)): 轻分隔线，不围出厚重卡片边框。

**The Blue-Orange Identity Rule.** 交互蓝与暖橙共同延续品牌球和路径语义；不要把其中一个扩张成大面积高饱和背景。

## Typography

**Display Font:** Geist (with -apple-system, BlinkMacSystemFont, PingFang SC, Segoe UI, sans-serif fallback)
**Body Font:** Geist (with system sans-serif and PingFang SC fallback)
**Label/Mono Font:** 不使用独立标签或等宽字体；数字沿用正文家族并在数据组件中启用等宽数字。

**Character:** Geist 的紧凑几何感让数据界面显得清楚而轻盈；中文回退到系统字体，维持自然阅读。标题使用中等偏轻的字重和略收紧字距，避免企业仪表盘的沉重感。

### Hierarchy
- **Display** (400, clamp(36px, 3.5vw, 56px), 1.35): 生涯唤醒等叙事界面的主标题。
- **Headline** (400, 30px, 1.4): 页面标题承担清楚的页面入口层级。
- **Title** (500, 16–17px): 卡片、区块和回放标题。
- **Body** (400, 14px, 1.8): 默认正文、表单与说明文字。
- **Label** (400, 10–12px): 导航、辅助信息和紧凑元数据。

## Layout

应用采用全视口桌面工作区：固定侧栏、顶栏与主内容区并列，页面自身通常限制在视口内，细节内容在内部区域滚动。主视图使用弹性分区与 `min-width: 0` 保持图表和文本能够收缩；窄窗口下减少侧栏与次要信息，并允许特定横向内容局部滚动。顶层页面不依赖长页面滚动。CSS 中常见的内边距与间距以 8、12、14、18、20、24、30、32px 等实用步进组合，不宣称统一的间距比例。

## Elevation & Depth

深度主要由背景明暗、透明层、细边和局部模糊建立，少数对象使用环境阴影来分离主体。`.liquid-glass` 的透光底极淡，背景模糊为 4px，内侧有轻微顶部高光并叠加 1.4px 渐变遮罩边；玻璃并非数据内容的默认容器。品牌球使用柔和投影与缓慢漂浮，输入聚焦以边框变亮和淡蓝环提示。

## Shapes

控件与容器以柔和的小圆角为主，常用 8–10px；圆形按钮与药丸标签用于明确的圆形动作/状态。边线保持细且低对比，玻璃边缘可用遮罩渐变表现，不使用厚重描边。原生球体保持圆润轮廓与透明层次。

## Components

### Buttons
- **Character:** 安静、直接，靠明暗与轻微状态变化表达可操作性。
- **Shape:** 柔和控件圆角 (9px)；助手头像与状态动作可采用圆形。
- **Primary:** 浅冰蓝底与深蓝字，常规内边距 (12px 17px)；小号按钮缩至 (8px 12px)。
- **Hover / Focus:** 悬停提高底色亮度；按下轻移 1px；键盘焦点显示 2px 浅蓝轮廓并外移 4px。
- **Secondary / Ghost:** 次级按钮使用低透明冷色底与细边；文字按钮无填充，仅改变文字亮度。

### Chips
- **Style:** 弱透明蓝底、冷色文字与细描边，标签采用紧凑内边距和小圆角。
- **State:** 选中状态由浅色文字、底色和局部高光共同表现，不单靠色相区分。

### Inputs / Fields
- **Style:** 墨蓝输入底、细冷色边线与 9px 圆角；占位文字比正文弱一阶。
- **Focus:** 边框转为较亮的蓝灰色，并出现淡蓝色外环。
- **Behavior:** 按钮、链接和表单控件共用清楚的键盘焦点轮廓。

### Navigation
- **Style:** 深色侧栏以文字为主，图标与文字间留有呼吸；默认项为雾蓝灰色。
- **State:** 悬停出现极淡底色；当前项使用横向浅蓝渐变底与细内高光，辅以小光点。

### Liquid Glass
玻璃容器以几乎透明的白色混合层、4px 背景模糊和内侧高光构成；渐变遮罩细边只强调材质轮廓。高对比表格和图表留在阅读底上。

## Do's and Don'ts

### Do:
- **Do** 让蓝色交互提示与暖橙细节延续玻璃球的身份配色。
- **Do** 将液态玻璃用于导航、工具、品牌和浮层，并把正文及图表放在稳定阅读底上。
- **Do** 为焦点保留可见的浅蓝轮廓，并同时使用文字、形状或线型表达图表状态。
- **Do** 保留原生投镜球资产的透明质感与蓝橙光色。

### Don't:
- **Don't** 把每个信息区都包成玻璃卡片；大段文字和精细数据需要稳定对比。
- **Don't** 用只靠颜色的方式编码关键操作或路径状态。
- **Don't** 用厚重边框或强结构阴影覆盖当前轻薄的层次关系。

## 投资生涯数据看板 · 2026-11-07

用户确认用数据看板扩展投资生涯，并移除重复的个人 AI 页。此页采用稳定的不透明阅读面；品牌视频继续用于侧栏、顶栏与其他叙事界面。

- 先显示六项账户概要，再用约 2:1 的两列安排账户轨迹/持仓风险、持仓结构/交易统计，年度复盘收为底部一行。打开助手时按内容容器宽度变为单列，允许看板内部滚动，不挤小数字来强塞全部内容。
- 看板表格正文 13px，标签与辅助信息不低于 12px，标题 14px/22–24px，关键数字 24–27px，年度数字 20–21px；均继承用户字号缩放，数字用等宽数字特性对齐。
- 阅读底 `#07121d`，区块 `#0c1b29`，主文字 `#edf3f8`，次文字 `#bdccd7`，辅助文字 `#a0b3c4`；曲线与焦点 `#a6dfff`，净投入及待穿透权重 `#ffb17e`。正损益 `#a4d5c2`、负损益 `#f0aca6` 同时带正负号，不仅依赖颜色。
- 数据区块 12px 圆角，分段选择器 6px，内部按钮 4px，仓位条 3px。弱边界分组，避免每个数字再套卡片。
- 主图在资产、资金流调整收益和回撤间切换；持仓在证券、行业和穿透间切换。指标点击解释公式，图表有键盘日期滑条与明细按钮；教学来源、截至日期及未知披露常驻可见。
