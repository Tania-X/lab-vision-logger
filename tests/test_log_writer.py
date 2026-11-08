import pytest
from unittest.mock import patch, MagicMock
from log_writer.writer import LogWriter
from storage.models import EventLog, Emergency
from video_processing.interface import VideoUnderstandingResult

@pytest.fixture
def mock_db():
    """模拟SeekDBClient"""
    return MagicMock()

@pytest.fixture
def mock_encryption_service():
    """模拟加密服务"""
    return MagicMock()

@pytest.fixture
def writer(mock_db, mock_encryption_service):
    """创建测试用的LogWriter实例"""
    with patch('log_writer.writer.SeekDBClient') as mock_db_class, \
         patch('log_writer.writer.FieldEncryptionService') as mock_encrypt_class:

        mock_db_class.return_value = mock_db
        mock_encrypt_class.return_value = mock_encryption_service

        writer = LogWriter()
        return writer

class TestLogWriter:
    """测试日志写入器"""

    def test_init_with_default_db(self):
        """测试使用默认数据库初始化"""
        with patch('log_writer.writer.SeekDBClient') as mock_db_class, \
             patch('log_writer.writer.FieldEncryptionService') as mock_encrypt_class:

            writer = LogWriter()

            mock_db_class.assert_called_once()
            mock_encrypt_class.assert_called_once()

    def test_init_with_custom_db(self, mock_db):
        """测试使用自定义数据库初始化"""
        with patch('log_writer.writer.FieldEncryptionService') as mock_encrypt_class:
            writer = LogWriter(db_client=mock_db)

            # 验证没有创建新的DB实例
            mock_encrypt_class.assert_called_once()

    def test_write_events_success(self, writer, mock_db, mock_encryption_service):
        """测试成功写入事件"""
        events = [
            EventLog(
                event_id="event_001",
                segment_id="seg_001",
                start_time="2024-01-01T10:00:00",
                end_time="2024-01-01T10:01:00",
                event_type="action",
                structured={"person_id": "p1", "equipment": ["烧杯"]},
                raw_text="用户拿起烧杯"
            ),
            EventLog(
                event_id="event_002",
                segment_id="seg_001",
                start_time="2024-01-01T10:01:00",
                end_time="2024-01-01T10:02:00",
                event_type="action",
                structured={"person_id": "p1", "equipment": ["试管"]},
                raw_text="用户使用试管"
            )
        ]

        # 执行写入
        writer.write_events(events)

        # 验证数据库调用
        assert mock_db.insert_event_log.call_count == 2
        mock_db.insert_event_log.assert_any_call(events[0])
        mock_db.insert_event_log.assert_any_call(events[1])

    def test_write_events_with_encryption(self, writer, mock_db, mock_encryption_service):
        """测试带加密的事件写入"""
        writer.enable_encryption = True

        event = EventLog(
            event_id="event_001",
            segment_id="seg_001",
            start_time="2024-01-01T10:00:00",
            end_time="2024-01-01T10:01:00",
            event_type="action",
            structured={"person_id": "p1", "appearance": "敏感外貌信息"},
            raw_text="用户操作"
        )

        # 模拟加密
        mock_encryption_service.encrypt_field.return_value = "encrypted_appearance"

        writer.write_events([event])

        # 验证加密服务被调用
        mock_encryption_service.encrypt_field.assert_called()

        # 验证数据库调用使用加密后的数据
        mock_db.insert_event_log.assert_called_once()
        inserted_event = mock_db.insert_event_log.call_args[0][0]
        assert inserted_event.structured["appearance"] == "encrypted_appearance"

    def test_write_events_db_error(self, writer, mock_db):
        """测试数据库错误的情况"""
        event = EventLog(
            event_id="event_001",
            segment_id="seg_001",
            start_time="2024-01-01T10:00:00",
            end_time="2024-01-01T10:01:00",
            event_type="action",
            structured={"person_id": "p1"},
            raw_text="测试事件"
        )

        mock_db.insert_event_log.side_effect = Exception("数据库连接失败")

        with pytest.raises(RuntimeError, match="写入事件日志失败"):
            writer.write_events([event])

    def test_write_emergency_success(self, writer, mock_db):
        """测试成功写入紧急事件"""
        emergency = Emergency(
            emergency_id="emerg_001",
            description="火灾警报",
            status="PENDING",
            start_time="2024-01-01T10:00:00",
            end_time="2024-01-01T10:01:00",
            segment_id="seg_001"
        )

        writer.write_emergency(emergency)

        # 验证数据库调用
        mock_db.insert_emergency_log.assert_called_once_with(emergency)

    def test_write_emergency_with_db_error(self, writer, mock_db):
        """测试紧急事件写入数据库错误"""
        emergency = Emergency(
            emergency_id="emerg_001",
            description="测试紧急事件",
            status="PENDING",
            start_time="2024-01-01T10:00:00",
            end_time="2024-01-01T10:01:00",
            segment_id="seg_001"
        )

        mock_db.insert_emergency_log.side_effect = Exception("DB错误")

        with pytest.raises(RuntimeError, match="写入紧急事件日志失败"):
            writer.write_emergency(emergency)

    def test_write_from_video_result(self, writer, mock_db):
        """测试从视频理解结果写入"""
        result = VideoUnderstandingResult(
            events=[
                EventLog(
                    event_id="event_001",
                    segment_id="seg_001",
                    start_time="2024-01-01T10:00:00",
                    end_time="2024-01-01T10:01:00",
                    event_type="action",
                    structured={"person_id": "p1"},
                    raw_text="测试事件"
                )
            ],
            persons=[],
            equipment=[],
            emergencies=[
                Emergency(
                    emergency_id="emerg_001",
                    description="测试紧急",
                    status="PENDING",
                    start_time="2024-01-01T10:00:00",
                    end_time="2024-01-01T10:01:00",
                    segment_id="seg_001"
                )
            ]
        )

        writer.write_from_video_result(result)

        # 验证事件和紧急事件都被写入
        mock_db.insert_event_log.assert_called_once()
        mock_db.insert_emergency_log.assert_called_once()

class TestLogWriterEncryption:
    """测试日志写入器的加密功能"""

    def test_enable_encryption(self, writer):
        """测试启用加密"""
        writer.enable_encryption = True
        assert writer.enable_encryption is True

    def test_disable_encryption(self, writer):
        """测试禁用加密"""
        writer.enable_encryption = False
        assert writer.enable_encryption is False

    def test_encryption_service_initialization(self):
        """测试加密服务初始化"""
        with patch('log_writer.writer.FieldEncryptionService') as mock_encrypt_class:
            mock_encryption = MagicMock()
            mock_encrypt_class.return_value = mock_encryption

            writer = LogWriter()

            assert writer.encryption_service == mock_encryption
            mock_encrypt_class.assert_called_once()

class TestLogWriterIntegration:
    """测试日志写入器的集成行为"""

    def test_full_write_workflow(self, writer, mock_db, mock_encryption_service):
        """测试完整的写入工作流"""
        # 启用加密
        writer.enable_encryption = True

        # 准备测试数据
        event = EventLog(
            event_id="event_001",
            segment_id="seg_001",
            start_time="2024-01-01T10:00:00",
            end_time="2024-01-01T10:01:00",
            event_type="action",
            structured={"person_id": "p1", "appearance": "原始外貌"},
            raw_text="测试事件"
        )

        emergency = Emergency(
            emergency_id="emerg_001",
            description="测试紧急",
            status="PENDING",
            start_time="2024-01-01T10:00:00",
            end_time="2024-01-01T10:01:00",
            segment_id="seg_001"
        )

        # 模拟加密
        mock_encryption_service.encrypt_field.return_value = "加密后外貌"

        # 执行写入
        writer.write_events([event])
        writer.write_emergency(emergency)

        # 验证加密被调用
        mock_encryption_service.encrypt_field.assert_called_with(
            {"person_id": "p1", "appearance": "原始外貌"},
            "appearance"
        )

        # 验证数据库调用使用加密数据
        inserted_event = mock_db.insert_event_log.call_args[0][0]
        assert inserted_event.structured["appearance"] == "加密后外貌"

        mock_db.insert_emergency_log.assert_called_once_with(emergency)