import pytest
from unittest.mock import patch, MagicMock
from orchestration.pipeline import VideoLogPipeline
from video_processing.interface import VideoUnderstandingResult, EventLog, PersonInfo

@pytest.fixture
def mock_segmenter():
    """模拟视频分段器"""
    return MagicMock()

@pytest.fixture
def mock_processor():
    """模拟视频处理器"""
    return MagicMock()

@pytest.fixture
def mock_writer():
    """模拟日志写入器"""
    return MagicMock()

@pytest.fixture
def pipeline(mock_segmenter, mock_processor, mock_writer):
    """创建测试用的管道实例"""
    with patch('orchestration.pipeline.VideoSegmenter') as mock_seg_class, \
         patch('orchestration.pipeline.Qwen3VLFlashProcessor') as mock_proc_class, \
         patch('orchestration.pipeline.LogWriter') as mock_writer_class:

        mock_seg_class.return_value = mock_segmenter
        mock_proc_class.return_value = mock_processor
        mock_writer_class.return_value = mock_writer

        pipeline = VideoLogPipeline()
        return pipeline

class TestVideoLogPipeline:
    """测试视频日志处理管道"""

    def test_init_with_default_components(self):
        """测试使用默认组件初始化"""
        with patch('orchestration.pipeline.VideoSegmenter') as mock_seg_class, \
             patch('orchestration.pipeline.Qwen3VLFlashProcessor') as mock_proc_class, \
             patch('orchestration.pipeline.LogWriter') as mock_writer_class:

            pipeline = VideoLogPipeline()

            # 验证组件被正确创建
            mock_seg_class.assert_called_once()
            mock_proc_class.assert_called_once()
            mock_writer_class.assert_called_once()

            assert pipeline.segmenter is not None
            assert pipeline.processor is not None
            assert pipeline.writer is not None

    def test_init_with_custom_components(self):
        """测试使用自定义组件初始化"""
        custom_segmenter = MagicMock()
        custom_processor = MagicMock()
        custom_writer = MagicMock()

        pipeline = VideoLogPipeline(
            segmenter=custom_segmenter,
            processor=custom_processor,
            writer=custom_writer
        )

        assert pipeline.segmenter == custom_segmenter
        assert pipeline.processor == custom_processor
        assert pipeline.writer == custom_writer

    def test_process_video_full_flow(self, pipeline, mock_segmenter, mock_processor, mock_writer):
        """测试完整的视频处理流程"""
        video_path = "/path/to/test_video.mp4"

        # 模拟分段结果
        mock_segment1 = MagicMock()
        mock_segment1.video_path = "/tmp/segment1.mp4"
        mock_segment1.start_time = 0.0
        mock_segment1.end_time = 60.0

        mock_segment2 = MagicMock()
        mock_segment2.video_path = "/tmp/segment2.mp4"
        mock_segment2.start_time = 60.0
        mock_segment2.end_time = 120.0

        mock_segments = [mock_segment1, mock_segment2]
        mock_segmenter.segment_video.return_value = mock_segments

        # 模拟处理结果
        result1 = VideoUnderstandingResult(
            events=[
                EventLog(
                    event_id="event_001",
                    segment_id="seg_001",
                    start_time="2024-01-01T10:00:00",
                    end_time="2024-01-01T10:01:00",
                    event_type="action",
                    structured={"person_id": "p1", "equipment": ["烧杯"]},
                    raw_text="用户拿起烧杯"
                )
            ],
            persons=[
                PersonInfo(person_id="p1", appearance="身穿白大褂的研究员")
            ],
            equipment=["烧杯"],
            emergencies=[]
        )

        result2 = VideoUnderstandingResult(
            events=[
                EventLog(
                    event_id="event_002",
                    segment_id="seg_002",
                    start_time="2024-01-01T10:01:00",
                    end_time="2024-01-01T10:02:00",
                    event_type="action",
                    structured={"person_id": "p1", "equipment": ["试管"]},
                    raw_text="用户使用试管"
                )
            ],
            persons=[],
            equipment=["试管"],
            emergencies=[]
        )

        mock_processor.process_segment.side_effect = [result1, result2]

        # 执行处理
        results = pipeline.process_video(video_path)

        # 验证调用链
        mock_segmenter.segment_video.assert_called_once_with(video_path)
        assert mock_processor.process_segment.call_count == 2
        mock_processor.process_segment.assert_any_call(mock_segment1)
        mock_processor.process_segment.assert_any_call(mock_segment2)

        # 验证写入调用
        assert mock_writer.write_events.call_count == 2
        mock_writer.write_events.assert_any_call(result1.events)
        mock_writer.write_events.assert_any_call(result2.events)

        # 验证返回结果
        assert len(results) == 2
        assert results[0] == result1
        assert results[1] == result2

    def test_process_video_segmentation_failure(self, pipeline, mock_segmenter):
        """测试视频分段失败的情况"""
        video_path = "/path/to/test_video.mp4"

        mock_segmenter.segment_video.side_effect = Exception("分段失败")

        with pytest.raises(Exception, match="分段失败"):
            pipeline.process_video(video_path)

        # 验证没有进行后续处理
        pipeline.processor.process_segment.assert_not_called()
        pipeline.writer.write_events.assert_not_called()

    def test_process_video_processing_failure(self, pipeline, mock_segmenter, mock_processor, mock_writer):
        """测试视频处理失败的情况"""
        video_path = "/path/to/test_video.mp4"

        mock_segment = MagicMock()
        mock_segmenter.segment_video.return_value = [mock_segment]

        mock_processor.process_segment.side_effect = Exception("处理失败")

        with pytest.raises(Exception, match="处理失败"):
            pipeline.process_video(video_path)

        # 验证分段成功但写入未进行
        mock_segmenter.segment_video.assert_called_once()
        mock_processor.process_segment.assert_called_once()
        pipeline.writer.write_events.assert_not_called()

    def test_process_video_empty_segments(self, pipeline, mock_segmenter):
        """测试空分段结果"""
        video_path = "/path/to/test_video.mp4"

        mock_segmenter.segment_video.return_value = []

        results = pipeline.process_video(video_path)

        # 验证返回空结果
        assert results == []

        # 验证没有进行处理和写入
        pipeline.processor.process_segment.assert_not_called()
        pipeline.writer.write_events.assert_not_called()

class TestPipelineIntegration:
    """测试管道的集成行为"""

    def test_pipeline_with_real_components(self):
        """测试使用真实组件的管道（通过mock隔离外部依赖）"""
        with patch('orchestration.pipeline.VideoSegmenter') as mock_seg_class, \
             patch('orchestration.pipeline.Qwen3VLFlashProcessor') as mock_proc_class, \
             patch('orchestration.pipeline.LogWriter') as mock_writer_class, \
             patch('orchestration.pipeline.SeekDBClient') as mock_db_class:

            # 创建mock实例
            mock_segmenter = MagicMock()
            mock_processor = MagicMock()
            mock_writer = MagicMock()
            mock_db = MagicMock()

            mock_seg_class.return_value = mock_segmenter
            mock_proc_class.return_value = mock_processor
            mock_writer_class.return_value = mock_writer
            mock_db_class.return_value = mock_db

            pipeline = VideoLogPipeline()

            # 验证所有组件都正确初始化
            assert pipeline.segmenter == mock_segmenter
            assert pipeline.processor == mock_processor
            assert pipeline.writer == mock_writer

            # 验证数据库连接被传递给writer
            mock_writer_class.assert_called_once()
            writer_call_args = mock_writer_class.call_args
            assert 'db_client' in writer_call_args[1]