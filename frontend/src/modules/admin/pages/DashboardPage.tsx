import { DashboardOutlined } from '@ant-design/icons'
import { Result } from 'antd'

export default function DashboardPage() {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Result
        icon={<DashboardOutlined />}
        title="管理后台概览"
        subTitle="管理后台功能开发中，后续将提供用户总数、生成图片数、Token 统计等概览。"
      />
    </div>
  )
}
