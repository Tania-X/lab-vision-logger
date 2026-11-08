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

class TestAuthAPI:
    """测试认证API - 注册和登录功能"""

    def test_register_user_success(self, client, mock_db):
        """测试用户注册成功"""
        user_data = {
            "username": "testuser",
            "password": "testpass123",
            "public_key": "test_public_key"
        }

        # 模拟数据库操作
        with patch('web_api.routers.auth.hash_password') as mock_hash, \
             patch('web_api.routers.auth.SeekDBClient') as mock_db_class, \
             patch('web_api.routers.auth.generate_user_id') as mock_gen_id:

            mock_hash.return_value = "hashed_password"
            mock_gen_id.return_value = "user_123"
            mock_db_class.return_value = mock_db
            mock_db.insert_user.return_value = True

            response = client.post("/auth/register", json=user_data)

            assert response.status_code == 200
            data = response.json()
            assert "user_id" in data
            assert data["user_id"] == "user_123"

            # 验证数据库调用
            mock_db.insert_user.assert_called_once()
            call_args = mock_db.insert_user.call_args[0][0]
            assert call_args["username"] == "testuser"
            assert call_args["password_hash"] == "hashed_password"
            assert call_args["public_key_pem"] == "test_public_key"

    def test_register_user_duplicate_username(self, client, mock_db):
        """测试用户名重复注册"""
        user_data = {
            "username": "existinguser",
            "password": "testpass123",
            "public_key": "test_public_key"
        }

        with patch('web_api.routers.auth.SeekDBClient') as mock_db_class:
            mock_db_class.return_value = mock_db
            mock_db.insert_user.side_effect = Exception("用户名已存在")

            response = client.post("/auth/register", json=user_data)

            assert response.status_code == 400
            data = response.json()
            assert "detail" in data

    def test_register_user_invalid_data(self, client):
        """测试无效注册数据"""
        # 缺少必填字段
        invalid_data = {
            "username": "testuser"
            # 缺少password和public_key
        }

        response = client.post("/auth/register", json=invalid_data)

        assert response.status_code == 422  # Pydantic验证错误

    def test_login_success(self, client, mock_db):
        """测试登录成功"""
        login_data = {
            "username": "testuser",
            "password": "testpass123"
        }

        with patch('web_api.routers.auth.verify_password') as mock_verify, \
             patch('web_api.routers.auth.create_session') as mock_session, \
             patch('web_api.routers.auth.SeekDBClient') as mock_db_class:

            mock_verify.return_value = True
            mock_session.return_value = "session_token_123"
            mock_db_class.return_value = mock_db
            mock_db.get_user_by_username.return_value = {
                "user_id": "user_123",
                "username": "testuser",
                "role": "user",
                "password_hash": "hashed_pass"
            }

            response = client.post("/auth/login", json=login_data)

            assert response.status_code == 200
            data = response.json()
            assert "session_token" in data
            assert data["session_token"] == "session_token_123"

    def test_login_invalid_credentials(self, client, mock_db):
        """测试无效凭据登录"""
        login_data = {
            "username": "testuser",
            "password": "wrongpass"
        }

        with patch('web_api.routers.auth.verify_password') as mock_verify, \
             patch('web_api.routers.auth.SeekDBClient') as mock_db_class:

            mock_verify.return_value = False
            mock_db_class.return_value = mock_db

            response = client.post("/auth/login", json=login_data)

            assert response.status_code == 401
            data = response.json()
            assert "detail" in data

    def test_login_user_not_found(self, client, mock_db):
        """测试用户不存在的登录"""
        login_data = {
            "username": "nonexistent",
            "password": "testpass123"
        }

        with patch('web_api.routers.auth.SeekDBClient') as mock_db_class:
            mock_db_class.return_value = mock_db
            mock_db.get_user_by_username.return_value = None

            response = client.post("/auth/login", json=login_data)

            assert response.status_code == 401

    def test_login_invalid_request(self, client):
        """测试无效登录请求"""
        invalid_data = {
            "username": "testuser"
            # 缺少password
        }

        response = client.post("/auth/login", json=invalid_data)

        assert response.status_code == 422