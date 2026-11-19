import { describe, expect, it, vi } from 'vitest'
import { generateUuidV4, rebuildDraftForExplicitFailure, retryEnvelope, runSubmit } from './submit'
import type { SubmitApiPort, SubmitStoragePort } from './submit'
import type { AttemptSubmitApiResult } from '../api/attempts'
import type { EnvelopeReadResult, EnvelopeWriteResult } from './storage'
import { ATTEMPT_MESSAGES } from './errors'
import { makeDetail, makeEnvelope, makeSummary } from '../test/fixtures'

function makeStorage(options: {
  initial?: EnvelopeReadResult
  write?: EnvelopeWriteResult
  writeDraft?: { kind: 'ok' } | { kind: 'unavailable' }
} = {}): SubmitStoragePort {
  const initial = options.initial ?? { kind: 'none' }
  const write = options.write
  return {
    readEnvelope: vi.fn(() => initial),
    writeEnvelopeVerified: vi.fn(
      (candidate) => write ?? { kind: 'ok' as const, envelope: candidate },
    ),
    markEnvelopeUnknown: vi.fn(),
    writeDraftVerified: vi.fn(() => options.writeDraft ?? { kind: 'ok' as const }),
  }
}

function makeApi(result: AttemptSubmitApiResult): SubmitApiPort {
  return { submit: vi.fn().mockResolvedValue(result) }
}

const PAYLOAD = {
  loaded_question_ids: [11, 12, 13, 14],
  answers: [{ question_id: 11 as const, selected_option: 'A' as const }],
}

describe('T-06 提交编排（首次）', () => {
  it('无信封：写新信封（UUIDv4）并发送同一 key/payload', async () => {
    const storage = makeStorage()
    const api = makeApi({
      kind: 'success',
      value: { kind: 'submitted', summary: makeSummary() },
    })
    const result = await runSubmit({
      userId: 7,
      examPaperId: 1,
      payload: PAYLOAD,
      storage,
      api,
    })
    expect(result.kind).toBe('submitted')
    expect(storage.writeEnvelopeVerified).toHaveBeenCalledTimes(1)
    const envelope = vi.mocked(storage.writeEnvelopeVerified).mock.calls[0][0]
    expect(envelope.key[14]).toBe('4')
    expect(api.submit).toHaveBeenCalledWith(1, envelope.frozenPayload, envelope.key)
  })

  it('存储不可用：不发送，返回内存信封等待用户确认', async () => {
    const storage = makeStorage({ write: { kind: 'unavailable' } })
    const api = makeApi({
      kind: 'success',
      value: { kind: 'submitted', summary: makeSummary() },
    })
    const result = await runSubmit({
      userId: 7,
      examPaperId: 1,
      payload: PAYLOAD,
      storage,
      api,
    })
    expect(result.kind).toBe('needs-storage-confirmation')
    expect(api.submit).not.toHaveBeenCalled()
  })

  it('已有信封：用原 key/frozenPayload，不读当前答案', async () => {
    const envelope = makeEnvelope({ state: 'unknown' })
    const storage = makeStorage({ initial: { kind: 'valid', envelope } })
    const api = makeApi({
      kind: 'success',
      value: { kind: 'submitted', summary: makeSummary() },
    })
    await runSubmit({
      userId: 7,
      examPaperId: 1,
      payload: PAYLOAD,
      storage,
      api,
    })
    expect(storage.writeEnvelopeVerified).not.toHaveBeenCalled()
    expect(api.submit).toHaveBeenCalledWith(1, envelope.frozenPayload, envelope.key)
  })

  it('写信封冲突：采用读回信封发送', async () => {
    const other = makeEnvelope({
      key: '11111111-2222-4333-8444-555555555555',
    })
    const storage = makeStorage({ write: { kind: 'conflict', envelope: other } })
    const api = makeApi({
      kind: 'success',
      value: { kind: 'submitted', summary: makeSummary() },
    })
    await runSubmit({
      userId: 7,
      examPaperId: 1,
      payload: PAYLOAD,
      storage,
      api,
    })
    expect(api.submit).toHaveBeenCalledWith(1, other.frozenPayload, other.key)
  })

  it('信封损坏：不构造合法信封、不发送', async () => {
    const storage = makeStorage({
      initial: { kind: 'corrupt', rawRecordKey: 'k', reason: 'bad-json' },
    })
    const api = makeApi({
      kind: 'success',
      value: { kind: 'submitted', summary: makeSummary() },
    })
    const result = await runSubmit({
      userId: 7,
      examPaperId: 1,
      payload: PAYLOAD,
      storage,
      api,
    })
    expect(result).toEqual({
      kind: 'envelope-corrupt',
      rawRecordKey: 'k',
      reason: 'bad-json',
    })
    expect(api.submit).not.toHaveBeenCalled()
  })
})

describe('T-06 结果处理', () => {
  async function submitWith(result: AttemptSubmitApiResult) {
    const envelope = makeEnvelope()
    const storage = makeStorage({ initial: { kind: 'valid', envelope } })
    const api = makeApi(result)
    return {
      storage,
      result: await runSubmit({
        userId: 7,
        examPaperId: 1,
        payload: PAYLOAD,
        storage,
        api,
      }),
    }
  }

  it('网络异常 → unknown 且标记信封 unknown', async () => {
    const { storage, result } = await submitWith({ kind: 'network' })
    expect(result.kind).toBe('unknown')
    expect(storage.markEnvelopeUnknown).toHaveBeenCalledWith(7, 1)
  })

  it('500 → unknown 且保留信封', async () => {
    const { storage, result } = await submitWith({
      kind: 'http-error',
      status: 500,
      msg: '服务器错误',
    })
    expect(result.kind).toBe('unknown')
    expect(storage.markEnvelopeUnknown).toHaveBeenCalled()
  })

  it('E08 → terminal-e08', async () => {
    const { result } = await submitWith({
      kind: 'http-error',
      status: 400,
      msg: ATTEMPT_MESSAGES.alreadySubmitted,
    })
    expect(result.kind).toBe('terminal-e08')
  })

  it('E09 → check-status 且不自动新键', async () => {
    const { result } = await submitWith({
      kind: 'http-error',
      status: 400,
      msg: ATTEMPT_MESSAGES.idempotencyConflict,
    })
    expect(result.kind).toBe('check-status')
  })

  it('E04 → 明确失败计划 reload-clear', async () => {
    const { result } = await submitWith({
      kind: 'http-error',
      status: 400,
      msg: ATTEMPT_MESSAGES.contentUpdated,
    })
    expect(result.kind).toBe('explicit-failure')
    if (result.kind === 'explicit-failure') {
      expect(result.plan.action).toBe('reload-clear')
      expect(result.plan.clearDraft).toBe(true)
    }
  })

  it('200 但汇总不可解析 → submitted-without-summary（不重试）', async () => {
    const { result } = await submitWith({
      kind: 'success',
      value: { kind: 'submitted-without-summary', examPaperId: 1 },
    })
    expect(result.kind).toBe('submitted-without-summary')
  })
})

describe('pending 同键重试', () => {
  it('不重新读当前答案，复用原 key/payload', async () => {
    const envelope = makeEnvelope({ state: 'unknown' })
    const api = makeApi({
      kind: 'success',
      value: { kind: 'submitted', summary: makeSummary() },
    })
    const storage = makeStorage()
    await retryEnvelope({ envelope, storage, api })
    expect(api.submit).toHaveBeenCalledWith(1, envelope.frozenPayload, envelope.key)
  })
})

describe('AC-50 只留信封时重建草稿', () => {
  it('重建并读回成功 → rebuilt', () => {
    const storage = makeStorage({ writeDraft: { kind: 'ok' } })
    const result = rebuildDraftForExplicitFailure({
      envelope: makeEnvelope(),
      detail: makeDetail(),
      paperLabel: 'label',
      storage,
    })
    expect(result.kind).toBe('rebuilt')
    expect(storage.writeDraftVerified).toHaveBeenCalledTimes(1)
    if (result.kind === 'rebuilt') {
      expect(result.draft.answers).toEqual({ 11: 'A' })
    }
  })

  it('题目集合变化 → incompatible，不清信封', () => {
    const storage = makeStorage()
    const result = rebuildDraftForExplicitFailure({
      envelope: makeEnvelope({
        frozenPayload: {
          loaded_question_ids: [11, 12],
          answers: [{ question_id: 11, selected_option: 'A' }],
        },
      }),
      detail: makeDetail(),
      paperLabel: 'label',
      storage,
    })
    expect(result.kind).toBe('incompatible')
    expect(storage.writeDraftVerified).not.toHaveBeenCalled()
  })

  it('写入/读回失败 → write-failed，由页面保留信封冻结', () => {
    const storage = makeStorage({ writeDraft: { kind: 'unavailable' } })
    const result = rebuildDraftForExplicitFailure({
      envelope: makeEnvelope(),
      detail: makeDetail(),
      paperLabel: 'label',
      storage,
    })
    expect(result.kind).toBe('write-failed')
  })
})

describe('UUIDv4 生成', () => {
  it('版本/变体正确', () => {
    for (let index = 0; index < 20; index += 1) {
      const value = generateUuidV4()
      expect(value[14]).toBe('4')
      expect('89ab').toContain(value[19])
    }
  })
})
