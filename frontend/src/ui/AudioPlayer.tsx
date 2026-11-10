import { useEffect, useRef, useState } from 'react'
import { CaretRightOutlined, PauseOutlined, ReloadOutlined, SoundOutlined } from '@ant-design/icons'
import { Button, Slider, Space, Spin, Typography } from 'antd'
import { loadAudioSource } from '../api/audio'
import type { AudioSource } from '../api/audio'
import { isAbortError } from '../utils/concurrency'
import { formatDuration } from '../utils/format'

interface AudioPlayerProps {
  examPaperId: number
  /** 接口给出的总时长，媒体元数据就绪前用作占位。 */
  fallbackDurationMs?: number | null
  /** 是否吸顶（学生端整卷页使用）。 */
  sticky?: boolean
}

type LoadStatus = 'loading' | 'ready' | 'error'

/**
 * 整段下载后本地播放的音频播放器。
 *
 * - 请求走 api/audio.ts 的二进制通道，不经过 JSON 外壳拦截器；
 * - 组件卸载、切换试卷、重试时取消请求并释放对象 URL；
 * - 进度拖动只在已下载数据内定位，不产生服务端 Range 请求。
 */
export default function AudioPlayer({ examPaperId, fallbackDurationMs, sticky }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const sourceRef = useRef<AudioSource | null>(null)
  const [objectUrl, setObjectUrl] = useState<string | null>(null)
  const [status, setStatus] = useState<LoadStatus>('loading')
  const [errorText, setErrorText] = useState('')
  const [playing, setPlaying] = useState(false)
  const [currentMs, setCurrentMs] = useState(0)
  const [mediaDurationMs, setMediaDurationMs] = useState(0)
  const [volume, setVolume] = useState(1)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setStatus('loading')
    setErrorText('')
    setPlaying(false)
    setCurrentMs(0)
    setMediaDurationMs(0)
    setObjectUrl(null)

    loadAudioSource(examPaperId, controller.signal)
      .then((source) => {
        if (controller.signal.aborted) {
          source.release()
          return
        }
        sourceRef.current = source
        setObjectUrl(source.objectUrl)
        setStatus('ready')
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) {
          return
        }
        setStatus('error')
        setErrorText(error instanceof Error ? error.message : '音频加载失败，请稍后重试')
      })

    return () => {
      controller.abort()
      sourceRef.current?.release()
      sourceRef.current = null
    }
  }, [examPaperId, reloadKey])

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = volume
    }
  }, [volume, objectUrl])

  const durationMs = mediaDurationMs > 0 ? mediaDurationMs : (fallbackDurationMs ?? 0)

  const togglePlay = async () => {
    const element = audioRef.current
    if (!element || status !== 'ready') {
      return
    }
    if (element.paused) {
      try {
        await element.play()
      } catch {
        setStatus('error')
        setErrorText('浏览器未能播放该音频，请重试')
      }
    } else {
      element.pause()
    }
  }

  const seekTo = (value: number) => {
    const element = audioRef.current
    if (element && status === 'ready') {
      element.currentTime = value
      setCurrentMs(value * 1000)
    }
  }

  return (
    <div className={sticky ? 'player-bar player-bar--sticky' : 'player-bar'}>
      <audio
        ref={audioRef}
        src={objectUrl ?? undefined}
        preload="auto"
        onLoadedMetadata={() => {
          const element = audioRef.current
          if (element && Number.isFinite(element.duration)) {
            setMediaDurationMs(element.duration * 1000)
          }
        }}
        onTimeUpdate={() => {
          const element = audioRef.current
          if (element) {
            setCurrentMs(element.currentTime * 1000)
          }
        }}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onError={() => {
          if (status === 'ready') {
            setStatus('error')
            setErrorText('音频加载失败，请点击重试')
          }
        }}
      />

      {status === 'loading' ? (
        <Space size={8}>
          <Spin size="small" />
          <Typography.Text type="secondary">音频加载中…</Typography.Text>
        </Space>
      ) : (
        <Button
          shape="circle"
          type="primary"
          aria-label={playing ? '暂停' : '播放'}
          icon={playing ? <PauseOutlined /> : <CaretRightOutlined />}
          onClick={() => void togglePlay()}
          disabled={status === 'error'}
        />
      )}

      <Typography.Text className="player-time">{formatDuration(currentMs)}</Typography.Text>

      <Slider
        className="player-track"
        min={0}
        max={Math.max(1, Math.round(durationMs / 1000))}
        step={1}
        value={Math.min(Math.round(currentMs / 1000), Math.round(durationMs / 1000))}
        onChange={(value) => setCurrentMs(value * 1000)}
        onChangeComplete={(value) => seekTo(value)}
        tooltip={{ formatter: (value) => formatDuration((value ?? 0) * 1000) }}
        disabled={status !== 'ready'}
      />

      <Typography.Text className="player-time">{formatDuration(durationMs)}</Typography.Text>

      <Space size={6} className="player-volume">
        <SoundOutlined className="player-volume-icon" />
        <Slider
          min={0}
          max={1}
          step={0.05}
          value={volume}
          onChange={(value) => setVolume(value)}
          tooltip={{ formatter: (value) => `${Math.round((value ?? 0) * 100)}%` }}
          aria-label="音量"
        />
      </Space>

      {status === 'error' && (
        <Space size={8}>
          <Typography.Text type="danger">{errorText}</Typography.Text>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => setReloadKey((key) => key + 1)}
          >
            重试
          </Button>
        </Space>
      )}
    </div>
  )
}
