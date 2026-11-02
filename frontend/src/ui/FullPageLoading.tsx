import { Spin } from 'antd'

/** 恢复登录态 / 页面懒加载时的整页加载态。 */
export default function FullPageLoading() {
  return (
    <div className="full-page-center">
      <Spin size="large" />
    </div>
  )
}
