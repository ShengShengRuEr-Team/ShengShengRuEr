import { useEffect, useState } from 'react'
import { Alert, Button, Descriptions, Select, Space, Typography } from 'antd'
import { getProviders, type LibraryProvider } from '../../../api/library'

interface Props {
  value: string
  onChange: (value: string) => void
  onReadyChange: (ready: boolean) => void
  disabled: boolean
}

export default function ModelProviderPanel({value, onChange, onReadyChange, disabled}: Props) {
  const [items, setItems] = useState<LibraryProvider[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(''); setItems([])
    void getProviders(controller.signal).then(result => {
      if (!controller.signal.aborted) setItems(result.items)
    }).catch(cause => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '无法读取模型配置')
    }).finally(() => {if (!controller.signal.aborted) setLoading(false)})
    return () => controller.abort()
  }, [refresh])
  const selected = items.find(item => item.provider === value)
  const ready = !loading && !error && Boolean(selected?.configuration_ready)
  useEffect(() => {onReadyChange(ready)}, [ready, onReadyChange])
  return <Space orientation="vertical" style={{width:'100%'}}>
    <Space wrap>
      <Typography.Text id="library-provider-label">生成模型</Typography.Text>
      <Select aria-labelledby="library-provider-label" value={value} onChange={onChange} disabled={disabled} loading={loading} style={{width:280}} options={[
        {value:'deepseek',label:'DeepSeek · deepseek-flash'},
        {value:'bailian',label:'千问 · qwen3.8-flash'},
      ]}/>
      <Button disabled={loading || disabled} onClick={() => setRefresh(current => current + 1)}>刷新模型配置</Button>
    </Space>
    {error ? <Alert type="error" showIcon title="模型配置读取失败" description={error}/> : !loading && (
      <Alert type={ready ? 'info' : 'warning'} showIcon title={ready ? '模型配置已就绪' : '模型配置待补齐'} description={ready
        ? '配置检查不发起模型调用。选择题目并提交生成后才会运行，实际调用仍受来源核听和累计预算限制。'
        : selected?.issues.map(issue => issue.message).join('；') || '所选模型尚未提供配置，请联系管理员检查。'}/>
    )}
    {selected?.provider === 'bailian' && <Descriptions size="small" column={{xs:1,md:2}} items={[
      {key:'region',label:'服务地域',children:({beijing:'北京',singapore:'新加坡'} as Record<string,string>)[selected.region] ?? selected.region},
      {key:'rate',label:'费用换算',children:selected.usd_per_currency ? `1 元人民币 ≈ ${Number(selected.usd_per_currency).toFixed(8)} 美元` : '待配置'},
      {key:'source',label:'汇率依据',span:2,children:selected.exchange_rate_source || '待配置'},
      {key:'time',label:'配置生效时间',span:2,children:selected.exchange_rate_effective_at ? new Date(selected.exchange_rate_effective_at).toLocaleString('zh-CN') : '待配置'},
    ]}/>}
  </Space>
}
