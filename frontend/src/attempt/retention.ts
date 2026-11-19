import type {
  KeyRetentionPolicy,
  RetentionDecision,
} from './types'

const DAY_MS = 24 * 60 * 60 * 1000

/**
 * 流程 P-03 未确认：固定 unknown，自动重试关闭。
 * 确认服务端保留期后只能由配置改动本常量，页面逻辑不再改。
 */
export const KEY_RETENTION_POLICY: KeyRetentionPolicy = { kind: 'unknown' }

/**
 * 自动重试判定（需求 §3.6）：
 * - unknown：禁止自动；手动同键 + 强警告；
 * - permanent：requestedAt 合法才自动；
 * - days：年龄 < days-1 天才自动（固定 1 天安全余量）；
 * - requestedAt 非法：禁止自动。
 */
export function canAutoRetry(
  requestedAt: string,
  policy: KeyRetentionPolicy = KEY_RETENTION_POLICY,
  now = Date.now(),
): RetentionDecision {
  const requested = Date.parse(requestedAt)
  if (Number.isNaN(requested) || requested > now + 5 * 60 * 1000) {
    return {
      autoRetry: false,
      manualRetry: true,
      warning: 'strong',
      reason: 'invalid-time',
    }
  }
  if (policy.kind === 'unknown') {
    return {
      autoRetry: false,
      manualRetry: true,
      warning: 'strong',
      reason: 'unknown-policy',
    }
  }
  if (policy.kind === 'permanent') {
    return {
      autoRetry: true,
      manualRetry: true,
      warning: 'none',
      reason: 'allowed',
    }
  }
  const margin = Math.max(policy.days - 1, 0) * DAY_MS
  const age = now - requested
  if (age < margin) {
    return {
      autoRetry: true,
      manualRetry: true,
      warning: 'none',
      reason: 'allowed',
    }
  }
  return {
    autoRetry: false,
    manualRetry: true,
    warning: 'strong',
    reason: 'expired',
  }
}

export function retentionNotice(decision: RetentionDecision): string {
  switch (decision.reason) {
    case 'unknown-policy':
      return '服务端保留期尚未确认，自动重试已关闭；如需重试，请手动使用原提交编号。'
    case 'expired':
      return '已接近或超过服务端保留期，自动重试已关闭；手动重试可能无法确认结果。'
    case 'invalid-time':
      return '本机提交时间无法识别，自动重试已关闭；请先查询提交状态。'
    default:
      return '自动重试可用；每页面进入最多自动重试一次，失败转手动。'
  }
}
