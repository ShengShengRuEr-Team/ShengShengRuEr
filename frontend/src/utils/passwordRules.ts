/**
 * 前端侧规则提示，与后端 `schemas_admin/users.py` 逐字一致：
 * - 用户名去空格后 `[A-Za-z0-9_]{3,50}`；
 * - 密码 10—64 字符、UTF-8 ≤72 字节、至少一个 ASCII 字母与一个数字；
 * - reason 去空格后 1—200 字；昵称去空格后 ≤50 字。
 * 前端只做提示，最终仍由后端兜底（非法一律 422）。
 */

export const USERNAME_MIN_LENGTH = 3
export const USERNAME_MAX_LENGTH = 50
export const PASSWORD_MIN_LENGTH = 10
export const PASSWORD_MAX_LENGTH = 64
export const PASSWORD_MAX_BYTES = 72
export const REASON_MAX_LENGTH = 200
export const NICKNAME_MAX_LENGTH = 50

const USERNAME_PATTERN = /^[A-Za-z0-9_]{3,50}$/

export function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).length
}

/** 返回错误文案，null 表示通过。 */
export function validateUsername(value: string): string | null {
  const candidate = value.trim()
  if (!USERNAME_PATTERN.test(candidate)) {
    return '用户名需为 3—50 位字母、数字或下划线'
  }
  return null
}

export function validatePassword(value: string): string | null {
  // 后端按字符数（码点）判断长度，这里用 Array.from 对齐。
  const characters = Array.from(value)
  if (
    characters.length < PASSWORD_MIN_LENGTH ||
    characters.length > PASSWORD_MAX_LENGTH
  ) {
    return `密码长度需为 ${PASSWORD_MIN_LENGTH}—${PASSWORD_MAX_LENGTH} 个字符`
  }
  if (utf8ByteLength(value) > PASSWORD_MAX_BYTES) {
    return '密码 UTF-8 编码不得超过 72 字节'
  }
  if (!/[A-Za-z]/.test(value)) {
    return '密码必须包含至少一个 ASCII 字母'
  }
  if (!/[0-9]/.test(value)) {
    return '密码必须包含至少一个数字'
  }
  return null
}

export function validateReason(value: string): string | null {
  const candidate = value.trim()
  if (candidate.length < 1 || candidate.length > REASON_MAX_LENGTH) {
    return 'reason 需为 1—200 个字符'
  }
  return null
}

export function validateNickname(value: string): string | null {
  if (value.trim().length > NICKNAME_MAX_LENGTH) {
    return '昵称不得超过 50 个字符'
  }
  return null
}
