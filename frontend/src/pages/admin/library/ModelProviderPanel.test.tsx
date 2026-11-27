import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { getProviders, type LibraryProvider } from '../../../api/library'
import ModelProviderPanel from './ModelProviderPanel'

vi.mock('../../../api/library', () => ({getProviders:vi.fn()}))
const provider: LibraryProvider = {
  provider:'bailian', requested_model:'qwen3.8-flash',region:'beijing',credentials_configured:true,
  configuration_ready:true,issues:[],currency:'CNY',usd_per_currency:'0.15',
  exchange_rate_source:'Synthetic rate evidence',exchange_rate_effective_at:'2026-11-24T09:15:00+08:00',
}
beforeEach(() => vi.mocked(getProviders).mockReset())

it('显示所选模型的配置与换算依据，并报告就绪状态', async () => {
  vi.mocked(getProviders).mockResolvedValue({items:[provider],connectivity_checked:false})
  const ready = vi.fn()
  render(<ModelProviderPanel value="bailian" onChange={vi.fn()} onReadyChange={ready} disabled={false}/>)
  expect(await screen.findByText('模型配置已就绪')).toBeInTheDocument()
  expect(screen.getByText('Synthetic rate evidence')).toBeInTheDocument()
  expect(screen.getByText('1 元人民币 ≈ 0.15000000 美元')).toBeInTheDocument()
  await waitFor(() => expect(ready).toHaveBeenLastCalledWith(true))
  expect(getProviders).toHaveBeenCalledTimes(1)
})

it('缺配置或读取失败时禁止生成，刷新配置后恢复', async () => {
  vi.mocked(getProviders).mockRejectedValueOnce(new Error('配置服务暂时不可用')).mockResolvedValueOnce({
    items:[{...provider,configuration_ready:false,issues:[{code:'CREDENTIALS_MISSING',message:'尚未配置密钥'}]}],connectivity_checked:false,
  })
  const ready = vi.fn(), user = userEvent.setup()
  render(<ModelProviderPanel value="bailian" onChange={vi.fn()} onReadyChange={ready} disabled={false}/>)
  expect(await screen.findByText('模型配置读取失败')).toBeInTheDocument()
  expect(ready).toHaveBeenLastCalledWith(false)
  await user.click(screen.getByRole('button',{name:'刷新模型配置'}))
  expect(await screen.findByText('尚未配置密钥')).toBeInTheDocument()
  expect(ready).toHaveBeenLastCalledWith(false)
})
