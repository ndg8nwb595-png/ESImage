import { describe, expect, it } from 'vitest'

import { defaultLandingPath, parseSafeRedirect } from './redirect'

describe('parseSafeRedirect', () => {
  it('接受站内路径', () => {
    expect(parseSafeRedirect('/workspace')).toBe('/workspace')
    expect(parseSafeRedirect('/history?page=2')).toBe('/history?page=2')
  })

  it('拒绝空值与非法值', () => {
    expect(parseSafeRedirect(null)).toBeNull()
    expect(parseSafeRedirect('')).toBeNull()
    expect(parseSafeRedirect('https://evil.com')).toBeNull()
    expect(parseSafeRedirect('//evil.com')).toBeNull()
    expect(parseSafeRedirect('/..\\etc')).toBeNull()
    expect(parseSafeRedirect('/a/../b')).toBeNull()
    expect(parseSafeRedirect('javascript:alert(1)')).toBeNull()
  })
})

describe('defaultLandingPath', () => {
  it('仅管理员/超管进入管理后台', () => {
    expect(defaultLandingPath(['admin'])).toBe('/admin/dashboard')
    expect(defaultLandingPath(['super_admin'])).toBe('/admin/dashboard')
  })

  it('含普通用户角色优先进入创作工作台', () => {
    expect(defaultLandingPath(['user'])).toBe('/workspace')
    expect(defaultLandingPath(['user', 'admin'])).toBe('/workspace')
    expect(defaultLandingPath(['user', 'super_admin'])).toBe('/workspace')
  })
})
