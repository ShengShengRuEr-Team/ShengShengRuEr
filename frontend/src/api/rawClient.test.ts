import { describe, expect, it, vi } from 'vitest'
import { parseFilename, saveBlob } from './admin/exports'
import { extractErrorMessage } from './rawClient'

describe('parseFilename', () => {
  it('解析带引号与不带引号的附件名', () => {
    expect(parseFilename('attachment; filename="admin-users-20261117-120000.csv"')).toBe(
      'admin-users-20261117-120000.csv',
    )
    expect(parseFilename('attachment; filename=admin-login-logs.csv')).toBe(
      'admin-login-logs.csv',
    )
  })

  it('缺失时返回 null', () => {
    expect(parseFilename(undefined)).toBeNull()
    expect(parseFilename('inline')).toBeNull()
  })
})

describe('extractErrorMessage', () => {
  it('解析 JSON blob 中的 msg', async () => {
    const blob = new Blob([JSON.stringify({ code: 400, msg: '导出行数超过上限' })], {
      type: 'application/json',
    })
    await expect(extractErrorMessage(blob)).resolves.toBe('导出行数超过上限')
  })

  it('解析对象响应与网络失败', async () => {
    await expect(extractErrorMessage({ msg: '没有权限' })).resolves.toBe('没有权限')
    await expect(extractErrorMessage(undefined)).resolves.toBe('网络请求失败')
  })

  it('无法解析的 blob 使用固定文案，不外泄内容', async () => {
    const blob = new Blob(['<html>secret</html>'], { type: 'text/html' })
    const message = await extractErrorMessage(blob)
    expect(message).toBe('导出失败')
    expect(message).not.toContain('secret')
  })
})

describe('saveBlob', () => {
  it('创建临时下载链接并释放', () => {
    const createObjectURL = vi.fn(() => 'blob:mock-url')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    })
    const click = vi.fn()
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const element = originalCreateElement(tag)
      if (tag === 'a') {
        element.click = click
      }
      return element
    })

    saveBlob(new Blob(['x']), 'admin-users.csv')

    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(click).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
    vi.unstubAllGlobals()
  })
})
