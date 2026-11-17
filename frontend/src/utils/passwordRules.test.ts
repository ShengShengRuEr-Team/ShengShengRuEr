import { describe, expect, it } from 'vitest'
import {
  PASSWORD_MAX_BYTES,
  utf8ByteLength,
  validateNickname,
  validatePassword,
  validateReason,
  validateUsername,
} from './passwordRules'

describe('validateUsername', () => {
  it('接受 3—50 位字母数字下划线', () => {
    expect(validateUsername('abc')).toBeNull()
    expect(validateUsername('a_1')).toBeNull()
    expect(validateUsername('a'.repeat(50))).toBeNull()
  })

  it('拒绝越界、非法字符与空白', () => {
    expect(validateUsername('ab')).not.toBeNull()
    expect(validateUsername('a'.repeat(51))).not.toBeNull()
    expect(validateUsername('中文名')).not.toBeNull()
    expect(validateUsername('bad-name')).not.toBeNull()
    expect(validateUsername('   ')).not.toBeNull()
  })
})

describe('validatePassword', () => {
  it('接受 10—64 字符且含字母与数字', () => {
    expect(validatePassword('abcd123456')).toBeNull()
    expect(validatePassword('a1'.repeat(32))).toBeNull()
  })

  it('拒绝长度、字符与字节越界', () => {
    expect(validatePassword('abc123456')).not.toBeNull()
    expect(validatePassword('1'.repeat(10))).not.toBeNull()
    expect(validatePassword('a'.repeat(10))).not.toBeNull()
    expect(validatePassword('a1'.repeat(33))).not.toBeNull()
  })

  it('中文密码按 UTF-8 字节判定 72 字节边界', () => {
    // 每个汉字 3 字节：22 个汉字 = 66 字节，加 "a1" 2 字节 = 68 字节，宽度合法。
    const within = '汉'.repeat(22) + 'a1'
    expect(utf8ByteLength(within)).toBe(68)
    expect(validatePassword(within)).toBeNull()

    // 24 个汉字 = 72 字节，加 "a1" 超过 72 字节 → 拒绝。
    const over = '汉'.repeat(24) + 'a1'
    expect(utf8ByteLength(over)).toBeGreaterThan(PASSWORD_MAX_BYTES)
    expect(validatePassword(over)).not.toBeNull()

    // 恰好 72 字节且含字母数字：23 个汉字（69）+ "a1"（2）= 71，合法。
    const exact = '汉'.repeat(23) + 'a1'
    expect(utf8ByteLength(exact)).toBe(71)
    expect(validatePassword(exact)).toBeNull()
  })
})

describe('validateReason 与 validateNickname', () => {
  it('reason 去空格后 1—200 字', () => {
    expect(validateReason('违规')).toBeNull()
    expect(validateReason('   ')).not.toBeNull()
    expect(validateReason('x'.repeat(200))).toBeNull()
    expect(validateReason('x'.repeat(201))).not.toBeNull()
  })

  it('昵称 ≤50 字，可空', () => {
    expect(validateNickname('')).toBeNull()
    expect(validateNickname('x'.repeat(50))).toBeNull()
    expect(validateNickname('x'.repeat(51))).not.toBeNull()
  })
})
