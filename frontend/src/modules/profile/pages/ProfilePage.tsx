import { UserOutlined } from '@ant-design/icons'
import { Result } from 'antd'

export default function ProfilePage() {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Result
        icon={<UserOutlined />}
        title="个人中心"
        subTitle="个人中心功能开发中，后续将支持修改显示名、邮箱与登录密码。"
      />
    </div>
  )
}
