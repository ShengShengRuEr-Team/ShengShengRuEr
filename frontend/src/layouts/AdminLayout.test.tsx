import { describe, expect, it } from 'vitest'
import { visibleAdminMenu } from './AdminLayout'

function keys(items: ReturnType<typeof visibleAdminMenu>): string[] {
  return (items ?? []).map((item) => String(item?.key))
}

describe('管理端菜单权限过滤', () => {
  it('拥有用户/日志/本人读权限时全部显示', () => {
    const menuKeys = keys(
      visibleAdminMenu(
        (code) =>
          code === 'admin:user:read' ||
          code === 'admin:log:read' ||
          code === 'admin:self:read',
      ),
    )
    expect(menuKeys).toContain('/admin/users')
    expect(menuKeys).toContain('/admin/logs/login')
    expect(menuKeys).toContain('/admin/profile')
  })

  it('无权限时隐藏用户与个人中心，仅保留基础项', () => {
    const menuKeys = keys(visibleAdminMenu(() => false))
    expect(menuKeys).not.toContain('/admin/users')
    expect(menuKeys).not.toContain('/admin/profile')
    expect(menuKeys).toContain('/admin')
    expect(menuKeys).toContain('/admin/listening-papers')
  })
})
