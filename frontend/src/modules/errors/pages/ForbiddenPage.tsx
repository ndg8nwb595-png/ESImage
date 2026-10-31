import { Button, Result } from 'antd'
import { useNavigate } from 'react-router-dom'

export default function ForbiddenPage() {
  const navigate = useNavigate()
  return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Result
        status="403"
        title="403"
        subTitle="抱歉，你没有权限访问该页面。"
        extra={
          <Button type="primary" onClick={() => navigate('/workspace')}>
            返回工作台
          </Button>
        }
      />
    </div>
  )
}
