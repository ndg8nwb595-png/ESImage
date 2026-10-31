// 设计 token（ui-ux-pro-max 定调）：专业极简、navy 主色 + 蓝辅色、浅色背景。
// 作为唯一颜色来源，组件内不散落硬编码 hex。

import type { ThemeConfig } from 'antd'

export const colors = {
  primary: '#1E3A5F', // 主色：深藏青（品牌）
  secondary: '#2563EB', // 辅色：蓝（链接/强调）
  accent: '#059669', // 成功/确认：绿
  background: '#F8FAFC', // 页面背景
  foreground: '#0F172A', // 正文
  muted: '#F1F3F5', // 弱背景
  border: '#E4E7EB', // 边框
  destructive: '#DC2626', // 危险
} as const

/** 中文字体优先系统字体；Inter 作为拉丁字形首选（不依赖被墙的 Google Fonts CDN）。 */
export const fontFamily =
  "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"

export const themeConfig: ThemeConfig = {
  token: {
    colorPrimary: colors.primary,
    colorLink: colors.secondary,
    colorSuccess: colors.accent,
    colorError: colors.destructive,
    colorBgLayout: colors.background,
    colorTextBase: colors.foreground,
    colorBorder: colors.border,
    borderRadius: 6,
    fontFamily,
  },
}
