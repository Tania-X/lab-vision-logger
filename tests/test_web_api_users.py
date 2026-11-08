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
    """有效的会话令牌"""
    return "valid_session_token_123"

class TestUserAPI:
    """测试用户管理API"""

    def test_get_user_profile_success(self, client, mock_db, valid_session_token):
        """测试获取用户资料成功"""
        expected_user = {
            "user_id": "user_123",
            "username": "testuser",
            "role": "user"
        }

        with patch('web_api.dependencies.get_current_user') as mock_get_user, \
             patch('web_api.routers.users.SeekDBClient') as mock_db_class:

            mock_get_user.return_value = expected_user
            mock_db_class.return_value = mock_db

            response = client.get("/users/me",
                                headers={"Authorization": f"Bearer {valid_session_token}"})

            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == "user_123"
            assert data["username"] == "testuser"
            assert data["role"] == "user"

    def test_get_user_profile_unauthorized(self, client):
        """测试未授权访问用户资料"""
        response = client.get("/users/me")

        assert response.status_code == 401

    def test_generate_qr_code_success(self, client, mock_db, valid_session_token):
        """测试生成二维码成功"""
        user_data = {
            "user_id": "user_123",
            "username": "testuser",
            "public_key": "test_public_key_pem"
        }

        with patch('web_api.dependencies.get_current_user') as mock_get_user, \
             patch('web_api.routers.users.generate_qr_data') as mock_qr_gen, \
             patch('web_api.routers.users.SeekDBClient') as mock_db_class:

            mock_get_user.return_value = user_data
            mock_qr_gen.return_value = {"qr_code": "encoded_qr_data"}
            mock_db_class.return_value = mock_db

            response = client.get("/users/me/qrcode",
                                headers={"Authorization": f"Bearer {valid_session_token}"})

            assert response.status_code == 200
            data = response.json()
            assert "qr_code" in data
            assert data["qr_code"] == "encoded_qr_data"

            # 验证QR数据生成调用
            mock_qr_gen.assert_called_once_with("user_123", "test_public_key_pem")

    def test_generate_qr_code_unauthorized(self, client):
        """测试未授权生成二维码"""
        response = client.get("/users/me/qrcode")

        assert response.status_code == 401

class TestUserAPIDependencies:
    """测试用户API的依赖注入"""

    def test_get_db_dependency(self):
        """测试数据库依赖注入"""
        with patch('web_api.dependencies.SeekDBClient') as mock_db_class:
            mock_db_instance = MagicMock()
            mock_db_class.return_value = mock_db_instance

            from web_api.dependencies import get_db
            result = get_db()

            assert result == mock_db_instance
            mock_db_class.assert_called_once()

    def test_get_current_user_from_session(self, mock_db):
        """测试从会话获取当前用户"""
        session_token = "valid_session_123"
        expected_user = {
            "user_id": "user_123",
            "username": "testuser",
            "role": "user"
        }

        with patch('web_api.dependencies.verify_session') as mock_verify, \
             patch('web_api.dependencies.SeekDBClient') as mock_db_class:

            mock_verify.return_value = "user_123"
            mock_db_class.return_value = mock_db
            mock_db.get_user_by_id.return_value = expected_user

            from web_api.dependencies import get_current_user
            result = get_current_user(session_token)

            assert result == expected_user
            mock_verify.assert_called_once_with(session_token)
            mock_db.get_user_by_id.assert_called_once_with("user_123")

    def test_get_current_user_invalid_session(self, mock_db):
        """测试无效会话"""
        with patch('web_api.dependencies.verify_session') as mock_verify:
            mock_verify.return_value = None

            from web_api.dependencies import get_current_user

            with pytest.raises(Exception):  # 应该抛出HTTPException
                get_current_user("invalid_token")