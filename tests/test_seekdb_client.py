import pytest
from unittest.mock import MagicMock, patch
from storage.seekdb_client import SeekDBClient
from storage.models import EventLog
import json

@pytest.fixture
def mock_connection():
    """模拟数据库连接"""
    return MagicMock()

@pytest.fixture
def mock_cursor():
    """模拟数据库游标"""
    cursor = MagicMock()
    # 配置上下文管理器：with cursor as c: 中的 c 就是 cursor 本身
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    return cursor

@pytest.fixture
def mock_db_client(mock_connection, mock_cursor):
    """模拟SeekDBClient实例"""
    with patch('storage.seekdb_client.pymysql.connect') as mock_connect:
        mock_connect.return_value = mock_connection
        # cursor() 返回 mock_cursor，且 mock_cursor 已配置好 __enter__
        mock_connection.cursor.return_value = mock_cursor
        client = SeekDBClient()
        yield client

class TestSeekDBClientConnection:
    """测试SeekDBClient连接相关功能"""

    @patch('storage.seekdb_client.pymysql.connect')
    def test_init_success(self, mock_connect):
        """测试客户端初始化成功"""
        mock_connection = MagicMock()
        mock_connect.return_value = mock_connection

        client = SeekDBClient()

        assert client.connection == mock_connection
        mock_connect.assert_called_once()

    @patch('storage.seekdb_client.pymysql.connect')
    def test_init_connection_error(self, mock_connect):
        """测试连接失败的情况"""
        mock_connect.side_effect = Exception("Connection failed")

        with pytest.raises(ConnectionError, match="无法连接到 SeekDB"):
            SeekDBClient()

class TestSeekDBClientCRUD:
    """测试SeekDBClient的CRUD操作"""

    def test_insert_event_log_success(self, mock_db_client, mock_connection, mock_cursor):
        """测试成功插入事件日志"""
        # 准备测试数据
        event = EventLog(
            event_id="test_event_001",
            segment_id="seg_001",
            start_time="2024-01-01T10:00:00",
            end_time="2024-01-01T10:01:00",
            event_type="action",
            structured={"person_id": "p1", "equipment": ["test"]},
            raw_text="测试事件"
        )

        # 执行插入
        result = mock_db_client.insert_event_log(event)

        # 验证调用
        assert result is None  # insert_event_log没有返回值
        mock_cursor.execute.assert_called_once()
        mock_connection.commit.assert_called_once()

        # 验证SQL参数
        args, kwargs = mock_cursor.execute.call_args
        sql, params = args
        assert "INSERT INTO logs_raw" in sql
        assert params[0] == "test_event_001"
        assert json.loads(params[5]) == {"person_id": "p1", "equipment": ["test"]}

    def test_insert_event_log_rollback_on_error(self, mock_db_client, mock_connection, mock_cursor):
        """测试插入失败时的回滚"""
        mock_cursor.execute.side_effect = Exception("DB Error")

        event = EventLog(
            event_id="test_event_001",
            segment_id="seg_001",
            start_time="2024-01-01T10:00:00",
            end_time="2024-01-01T10:01:00",
            event_type="action",
            structured={"person_id": "p1"},
            raw_text="测试事件"
        )

        with pytest.raises(RuntimeError, match="插入事件日志失败"):
            mock_db_client.insert_event_log(event)

        mock_connection.rollback.assert_called_once()
        mock_connection.commit.assert_not_called()

    def test_get_pending_emergency_count(self, mock_db_client, mock_cursor):
        """测试获取待处理紧急事件数量"""
        mock_cursor.fetchone.return_value = {"count": 5}

        result = mock_db_client.get_pending_emergency_count()

        assert result == 5
        mock_cursor.execute.assert_called_once_with("SELECT COUNT(*) as count FROM emergencies WHERE status = 'PENDING'")

    def test_resolve_emergency_success(self, mock_db_client, mock_connection, mock_cursor):
        """测试成功解决紧急事件"""
        mock_cursor.rowcount = 1

        result = mock_db_client.resolve_emergency("emergency_001")

        assert result is True
        mock_connection.commit.assert_called_once()

        args, kwargs = mock_cursor.execute.call_args
        sql, params = args
        assert "UPDATE emergencies" in sql
        assert params == ("emergency_001",)

    def test_get_user_public_key_success(self, mock_db_client, mock_cursor):
        """测试成功获取用户公钥"""
        mock_cursor.fetchone.return_value = {"public_key_pem": "test_public_key"}

        result = mock_db_client.get_user_public_key("user_001")

        assert result == "test_public_key"

    def test_get_user_public_key_not_found(self, mock_db_client, mock_cursor):
        """测试用户不存在的情况"""
        mock_cursor.fetchone.return_value = None

        # 实际代码捕获 ValueError 并包装为 RuntimeError
        with pytest.raises(RuntimeError, match="获取用户公钥失败: 用户 user_001 不存在"):
            mock_db_client.get_user_public_key("user_001")

class TestSeekDBClientEncryption:
    """测试SeekDBClient的加密相关功能"""

    def test_insert_field_encryption_key(self, mock_db_client, mock_connection, mock_cursor):
        """测试插入字段加密密钥"""
        mock_db_client.insert_field_encryption_key(
            ref_id="event_001",
            field_path="appearance",
            user_id="user_001",
            encrypted_dek="encrypted_key_data"
        )

        mock_cursor.execute.assert_called_once()
        mock_connection.commit.assert_called_once()

        args, kwargs = mock_cursor.execute.call_args
        sql, params = args
        assert "INSERT INTO field_encryption_keys" in sql
        assert params == ("event_001", "1970-01-01", "appearance", "user_001", "encrypted_key_data")

    def test_insert_appearance_record(self, mock_db_client, mock_connection, mock_cursor):
        """测试插入人物外貌记录"""
        mock_db_client.insert_appearance_record(
            person_id="p1",
            date="2024-01-01",
            user_id="user_001",
            appearance="encrypted_appearance_data"
        )

        mock_cursor.execute.assert_called_once()
        mock_connection.commit.assert_called_once()

        args, kwargs = mock_cursor.execute.call_args
        sql, params = args
        assert "INSERT INTO person_appearances" in sql
        assert params == ("p1", "2024-01-01", "user_001", "encrypted_appearance_data")