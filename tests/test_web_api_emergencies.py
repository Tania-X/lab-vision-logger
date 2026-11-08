import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from web_api.main import app

@pytest.fixture
def client():
    """FastAPI测试客户端"""
    return TestClient(app)

@pytest.fixture
def mock_db():
    """模拟SeekDBClient"""
    return MagicMock()

@pytest.fixture
def valid_session_token():
    """有效的用户会话令牌"""
    return "user_session_token_123"

@pytest.fixture
def admin_session_token():
    """管理员会话令牌"""
    return "admin_session_token_123"

class TestEmergencyAPI:
    """测试紧急事件API"""

    def test_get_pending_count_success(self, client, mock_db, valid_session_token):
        """测试获取待处理紧急事件数量成功"""
        with patch('web_api.dependencies.get_current_user') as mock_get_user, \
             patch('web_api.routers.emergencies.SeekDBClient') as mock_db_class:

            mock_get_user.return_value = {
                "user_id": "user_001",
                "username": "testuser",
                "role": "user"
            }
            mock_db_class.return_value = mock_db
            mock_db.get_pending_emergency_count.return_value = 3

            response = client.get("/emergencies/pending_count",
                                headers={"Authorization": f"Bearer {valid_session_token}"})

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 3

    def test_get_pending_count_unauthorized(self, client):
        """测试未授权访问待处理数量"""
        response = client.get("/emergencies/pending_count")

        assert response.status_code == 401

    def test_list_emergencies_success(self, client, mock_db, valid_session_token):
        """测试列出紧急事件成功"""
        mock_emergencies = [
            {
                "emergency_id": "emerg_001",
                "description": "火灾警报",
                "status": "PENDING",
                "start_time": "2024-01-01T10:00:00",
                "segment_id": "seg_001"
            },
            {
                "emergency_id": "emerg_002",
                "description": "化学品泄漏",
                "status": "RESOLVED",
                "start_time": "2024-01-01T10:05:00",
                "segment_id": "seg_002"
            }
        ]

        with patch('web_api.dependencies.get_current_user') as mock_get_user, \
             patch('web_api.routers.emergencies.SeekDBClient') as mock_db_class:

            mock_get_user.return_value = {
                "user_id": "user_001",
                "username": "testuser",
                "role": "user"
            }
            mock_db_class.return_value = mock_db
            mock_db.get_emergencies.return_value = mock_emergencies
            mock_db.get_emergency_count.return_value = 2

            response = client.get("/emergencies/list?page=1&limit=10",
                                headers={"Authorization": f"Bearer {valid_session_token}"})

            assert response.status_code == 200
            data = response.json()
            assert data["emergencies"] == mock_emergencies
            assert data["total"] == 2
            assert data["page"] == 1
            assert data["limit"] == 10

    def test_list_emergencies_with_filters(self, client, mock_db, valid_session_token):
        """测试带过滤条件的紧急事件列表"""
        with patch('web_api.dependencies.get_current_user') as mock_get_user, \
             patch('web_api.routers.emergencies.SeekDBClient') as mock_db_class:

            mock_get_user.return_value = {
                "user_id": "user_001",
                "username": "testuser",
                "role": "user"
            }
            mock_db_class.return_value = mock_db
            mock_db.get_emergencies.return_value = []
            mock_db.get_emergency_count.return_value = 0

            response = client.get("/emergencies/list?status=RESOLVED&page=1&limit=5",
                                headers={"Authorization": f"Bearer {valid_session_token}"})

            assert response.status_code == 200

            # 验证过滤参数传递
            mock_db.get_emergencies.assert_called_once()
            call_args = mock_db.get_emergencies.call_args
            assert call_args[1]["status"] == "RESOLVED"
            assert call_args[1]["limit"] == 5
            assert call_args[1]["offset"] == 0

    def test_resolve_emergency_success(self, client, mock_db, admin_session_token):
        """测试管理员成功解决紧急事件"""
        emergency_id = "emerg_001"

        with patch('web_api.dependencies.get_current_user') as mock_get_user, \
             patch('web_api.routers.emergencies.SeekDBClient') as mock_db_class:

            mock_get_user.return_value = {
                "user_id": "admin_001",
                "username": "admin",
                "role": "admin"
            }
            mock_db_class.return_value = mock_db
            mock_db.resolve_emergency.return_value = True

            response = client.put(f"/emergencies/{emergency_id}/resolve",
                                headers={"Authorization": f"Bearer {admin_session_token}"})

            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "紧急事件已解决"

            # 验证数据库调用
            mock_db.resolve_emergency.assert_called_once_with(emergency_id)

    def test_resolve_emergency_not_found(self, client, mock_db, admin_session_token):
        """测试解决不存在的紧急事件"""
        emergency_id = "nonexistent_emerg"

        with patch('web_api.dependencies.get_current_user') as mock_get_user, \
             patch('web_api.routers.emergencies.SeekDBClient') as mock_db_class:

            mock_get_user.return_value = {
                "user_id": "admin_001",
                "username": "admin",
                "role": "admin"
            }
            mock_db_class.return_value = mock_db
            mock_db.resolve_emergency.return_value = False  # 没有行受到影响

            response = client.put(f"/emergencies/{emergency_id}/resolve",
                                headers={"Authorization": f"Bearer {admin_session_token}"})

            assert response.status_code == 404
            data = response.json()
            assert "未找到" in data["detail"]

    def test_resolve_emergency_regular_user_forbidden(self, client, mock_db, valid_session_token):
        """测试普通用户无法解决紧急事件"""
        emergency_id = "emerg_001"

        with patch('web_api.dependencies.get_current_user') as mock_get_user:
            mock_get_user.return_value = {
                "user_id": "user_001",
                "username": "regular_user",
                "role": "user"  # 非管理员
            }

            response = client.put(f"/emergencies/{emergency_id}/resolve",
                                headers={"Authorization": f"Bearer {valid_session_token}"})

            assert response.status_code == 403

class TestEmergencyAPIDataValidation:
    """测试紧急事件API的数据验证"""

    def test_list_emergencies_invalid_page(self, client, valid_session_token):
        """测试无效页码参数"""
        with patch('web_api.dependencies.get_current_user') as mock_get_user:
            mock_get_user.return_value = {
                "user_id": "user_001",
                "username": "testuser",
                "role": "user"
            }

            response = client.get("/emergencies/list?page=0&limit=10",
                                headers={"Authorization": f"Bearer {valid_session_token}"})

            assert response.status_code == 422  # 参数验证错误

    def test_list_emergencies_invalid_limit(self, client, valid_session_token):
        """测试无效限制参数"""
        with patch('web_api.dependencies.get_current_user') as mock_get_user:
            mock_get_user.return_value = {
                "user_id": "user_001",
                "username": "testuser",
                "role": "user"
            }

            response = client.get("/emergencies/list?page=1&limit=0",
                                headers={"Authorization": f"Bearer {valid_session_token}"})

            assert response.status_code == 422

    def test_resolve_emergency_invalid_id(self, client, admin_session_token):
        """测试无效紧急事件ID"""
        invalid_id = ""

        with patch('web_api.dependencies.get_current_user') as mock_get_user:
            mock_get_user.return_value = {
                "user_id": "admin_001",
                "username": "admin",
                "role": "admin"
            }

            response = client.put(f"/emergencies/{invalid_id}/resolve",
                                headers={"Authorization": f"Bearer {admin_session_token}"})

            assert response.status_code == 422  # 路径参数验证错误