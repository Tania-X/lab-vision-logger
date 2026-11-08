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
def admin_session_token():
    """管理员会话令牌"""
    return "admin_session_token_123"

class TestAdminAPI:
    """测试管理员API"""

    def test_get_table_list_success(self, client, mock_db, admin_session_token):
        """测试获取表列表成功"""
        expected_tables = ["users", "event_logs", "emergencies", "person_appearances"]

        with patch('web_api.dependencies.get_current_user') as mock_get_user, \
             patch('web_api.routers.admin.SeekDBClient') as mock_db_class:

            mock_get_user.return_value = {
                "user_id": "admin_001",
                "username": "admin",
                "role": "admin"
            }
            mock_db_class.return_value = mock_db
            mock_db.get_table_list.return_value = expected_tables

            response = client.get("/admin/tables",
                                headers={"Authorization": f"Bearer {admin_session_token}"})

            assert response.status_code == 200
            data = response.json()
            assert data == expected_tables

    def test_get_table_list_unauthorized(self, client, mock_db, valid_session_token):
        """测试非管理员用户访问表列表"""
        with patch('web_api.dependencies.get_current_user') as mock_get_user:
            mock_get_user.return_value = {
                "user_id": "user_001",
                "username": "regular_user",
                "role": "user"  # 非管理员
            }

            response = client.get("/admin/tables",
                                headers={"Authorization": f"Bearer {valid_session_token}"})

            assert response.status_code == 403

    def test_get_table_data_success(self, client, mock_db, admin_session_token):
        """测试获取表数据成功"""
        table_name = "users"
        mock_data = [
            {"user_id": "user_001", "username": "testuser", "role": "user"},
            {"user_id": "user_002", "username": "admin", "role": "admin"}
        ]
        total_count = 2

        with patch('web_api.dependencies.get_current_user') as mock_get_user, \
             patch('web_api.routers.admin.SeekDBClient') as mock_db_class:

            mock_get_user.return_value = {
                "user_id": "admin_001",
                "username": "admin",
                "role": "admin"
            }
            mock_db_class.return_value = mock_db
            mock_db.query_table.return_value = (mock_data, total_count)

            response = client.get(f"/admin/table/{table_name}?page=1&limit=10",
                                headers={"Authorization": f"Bearer {admin_session_token}"})

            assert response.status_code == 200
            data = response.json()
            assert data["data"] == mock_data
            assert data["total"] == total_count
            assert data["page"] == 1
            assert data["limit"] == 10

            # 验证数据库调用
            mock_db.query_table.assert_called_once_with(table_name, page=1, limit=10)

    def test_get_table_data_invalid_table(self, client, mock_db, admin_session_token):
        """测试访问无效表名"""
        invalid_table = "nonexistent_table"

        with patch('web_api.dependencies.get_current_user') as mock_get_user, \
             patch('web_api.routers.admin.SeekDBClient') as mock_db_class:

            mock_get_user.return_value = {
                "user_id": "admin_001",
                "username": "admin",
                "role": "admin"
            }
            mock_db_class.return_value = mock_db
            mock_db.query_table.side_effect = ValueError("表不存在")

            response = client.get(f"/admin/table/{invalid_table}",
                                headers={"Authorization": f"Bearer {admin_session_token}"})

            assert response.status_code == 400

    def test_vector_search_success(self, client, mock_db, admin_session_token):
        """测试向量搜索成功"""
        search_query = "实验室实验"
        mock_results = [
            {"id": "log_001", "content": "用户在实验室进行化学实验", "similarity": 0.95},
            {"id": "log_002", "content": "实验室内设备操作", "similarity": 0.87}
        ]

        with patch('web_api.dependencies.get_current_user') as mock_get_user, \
             patch('web_api.routers.admin.EmbeddingService') as mock_embedding_class, \
             patch('web_api.routers.admin.SeekDBClient') as mock_db_class:

            mock_get_user.return_value = {
                "user_id": "admin_001",
                "username": "admin",
                "role": "admin"
            }

            mock_embedding = MagicMock()
            mock_embedding_class.return_value = mock_embedding
            mock_embedding.encode_text.return_value = [0.1] * 1024  # 模拟向量

            mock_db_class.return_value = mock_db
            mock_db.vector_search.return_value = mock_results

            response = client.post("/admin/vector-search",
                                 json={"query": search_query, "limit": 5},
                                 headers={"Authorization": f"Bearer {admin_session_token}"})

            assert response.status_code == 200
            data = response.json()
            assert data == mock_results

            # 验证调用链
            mock_embedding.encode_text.assert_called_once_with(search_query)
            mock_db.vector_search.assert_called_once()

    def test_vector_search_empty_query(self, client, mock_db, admin_session_token):
        """测试空查询的向量搜索"""
        with patch('web_api.dependencies.get_current_user') as mock_get_user:
            mock_get_user.return_value = {
                "user_id": "admin_001",
                "username": "admin",
                "role": "admin"
            }

            response = client.post("/admin/vector-search",
                                 json={"query": "", "limit": 5},
                                 headers={"Authorization": f"Bearer {admin_session_token}"})

            assert response.status_code == 422  # 验证错误

class TestAdminAPIAuthorization:
    """测试管理员API的权限控制"""

    def test_admin_only_endpoints_block_regular_users(self, client):
        """测试管理员专用端点阻止普通用户访问"""
        endpoints = [
            "/admin/tables",
            "/admin/table/users",
            "/admin/vector-search"
        ]

        for endpoint in endpoints:
            with patch('web_api.dependencies.get_current_user') as mock_get_user:
                mock_get_user.return_value = {
                    "user_id": "user_001",
                    "username": "regular_user",
                    "role": "user"
                }

                if endpoint == "/admin/vector-search":
                    response = client.post(endpoint, json={"query": "test"})
                else:
                    response = client.get(endpoint)

                assert response.status_code == 403

    def test_admin_endpoints_allow_admin_users(self, client, mock_db):
        """测试管理员端点允许管理员访问"""
        with patch('web_api.dependencies.get_current_user') as mock_get_user, \
             patch('web_api.routers.admin.SeekDBClient') as mock_db_class:

            mock_get_user.return_value = {
                "user_id": "admin_001",
                "username": "admin",
                "role": "admin"
            }
            mock_db_class.return_value = mock_db
            mock_db.get_table_list.return_value = ["users"]

            response = client.get("/admin/tables",
                                headers={"Authorization": "Bearer admin_token"})

            assert response.status_code == 200