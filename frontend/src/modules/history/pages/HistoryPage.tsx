import { HistoryOutlined } from '@ant-design/icons'
import { Result } from 'antd'

export default function HistoryPage() {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Result
        icon={<HistoryOutlined />}
        title="历史作品"
        subTitle="历史作品功能开发中，后续将展示最终成功的正式图，支持预览与下载。"
      />
    </div>
  )
}
