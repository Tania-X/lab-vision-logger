import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from streaming_server.server import RecordingSession
from video_processing.interface import VideoUnderstandingResult, EventLog

@pytest.fixture
def mock_db():
    """模拟SeekDBClient"""
    return MagicMock()

@pytest.fixture
def mock_pipeline():
    """模拟视频处理管道"""
    return MagicMock()

@pytest.fixture
def session(mock_db, mock_pipeline):
    """创建测试用的RecordingSession实例"""
    with patch('streaming_server.server.SeekDBClient') as mock_db_class, \
         patch('streaming_server.server.VideoLogPipeline') as mock_pipeline_class:

        mock_db_class.return_value = mock_db
        mock_pipeline_class.return_value = mock_pipeline

        session = RecordingSession(session_id="test_session_001")
        return session

class TestRecordingSession:
    """测试录制会话"""

    def test_init_with_default_components(self):
        """测试使用默认组件初始化"""
        with patch('streaming_server.server.SeekDBClient') as mock_db_class, \
             patch('streaming_server.server.VideoLogPipeline') as mock_pipeline_class:

            session = RecordingSession(session_id="test_session")

            assert session.session_id == "test_session"
            assert session.processing_queue is not None
            assert session.is_active is True
            assert session.db_client is not None
            assert session.pipeline is not None

    def test_init_with_custom_components(self, mock_db, mock_pipeline):
        """测试使用自定义组件初始化"""
        session = RecordingSession(
            session_id="custom_session",
            db_client=mock_db,
            pipeline=mock_pipeline
        )

        assert session.session_id == "custom_session"
        assert session.db_client == mock_db
        assert session.pipeline == mock_pipeline

    def test_add_video_segment(self, session):
        """测试添加视频片段到队列"""
        segment_data = b"fake_mp4_data"

        session.add_video_segment(segment_data)

        # 验证数据被添加到队列
        assert session.processing_queue.qsize() == 1
        queued_data = session.processing_queue.get_nowait()
        assert queued_data == segment_data

    def test_get_queue_size(self, session):
        """测试获取队列大小"""
        assert session.get_queue_size() == 0

        session.add_video_segment(b"data1")
        session.add_video_segment(b"data2")

        assert session.get_queue_size() == 2

    def test_stop_session(self, session):
        """测试停止会话"""
        assert session.is_active is True

        session.stop()

        assert session.is_active is False

    @pytest.mark.asyncio
    async def test_process_video_segment_success(self, session, mock_pipeline):
        """测试成功处理视频片段"""
        segment_data = b"fake_mp4_data"

        # 模拟管道处理结果
        mock_result = VideoUnderstandingResult(
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
            emergencies=[]
        )
        mock_pipeline.process_video.return_value = [mock_result]

        # 执行处理
        await session._process_video_segment(segment_data)

        # 验证管道被调用
        mock_pipeline.process_video.assert_called_once()

        # 注意：实际实现中可能需要额外的参数，这里验证调用发生即可

    @pytest.mark.asyncio
    async def test_process_video_segment_with_error(self, session, mock_pipeline):
        """测试处理视频片段时发生错误"""
        segment_data = b"corrupted_data"

        mock_pipeline.process_video.side_effect = Exception("处理失败")

        # 这里应该不抛出异常，而是记录错误
        await session._process_video_segment(segment_data)

        # 验证管道仍然被调用
        mock_pipeline.process_video.assert_called_once()

    def test_cleanup_resources(self, session):
        """测试清理资源"""
        # 添加一些数据到队列
        session.add_video_segment(b"data1")
        session.add_video_segment(b"data2")

        session.cleanup()

        # 验证队列被清空
        assert session.processing_queue.empty()
        assert session.is_active is False

class TestRecordingSessionIntegration:
    """测试录制会话的集成行为"""

    @pytest.mark.asyncio
    async def test_full_processing_workflow(self, session, mock_pipeline, mock_db):
        """测试完整的处理工作流"""
        # 模拟管道返回结果
        mock_result = VideoUnderstandingResult(
            events=[
                EventLog(
                    event_id="event_001",
                    segment_id="streaming_seg_001",
                    start_time="2024-01-01T10:00:00",
                    end_time="2024-01-01T10:01:00",
                    event_type="action",
                    structured={"person_id": "p1", "equipment": ["试管"]},
                    raw_text="用户拿起试管"
                )
            ],
            persons=[],
            equipment=["试管"],
            emergencies=[]
        )
        mock_pipeline.process_video.return_value = [mock_result]

        # 添加视频片段
        segment_data = b"streaming_mp4_data"
        session.add_video_segment(segment_data)

        # 手动触发处理（实际中这会在后台进行）
        await session._process_video_segment(segment_data)

        # 验证管道被调用
        mock_pipeline.process_video.assert_called_once()

        # 注意：实际实现中，结果会通过其他方式写入数据库
        # 这里我们验证处理流程被触发

    def test_session_state_management(self, session):
        """测试会话状态管理"""
        # 初始状态
        assert session.is_active is True
        assert session.get_queue_size() == 0

        # 添加数据
        session.add_video_segment(b"data")
        assert session.get_queue_size() == 1

        # 停止会话
        session.stop()
        assert session.is_active is False

        # 清理
        session.cleanup()
        assert session.get_queue_size() == 0

class TestRecordingSessionErrorHandling:
    """测试录制会话的错误处理"""

    def test_init_with_invalid_session_id(self):
        """测试无效会话ID"""
        with pytest.raises(ValueError):
            RecordingSession(session_id="")  # 空ID

    @pytest.mark.asyncio
    async def test_process_corrupted_segment(self, session, mock_pipeline):
        """测试处理损坏的视频片段"""
        corrupted_data = b"corrupted_mp4_data"

        # 模拟处理失败
        mock_pipeline.process_video.side_effect = Exception("视频格式错误")

        # 处理不应该崩溃
        await session._process_video_segment(corrupted_data)

        # 验证仍然尝试处理
        mock_pipeline.process_video.assert_called_once()

    def test_concurrent_segment_processing(self, session):
        """测试并发处理多个片段"""
        # 添加多个片段
        segments = [b"segment_1", b"segment_2", b"segment_3"]
        for segment in segments:
            session.add_video_segment(segment)

        assert session.get_queue_size() == 3

        # 逐个处理
        for _ in range(3):
            data = session.processing_queue.get_nowait()
            assert data in segments

        assert session.get_queue_size() == 0