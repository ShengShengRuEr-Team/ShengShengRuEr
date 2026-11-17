import type { SubmitErrorPlan } from './types'

/**
 * 后端 msg 常量（与 backend/app/schemas_attempts.py 的 MSG_E03–E09 逐字对应）。
 * 错误身份 = HTTP status + msg；E07 用固定前缀识别，其余精确相等；
 * 未列入的组合一律按未知错误保护。
 */
export const ATTEMPT_MESSAGES = {
  /** E03/E14：404 不可访问（不存在/未开放/已下线统一文案）。 */
  notAccessible: '资源不存在',
  /** E04：400 内容版本变化。 */
  contentUpdated: '内容已更新，请重新作答',
  /** E05：400 缺少/非法 Idempotency-Key。 */
  invalidIdempotencyKey: '缺少或非法的提交键 Idempotency-Key',
  /** E07：400 固定前缀。 */
  invalidContentPrefix: '提交内容不合法：',
  /** E08：400 同卷已成功提交（限次 1）。 */
  alreadySubmitted: '本轮同一试卷仅允许提交一次',
  /** E09：400 同键被其他 payload 使用。 */
  idempotencyConflict: '提交键已用于其他提交，请使用新键',
} as const

const UNKNOWN_PLAN: SubmitErrorPlan = {
  action: 'unknown-retry',
  message: '结果未确认，答案已冻结；请同键重试或查询状态',
  clearDraft: false,
  clearEnvelope: false,
  rebuildDraftFirst: false,
}

/**
 * API-1 错误白名单（需求 §9.1）。
 * 「保留答案」类（403/404/E05/E07/422）先重建草稿并读回校验成功，才清信封；
 * 页面按 rebuildDraftFirst 执行，不能在此直接清。
 * 状态码以后端实现为准：E04/E05/E07/E08/E09 均为 400，E03/E14 为 404。
 */
export function classifySubmitError(
  status: number,
  msg: string,
): SubmitErrorPlan {
  if (status === 401) {
    return {
      action: 'unauthorized',
      message: '登录失效，请重新登录后查询提交状态',
      clearDraft: false,
      clearEnvelope: false,
      rebuildDraftFirst: false,
    }
  }
  if (status === 403) {
    return {
      action: 'restore-answer',
      message: '当前账号无作答权限；作答已保留',
      clearDraft: false,
      clearEnvelope: true,
      rebuildDraftFirst: true,
    }
  }
  if (status === 404 && msg === ATTEMPT_MESSAGES.notAccessible) {
    return {
      action: 'restore-answer',
      message: '试卷不可访问；作答已保留',
      clearDraft: false,
      clearEnvelope: true,
      rebuildDraftFirst: true,
    }
  }
  if (status === 400 && msg === ATTEMPT_MESSAGES.contentUpdated) {
    return {
      action: 'reload-clear',
      message: '试卷内容已更新，请重新作答',
      clearDraft: true,
      clearEnvelope: true,
      rebuildDraftFirst: false,
    }
  }
  if (status === 400 && msg === ATTEMPT_MESSAGES.invalidIdempotencyKey) {
    return {
      action: 'restore-answer',
      message: '提交键异常，请刷新后重试；作答已保留',
      clearDraft: false,
      clearEnvelope: true,
      rebuildDraftFirst: true,
    }
  }
  if (status === 400 && msg.startsWith(ATTEMPT_MESSAGES.invalidContentPrefix)) {
    return {
      action: 'restore-answer',
      message: '提交内容异常，请刷新后重试；作答已保留',
      clearDraft: false,
      clearEnvelope: true,
      rebuildDraftFirst: true,
    }
  }
  if (status === 422) {
    return {
      action: 'restore-answer',
      message: '提交参数校验失败，请刷新后重试；作答已保留',
      clearDraft: false,
      clearEnvelope: true,
      rebuildDraftFirst: true,
    }
  }
  if (status === 400 && msg === ATTEMPT_MESSAGES.alreadySubmitted) {
    return {
      action: 'terminal-e08',
      message: '本卷已提交，不能重复提交',
      clearDraft: true,
      clearEnvelope: true,
      rebuildDraftFirst: false,
    }
  }
  if (status === 400 && msg === ATTEMPT_MESSAGES.idempotencyConflict) {
    return {
      action: 'check-status',
      message: '提交状态未确认；请查询提交状态',
      clearDraft: false,
      clearEnvelope: false,
      rebuildDraftFirst: false,
    }
  }
  if (status >= 500) {
    return {
      ...UNKNOWN_PLAN,
      message: '结果未确认，答案已冻结；请同键重试或查询状态',
    }
  }
  // 未知 400/4xx：保留信封与 pending，不放开编辑、不自动新键。
  return UNKNOWN_PLAN
}

export function isUnansweredStrongWarning(answered: number): boolean {
  return answered === 0
}
