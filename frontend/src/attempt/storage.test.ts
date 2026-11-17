import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  DRAFT_TTL_MS,
  MAX_DRAFTS_PER_USER,
  SUBMITTED_TTL_MS,
  clearDraftAndIndex,
  draftKey,
  enforceDraftLimit,
  envelopeKey,
  hasSubmittedMarker,
  indexKey,
  persistDraft,
  readDraft,
  readEnvelope,
  readIndex,
  readSubmitted,
  removeEnvelope,
  removeSubmitted,
  submittedKey,
  writeDraft,
  writeEnvelopeVerified,
  writeIndexEntry,
  writeSubmitted,
} from './storage'
import { makeDraft, makeEnvelope, makeSubmittedCache } from '../test/fixtures'

const UID = 7
const PID = 1

afterEach(() => {
  vi.restoreAllMocks()
})

describe('T-01/T-02 草稿存储', () => {
  it('写入/读取/用户隔离', () => {
    expect(writeDraft(makeDraft()).kind).toBe('ok')
    expect(readDraft(UID, PID).kind).toBe('valid')
    expect(readDraft(8, PID).kind).toBe('empty')
    expect(readDraft(UID, 2).kind).toBe('empty')
  })

  it('TTL 边界：>= 30 天过期并删除', () => {
    writeDraft(makeDraft({ updatedAt: new Date().toISOString() }))
    expect(readDraft(UID, PID, Date.now() + DRAFT_TTL_MS - 1000).kind).toBe('valid')
    expect(readDraft(UID, PID, Date.now() + DRAFT_TTL_MS).kind).toBe('empty')
    expect(window.localStorage.getItem(draftKey(UID, PID))).toBeNull()
  })

  it('损坏草稿删除并返回 invalid', () => {
    window.localStorage.setItem(draftKey(UID, PID), '{broken')
    expect(readDraft(UID, PID).kind).toBe('invalid')
    expect(window.localStorage.getItem(draftKey(UID, PID))).toBeNull()
  })

  it('每用户最多 10 份，淘汰最旧普通草稿', () => {
    const base = Date.now()
    for (let index = 0; index < MAX_DRAFTS_PER_USER + 1; index += 1) {
      const paperId = 100 + index
      writeDraft(
        makeDraft({
          examPaperId: paperId,
          updatedAt: new Date(base + index * 1000).toISOString(),
        }),
      )
    }
    enforceDraftLimit(UID, base + 60_000)
    expect(window.localStorage.getItem(draftKey(UID, 100))).toBeNull()
    expect(window.localStorage.getItem(draftKey(UID, 110))).not.toBeNull()
  })
})

describe('T-09 信封存储与损坏保护', () => {
  it('写后读回成功', () => {
    const envelope = makeEnvelope()
    const result = writeEnvelopeVerified(envelope)
    expect(result.kind).toBe('ok')
    expect(readEnvelope(UID, PID).kind).toBe('valid')
  })

  it('已有合法信封时不覆盖，返回 conflict', () => {
    const first = makeEnvelope()
    expect(writeEnvelopeVerified(first).kind).toBe('ok')
    const second = makeEnvelope({
      key: '11111111-2222-4333-8444-555555555555',
      requestedAt: '2026-11-15T00:00:00.000Z',
    })
    const result = writeEnvelopeVerified(second)
    expect(result.kind).toBe('conflict')
    if (result.kind === 'conflict') {
      expect(result.envelope.key).toBe(first.key)
    }
  })

  it('损坏信封不被覆盖，进入 corrupt 保护', () => {
    window.localStorage.setItem(envelopeKey(UID, PID), '{broken')
    expect(readEnvelope(UID, PID)).toMatchObject({
      kind: 'corrupt',
      reason: 'bad-json',
    })
    const result = writeEnvelopeVerified(makeEnvelope())
    expect(result.kind).toBe('unavailable')
    expect(window.localStorage.getItem(envelopeKey(UID, PID))).toBe('{broken')
  })

  it('普通保存不触碰信封（多标签防覆盖）', () => {
    const envelope = makeEnvelope()
    writeEnvelopeVerified(envelope)
    persistDraft(makeDraft({ answers: { 11: 'B' } }))
    const after = readEnvelope(UID, PID)
    expect(after.kind).toBe('valid')
    if (after.kind === 'valid') {
      expect(after.envelope.key).toBe(envelope.key)
      expect(after.envelope.frozenPayload).toEqual(envelope.frozenPayload)
    }
  })

  it('信封不参与草稿淘汰', () => {
    writeEnvelopeVerified(makeEnvelope())
    const base = Date.now()
    for (let index = 0; index < MAX_DRAFTS_PER_USER + 1; index += 1) {
      const paperId = 200 + index
      writeDraft(
        makeDraft({
          examPaperId: paperId,
          updatedAt: new Date(base + index * 1000).toISOString(),
        }),
      )
    }
    enforceDraftLimit(UID, base + 60_000)
    expect(readEnvelope(UID, PID).kind).toBe('valid')
  })

  it('removeEnvelope 删除', () => {
    writeEnvelopeVerified(makeEnvelope())
    removeEnvelope(UID, PID)
    expect(readEnvelope(UID, PID).kind).toBe('none')
  })
})

describe('T-14 提交标记', () => {
  it('写入/读取/写入前检查', () => {
    expect(writeSubmitted(makeSubmittedCache()).kind).toBe('ok')
    expect(hasSubmittedMarker(UID, PID)).toBe(true)
    const read = readSubmitted(UID, PID)
    expect(read.kind).toBe('valid')
  })

  it('TTL >= 30 天过期并删除', () => {
    const cache = makeSubmittedCache({ savedAt: new Date().toISOString() })
    writeSubmitted(cache)
    const now = Date.now()
    expect(readSubmitted(UID, PID, now + SUBMITTED_TTL_MS - 1000).kind).toBe('valid')
    expect(readSubmitted(UID, PID, now + SUBMITTED_TTL_MS).kind).toBe('none')
    expect(window.localStorage.getItem(submittedKey(UID, PID))).toBeNull()
  })

  it('API-3 false 时删除标记', () => {
    writeSubmitted(makeSubmittedCache())
    removeSubmitted(UID, PID)
    expect(readSubmitted(UID, PID).kind).toBe('none')
  })

  it('submittedAt=null 的标记合法且刷新后保持只读依据', () => {
    writeSubmitted(makeSubmittedCache({ submittedAt: null, summary: null }))
    const read = readSubmitted(UID, PID)
    expect(read.kind).toBe('valid')
    if (read.kind === 'valid') {
      expect(read.cache.submittedAt).toBeNull()
      expect(read.cache.summary).toBeNull()
    }
  })
})

describe('T-15 存储不可用降级', () => {
  it('localStorage 访问抛错时返回 unavailable，不崩溃', () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, 'localStorage')
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('denied')
      },
    })
    try {
      expect(readDraft(UID, PID).kind).toBe('unavailable')
      expect(readEnvelope(UID, PID).kind).toBe('unavailable')
      expect(readSubmitted(UID, PID).kind).toBe('unavailable')
      expect(writeDraft(makeDraft()).kind).toBe('unavailable')
      expect(writeEnvelopeVerified(makeEnvelope()).kind).toBe('unavailable')
      expect(persistDraft(makeDraft()).kind).toBe('unavailable')
    } finally {
      if (descriptor) {
        Object.defineProperty(window, 'localStorage', descriptor)
      }
    }
  })
})

describe('索引', () => {
  it('写入/读取/清理，hasPending 跟随信封', () => {
    writeIndexEntry(UID, {
      examPaperId: PID,
      paperLabel: 'label',
      updatedAt: new Date().toISOString(),
      answeredCount: 2,
      totalCount: 4,
      hasPending: false,
    })
    expect(readIndex(UID).entries).toHaveLength(1)
    expect(window.localStorage.getItem(indexKey(UID))).not.toBeNull()

    writeEnvelopeVerified(makeEnvelope())
    persistDraft(makeDraft())
    expect(readIndex(UID).entries[0]?.hasPending).toBe(true)

    clearDraftAndIndex(UID, PID)
    expect(readIndex(UID).entries).toHaveLength(0)
  })
})
